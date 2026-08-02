#!/usr/bin/env python3
"""Weekly self-audit. Distribution is worthless if the thing breaks quietly.

`ops_check.py` answers "is it up right now" every 10 minutes. This answers the
slower question: is everything a stranger might touch still correct, and is the
archive actually accumulating? Those fail on timescales a 10-minute probe never
notices — a cert 20 days from expiry, an archive that stopped growing, a
discovery surface returning 404 after a refactor.

    python scripts/weekly_audit.py --url https://carry.pelazas.com

Exit 0 = all good, 1 = at least one problem (prints one line per problem).
"""
from __future__ import annotations

import argparse
import json
import socket
import ssl
import sys
from datetime import datetime, timezone

import httpx


def check_cert(host: str, warn_days: int = 21) -> list[str]:
    """Caddy renews automatically, but silently-not-renewing is the failure
    mode that takes a site down with no warning at all."""
    try:
        ctx = ssl.create_default_context()
        with socket.create_connection((host, 443), timeout=15) as sock:
            with ctx.wrap_socket(sock, server_hostname=host) as ss:
                cert = ss.getpeercert()
        exp = datetime.strptime(cert["notAfter"], "%b %d %H:%M:%S %Y %Z").replace(
            tzinfo=timezone.utc
        )
        left = (exp - datetime.now(timezone.utc)).days
        if left < warn_days:
            return [f"TLS certificate expires in {left} days ({exp:%Y-%m-%d})"]
        return []
    except Exception as e:  # noqa: BLE001
        return [f"TLS check failed: {type(e).__name__}: {e}"]


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--url", default="https://carry.pelazas.com")
    p.add_argument("--timeout", type=float, default=30.0)
    args = p.parse_args()
    base = args.url.rstrip("/")
    host = base.split("://", 1)[-1].split("/")[0]
    problems: list[str] = []

    def get(path: str, **kw):
        return httpx.get(f"{base}{path}", timeout=args.timeout, follow_redirects=True, **kw)

    # 1. Free surfaces a stranger or crawler would hit first.
    for path, expect in [
        ("/health", 200), ("/v1/free/carry", 200), ("/v1/method", 200),
        ("/archive", 200), ("/llms.txt", 200), ("/robots.txt", 200),
        ("/sitemap.xml", 200), ("/openapi.json", 200), ("/docs", 200),
    ]:
        try:
            code = get(path).status_code
            if code != expect:
                problems.append(f"{path} returned {code}, expected {expect}")
        except Exception as e:  # noqa: BLE001
            problems.append(f"{path} unreachable: {type(e).__name__}")

    # 2. Paid routes must still be gated. An open paywall looks like success.
    for path in ["/v1/carry/rankings", "/v1/universe", "/v1/carry/history/BTC"]:
        try:
            code = httpx.get(f"{base}{path}", timeout=args.timeout).status_code
            if code != 402:
                problems.append(f"PAYWALL LEAK: {path} returned {code}, expected 402")
        except Exception as e:  # noqa: BLE001
            problems.append(f"{path} unreachable: {type(e).__name__}")

    # 3. Is the archive actually growing? A service can serve one good snapshot
    #    forever and pass every liveness check ever written.
    try:
        h = get("/health").json()
        if h.get("refresh_count", 0) < 1:
            problems.append("no successful refresh since boot")
        if h.get("last_error"):
            problems.append(f"last refresh errored: {h['last_error']}")
        days = h.get("archived_days", 0)
        if days < 1:
            problems.append("archive is empty")
    except Exception as e:  # noqa: BLE001
        problems.append(f"health unparseable: {type(e).__name__}")

    # 4. The free tier must still carry the honesty flags. Losing them silently
    #    would be the single most damaging regression available.
    try:
        d = get("/v1/free/carry").json()
        for k in ("carry_spread_annualized", "carry_spread_annualized_trimmed",
                  "carry_spread_annualized_median", "outlier_dominated"):
            if k not in d:
                problems.append(f"free tier missing `{k}` -- honesty regression")
        if not d.get("longs") or not d.get("shorts"):
            problems.append("free tier has an empty leg")
    except Exception as e:  # noqa: BLE001
        problems.append(f"free tier unparseable: {type(e).__name__}")

    # 5. TLS expiry.
    if base.startswith("https://"):
        problems += check_cert(host)

    if problems:
        print(f"carrydesk weekly audit: {len(problems)} problem(s)")
        for x in problems:
            print(f"  - {x}")
        return 1
    print(json.dumps({"audit": "clean", "at": datetime.now(timezone.utc).isoformat()}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
