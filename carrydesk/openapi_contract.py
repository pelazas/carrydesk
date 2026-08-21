"""OpenAPI payment and success declarations derived from live handler facts.

These objects document what the paid GET handlers already return and what the
x402 middleware already charges. They are not response_model validators and
must not filter, coerce, or reject runtime bodies.
"""
from __future__ import annotations

from x402.mechanisms.evm.default_assets import DEFAULT_ASSETS

from . import config as C

SCHEME = "exact"

# The only networks carrydesk documents, charges, and settles on: Base
# mainnet (CDP facilitator) and Base Sepolia (public facilitator). Paid-route
# contract metadata fails closed everywhere else -- see payment_info.
SUPPORTED_NETWORKS = frozenset({C.BASE_MAINNET, C.BASE_SEPOLIA})


def default_usdc_asset(network: str) -> str | None:
    """The SDK's index-0 charged asset iff it is USDC, else None.

    ``$`` prices are charged against ``DEFAULT_ASSETS[network][0]``, so only
    that first entry counts. Anything else in the list -- e.g. USDT0 leading
    on eip155:988 -- is not what this service bills, and returning it would
    mislabel a non-USDC contract as USDC.
    """
    entries = DEFAULT_ASSETS.get(network) or []
    if not entries:
        return None
    first = entries[0]
    if first.get("symbol") == "USDC" and first.get("asset"):
        return first["asset"]
    return None


def payment_info(price: str, resource_path: str) -> dict:
    """Machine-readable paid-operation mark for one exact GET.

    Price comes from the existing PRICE_* config strings. Network, optional
    payTo, and the SDK default USDC asset come from the same env the
    middleware already uses. Fails closed on any network outside
    SUPPORTED_NETWORKS or whose index-0 SDK asset is not USDC, rather than
    omitting or inventing an asset. Empty X402_PAY_TO omits payTo (dev/CI run
    open), on a supported Base network only.
    """
    if not resource_path.startswith("/") or resource_path.startswith("//"):
        raise ValueError(f"resource_path must be an absolute path: {resource_path}")
    amount = price.lstrip("$")
    network = C.X402_NETWORK
    if network not in SUPPORTED_NETWORKS:
        raise RuntimeError(
            f"unsupported payment network {network!r}: paid-route contract "
            f"metadata is defined exactly for {sorted(SUPPORTED_NETWORKS)}"
        )
    asset = default_usdc_asset(network)
    if not asset:
        raise RuntimeError(
            f"x402 SDK default charged asset for {network!r} is not USDC; "
            "refusing to declare paid-route metadata without the real asset"
        )
    x402: dict = {
        "scheme": SCHEME,
        "network": network,
        "asset": asset,
    }
    if C.X402_PAY_TO:
        x402["payTo"] = C.X402_PAY_TO
    origin = C.PUBLIC_URL.rstrip("/")
    x402["resource"] = f"{origin}{resource_path}"
    return {
        "price": {"amount": amount, "currency": "USDC", "mode": "fixed"},
        "protocols": [{"x402": x402}],
    }


def _object(required: list[str], properties: dict, extra: bool = True) -> dict:
    schema = {
        "type": "object",
        "required": required,
        "properties": properties,
    }
    if extra:
        schema["additionalProperties"] = True
    return schema


RANKING_ROW = _object(
    [
        "coin",
        "mean_funding_hourly",
        "mean_funding_annualized",
        "funding_now_hourly",
        "funding_now_annualized",
        "day_notional_volume",
        "open_interest",
        "mark_price",
        "n_points",
        "coverage",
        "rank",
        "leg",
        "weight",
    ],
    {
        "coin": {"type": "string"},
        "mean_funding_hourly": {"type": "number"},
        "mean_funding_annualized": {"type": "number"},
        "funding_now_hourly": {"type": "number"},
        "funding_now_annualized": {"type": "number"},
        "day_notional_volume": {"type": "number"},
        "open_interest": {"type": "number"},
        "mark_price": {"type": "number"},
        "n_points": {"type": "integer"},
        "coverage": {"type": "number"},
        "rank": {"type": "integer"},
        "leg": {"type": ["string", "null"]},
        "weight": {"type": "number"},
    },
)

RANKINGS_200 = _object(
    [
        "as_of",
        "as_of_ts",
        "source",
        "method",
        "universe_size",
        "tradable",
        "carry_spread_hourly",
        "carry_spread_annualized",
        "carry_spread_annualized_trimmed",
        "carry_spread_annualized_median",
        "headline_vs_typical",
        "outlier_dominated",
        "long_leg_mean_annualized",
        "short_leg_mean_annualized",
        "expected_annual_return",
        "rankings",
        "tier",
    ],
    {
        "as_of": {"type": "string"},
        "as_of_ts": {"type": "integer"},
        "source": {"type": "string"},
        "method": _object(
            [
                "lookback_hours",
                "k_per_leg",
                "min_daily_volume",
                "max_universe",
                "funding_interval_hours",
            ],
            {
                "lookback_hours": {"type": "integer"},
                "k_per_leg": {"type": "integer"},
                "min_daily_volume": {"type": "number"},
                "max_universe": {"type": "integer"},
                "funding_interval_hours": {"type": "integer"},
            },
        ),
        "universe_size": {"type": "integer"},
        "tradable": {"type": "boolean"},
        "carry_spread_hourly": {"type": "number"},
        "carry_spread_annualized": {"type": "number"},
        "carry_spread_annualized_trimmed": {"type": "number"},
        "carry_spread_annualized_median": {"type": "number"},
        # Present as a key even when the median is 0 and the ratio is None.
        "headline_vs_typical": {"type": ["number", "null"]},
        "outlier_dominated": {"type": "boolean"},
        "long_leg_mean_annualized": {"type": "number"},
        "short_leg_mean_annualized": {"type": "number"},
        "expected_annual_return": _object(
            ["from_median", "from_mean", "basis_note"],
            {
                "from_median": {"type": "object", "additionalProperties": True},
                "from_mean": {"type": "object", "additionalProperties": True},
                "basis_note": {"type": "string"},
            },
        ),
        "rankings": {"type": "array", "items": RANKING_ROW},
        "tier": {"type": "string", "const": "paid"},
    },
)

UNIVERSE_ROW = _object(
    [
        "coin",
        "day_notional_volume",
        "open_interest",
        "mark_price",
        "funding_now_annualized",
        "mean_funding_annualized",
        "carry_rank",
    ],
    {
        "coin": {"type": "string"},
        "day_notional_volume": {"type": "number"},
        "open_interest": {"type": "number"},
        "mark_price": {"type": "number"},
        "funding_now_annualized": {"type": "number"},
        "mean_funding_annualized": {"type": "number"},
        "carry_rank": {"type": "integer"},
    },
)

UNIVERSE_200 = _object(
    ["as_of", "as_of_ts", "n", "min_daily_volume", "sorted_by", "universe"],
    {
        "as_of": {"type": "string"},
        "as_of_ts": {"type": "integer"},
        "n": {"type": "integer"},
        "min_daily_volume": {"type": "number"},
        "sorted_by": {"type": "string"},
        "universe": {"type": "array", "items": UNIVERSE_ROW},
    },
)

HISTORY_200 = _object(
    ["coin", "days", "n", "history"],
    {
        "coin": {"type": "string"},
        "days": {"type": "integer"},
        "n": {"type": "integer"},
        "history": {"type": "array", "items": {"type": "object", "additionalProperties": True}},
    },
)


def json_200(schema: dict, description: str) -> dict:
    return {
        "description": description,
        "content": {"application/json": {"schema": schema}},
    }
