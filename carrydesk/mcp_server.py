"""MCP server -- the primary distribution channel.

A trader adds this once to Claude Code / Claude Desktop / Cursor and their agent
can pull the carry ranking forever. No signup form, no dashboard, no API key to
copy-paste: the install IS the onboarding.

It is a thin client over the HTTP API, not a second implementation. One source
of truth, and a paid call through MCP settles exactly like a paid call over HTTP.

Wallet is optional:
  no CARRYDESK_PRIVATE_KEY  -> free tools work, paid tools return the price and
                               how to enable payment. Nothing breaks.
  CARRYDESK_PRIVATE_KEY set -> httpx is wrapped with x402 auto-payment and paid
                               tools settle in USDC transparently.

Run:  python -m carrydesk.mcp_server
"""
from __future__ import annotations

import json
import logging
import os
from typing import Any

import httpx
from mcp.server import MCPServer

from . import __version__

log = logging.getLogger("carrydesk.mcp")

API_BASE = os.getenv("CARRYDESK_API_BASE", "https://carry.pelazas.com").rstrip("/")
PRIVATE_KEY = os.getenv("CARRYDESK_PRIVATE_KEY", "").strip()
TIMEOUT = float(os.getenv("CARRYDESK_TIMEOUT", 30.0))

server = MCPServer(
    name="carrydesk",
    title="carrydesk — Hyperliquid funding carry",
    # Derived, never hardcoded: a server announcing a version it isn't makes
    # every client's introspection wrong, and it drifts the moment you publish.
    version=__version__,
    instructions=(
        "Cross-sectional funding-carry rankings for Hyperliquid perpetuals: which "
        "perps are paying to hold long, which are paying to hold short, and the "
        "spread between the two legs. Use carry_snapshot for the free delayed view "
        "and carry_rankings for the full live ranking. Always surface the caveats "
        "from carry_method when a user is deciding whether to act on this."
    ),
)


def _build_client() -> tuple[httpx.AsyncClient, bool]:
    """Return (client, paid_enabled). Falls back to plain httpx on any problem."""
    if not PRIVATE_KEY:
        return httpx.AsyncClient(timeout=TIMEOUT), False
    try:
        from eth_account import Account
        from x402.client import x402Client
        from x402.http.clients.httpx import wrapHttpxWithPayment
        from x402.mechanisms.evm import EthAccountSigner
        from x402.mechanisms.evm.exact import register_exact_evm_client

        acct = Account.from_key(PRIVATE_KEY)
        client = x402Client()
        register_exact_evm_client(client, EthAccountSigner(acct))
        log.info("x402 auto-payment enabled for %s", acct.address)
        return wrapHttpxWithPayment(client, timeout=TIMEOUT), True
    except Exception as e:  # noqa: BLE001
        log.error("x402 client setup failed (%s); paid tools disabled", e)
        return httpx.AsyncClient(timeout=TIMEOUT), False


_client: httpx.AsyncClient | None = None
_paid_enabled = False


async def _get(path: str, params: dict | None = None) -> Any:
    global _client, _paid_enabled
    if _client is None:
        _client, _paid_enabled = _build_client()
    r = await _client.get(f"{API_BASE}{path}", params=params or {})
    if r.status_code == 402:
        return {
            "error": "payment_required",
            "message": (
                "This is a paid endpoint and no wallet is configured. Set "
                "CARRYDESK_PRIVATE_KEY in the MCP server env to enable automatic "
                "USDC payment, or use carry_snapshot for the free delayed view."
            ),
            "price": _decode_price(r),
            "free_alternative": "carry_snapshot",
        }
    if r.status_code == 503:
        return {
            "error": "upstream_unavailable",
            "message": "carrydesk has no fresh snapshot right now. Retry shortly.",
            "detail": _safe_json(r),
        }
    r.raise_for_status()
    return r.json()


def _safe_json(r: httpx.Response) -> Any:
    try:
        return r.json()
    except Exception:  # noqa: BLE001
        return r.text[:500]


def _decode_price(r: httpx.Response) -> dict | None:
    """Pull the human-readable price out of the x402 challenge header.

    x402 v2 returns an empty body and puts base64 payment requirements in the
    `payment-required` header, so the price is not in the JSON.
    """
    import base64

    hdr = r.headers.get("payment-required")
    if not hdr:
        return None
    try:
        pad = "=" * (-len(hdr) % 4)
        req = json.loads(base64.b64decode(hdr + pad))
        acc = (req.get("accepts") or [{}])[0]
        amount = int(acc.get("amount", 0))
        return {
            "usdc": round(amount / 1e6, 6),
            "network": acc.get("network"),
            "pay_to": acc.get("payTo"),
        }
    except Exception:  # noqa: BLE001
        return None


# --- free tools -------------------------------------------------------------


@server.tool(
    description=(
        "FREE. Cross-sectional funding-carry snapshot for Hyperliquid perps: the "
        "top 5 coins on each leg (long = market pays you to hold, short = you get "
        "paid to short) plus the carry spread. Delayed 24h. Use this first."
    )
)
async def carry_snapshot() -> dict:
    return await _get("/v1/free/carry")


@server.tool(
    description=(
        "FREE. How the carry ranking is computed -- universe filter, lookback, leg "
        "construction -- and the caveats that matter before anyone trades on it. "
        "Read this before presenting the numbers as actionable."
    )
)
async def carry_method() -> dict:
    return await _get("/v1/method")


@server.tool(description="FREE. Service health and data freshness.")
async def carry_health() -> dict:
    return await _get("/health")


# --- paid tools -------------------------------------------------------------


@server.tool(
    description=(
        "PAID (~$0.05 USDC). Full live cross-sectional funding-carry ranking across "
        "every liquid Hyperliquid perp: trailing 14d mean funding annualized, rank, "
        "long/short leg and dollar-neutral weights, plus outlier-robust spread "
        "variants. Set k to change coins per leg (1-20)."
    )
)
async def carry_rankings(k: int = 10, min_volume: float = 0) -> dict:
    return await _get("/v1/carry/rankings", {"k": k, "min_volume": min_volume})


@server.tool(
    description=(
        "PAID (~$0.02 USDC). Archived rank and trailing funding history for one "
        "coin, from carrydesk's own published snapshots. Use to check whether a "
        "coin's carry is persistent or a one-day artifact."
    )
)
async def carry_history(coin: str, days: int = 30) -> dict:
    return await _get(f"/v1/carry/history/{coin.upper()}", {"days": days})


@server.tool(
    description=(
        "PAID (~$0.01 USDC). The liquid Hyperliquid perp universe sorted by daily "
        "notional volume, with open interest, mark price and current funding."
    )
)
async def carry_universe() -> dict:
    return await _get("/v1/universe")


def main() -> None:
    logging.basicConfig(level=logging.INFO)
    server.run(transport="stdio")


if __name__ == "__main__":
    main()
