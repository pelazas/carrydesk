#!/usr/bin/env python3
"""Ops probe. Exit 0 = healthy, 1 = degraded, 2 = down.

Designed to be run from cron and piped straight into an alert channel. Prints a
single human-readable line on failure and nothing on success, so a cron job with
MAILTO or a `|| hermes --deliver telegram:<chat_id>` wrapper only fires on real
problems.

    */10 * * * * /path/.venv/bin/python scripts/ops_check.py || \
      hermes 'carrydesk alert' --deliver telegram:<chat-id>

Checks, in order of how much they matter:
  1. Is the service answering at all?
  2. Does it have a snapshot?
  3. Is that snapshot fresh (< 3 refresh intervals old)?
  4. Did the last refresh error?
  5. Is the archive actually growing? (a service that serves stale data forever
     looks healthy on every other check)
"""
from __future__ import annotations

import argparse
import sys

import httpx

DEGRADED, DOWN = 1, 2


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--url", default="http://127.0.0.1:8000", help="service base url")
    p.add_argument("--max-stale", type=int, default=3 * 3600, help="seconds")
    p.add_argument("--timeout", type=float, default=15.0)
    args = p.parse_args()

    base = args.url.rstrip("/")

    try:
        r = httpx.get(f"{base}/health", timeout=args.timeout)
    except Exception as e:  # noqa: BLE001
        print(f"carrydesk DOWN: /health unreachable at {base} ({type(e).__name__}: {e})")
        return DOWN

    try:
        h = r.json()
    except Exception:  # noqa: BLE001
        print(f"carrydesk DOWN: /health returned non-JSON (HTTP {r.status_code})")
        return DOWN

    if not h.get("has_snapshot"):
        print(f"carrydesk DOWN: no snapshot. last_error={h.get('last_error')}")
        return DOWN

    stale = h.get("seconds_since_refresh")
    if stale is not None and stale > args.max_stale:
        print(
            f"carrydesk DEGRADED: data {stale // 60}min old "
            f"(limit {args.max_stale // 60}min). last_error={h.get('last_error')}"
        )
        return DEGRADED

    if h.get("last_error"):
        print(f"carrydesk DEGRADED: last refresh failed: {h['last_error']}")
        return DEGRADED

    # A service can serve one good snapshot forever and pass every check above.
    # The archive growing is the only proof the pipeline is still alive.
    if h.get("refresh_count", 0) < 1:
        print("carrydesk DEGRADED: no successful refresh since boot")
        return DEGRADED

    # The paid surface must actually be gated. An open paywall is a silent
    # revenue leak that no uptime check would ever catch.
    if h.get("paywall_active"):
        try:
            probe = httpx.get(f"{base}/v1/carry/rankings", timeout=args.timeout)
            if probe.status_code != 402:
                print(
                    f"carrydesk DEGRADED: PAYWALL LEAK -- /v1/carry/rankings "
                    f"returned {probe.status_code}, expected 402"
                )
                return DEGRADED
        except Exception as e:  # noqa: BLE001
            print(f"carrydesk DEGRADED: paywall probe failed ({type(e).__name__}: {e})")
            return DEGRADED

    return 0


if __name__ == "__main__":
    sys.exit(main())
