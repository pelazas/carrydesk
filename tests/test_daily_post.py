"""The daily post is the artifact intended to go public, unedited, forever.

It is rendered by cron and read by humans on a social feed, where there is no
room for a caveat and no chance to revise. So its wording has to be right at the
moment it is generated, not fixed afterwards.

Two problems this file exists for. The post said "Outlier-dominated **today**",
implying an exception — but after the flag was corrected it fires on nearly
every reading, so "today" misrepresented the normal state of the market. And it
printed "Delayed 0h", which reads like a bug when it means "not delayed".
"""
from __future__ import annotations

import importlib.util
import pathlib

import pytest

_spec = importlib.util.spec_from_file_location(
    "daily_post", pathlib.Path(__file__).parent.parent / "scripts" / "daily_post.py"
)
dp = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(dp)


def snap(*, delayed_hours: int = 0, outlier: bool = True, mult: float | None = 4.6,
         coin: str = "SAGA") -> dict:
    return {
        "as_of": "2026-08-03T06:00:00+00:00",
        "as_of_ts": int(__import__("time").time()) - 600,
        "universe_size": 40,
        "method": {"lookback_hours": 336},
        "carry_spread_annualized": 0.534,
        "carry_spread_annualized_trimmed": 0.283,
        "carry_spread_annualized_median": 0.117,
        "headline_vs_typical": mult,
        "outlier_dominated": outlier,
        "delay_hours": delayed_hours,
        "delayed": bool(delayed_hours),
        "longs": [{"coin": f"{coin}L{i}", "mean_funding_annualized": -0.05,
                   "day_notional_volume": 3e6} for i in range(5)],
        "shorts": [{"coin": f"{coin}S{i}", "mean_funding_annualized": 0.9,
                    "day_notional_volume": 2e6} for i in range(5)],
    }


# --- the post must not misrepresent how normal the outlier state is ---------


def test_outlier_note_does_not_call_the_normal_state_an_exception():
    md = dp.render_markdown(snap())
    assert "dominated today" not in md.lower()
    assert "usual state" in md, "the note should say this is normal, not today's quirk"


def test_outlier_note_quotes_the_actual_multiple():
    assert "4.6x" in dp.render_markdown(snap(mult=4.6))
    assert "12.1x" in dp.render_markdown(snap(mult=12.1))


def test_outlier_note_degrades_when_the_multiple_is_missing():
    md = dp.render_markdown(snap(mult=None))
    assert "several times" in md and "None" not in md


def test_no_outlier_note_when_the_readings_agree():
    md = dp.render_markdown(snap(outlier=False))
    assert "overstates a typical coin" not in md


# --- freshness wording ------------------------------------------------------


def test_live_reading_is_not_reported_as_delayed_zero_hours():
    md = dp.render_markdown(snap(delayed_hours=0))
    assert "Delayed 0h" not in md
    assert "Live reading" in md


def test_a_delayed_snapshot_says_how_delayed():
    md = dp.render_markdown(snap(delayed_hours=24))
    assert "Delayed 24h" in md and "Live reading" not in md


# --- the short form has a hard character budget -----------------------------


@pytest.mark.parametrize("coin", ["A", "SAGA", "FARTCOIN", "MOODENGVERYLONG"])
@pytest.mark.parametrize("mult", [3.1, 12.4, 148.9])
def test_x_post_fits_the_character_limit(coin, mult):
    """Coin names and the multiple both vary; the budget must hold regardless."""
    text = dp.render_x(snap(coin=coin, mult=mult))
    assert len(text) <= 280, f"X post is {len(text)} chars with coin={coin} mult={mult}"


def test_x_post_leads_with_both_numbers():
    text = dp.render_x(snap())
    assert "mean" in text and "median" in text


def test_x_post_always_carries_the_disclaimer():
    for kwargs in ({}, {"outlier": False}, {"delayed_hours": 24}):
        assert "Not advice" in dp.render_x(snap(**kwargs))


# --- the gate still refuses bad snapshots -----------------------------------


def test_gate_passes_a_healthy_snapshot():
    assert dp.gate(snap()) == []


def test_gate_blocks_an_empty_leg():
    s = snap()
    s["longs"] = []
    assert any("empty leg" in p for p in dp.gate(s))
