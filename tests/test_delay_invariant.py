"""One invariant: every number on a free surface comes from the delayed cutoff.

This file exists because I broke that invariant four times in one afternoon,
and each fix caused the next break. The free tier flipped to 24h-delayed data
at 09:43 and, in order:

1. the page chart still plotted the live archive, labelling its endpoint with
   today's mean and median beside tiles showing yesterday's;
2. the /archive table's newest row reported today's live closing spread;
3. the /archive header counted 84 snapshots above a table listing 22;
4. the page's schema.org catalog advertised the full archive size to machines
   while humans saw the delayed slice.

Each time I fixed the instance in front of me rather than the rule. Patching
sites does not converge -- there is always one more consumer. So this test reads
the source, finds every archive read on every free route, and fails on any that
is not bounded. A new free surface added next month is covered without anyone
remembering this happened.
"""
from __future__ import annotations

import pathlib
import re

import pytest

API = pathlib.Path(__file__).parent.parent / "carrydesk" / "api.py"

# Routes a caller reaches without paying. Anything they render must respect
# the delay; the paid routes are exactly the ones allowed to see live data.
FREE_ROUTES = {"/", "/archive", "/v1/free/carry", "/health", "/llms.txt",
               "/robots.txt", "/sitemap.xml", "/v1/method", "/api"}

# Store methods that read the archive and therefore need bounding.
ARCHIVE_READERS = {"spread_series", "archive_index", "totals", "history"}

# `delayed()` IS the cutoff, and `health()` reports service state rather than
# market data, so neither takes a bound.
SELF_BOUNDING = {"delayed", "health"}

# The one deliberate unbounded read: /archive compares full totals against
# shown totals to tell the reader how much is being held back. Disclosing the
# size of what you withhold is the opposite of leaking it.
ALLOWED_UNBOUNDED = {("/archive", "totals")}


def route_bodies() -> dict[str, str]:
    src = API.read_text()
    parts = re.split(r'@app\.get\("([^"]+)"', src)
    out: dict[str, str] = {}
    for i in range(1, len(parts), 2):
        path = parts[i]
        body = parts[i + 1].split("@app.get")[0]
        out[path] = out.get(path, "") + body
    return out


def archive_reads(body: str) -> list[tuple[str, str]]:
    return [
        (fn, args)
        for fn, args in re.findall(r"store\.(\w+)\(([^)]*)\)", body)
        if fn in ARCHIVE_READERS or fn in SELF_BOUNDING
    ]


def test_the_scanner_actually_finds_calls():
    """A structural test that matches nothing would pass forever."""
    bodies = route_bodies()
    assert "/" in bodies and "/archive" in bodies
    assert archive_reads(bodies["/archive"]), "scanner found no store calls to check"


@pytest.mark.parametrize("route", sorted(FREE_ROUTES))
def test_free_routes_never_read_the_archive_unbounded(route):
    body = route_bodies().get(route)
    if body is None:
        pytest.skip(f"{route} is not a @app.get route")
    for fn, args in archive_reads(body):
        if fn in SELF_BOUNDING or (route, fn) in ALLOWED_UNBOUNDED:
            continue
        assert "until_ts" in args, (
            f"{route} calls store.{fn}() without until_ts -- a free surface "
            f"rendering unbounded archive data leaks what the delay withholds"
        )


def test_paid_routes_are_not_accidentally_delayed():
    """The mirror image: paid callers must get live data, or they are being
    charged for the free tier."""
    bodies = route_bodies()
    for route in ("/v1/carry/rankings", "/v1/universe"):
        body = bodies.get(route, "")
        assert "until_ts" not in body, f"{route} is paid but bounded to the delay"
        assert "store.delayed" not in body, f"{route} is paid but serves delayed data"


def test_every_allowed_exception_is_still_a_real_route():
    """Stops the allowlist rotting into a blanket exemption."""
    bodies = route_bodies()
    for route, fn in ALLOWED_UNBOUNDED:
        assert route in bodies, f"allowlisted {route} no longer exists"
        assert f"store.{fn}(" in bodies[route], (
            f"allowlist keeps {route}/{fn} exempt but it no longer calls it"
        )
