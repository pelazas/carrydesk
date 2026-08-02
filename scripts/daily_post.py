#!/usr/bin/env python3
"""Render the daily proof post from the free snapshot.

This is the funnel. One timestamped, never-deleted post per day showing what the
ranking said *in advance*. Six weeks of these is the only thing that makes anyone
trust the paid endpoints.

It renders; it does not publish. Publishing is a separate, deliberate step —
partly so the first couple of weeks can be human-approved to calibrate voice, and
partly because an unattended poster is one bad snapshot away from destroying the
credibility the archive exists to build.

    python scripts/daily_post.py --url http://127.0.0.1:8000            # preview
    python scripts/daily_post.py --url ... --format x                   # for X
    python scripts/daily_post.py --url ... --out posts/2026-08-02.md

Exit 1 means DO NOT POST: the gate rejected the snapshot.
"""
from __future__ import annotations

import argparse
import sys
from datetime import datetime, timezone

import httpx

MAX_STALE_HOURS = 36


def pct(x: float | None) -> str:
    return "n/a" if x is None else f"{100 * x:+.1f}%"


def gate(snap: dict) -> list[str]:
    """Reasons not to post. Empty list means it is safe to publish.

    Deliberately conservative: a skipped day costs a little attention, a wrong
    number costs the whole track record.
    """
    problems = []
    if not snap.get("longs") or not snap.get("shorts"):
        problems.append("snapshot has an empty leg")
    if snap.get("universe_size", 0) < 20:
        problems.append(f"universe only {snap.get('universe_size')} coins")
    spread = snap.get("carry_spread_annualized")
    if spread is None:
        problems.append("no carry spread in snapshot")
    elif abs(spread) > 5.0:
        problems.append(f"carry spread {pct(spread)} outside sane band")
    ts = snap.get("as_of_ts")
    if ts:
        age_h = (datetime.now(timezone.utc).timestamp() - ts) / 3600
        if age_h > MAX_STALE_HOURS:
            problems.append(f"snapshot is {age_h:.0f}h old")
    else:
        problems.append("snapshot has no timestamp")
    return problems


def render_markdown(snap: dict) -> str:
    day = snap["as_of"][:10]
    lines = [
        f"# Hyperliquid funding carry — {day}",
        "",
        f"Ranked {snap['universe_size']} liquid perps by trailing "
        f"{snap['method']['lookback_hours'] // 24}d mean funding.",
        "",
        "| | annualized |",
        "|---|---|",
        f"| carry spread (mean) | {pct(snap.get('carry_spread_annualized'))} |",
        f"| carry spread (trimmed) | {pct(snap.get('carry_spread_annualized_trimmed'))} |",
        f"| carry spread (median) | {pct(snap.get('carry_spread_annualized_median'))} |",
        "",
    ]
    if snap.get("outlier_dominated"):
        lines += [
            "> **Outlier-dominated today.** One or two illiquid names carry most "
            "of the headline spread. The median is the number to trust.",
            "",
        ]
    lines += ["**Long leg** — the market pays you to hold these:", ""]
    for r in snap["longs"]:
        lines.append(
            f"- `{r['coin']}` {pct(r['mean_funding_annualized'])} "
            f"(${r['day_notional_volume'] / 1e6:.1f}m/day)"
        )
    lines += ["", "**Short leg** — you get paid to short these:", ""]
    for r in snap["shorts"]:
        lines.append(
            f"- `{r['coin']}` {pct(r['mean_funding_annualized'])} "
            f"(${r['day_notional_volume'] / 1e6:.1f}m/day)"
        )
    lines += [
        "",
        "---",
        "",
        f"Delayed {snap.get('delay_hours', 0)}h. Gross of fees and slippage. "
        "A structural risk premium, not a prediction — it can go negative.",
        "Not investment advice.",
        "",
        "Live full ranking: `GET /v1/carry/rankings`",
    ]
    return "\n".join(lines)


def render_x(snap: dict) -> str:
    """Short form. Kept under ~280 chars; the detail lives in the linked page."""
    day = snap["as_of"][:10]
    longs = ", ".join(r["coin"] for r in snap["longs"][:3])
    shorts = ", ".join(r["coin"] for r in snap["shorts"][-3:])
    head = pct(snap.get("carry_spread_annualized"))
    med = pct(snap.get("carry_spread_annualized_median"))
    note = " (outlier-dominated)" if snap.get("outlier_dominated") else ""
    return (
        f"Hyperliquid funding carry — {day}\n\n"
        f"Spread: {head} mean / {med} median{note}\n\n"
        f"Paid to hold long: {longs}\n"
        f"Paid to short: {shorts}\n\n"
        f"{snap['universe_size']} perps ranked on 14d trailing funding. "
        f"Gross of costs. Not advice."
    )


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--url", default="http://127.0.0.1:8000")
    p.add_argument("--format", choices=["md", "x"], default="md")
    p.add_argument("--out", help="write to file instead of stdout")
    p.add_argument("--timeout", type=float, default=20.0)
    args = p.parse_args()

    try:
        r = httpx.get(f"{args.url.rstrip('/')}/v1/free/carry", timeout=args.timeout)
        r.raise_for_status()
        snap = r.json()
    except Exception as e:  # noqa: BLE001
        print(f"DO NOT POST: could not fetch snapshot ({type(e).__name__}: {e})",
              file=sys.stderr)
        return 1

    problems = gate(snap)
    if problems:
        print("DO NOT POST — gate rejected the snapshot:", file=sys.stderr)
        for x in problems:
            print(f"  - {x}", file=sys.stderr)
        return 1

    text = render_markdown(snap) if args.format == "md" else render_x(snap)
    if args.out:
        with open(args.out, "w") as fh:
            fh.write(text + "\n")
        print(f"wrote {args.out}", file=sys.stderr)
    else:
        print(text)
    return 0


if __name__ == "__main__":
    sys.exit(main())
