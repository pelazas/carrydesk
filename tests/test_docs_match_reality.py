"""Published descriptions must match what the service actually does.

carrydesk describes itself in three places a stranger or an agent will read:
`/llms.txt`, `/v1/method`, and the public page. All three are hand-written
prose sitting next to code that changes. Prose does not fail loudly when it
goes stale — it just quietly starts lying, which for this product is the
expensive kind of wrong.

This caught two real gaps the hour it was written: a field shipped to every
caller that was documented nowhere, and `/v1/method` — the endpoint whose whole
purpose is explaining the methodology — describing none of the fields that
decide whether the headline should be believed.
"""
from __future__ import annotations

import asyncio
import json

import pytest

from carrydesk import config as C
from carrydesk.api import method as method_endpoint
from carrydesk.carry import build_ranking, free_view
from carrydesk.discovery import llms_txt

# The fields whose whole job is telling a caller how much to trust the headline.
HONESTY_FIELDS = [
    "carry_spread_annualized",
    "carry_spread_annualized_trimmed",
    "carry_spread_annualized_median",
    "headline_vs_typical",
    "outlier_dominated",
]


@pytest.fixture(scope="module")
def method_doc() -> str:
    return json.dumps(asyncio.run(method_endpoint()))


@pytest.fixture(scope="module")
def snapshot() -> dict:
    universe = [
        {"coin": f"C{i}", "day_notional_volume": 5e6, "funding_now": 0.0,
         "open_interest": 1.0, "mark_price": 1.0, "max_leverage": 10}
        for i in range(40)
    ]
    funding = {
        f"C{i}": {"mean_hourly": (i - 20) * 1e-6, "n_points": 336,
                  "coverage": 1.0, "first_ts": 0, "last_ts": 1}
        for i in range(40)
    }
    return build_ranking(universe, funding)


@pytest.mark.parametrize("field", HONESTY_FIELDS)
def test_every_honesty_field_is_documented_in_llms_txt(field):
    assert field in llms_txt(), f"{field} is returned to callers but absent from /llms.txt"


@pytest.mark.parametrize("field", HONESTY_FIELDS)
def test_every_honesty_field_is_documented_in_method(field, method_doc):
    assert field in method_doc, f"{field} is returned but /v1/method never explains it"


@pytest.mark.parametrize("field", HONESTY_FIELDS)
def test_every_documented_field_is_actually_returned(field, snapshot):
    """The other direction: documentation must not promise what we do not ship."""
    assert field in free_view(snapshot), f"{field} is documented but not in the free tier"


def test_method_params_match_the_config_that_is_used(method_doc):
    """A stated lookback that differs from the computed one is a lie about data."""
    doc = json.loads(method_doc)
    assert doc["signal"]["lookback_hours"] == C.LOOKBACK_HOURS
    assert doc["construction"]["k_per_leg"] == C.K_PER_LEG
    assert doc["universe"]["min_daily_notional_volume_usd"] == C.MIN_DAILY_VOLUME
    assert doc["universe"]["max_coins"] == C.MAX_UNIVERSE
    assert doc["signal"]["min_coverage"] == C.MIN_COVERAGE


def test_method_params_match_what_a_snapshot_reports(method_doc, snapshot):
    doc = json.loads(method_doc)
    assert doc["signal"]["lookback_hours"] == snapshot["method"]["lookback_hours"]
    assert doc["construction"]["k_per_leg"] == snapshot["method"]["k_per_leg"]
    assert doc["universe"]["min_daily_notional_volume_usd"] == snapshot["method"]["min_daily_volume"]


def test_llms_txt_quotes_the_prices_actually_charged():
    """Prices live in config; llms.txt states them in prose. They must agree."""
    txt = llms_txt()
    for price in (C.PRICE_RANKINGS, C.PRICE_HISTORY, C.PRICE_UNIVERSE):
        assert price in txt, f"llms.txt does not state the real price {price}"


def test_llms_txt_lists_every_mcp_tool_that_exists():
    from carrydesk import mcp_server

    advertised = llms_txt()
    for name in ("carry_snapshot", "carry_method", "carry_health",
                 "carry_rankings", "carry_history", "carry_universe"):
        assert hasattr(mcp_server, name), f"{name} advertised but not defined"
        assert name in advertised, f"{name} exists but /llms.txt never mentions it"


def test_free_tier_size_claim_matches_what_is_served(snapshot):
    fv = free_view(snapshot)
    assert len(fv["longs"]) == C.FREE_TIER_K
    assert len(fv["shorts"]) == C.FREE_TIER_K
    assert str(C.FREE_TIER_K) in fv["showing"]


def test_caveats_are_present_and_not_empty(method_doc):
    """The caveats block is part of the product, not boilerplate (DECISIONS D1)."""
    doc = json.loads(method_doc)
    assert len(doc["caveats"]) >= 3
    joined = " ".join(doc["caveats"]).lower()
    assert "not investment advice" in joined
    assert "negative" in joined
