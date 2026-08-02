"""Hyperliquid public REST client.

Read-only. No API key, no wallet, no signing -- everything this service sells is
derived from the public /info endpoint. That is deliberate: it means the data
pipeline has no credentials to leak and can run anywhere.
"""
from __future__ import annotations

import asyncio
import logging
import time

import httpx

from . import config as C

log = logging.getLogger("carrydesk.hl")


class HyperliquidError(RuntimeError):
    pass


class HLClient:
    def __init__(self, base_url: str = C.HL_API_URL, timeout: float = C.HL_TIMEOUT):
        self.base_url = base_url.rstrip("/")
        self._client = httpx.AsyncClient(
            timeout=timeout,
            headers={"Content-Type": "application/json"},
            limits=httpx.Limits(max_connections=C.HL_CONCURRENCY * 2),
        )
        self._sem = asyncio.Semaphore(C.HL_CONCURRENCY)

    async def aclose(self) -> None:
        await self._client.aclose()

    async def _post(self, payload: dict) -> object:
        async with self._sem:
            for attempt in range(3):
                try:
                    r = await self._client.post(f"{self.base_url}/info", json=payload)
                    if r.status_code == 429:
                        await asyncio.sleep(1.5 * (attempt + 1))
                        continue
                    r.raise_for_status()
                    return r.json()
                except (httpx.TimeoutException, httpx.TransportError) as e:
                    if attempt == 2:
                        raise HyperliquidError(f"{payload.get('type')}: {e}") from e
                    await asyncio.sleep(1.0 * (attempt + 1))
        raise HyperliquidError(f"{payload.get('type')}: retries exhausted")

    async def meta_and_asset_ctxs(self) -> tuple[dict, list]:
        d = await self._post({"type": "metaAndAssetCtxs"})
        if not isinstance(d, list) or len(d) < 2:
            raise HyperliquidError("metaAndAssetCtxs: unexpected shape")
        return d[0], d[1]

    async def funding_history(self, coin: str, start_ms: int, end_ms: int) -> list[dict]:
        d = await self._post(
            {"type": "fundingHistory", "coin": coin, "startTime": start_ms, "endTime": end_ms}
        )
        return d if isinstance(d, list) else []

    # -- derived -------------------------------------------------------------

    async def liquid_universe(
        self, min_volume: float = C.MIN_DAILY_VOLUME, max_n: int = C.MAX_UNIVERSE
    ) -> list[dict]:
        """Perps above the daily-volume floor, most liquid first.

        Mirrors signal.liquid_universe() in the trading bot, but returns the
        volume and current funding too, since those are worth selling.
        """
        meta, ctxs = await self.meta_and_asset_ctxs()
        rows = []
        for u, c in zip(meta.get("universe", []), ctxs):
            try:
                if u.get("isDelisted"):
                    continue
                vol = float(c.get("dayNtlVlm") or 0)
                if vol < min_volume:
                    continue
                rows.append(
                    {
                        "coin": u["name"],
                        "day_notional_volume": vol,
                        "funding_now": float(c.get("funding") or 0.0),
                        "open_interest": float(c.get("openInterest") or 0.0),
                        "mark_price": float(c.get("markPx") or 0.0),
                        "max_leverage": u.get("maxLeverage"),
                    }
                )
            except (KeyError, TypeError, ValueError):
                continue
        rows.sort(key=lambda r: -r["day_notional_volume"])
        return rows[:max_n]

    async def trailing_funding(
        self, coins: list[str], hours: int = C.LOOKBACK_HOURS
    ) -> dict[str, dict]:
        """Mean hourly funding over the trailing window, per coin, fetched concurrently.

        Returns {coin: {mean_hourly, n_points, coverage, first_ts, last_ts}}.
        Coins with less than MIN_COVERAGE of the expected points are dropped --
        a thin series makes the mean meaningless and would corrupt the ranking.
        """
        end = int(time.time() * 1000)
        start = end - hours * 3600 * 1000
        expected = hours / C.FUNDING_INTERVAL_HOURS

        async def one(coin: str):
            try:
                rows = await self.funding_history(coin, start, end)
            except HyperliquidError as e:
                log.warning("%s funding fetch failed: %s", coin, e)
                return coin, None
            if not rows:
                return coin, None
            coverage = len(rows) / expected
            if coverage < C.MIN_COVERAGE:
                log.info("%s: coverage %.2f below floor, dropping", coin, coverage)
                return coin, None
            try:
                rates = [float(r["fundingRate"]) for r in rows]
            except (KeyError, TypeError, ValueError):
                return coin, None
            return coin, {
                "mean_hourly": sum(rates) / len(rates),
                "n_points": len(rows),
                "coverage": round(coverage, 4),
                "first_ts": rows[0].get("time"),
                "last_ts": rows[-1].get("time"),
            }

        results = await asyncio.gather(*(one(c) for c in coins))
        return {c: v for c, v in results if v is not None}
