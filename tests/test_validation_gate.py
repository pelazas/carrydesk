"""The gate that keeps wrong numbers off the site.

This service publishes unattended, hourly, forever. The single promise that
makes that safe is: *a bad snapshot raises, and the previous good one keeps
serving*. If the gate lets something through, carrydesk publishes a wrong
number under its own timestamp, into an append-only archive, and the archive is
the only asset it has.

Neither the gate nor the refresh loop had a single test before this file.
"""
from __future__ import annotations

import asyncio
import json

import pytest

from carrydesk import config as C
from carrydesk.store import SnapshotStore, refresh_loop


def good(universe: int = 40, spread: float = 0.30, coverage: float = 1.0) -> dict:
    return {
        "as_of": "2026-08-02T18:00:00+00:00",
        "as_of_ts": 1785693600,
        "universe_size": universe,
        "carry_spread_annualized": spread,
        "carry_spread_annualized_median": spread / 3,
        "rankings": [
            {"coin": f"C{i}", "coverage": coverage, "rank": i + 1}
            for i in range(universe)
        ],
    }


@pytest.fixture()
def store(tmp_path):
    return SnapshotStore(snapshot_dir=tmp_path)


# --- the gate itself --------------------------------------------------------


def test_a_healthy_snapshot_passes(store):
    store._validate(good())  # must not raise


def test_too_few_coins_is_rejected(store):
    """Below 2k the legs cannot be built, so the spread is meaningless."""
    with pytest.raises(ValueError, match="universe too small"):
        store._validate(good(universe=2 * C.K_PER_LEG - 1))


@pytest.mark.parametrize("spread", [5.5, -5.5, 99.0, -12.0])
def test_absurd_spreads_are_rejected(store, spread):
    """500%/yr means the upstream data broke, not that we found free money."""
    with pytest.raises(ValueError, match="sanity band"):
        store._validate(good(spread=spread))


@pytest.mark.parametrize("spread", [4.9, -4.9, 0.0])
def test_extreme_but_possible_spreads_pass(store, spread):
    """The band must not reject real readings -- a false alarm stops publishing."""
    store._validate(good(spread=spread))


def test_thin_coverage_is_rejected(store):
    """A coin with half its funding history makes its mean meaningless."""
    with pytest.raises(ValueError, match="coverage"):
        store._validate(good(coverage=C.MIN_COVERAGE - 0.01))


# --- the promise: bad data never displaces good data ------------------------


class FakeClient:
    """Stands in for HLClient. `mode` decides what the next refresh produces."""

    def __init__(self):
        self.mode = "good"
        self.calls = 0

    async def liquid_universe(self, *a, **k):
        self.calls += 1
        if self.mode == "upstream_down":
            raise RuntimeError("hyperliquid unreachable")
        if self.mode == "empty":
            return []
        n = 3 if self.mode == "tiny" else 40
        return [
            {"coin": f"C{i}", "day_notional_volume": 5e6, "funding_now": 0.0,
             "open_interest": 1.0, "mark_price": 1.0, "max_leverage": 10}
            for i in range(n)
        ]

    async def trailing_funding(self, coins, *a, **k):
        # Half the coins negative, half positive -> a sane spread.
        return {
            c: {"mean_hourly": (1e-5 if i % 2 else -1e-5), "n_points": 336,
                "coverage": 1.0, "first_ts": 0, "last_ts": 1}
            for i, c in enumerate(coins)
        }


def test_a_rejected_refresh_leaves_the_good_snapshot_serving(store):
    """The core guarantee."""
    c = FakeClient()
    first = asyncio.run(store.refresh(c))
    assert store.current is first

    c.mode = "tiny"  # 3 coins -> fails the universe check
    with pytest.raises(Exception):
        asyncio.run(store.refresh(c))

    assert store.current is first, "a rejected snapshot displaced the good one"
    assert store.refresh_count == 1


def test_a_rejected_snapshot_is_never_archived(store):
    """The archive is append-only, so a bad line there is permanent."""
    c = FakeClient()
    asyncio.run(store.refresh(c))
    before = sorted(p.read_text() for p in store.dir.glob("*.jsonl"))

    c.mode = "tiny"
    with pytest.raises(Exception):
        asyncio.run(store.refresh(c))

    after = sorted(p.read_text() for p in store.dir.glob("*.jsonl"))
    assert before == after, "a rejected snapshot reached the archive"


def test_upstream_failure_does_not_wipe_the_snapshot(store):
    c = FakeClient()
    first = asyncio.run(store.refresh(c))
    c.mode = "upstream_down"
    with pytest.raises(Exception):
        asyncio.run(store.refresh(c))
    assert store.current is first
    assert store.health()["has_snapshot"] is True


def test_empty_universe_is_rejected_before_anything_is_stored(store):
    c = FakeClient()
    c.mode = "empty"
    with pytest.raises(Exception):
        asyncio.run(store.refresh(c))
    assert store.current is None
    assert list(store.dir.glob("*.jsonl")) == []


# --- the loop must never die ------------------------------------------------


def test_refresh_loop_survives_a_failure_and_records_it(store, monkeypatch):
    """If the loop dies the service serves one snapshot forever, looking healthy."""
    monkeypatch.setattr(C, "REFRESH_SECONDS", 0.01)
    c = FakeClient()
    c.mode = "upstream_down"

    async def run_briefly():
        task = asyncio.create_task(refresh_loop(store, c))
        await asyncio.sleep(0.08)
        task.cancel()
        return task

    task = asyncio.run(run_briefly())
    assert c.calls > 1, "loop stopped after the first failure"
    assert store.last_error and "hyperliquid unreachable" in store.last_error


def test_health_reports_degraded_with_no_snapshot(store):
    h = store.health()
    assert h["ok"] is False and h["has_snapshot"] is False


def test_archive_line_is_valid_json_and_complete(store):
    """Whatever is archived has to survive a round trip -- it is read back later."""
    asyncio.run(store.refresh(FakeClient()))
    path = next(store.dir.glob("*.jsonl"))
    lines = [x for x in path.read_text().splitlines() if x.strip()]
    assert len(lines) == 1
    parsed = json.loads(lines[0])
    for k in ("as_of", "as_of_ts", "carry_spread_annualized",
              "carry_spread_annualized_median", "rankings", "universe_size"):
        assert k in parsed


# --- the archive count must not flatter -------------------------------------
#
# The page advertised "66 snapshots", which reads as 66 observations. In fact
# the service recomputes on every restart, so 41 of the first 65 gaps were under
# five minutes and the real coverage was 19 hours. Same failure as quoting a
# mean without its median: a number that sounds better than the record.


def write_at(store: SnapshotStore, ts: int) -> None:
    from datetime import datetime, timezone
    s = good()
    s["as_of_ts"] = ts
    s["as_of"] = datetime.fromtimestamp(ts, tz=timezone.utc).isoformat()
    day = datetime.fromtimestamp(ts, tz=timezone.utc).strftime("%Y-%m-%d")
    with (store.dir / f"{day}.jsonl").open("a") as fh:
        fh.write(json.dumps(s) + "\n")


def test_distinct_hours_ignores_restart_bursts(store):
    """Six snapshots inside one hour are one hour of record, not six."""
    base = 1785700000 - (1785700000 % 3600)
    for offset in (0, 30, 60, 90, 120, 200):
        write_at(store, base + offset)
    t = store.totals()
    assert t["snapshots"] == 6
    assert t["distinct_hours"] == 1


def test_distinct_hours_counts_real_coverage(store):
    base = 1785700000 - (1785700000 % 3600)
    for h in range(5):
        write_at(store, base + h * 3600)
        write_at(store, base + h * 3600 + 45)  # a restart in the same hour
    t = store.totals()
    assert t["snapshots"] == 10
    assert t["distinct_hours"] == 5, "restart duplicates inflated the coverage figure"


def test_distinct_hours_spans_day_files(store):
    base = 1785715200  # a UTC midnight
    write_at(store, base - 3600)
    write_at(store, base + 3600)
    t = store.totals()
    assert t["days"] == 2 and t["distinct_hours"] == 2


def test_totals_can_be_bounded_to_what_a_delayed_page_shows(store):
    """The /archive header advertised 84 snapshots above a table listing 22 --
    counting evidence the page withholds, on a page whose whole argument is
    that the reader can check it."""
    base = 1785700000 - (1785700000 % 3600)
    for h in range(6):
        write_at(store, base + h * 3600)
    cutoff = base + 2 * 3600
    shown, full = store.totals(until_ts=cutoff), store.totals()
    assert shown["snapshots"] == 3 and full["snapshots"] == 6
    assert shown["distinct_hours"] == 3 and full["distinct_hours"] == 6
    assert shown["snapshots"] < full["snapshots"], "bounding had no effect"


def test_bounded_totals_days_reflect_only_shown_days(store):
    base = 1785715200  # a UTC midnight
    write_at(store, base - 3600)   # previous day
    write_at(store, base + 3600)   # next day
    assert store.totals()["days"] == 2
    assert store.totals(until_ts=base - 1800)["days"] == 1
