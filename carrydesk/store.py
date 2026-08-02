"""Snapshot cache + on-disk archive.

Two jobs:

1. Serve the API instantly. A refresh costs ~40 HTTP round-trips to Hyperliquid;
   no request should ever pay that. A background task refreshes; requests read
   whatever is in memory.

2. Build the track record automatically. Every snapshot is appended to
   data/snapshots/YYYY-MM-DD.jsonl and never rewritten. Six weeks of that file
   IS the proof that the ranking was published in advance, which is the only
   thing that makes anyone trust it. It also feeds the free (delayed) tier.
"""
from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime, timedelta, timezone
from pathlib import Path

from . import config as C
from .carry import build_ranking
from .hl import HLClient

log = logging.getLogger("carrydesk.store")


class SnapshotStore:
    def __init__(self, snapshot_dir: Path = C.SNAPSHOT_DIR):
        self.dir = Path(snapshot_dir)
        self.dir.mkdir(parents=True, exist_ok=True)
        self.current: dict | None = None
        self.last_error: str | None = None
        self.last_refresh_ts: int | None = None
        self.refresh_count = 0
        self._lock = asyncio.Lock()

    # -- refresh -------------------------------------------------------------

    async def refresh(self, client: HLClient) -> dict:
        async with self._lock:
            universe = await client.liquid_universe()
            if not universe:
                raise RuntimeError("empty liquid universe -- Hyperliquid returned nothing")
            funding = await client.trailing_funding([u["coin"] for u in universe])
            snap = build_ranking(universe, funding)
            self._validate(snap)
            self.current = snap
            self.last_error = None
            self.last_refresh_ts = snap["as_of_ts"]
            self.refresh_count += 1
            self._archive(snap)
            log.info(
                "refresh ok: %d coins, spread %.2f%%/yr",
                snap["universe_size"],
                100 * snap["carry_spread_annualized"],
            )
            return snap

    @staticmethod
    def _validate(snap: dict) -> None:
        """Gate before anything is stored or published.

        Publishing a wrong number unattended is worse than publishing nothing,
        so a failed snapshot raises and the previous good one keeps serving.
        """
        if snap["universe_size"] < 2 * C.K_PER_LEG:
            raise ValueError(
                f"universe too small: {snap['universe_size']} < {2 * C.K_PER_LEG}"
            )
        spread = snap["carry_spread_annualized"]
        # Sanity band. A real cross-sectional spread on major perps sits in the
        # low tens of percent; 500%/yr means the data is broken, not that we
        # found free money.
        if not (-5.0 < spread < 5.0):
            raise ValueError(f"carry spread {spread:.2f} outside sanity band")
        for r in snap["rankings"]:
            if r["coverage"] < C.MIN_COVERAGE:
                raise ValueError(f"{r['coin']}: coverage {r['coverage']} below floor")

    # -- archive -------------------------------------------------------------

    def _archive(self, snap: dict) -> None:
        day = datetime.fromtimestamp(snap["as_of_ts"], tz=timezone.utc).strftime("%Y-%m-%d")
        path = self.dir / f"{day}.jsonl"
        with path.open("a") as fh:
            fh.write(json.dumps(snap, separators=(",", ":")) + "\n")

    def delayed(self, hours: int = C.FREE_TIER_DELAY_HOURS) -> dict | None:
        """Newest archived snapshot at least `hours` old -- the free tier's data.

        Walks back day by day (max 7) so a gap in publishing degrades to
        "slightly staler free data" rather than an error.

        Returns None when the archive is younger than `hours` (day one) or when
        nothing was published within the walk-back window. The API then falls
        back to the *live* snapshot, which means the free tier briefly serves
        what the paid tier sells.

        That is deliberate. Day one it is the only option, and past the window it
        implies the archive has been broken for over a week -- at which point the
        public page still rendering matters more than a leak nobody is paying to
        avoid. `tests/test_delayed_tier.py` pins both ends of this behaviour.
        """
        cutoff = datetime.now(timezone.utc) - timedelta(hours=hours)
        cutoff_ts = int(cutoff.timestamp())
        for back in range(0, 8):
            day = (cutoff - timedelta(days=back)).strftime("%Y-%m-%d")
            path = self.dir / f"{day}.jsonl"
            if not path.exists():
                continue
            best = None
            for line in path.read_text().splitlines():
                if not line.strip():
                    continue
                try:
                    snap = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if snap.get("as_of_ts", 0) <= cutoff_ts:
                    if best is None or snap["as_of_ts"] > best["as_of_ts"]:
                        best = snap
            if best is not None:
                return best
        return None

    def history(self, coin: str, days: int = 30) -> list[dict]:
        """This coin's rank and trailing funding across archived snapshots."""
        out = []
        today = datetime.now(timezone.utc)
        for back in range(days):
            day = (today - timedelta(days=back)).strftime("%Y-%m-%d")
            path = self.dir / f"{day}.jsonl"
            if not path.exists():
                continue
            for line in path.read_text().splitlines():
                if not line.strip():
                    continue
                try:
                    snap = json.loads(line)
                except json.JSONDecodeError:
                    continue
                for r in snap.get("rankings", []):
                    if r["coin"] == coin:
                        out.append(
                            {
                                "as_of": snap["as_of"],
                                "as_of_ts": snap["as_of_ts"],
                                "rank": r["rank"],
                                "leg": r["leg"],
                                "mean_funding_annualized": r["mean_funding_annualized"],
                                "funding_now_annualized": r["funding_now_annualized"],
                            }
                        )
                        break
        out.sort(key=lambda r: r["as_of_ts"])
        return out

    def archive_index(self, days: int = 90) -> list[dict]:
        """One row per archived day: count, span, and the day's closing spread.

        Powers the public /archive page. Reads only the last line of interest
        per file rather than parsing everything, because this is rendered on
        request and the archive grows forever.
        """
        out = []
        for path in sorted(self.dir.glob("*.jsonl"), reverse=True)[:days]:
            first = last = None
            n = 0
            for line in path.read_text().splitlines():
                if not line.strip():
                    continue
                try:
                    snap = json.loads(line)
                except json.JSONDecodeError:
                    continue
                n += 1
                if first is None:
                    first = snap
                last = snap
            if last is None:
                continue
            out.append(
                {
                    "day": path.stem,
                    "snapshots": n,
                    "first_at": first.get("as_of"),
                    "last_at": last.get("as_of"),
                    "universe_size": last.get("universe_size"),
                    "carry_spread_annualized": last.get("carry_spread_annualized"),
                    "carry_spread_annualized_median": last.get(
                        "carry_spread_annualized_median"
                    ),
                    "outlier_dominated": last.get("outlier_dominated"),
                }
            )
        return out

    def spread_series(self, days: int = 90, max_points: int = 400) -> list[dict]:
        """Every archived snapshot as (ts, mean, median) for the public chart.

        Per-snapshot rather than per-day: the archive is hourly, and daily
        aggregation would throw away most of the record it exists to prove.

        Downsampled by even stride once past `max_points` so the SVG stays small
        as the archive grows — the shape is what the chart communicates, and a
        year of hourly points would be ~8700 path segments nobody can see.
        """
        rows = []
        for path in sorted(self.dir.glob("*.jsonl"))[-days:]:
            for line in path.read_text().splitlines():
                if not line.strip():
                    continue
                try:
                    s = json.loads(line)
                except json.JSONDecodeError:
                    continue
                mean = s.get("carry_spread_annualized")
                if mean is None:
                    continue
                rows.append(
                    {
                        "ts": s.get("as_of_ts"),
                        "as_of": s.get("as_of"),
                        "mean": mean,
                        "median": s.get("carry_spread_annualized_median"),
                    }
                )
        rows.sort(key=lambda r: r["ts"] or 0)
        if len(rows) > max_points:
            stride = len(rows) / max_points
            picked = [rows[int(i * stride)] for i in range(max_points)]
            # Always keep the true last point: the current reading must be the
            # one the chart ends on, not whichever sample the stride landed near.
            if picked[-1] is not rows[-1]:
                picked[-1] = rows[-1]
            rows = picked
        return rows

    def totals(self) -> dict:
        n = 0
        for path in self.dir.glob("*.jsonl"):
            n += sum(1 for line in path.read_text().splitlines() if line.strip())
        return {"snapshots": n, "days": len(list(self.dir.glob("*.jsonl")))}

    def health(self) -> dict:
        stale = None
        if self.last_refresh_ts:
            stale = int(datetime.now(timezone.utc).timestamp()) - self.last_refresh_ts
        return {
            "ok": self.current is not None and (stale is None or stale < C.REFRESH_SECONDS * 3),
            "has_snapshot": self.current is not None,
            "last_refresh_ts": self.last_refresh_ts,
            "seconds_since_refresh": stale,
            "refresh_count": self.refresh_count,
            "last_error": self.last_error,
            "archived_days": len(list(self.dir.glob("*.jsonl"))),
        }


async def refresh_loop(store: SnapshotStore, client: HLClient) -> None:
    """Background refresher. Never lets an exception kill the task."""
    while True:
        try:
            await store.refresh(client)
        except Exception as e:  # noqa: BLE001 - must not die
            store.last_error = f"{type(e).__name__}: {e}"
            log.error("refresh failed: %s", store.last_error)
        await asyncio.sleep(C.REFRESH_SECONDS)
