"""FastAPI service.

Three tiers, one data source:
  /v1/free/*     free, delayed 24h, top-5 each leg   -- the demo and the funnel
  /v1/carry/*    paid per call in USDC via x402      -- the product
  /health        always free                         -- for the ops monitor

Payments are enabled only when X402_PAY_TO is set. With no wallet configured the
service runs fully open, which is exactly what you want in dev and CI.

Nothing in this file calls an LLM. The data path, the pricing, and the payment
path are all deterministic -- a model in the billing path is a liability.
"""
from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.responses import JSONResponse

from . import config as C
from .carry import free_view
from .hl import HLClient
from .store import SnapshotStore, refresh_loop

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s"
)
log = logging.getLogger("carrydesk.api")

store = SnapshotStore()
client: HLClient | None = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    global client
    client = HLClient()
    # Prime synchronously so the first request after boot is never empty; if it
    # fails we still start (the loop retries) and /health reports degraded.
    try:
        await store.refresh(client)
    except Exception as e:  # noqa: BLE001
        store.last_error = f"{type(e).__name__}: {e}"
        log.error("initial refresh failed: %s", store.last_error)
    import asyncio

    task = asyncio.create_task(refresh_loop(store, client))
    try:
        yield
    finally:
        task.cancel()
        await client.aclose()


app = FastAPI(
    title="carrydesk",
    version="0.1.0",
    description=(
        "Cross-sectional funding-carry rankings for Hyperliquid perpetuals. "
        "The same signal a live market-neutral book trades, published as an API."
    ),
    lifespan=lifespan,
)


# --- payments ---------------------------------------------------------------


def _cdp_auth():
    """Auth provider for Coinbase's facilitator. None for the public one.

    Base **mainnet** settles only through CDP's facilitator, which requires a
    signed JWT per request. The public x402.org facilitator is testnet-only and
    needs no auth, so this returns None there.

    Fails loudly rather than silently falling back: a mainnet deployment that
    quietly can't settle would take payment challenges nobody can satisfy.
    """
    if not C.USING_CDP:
        return None
    if not (C.CDP_API_KEY_ID and C.CDP_API_KEY_SECRET):
        raise RuntimeError(
            "CDP facilitator selected but CDP_API_KEY_ID / CDP_API_KEY_SECRET are "
            "unset. Create them at https://cdp.coinbase.com (project -> API keys)."
        )

    from cdp.auth.utils.http import GetAuthHeadersOptions, get_auth_headers
    from x402.http.facilitator_client import CreateHeadersAuthProvider

    host = "api.cdp.coinbase.com"
    base = "/platform/v2/x402"

    def headers_for(method: str, path: str) -> dict[str, str]:
        return get_auth_headers(
            GetAuthHeadersOptions(
                api_key_id=C.CDP_API_KEY_ID,
                api_key_secret=C.CDP_API_KEY_SECRET,
                request_method=method,
                request_host=host,
                request_path=f"{base}{path}",
            )
        )

    # The CDP JWT binds the HTTP METHOD as well as the path, so each endpoint
    # must be signed with the verb the SDK actually uses. Signing everything
    # POST makes /supported return 401 and every paid route 500 at first
    # request. Verified in x402/http/facilitator_client.py: get_supported and
    # the bazaar discovery calls use GET; verify and settle use POST.
    ENDPOINTS = {
        "verify": ("POST", "/verify"),
        "settle": ("POST", "/settle"),
        "supported": ("GET", "/supported"),
        "bazaar": ("GET", "/discovery/resources"),
    }

    def create_headers() -> dict[str, dict[str, str]]:
        # Signed per call: these JWTs are short-lived, so they cannot be cached.
        return {k: headers_for(m, p) for k, (m, p) in ENDPOINTS.items()}

    log.info("using CDP facilitator with API key %s…", C.CDP_API_KEY_ID[:8])
    return CreateHeadersAuthProvider(create_headers)


def _install_payments(app: FastAPI) -> bool:
    """Attach the x402 paywall. No-op when no receiving wallet is configured."""
    if not C.PAYMENTS_ENABLED:
        log.warning("X402_PAY_TO unset -- running OPEN, no paywall")
        return False

    from x402.http.middleware.fastapi import payment_middleware
    from x402.http.types import PaymentOption, RouteConfig

    def opt(price: str) -> PaymentOption:
        return PaymentOption(
            scheme="exact",
            pay_to=C.X402_PAY_TO,
            price=price,
            network=C.X402_NETWORK,
            max_timeout_seconds=120,
        )

    routes = {
        "GET /v1/carry/rankings": RouteConfig(
            accepts=opt(C.PRICE_RANKINGS),
            description=(
                "Full cross-sectional funding-carry ranking across all liquid "
                "Hyperliquid perps: trailing 14d mean funding, annualized, rank, "
                "long/short leg assignment and dollar-neutral weights."
            ),
            mime_type="application/json",
            service_name=C.SERVICE_NAME,
            tags=["crypto", "funding", "perps", "hyperliquid"],
        ),
        # NOTE: x402 route patterns use [param] / :param / * -- NOT FastAPI's
        # {param}. Writing "{coin}" here re.escape()s to \{coin\}, never matches
        # /v1/carry/history/BTC, and the endpoint silently serves FOR FREE.
        # Verified 2026-08-02 in x402_http_server_base._compile_pattern.
        # PAYWALL_SELF_CHECK below exists to catch exactly this class of bug.
        "GET /v1/carry/history/[coin]": RouteConfig(
            accepts=opt(C.PRICE_HISTORY),
            description="Archived rank and trailing funding history for one coin.",
            mime_type="application/json",
            service_name=C.SERVICE_NAME,
            tags=["crypto", "funding", "history"],
        ),
        "GET /v1/universe": RouteConfig(
            accepts=opt(C.PRICE_UNIVERSE),
            description="Liquid Hyperliquid perp universe with volume, OI and current funding.",
            mime_type="application/json",
            service_name=C.SERVICE_NAME,
            tags=["crypto", "perps", "hyperliquid"],
        ),
    }

    from x402.http.facilitator_client import FacilitatorConfig, HTTPFacilitatorClient
    from x402.mechanisms.evm.exact import register_exact_evm_server
    from x402.server import x402ResourceServer

    fac = HTTPFacilitatorClient(
        FacilitatorConfig(url=C.X402_FACILITATOR_URL, auth_provider=_cdp_auth())
    )
    server = x402ResourceServer(fac)
    # The "exact" EVM scheme handler is NOT registered by default. Without this
    # every protected route 500s at first request with
    # 'No scheme for "exact" on "eip155:..."'. Registers eip155:* by default.
    register_exact_evm_server(server)

    _assert_routes_match(routes)
    app.middleware("http")(payment_middleware(routes=routes, server=server))
    log.info("x402 paywall active: %s -> %s", C.X402_NETWORK, C.X402_PAY_TO)
    return True


# One concrete URL per protected route. If a pattern stops matching its sample,
# that endpoint is being served for free and we refuse to boot.
PAYWALL_SELF_CHECK = {
    "GET /v1/carry/rankings": ("GET", "/v1/carry/rankings"),
    "GET /v1/carry/history/[coin]": ("GET", "/v1/carry/history/BTC"),
    "GET /v1/universe": ("GET", "/v1/universe"),
}


def _assert_routes_match(routes: dict) -> None:
    """Fail fast if a paid route's pattern doesn't cover its own sample URL.

    A silently-unmatched pattern is a revenue bypass that looks exactly like a
    working service, so this is a hard startup failure rather than a warning.
    Uses x402's own compiler so it cannot drift from the real matching logic.
    """
    from x402.http.middleware.fastapi import x402HTTPResourceServer
    from x402.mechanisms.evm.exact import register_exact_evm_server
    from x402.server import x402ResourceServer

    probe = x402ResourceServer(None)
    register_exact_evm_server(probe)
    compiled = x402HTTPResourceServer(probe, routes)._compiled_routes

    missing = []
    for key in routes:
        verb, path = PAYWALL_SELF_CHECK.get(key, (None, None))
        if path is None:
            missing.append(f"{key}: no self-check sample defined")
            continue
        hit = any(
            (r.verb in ("*", verb)) and r.regex.match(path)
            for r in compiled
            if r.pattern == key.split(" ", 1)[1]
        )
        if not hit:
            missing.append(f"{key}: pattern does not match {path}")
    if missing:
        raise RuntimeError(
            "x402 paywall self-check FAILED -- these routes would serve for free:\n  "
            + "\n  ".join(missing)
        )
    log.info("paywall self-check passed: %d routes gated", len(routes))


PAYWALL_ACTIVE = _install_payments(app)


def _require_snapshot() -> dict:
    if store.current is None:
        raise HTTPException(
            status_code=503,
            detail={
                "error": "no_snapshot",
                "message": "Upstream data not yet available. Retry shortly.",
                "last_error": store.last_error,
            },
        )
    return store.current


# --- free -------------------------------------------------------------------


@app.get("/health", tags=["meta"])
async def health():
    h = store.health()
    h["paywall_active"] = PAYWALL_ACTIVE
    h["network"] = C.X402_NETWORK if PAYWALL_ACTIVE else None
    return JSONResponse(h, status_code=200 if h["ok"] else 503)


@app.get("/v1/free/carry", tags=["free"])
async def free_carry():
    """Free tier: top-5 each leg, delayed 24h. No wallet, no key, no signup.

    Falls back to the live snapshot only when no archived snapshot is old enough
    yet (i.e. the first day the service runs).
    """
    snap = store.delayed()
    delayed = snap is not None
    if snap is None:
        snap = _require_snapshot()
    out = free_view(snap)
    out["delayed"] = delayed
    out["delay_hours"] = C.FREE_TIER_DELAY_HOURS if delayed else 0
    out["upgrade"] = {
        "live_full_ranking": "GET /v1/carry/rankings",
        "price": C.PRICE_RANKINGS,
        "payment": "x402 (USDC)" if PAYWALL_ACTIVE else "currently open",
    }
    return out


@app.get("/v1/method", tags=["free"])
async def method():
    """How the number is computed. Free on purpose -- it is the sales pitch."""
    return {
        "strategy": "cross-sectional funding carry on Hyperliquid perpetuals",
        "universe": {
            "min_daily_notional_volume_usd": C.MIN_DAILY_VOLUME,
            "max_coins": C.MAX_UNIVERSE,
        },
        "signal": {
            "lookback_hours": C.LOOKBACK_HOURS,
            "statistic": "mean hourly funding rate over the trailing window",
            "min_coverage": C.MIN_COVERAGE,
        },
        "construction": {
            "k_per_leg": C.K_PER_LEG,
            "long": "k coins with the most negative trailing funding",
            "short": "k coins with the most positive trailing funding",
            "sizing": "dollar-neutral, equal weight within leg",
        },
        "carry_spread": (
            "mean_funding(short_leg) - mean_funding(long_leg), annualized. "
            "Expected gross carry at leverage G is G/2 * carry_spread, before costs."
        ),
        "caveats": [
            "This is a structural risk premium, not a prediction. It can go negative.",
            "Gross of fees, slippage and borrow. Taker fees alone can erase it.",
            "Funding data is Hyperliquid's own; no cross-venue reconciliation yet.",
            "Informational only. Not investment advice, not a recommendation to trade.",
        ],
    }


# --- paid -------------------------------------------------------------------


@app.get("/v1/carry/rankings", tags=["paid"])
async def carry_rankings(
    k: int = Query(default=C.K_PER_LEG, ge=1, le=20, description="coins per leg"),
    min_volume: float = Query(default=0, ge=0, description="extra volume filter"),
):
    """Full live ranking. The flagship endpoint."""
    snap = dict(_require_snapshot())
    rows = [r for r in snap["rankings"] if r["day_notional_volume"] >= min_volume]
    if k != C.K_PER_LEG or min_volume > 0:
        from .carry import build_ranking

        universe = [
            {
                "coin": r["coin"],
                "day_notional_volume": r["day_notional_volume"],
                "funding_now": r["funding_now_hourly"],
                "open_interest": r["open_interest"],
                "mark_price": r["mark_price"],
                "max_leverage": None,
            }
            for r in rows
        ]
        funding = {
            r["coin"]: {
                "mean_hourly": r["mean_funding_hourly"],
                "n_points": r["n_points"],
                "coverage": r["coverage"],
                "first_ts": None,
                "last_ts": None,
            }
            for r in rows
        }
        snap = build_ranking(universe, funding, k=k)
        snap["as_of"] = store.current["as_of"]
        snap["as_of_ts"] = store.current["as_of_ts"]
    snap["tier"] = "paid"
    return snap


@app.get("/v1/carry/history/{coin}", tags=["paid"])
async def carry_history(
    coin: str,
    days: int = Query(default=30, ge=1, le=365),
):
    """Archived rank + trailing funding for one coin, from our own snapshots."""
    rows = store.history(coin.upper(), days=days)
    if not rows:
        raise HTTPException(
            status_code=404,
            detail={
                "error": "no_history",
                "message": f"No archived snapshots contain {coin.upper()}.",
                "archived_days": store.health()["archived_days"],
            },
        )
    return {"coin": coin.upper(), "days": days, "n": len(rows), "history": rows}


@app.get("/v1/universe", tags=["paid"])
async def universe():
    """Liquid perp universe with volume, open interest and current funding."""
    snap = _require_snapshot()
    # Sorted by liquidity, not by funding rank -- this endpoint answers
    # "what is tradable and how deep is it", which is a different question
    # from /v1/carry/rankings.
    rows = sorted(snap["rankings"], key=lambda r: -r["day_notional_volume"])
    return {
        "as_of": snap["as_of"],
        "as_of_ts": snap["as_of_ts"],
        "n": snap["universe_size"],
        "min_daily_volume": C.MIN_DAILY_VOLUME,
        "sorted_by": "day_notional_volume desc",
        "universe": [
            {
                "coin": r["coin"],
                "day_notional_volume": r["day_notional_volume"],
                "open_interest": r["open_interest"],
                "mark_price": r["mark_price"],
                "funding_now_annualized": r["funding_now_annualized"],
                "mean_funding_annualized": r["mean_funding_annualized"],
                "carry_rank": r["rank"],
            }
            for r in rows
        ],
    }


@app.get("/", include_in_schema=False)
async def root(request: Request):
    """HTML for browsers, JSON for everything else.

    The page is the funnel, so it must render even when the delayed snapshot
    isn't available yet -- it falls back to the live one rather than 503ing.
    """
    accept = request.headers.get("accept", "")
    if "text/html" in accept:
        from fastapi.responses import HTMLResponse

        from .web import render

        snap = store.delayed()
        delayed = snap is not None
        if snap is None:
            if store.current is None:
                return HTMLResponse(
                    "<h1>carrydesk</h1><p>Upstream data not yet available. "
                    "Retry shortly.</p>",
                    status_code=503,
                )
            snap = store.current
        return HTMLResponse(
            render(free_view(snap), delayed, store.health()["archived_days"])
        )
    return _index()


@app.get("/api", include_in_schema=False)
async def api_index():
    return _index()


def _index() -> dict:
    return {
        "service": "carrydesk",
        "what": "Cross-sectional funding-carry rankings for Hyperliquid perpetuals.",
        "free": ["GET /v1/free/carry", "GET /v1/method", "GET /health"],
        "paid": [
            f"GET /v1/carry/rankings ({C.PRICE_RANKINGS})",
            f"GET /v1/carry/history/{{coin}} ({C.PRICE_HISTORY})",
            f"GET /v1/universe ({C.PRICE_UNIVERSE})",
        ],
        "payment": "x402 / USDC" if PAYWALL_ACTIVE else "open (no paywall configured)",
        "docs": "/docs",
    }
