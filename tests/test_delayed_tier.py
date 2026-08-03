"""The free tier's live -> delayed transition.

This fires exactly once, ~24h after the first snapshot, and nothing exercises it
before then. Until the archive is a day old `store.delayed()` returns None and
the API silently falls back to the live snapshot; the moment an old-enough
snapshot exists the whole free path switches over. If that switch is wrong, the
public page, `/v1/free/carry` and every free MCP tool break at once — and it
would happen unattended, at whatever hour the archive crosses 24h.

So: simulate the crossing with a synthetic archive rather than wait for it.
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

import pytest

from carrydesk.carry import free_view
from carrydesk.store import SnapshotStore


def snap(ts: datetime, spread: float = 0.30) -> dict:
    return {
        "as_of": ts.isoformat(timespec="seconds"),
        "as_of_ts": int(ts.timestamp()),
        "source": "hyperliquid",
        "method": {"lookback_hours": 336, "k_per_leg": 2},
        "universe_size": 4,
        "tradable": True,
        "carry_spread_annualized": spread,
        "carry_spread_annualized_trimmed": spread * 0.6,
        "carry_spread_annualized_median": spread * 0.3,
        "outlier_dominated": False,
        "long_leg_mean_annualized": -spread / 2,
        "short_leg_mean_annualized": spread / 2,
        "expected_annual_return": {"gross_1.0": spread / 2, "gross_2.0": spread},
        "rankings": [
            {"coin": "AAA", "rank": 1, "leg": "long", "weight": 0.25,
             "mean_funding_annualized": -spread / 2, "funding_now_annualized": 0.0,
             "mean_funding_hourly": 0.0, "funding_now_hourly": 0.0,
             "day_notional_volume": 5e6, "open_interest": 1.0, "mark_price": 1.0,
             "n_points": 336, "coverage": 1.0},
            {"coin": "BBB", "rank": 2, "leg": "short", "weight": -0.25,
             "mean_funding_annualized": spread / 2, "funding_now_annualized": 0.0,
             "mean_funding_hourly": 0.0, "funding_now_hourly": 0.0,
             "day_notional_volume": 5e6, "open_interest": 1.0, "mark_price": 1.0,
             "n_points": 336, "coverage": 1.0},
        ],
    }


@pytest.fixture()
def store(tmp_path):
    return SnapshotStore(snapshot_dir=tmp_path)


def write(store: SnapshotStore, s: dict) -> None:
    day = datetime.fromtimestamp(s["as_of_ts"], tz=timezone.utc).strftime("%Y-%m-%d")
    with (store.dir / f"{day}.jsonl").open("a") as fh:
        fh.write(json.dumps(s) + "\n")


def test_before_24h_there_is_no_delayed_snapshot(store):
    """Day one: everything is fresh, so the API must fall back to live."""
    now = datetime.now(timezone.utc)
    for h in (0, 2, 5):
        write(store, snap(now - timedelta(hours=h)))
    assert store.delayed() is None


def test_at_the_crossing_the_oldest_eligible_snapshot_is_served(store):
    """The moment a >24h snapshot exists, it becomes the free tier's data."""
    now = datetime.now(timezone.utc)
    old = snap(now - timedelta(hours=26), spread=0.11)
    write(store, old)
    write(store, snap(now - timedelta(hours=1), spread=0.99))
    got = store.delayed()
    assert got is not None
    assert got["as_of_ts"] == old["as_of_ts"]
    # Must NOT leak the fresh one -- that would defeat the whole paid tier.
    assert got["carry_spread_annualized"] == pytest.approx(0.11)


def test_newest_eligible_wins_not_the_oldest(store):
    """With several old snapshots, serve the freshest that is still >24h old."""
    now = datetime.now(timezone.utc)
    for h, sp in ((50, 0.10), (30, 0.20), (25, 0.30), (2, 0.90)):
        write(store, snap(now - timedelta(hours=h), spread=sp))
    got = store.delayed()
    assert got["carry_spread_annualized"] == pytest.approx(0.30)


def test_crossing_a_day_boundary_still_finds_it(store):
    """The archive is one file per UTC day, so the lookback must span files."""
    now = datetime.now(timezone.utc)
    write(store, snap(now - timedelta(hours=30), spread=0.42))
    write(store, snap(now, spread=0.90))
    got = store.delayed()
    assert got is not None and got["carry_spread_annualized"] == pytest.approx(0.42)


def test_free_view_of_a_delayed_snapshot_is_complete(store):
    """Whatever delayed() returns must still render a usable free tier."""
    now = datetime.now(timezone.utc)
    write(store, snap(now - timedelta(hours=26), spread=0.25))
    fv = free_view(store.delayed())
    for k in ("carry_spread_annualized", "carry_spread_annualized_trimmed",
              "carry_spread_annualized_median", "outlier_dominated", "longs", "shorts"):
        assert k in fv, f"free view lost `{k}` on the delayed path"
    assert fv["longs"] and fv["shorts"]
    assert "rankings" not in fv  # paid payload must never leak


def test_a_gap_in_publishing_degrades_rather_than_breaks(store):
    """If nothing was published for days, serve the newest old snapshot anyway."""
    now = datetime.now(timezone.utc)
    write(store, snap(now - timedelta(days=5), spread=0.15))
    got = store.delayed()
    assert got is not None and got["carry_spread_annualized"] == pytest.approx(0.15)


def test_beyond_the_lookback_window_returns_none_not_a_crash(store):
    """Older than the walk-back horizon: None is correct, an exception is not."""
    now = datetime.now(timezone.utc)
    write(store, snap(now - timedelta(days=40), spread=0.15))
    assert store.delayed() is None


# --- the delay must hold on every public surface, not just the JSON ---------
#
# After the free tier flipped to delayed data, the page still rendered its chart
# and archive table from the *live* archive. The chart labels its endpoint with
# that reading's mean and median, so the page published today's live headline
# beside stat tiles showing yesterday's: three stories on one page, and the
# numbers the delay exists to withhold given away for free.


def test_spread_series_stops_at_the_cutoff(store):
    now = datetime.now(timezone.utc)
    for h in (30, 26, 2, 0):
        write(store, snap(now - timedelta(hours=h), spread=0.1 * h))
    cutoff = store.delayed()["as_of_ts"]
    series = store.spread_series(until_ts=cutoff)
    assert series, "truncation must not empty the series"
    assert max(r["ts"] for r in series) <= cutoff
    assert all(r["ts"] <= cutoff for r in series)


def test_untruncated_series_would_leak(store):
    """Guards the regression directly: without a cutoff, live data is present."""
    now = datetime.now(timezone.utc)
    write(store, snap(now - timedelta(hours=26), spread=0.11))
    write(store, snap(now, spread=0.99))
    cutoff = store.delayed()["as_of_ts"]
    assert max(r["ts"] for r in store.spread_series()) > cutoff
    assert max(r["ts"] for r in store.spread_series(until_ts=cutoff)) <= cutoff


def test_archive_index_respects_the_cutoff(store):
    now = datetime.now(timezone.utc)
    write(store, snap(now - timedelta(hours=26), spread=0.11))
    write(store, snap(now, spread=0.99))
    cutoff = store.delayed()["as_of_ts"]
    for row in store.archive_index(until_ts=cutoff):
        assert row["carry_spread_annualized"] != pytest.approx(0.99), (
            "today's live closing spread leaked into the public archive table"
        )
