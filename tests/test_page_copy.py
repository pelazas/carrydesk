"""The public page must never claim something the numbers contradict.

carrydesk's only real asset is being trusted about numbers. A headline that says
"somebody is paying you" on a day the carry is negative is not a cosmetic bug —
it is the product failing at the one thing it sells, on the page most people
will only ever read the top of.

The carry spread does go negative. The page says so itself, two paragraphs down.
"""
from __future__ import annotations

import re

import pytest

from carrydesk.web import render


def snap(median: float, mean: float | None = None, outliers: bool = False) -> dict:
    mean = median * 4 if mean is None else mean
    shorts = [{"coin": "BBB", "mean_funding_annualized": median, "day_notional_volume": 5e6}]
    if outliers:
        shorts.append(
            {"coin": "SAGA", "mean_funding_annualized": 1.99, "day_notional_volume": 1.3e6}
        )
    return {
        "as_of": "2026-08-02T17:00:00+00:00",
        "as_of_ts": 1785690000,
        "universe_size": 40,
        "method": {"lookback_hours": 336},
        "carry_spread_annualized": mean,
        "carry_spread_annualized_trimmed": mean * 0.6,
        "carry_spread_annualized_median": median,
        "outlier_dominated": outliers,
        "longs": [{"coin": "AAA", "mean_funding_annualized": -0.02,
                   "day_notional_volume": 5e6}],
        "shorts": shorts,
    }


def headline(html: str) -> str:
    return re.sub(r"<[^>]*>", " ", re.search(r'<h1 class="hero">(.*?)</h1>', html, re.S).group(1))


@pytest.mark.parametrize("median", [0.125, 0.01, 0.0])
def test_positive_carry_says_you_get_paid(median):
    h = headline(render(snap(median), False, 3))
    assert "paying you" in h
    assert "costs you money" not in h


@pytest.mark.parametrize("median", [-0.09, -0.4, -0.001])
def test_negative_carry_never_claims_you_get_paid(median):
    """The bug this file exists for."""
    html = render(snap(median), False, 3)
    h = headline(html)
    assert "paying you" not in h, f"headline claims payment at {median:+.1%}"
    assert "costs you money" in h


@pytest.mark.parametrize("median", [0.125, -0.09])
def test_headline_and_lede_never_contradict(median):
    """They are rendered separately; nothing else stops them disagreeing."""
    html = render(snap(median), False, 3)
    h, positive = headline(html), median >= 0
    lede = re.search(r'<p class="lede">(.*?)</p>', html, re.S).group(1)
    assert ("paying you" in h) == positive
    if not positive:
        assert "against you" in lede


def test_headline_matches_the_number_it_prints():
    """Whatever percentage the lede shows must agree in sign with the claim."""
    for median in (0.2, -0.2):
        html = render(snap(median), False, 3)
        shown = re.search(r'<span class="big">([+-][\d.]+)%</span>', html).group(1)
        assert (float(shown) >= 0) == ("paying you" in headline(html))


def test_honesty_block_names_the_real_outlier():
    html = render(snap(0.1, mean=0.5, outliers=True), False, 3)
    assert "misleading" in html
    assert "SAGA" in html and "198" in html or "199" in html


def test_honesty_block_does_not_cry_wolf_when_readings_agree():
    """No outliers: it must say so rather than keep a warning up for effect."""
    html = render(snap(0.11, mean=0.12), False, 3)
    assert "misleading" not in html
    assert "agree closely" in html


def test_free_tier_never_renders_the_paid_payload():
    html = render(snap(0.125), False, 3)
    assert "carry_spread_hourly" not in html
    assert "dollar-neutral weights" not in html
