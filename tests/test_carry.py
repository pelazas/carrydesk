"""Unit tests for the ranking maths. No network."""
from __future__ import annotations

import pytest

from carrydesk.carry import annualize, build_ranking, free_view


def mk(coin: str, funding_hourly: float, vol: float = 5e6):
    return (
        {
            "coin": coin,
            "day_notional_volume": vol,
            "funding_now": funding_hourly,
            "open_interest": 1000.0,
            "mark_price": 100.0,
            "max_leverage": 10,
        },
        {
            "mean_hourly": funding_hourly,
            "n_points": 336,
            "coverage": 1.0,
            "first_ts": 0,
            "last_ts": 1,
        },
    )


def build(pairs, k=2):
    universe = [u for u, _ in pairs]
    funding = {u["coin"]: f for u, f in pairs}
    return build_ranking(universe, funding, k=k)


def test_legs_are_assigned_by_funding_not_volume():
    # Highest-volume coin has mid funding -- it must NOT end up on a leg.
    snap = build(
        [
            mk("AAA", -0.001),
            mk("BBB", -0.0005),
            mk("MID", 0.0, vol=999e6),
            mk("YYY", 0.0005),
            mk("ZZZ", 0.001),
        ],
        k=2,
    )
    legs = {r["coin"]: r["leg"] for r in snap["rankings"]}
    assert legs["AAA"] == "long" and legs["BBB"] == "long"
    assert legs["YYY"] == "short" and legs["ZZZ"] == "short"
    assert legs["MID"] is None


def test_book_is_dollar_neutral():
    snap = build([mk(c, f) for c, f in
                  [("A", -3e-4), ("B", -2e-4), ("C", 2e-4), ("D", 3e-4)]], k=2)
    assert sum(r["weight"] for r in snap["rankings"]) == pytest.approx(0.0)
    assert sum(abs(r["weight"]) for r in snap["rankings"]) == pytest.approx(1.0)


def test_carry_spread_matches_leg_means():
    snap = build([mk(c, f) for c, f in
                  [("A", -1e-4), ("B", -3e-4), ("C", 2e-4), ("D", 4e-4)]], k=2)
    # longs mean = -2e-4, shorts mean = +3e-4, spread = 5e-4/hr
    assert snap["carry_spread_hourly"] == pytest.approx(5e-4)
    assert snap["carry_spread_annualized"] == pytest.approx(annualize(5e-4))
    # Expected return at gross 1.0 is half the spread, on the mean basis.
    assert snap["expected_annual_return"]["from_mean"]["gross_1.0"] == pytest.approx(
        0.5 * annualize(5e-4)
    )


def test_outlier_dominated_flag_fires():
    """One absurd short dominates the mean; trimmed must expose it."""
    pairs = [mk(c, f) for c, f in [
        ("A", -1e-5), ("B", -1e-5), ("C", -1e-5),
        ("X", 1e-5), ("Y", 1e-5), ("HUGE", 5e-3),
    ]]
    snap = build(pairs, k=3)
    assert snap["carry_spread_annualized"] > snap["carry_spread_annualized_trimmed"]
    assert snap["outlier_dominated"] is True


def test_no_outlier_flag_on_clean_data():
    pairs = [mk(c, f) for c, f in [
        ("A", -2e-5), ("B", -2e-5), ("C", -2e-5),
        ("X", 2e-5), ("Y", 2e-5), ("Z", 2e-5),
    ]]
    snap = build(pairs, k=3)
    assert snap["outlier_dominated"] is False


def test_too_small_universe_is_flagged_not_crashed():
    snap = build([mk("A", -1e-4), mk("B", 1e-4)], k=10)
    assert snap["tradable"] is False
    assert snap["universe_size"] == 2


def test_free_view_withholds_the_full_universe():
    pairs = [mk(f"C{i}", (i - 10) * 1e-5) for i in range(20)]
    snap = build(pairs, k=6)
    free = free_view(snap, k=2)
    assert len(free["longs"]) == 2
    assert len(free["shorts"]) == 2
    # The paid payload must not leak through the free view.
    assert "rankings" not in free
    for row in free["longs"] + free["shorts"]:
        assert "mean_funding_hourly" not in row
        assert "open_interest" not in row
    # Headline numbers stay -- the free tier has to be genuinely useful.
    assert free["carry_spread_annualized"] == snap["carry_spread_annualized"]


def test_annualize_uses_hourly_funding():
    assert annualize(1e-5) == pytest.approx(1e-5 * 24 * 365)


# --- the honesty flag -------------------------------------------------------
#
# The original rule compared only trimmed-vs-mean and never looked at the
# median. Across the first 50 archived snapshots the median sat at 0.24 of the
# mean -- the headline overstated a typical coin roughly fourfold -- and the
# flag fired exactly once. The signal meant to carry the product's honesty was
# silent almost exactly when it mattered. These pin the fixed behaviour.


def test_flag_fires_when_the_median_is_far_below_the_headline():
    """The real-world case the old rule missed: mean ~3.8x the median."""
    pairs = [mk(c, f) for c, f in [
        ("A", -1e-5), ("B", -1e-5), ("C", -1e-5),
        ("X", 1e-5), ("Y", 1e-5), ("HUGE", 3e-4),
    ]]
    snap = build(pairs, k=3)
    assert snap["carry_spread_annualized"] > 3 * snap["carry_spread_annualized_median"]
    assert snap["outlier_dominated"] is True


def test_flag_is_quiet_when_the_coins_agree():
    """It must not be permanently on, or nobody will read it."""
    pairs = [mk(c, f) for c, f in [
        ("A", -2e-5), ("B", -2.1e-5), ("C", -1.9e-5),
        ("X", 2e-5), ("Y", 2.1e-5), ("Z", 1.9e-5),
    ]]
    snap = build(pairs, k=3)
    assert snap["outlier_dominated"] is False


def test_headline_vs_typical_reports_the_actual_multiple():
    pairs = [mk(c, f) for c, f in [
        ("A", -1e-5), ("B", -1e-5), ("C", -1e-5),
        ("X", 1e-5), ("Y", 1e-5), ("HUGE", 3e-4),
    ]]
    snap = build(pairs, k=3)
    ratio = snap["headline_vs_typical"]
    assert ratio is not None and ratio > 3
    assert ratio == pytest.approx(
        abs(snap["carry_spread_annualized"] / snap["carry_spread_annualized_median"]), rel=1e-2
    )


def test_headline_vs_typical_is_none_rather_than_dividing_by_zero():
    pairs = [mk(c, 0.0) for c in ("A", "B", "C", "D")]
    snap = build(pairs, k=2)
    assert snap["headline_vs_typical"] is None
    assert snap["outlier_dominated"] is False


def test_free_view_carries_both_honesty_fields():
    pairs = [mk(f"C{i}", (i - 10) * 1e-5) for i in range(20)]
    fv = free_view(build(pairs, k=6), k=2)
    assert "outlier_dominated" in fv and "headline_vs_typical" in fv


# --- expected_annual_return is the most actionable field in the payload ------
#
# It is named "expected annual return", so it is what a reader plans against.
# Derived from the mean alone it was overstating the typical coin by ~4.7x --
# a 52%/yr headline where the median supported 11%.


def test_expected_return_is_published_on_both_bases():
    pairs = [mk(c, f) for c, f in [
        ("A", -1e-5), ("B", -1e-5), ("C", -1e-5),
        ("X", 1e-5), ("Y", 1e-5), ("HUGE", 3e-4),
    ]]
    e = build(pairs, k=3)["expected_annual_return"]
    assert set(e) == {"from_median", "from_mean", "basis_note"}
    for basis in ("from_median", "from_mean"):
        assert set(e[basis]) == {"gross_1.0", "gross_2.0"}


def test_median_basis_is_not_the_inflated_one():
    """The whole point: the conservative figure must actually be conservative."""
    pairs = [mk(c, f) for c, f in [
        ("A", -1e-5), ("B", -1e-5), ("C", -1e-5),
        ("X", 1e-5), ("Y", 1e-5), ("HUGE", 3e-4),
    ]]
    e = build(pairs, k=3)["expected_annual_return"]
    assert e["from_median"]["gross_2.0"] < e["from_mean"]["gross_2.0"]


def test_gross_2_is_exactly_twice_gross_1_on_both_bases():
    """Leverage scales the carry linearly; anything else is an arithmetic bug."""
    pairs = [mk(c, f) for c, f in [
        ("A", -2e-5), ("B", -1e-5), ("X", 1e-5), ("Y", 2e-5),
    ]]
    e = build(pairs, k=2)["expected_annual_return"]
    for basis in ("from_median", "from_mean"):
        assert e[basis]["gross_2.0"] == pytest.approx(2 * e[basis]["gross_1.0"])


def test_basis_note_warns_that_the_spread_does_not_persist():
    pairs = [mk(c, f) for c, f in [("A", -1e-5), ("B", 1e-5)]]
    note = build(pairs, k=1)["expected_annual_return"]["basis_note"].lower()
    assert "gross of fees" in note
    assert "persist" in note


def test_free_view_states_what_the_caller_actually_got():
    """`full_universe_size` duplicated `universe_size` while the number that
    matters to a free caller -- how many coins they received -- was absent."""
    pairs = [mk(f"C{i}", (i - 10) * 1e-5) for i in range(20)]
    fv = free_view(build(pairs, k=6), k=3)
    assert "full_universe_size" not in fv
    assert fv["coins_shown"] == 6
    assert fv["universe_size"] == 20
    assert fv["coins_shown"] < fv["universe_size"], "free tier must be a subset"
