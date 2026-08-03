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
        mult = snap.get("headline_vs_typical")
        mult_txt = f"about {mult:.1f}x" if mult else "several times"
        # NOT "today" -- this fires on nearly every reading, so implying it is
        # today's exception would misrepresent how the market normally looks.
        lines += [
            f"> **The headline overstates a typical coin by {mult_txt}.** One or two "
            "illiquid names carry most of it. That is the usual state of this "
            "market, not today's exception. **The median is the number to trust.**",
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
    delay = snap.get("delay_hours") or 0
    freshness = f"Delayed {delay}h." if delay else "Live reading."
    lines += [
        "",
        "---",
        "",
        f"{freshness} Gross of fees and slippage. "
        "A structural risk premium, not a prediction — it can go negative.",
        "Not investment advice.",
        "",
        # The exact snapshot, not just the date. A day holds ~24 snapshots and
        # the free tier serves whichever is newest past the delay, so "the post
        # for 2026-08-02" is not one number -- rendered at 11:51 it said +44.6%,
        # and three hours later the same date rendered +49.3%. Citing the
        # timestamp makes the claim checkable against exactly one immutable line
        # in the archive, which is the whole point of publishing in advance.
        f"Snapshot `{snap['as_of']}` (`as_of_ts` {snap['as_of_ts']}) — verifiable "
        f"in <https://carry.pelazas.com/archive> and in "
        f"`data/snapshots/{snap['as_of'][:10]}.jsonl`.",
        "",
        "Live full ranking: `GET /v1/carry/rankings`",
    ]
    return "\n".join(lines)


X_LIMIT = 280


def render_x(snap: dict) -> str:
    """Short form, guaranteed to fit `X_LIMIT`.

    The coin lists are the only elastic part, so they shrink first. This is not
    hypothetical: three real tickers per leg (FARTCOIN, CASHCAT and friends)
    already pushed a naive three-and-three layout past 280, and a post that
    silently overruns is one that cannot be published at all.

    Order of sacrifice: coins first (down to one a side), then the coin lines
    entirely. The spread numbers and the disclaimer never go -- they are the
    reason the post exists.
    """
    day = snap["as_of"][:10]
    head = pct(snap.get("carry_spread_annualized"))
    med = pct(snap.get("carry_spread_annualized_median"))
    mult = snap.get("headline_vs_typical")
    note = (
        f" — headline overstates the typical coin {mult:.1f}x"
        if (snap.get("outlier_dominated") and mult)
        else ""
    )
    longs = [r["coin"] for r in snap.get("longs", [])]
    shorts = [r["coin"] for r in snap.get("shorts", [])][::-1]  # biggest payer first

    def build(n: int) -> str:
        coins = ""
        if n:
            coins = (
                f"Paid to hold long: {', '.join(longs[:n])}\n"
                f"Paid to short: {', '.join(shorts[:n])}\n\n"
            )
        return (
            f"Hyperliquid funding carry — {day}\n\n"
            f"Spread: {head} mean / {med} median{note}\n\n"
            f"{coins}"
            f"{snap.get('universe_size', 0)} perps ranked on 14d trailing funding. "
            f"Gross of costs. Not advice."
        )

    for n in (3, 2, 1, 0):
        text = build(n)
        if len(text) <= X_LIMIT:
            return text
    return build(0)


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--url", default="http://127.0.0.1:8000")
    p.add_argument("--format", choices=["md", "x"], default="md")
    p.add_argument("--out", help="write to this exact file instead of stdout")
    p.add_argument(
        "--out-dir",
        help=(
            "write to <dir>/<snapshot date>.md. Prefer this over --out for cron: "
            "the free tier is delayed, so today's run describes yesterday's data, "
            "and naming the file from the clock files a post under a date it is "
            "not about -- eventually two files with the same title."
        ),
    )
    p.add_argument(
        "--force",
        action="store_true",
        help="overwrite an existing post. Only correct if the existing one was "
        "never published anywhere.",
    )
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
    out = args.out
    if args.out_dir:
        # Name it for the data it contains, which also makes reruns idempotent
        # rather than accumulating near-duplicates.
        import os

        os.makedirs(args.out_dir, exist_ok=True)
        ext = "md" if args.format == "md" else "txt"
        out = os.path.join(args.out_dir, f"{snap['as_of'][:10]}.{ext}")
        # Write-once. A day holds ~24 snapshots and the free tier serves
        # whichever is newest past the delay, so a rerun files *different*
        # numbers under the same date -- the first version of this script would
        # have quietly overwritten a published post with a later reading. A
        # track record that can be edited after the fact proves nothing, which
        # is the same reason the snapshot archive is append-only.
        if os.path.exists(out) and not args.force:
            print(f"{out} already exists -- not overwriting a published post "
                  f"(pass --force if you are certain)", file=sys.stderr)
            return 0
    if out:
        with open(out, "w") as fh:
            fh.write(text + "\n")
        print(f"wrote {out}", file=sys.stderr)
    else:
        print(text)
    return 0


if __name__ == "__main__":
    sys.exit(main())
