#!/usr/bin/env python3
"""What has actually been paid, read from Base rather than from a doc.

Two reasons this exists.

**A settlement count in a markdown file decays the moment another call lands.**
`AGENTS.md` said "two settlements confirmed on-chain" while the true number was
four; it had been correct when written that morning. Any number an agent has to
remember to update is a number that will eventually be wrong, and the next agent
has no way to tell whether it is reading a fact or a fossil. So the doc now says
"run this script" and the number lives where it cannot go stale.

**The receiving balance looks like traction and is not.** Every payment so far
came from our own test wallet. An agent -- or a human -- glancing at $0.16 in
the receiving address could reasonably read it as demand, and would then make
distribution decisions on the basis of customers who do not exist. The headline
number here is therefore *distinct payers*, not dollars, and self-payments are
labelled when `CARRYDESK_SELF_PAYERS` names them.

    python scripts/revenue.py                 # last ~50h
    python scripts/revenue.py --hours 720     # last 30 days
    python scripts/revenue.py --json

Exit 0 always: this reports, it does not gate. `scripts/ops_check.py` is the
thing that decides whether something is broken.
"""
from __future__ import annotations

import argparse
import json
import os
import sys

import httpx

BASE_RPC = os.environ.get("BASE_RPC_URL", "https://mainnet.base.org")
USDC = "0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913"  # Circle USDC on Base
TRANSFER = "0xddf252ad1be2c89b69c2b068fc378daa952ba7f163c4a11628f55a4df523b3ef"

# The public RPC rejects wide eth_getLogs ranges, so the scan is paged. Base
# produces a block every ~2s.
LOG_SPAN = 9_000
BLOCKS_PER_HOUR = 1_800

# Price -> endpoint, so the report says what was bought and not just how much.
# Kept in sync by tests/test_docs_match_reality.py, which reads config.
PRICE_ENDPOINT = {
    "0.05": "/v1/carry/rankings",
    "0.02": "/v1/carry/history/{coin}",
    "0.01": "/v1/universe",
}


def rpc(method: str, params: list) -> object:
    """JSON-RPC that raises on error rather than returning an empty result.

    The first version of this scan did `r.get("result") or []` and printed
    "0 settlements" for an address holding real USDC -- the RPC had rejected the
    block range and the error was discarded. A revenue report that fails silently
    to zero is worse than one that crashes.
    """
    r = httpx.post(
        BASE_RPC,
        json={"jsonrpc": "2.0", "id": 1, "method": method, "params": params},
        timeout=45,
    )
    r.raise_for_status()
    body = r.json()
    if "error" in body:
        raise RuntimeError(f"{method}: {body['error']}")
    return body["result"]


def topic_addr(addr: str) -> str:
    return "0x" + "0" * 24 + addr[2:].lower()


def settlements(receiver: str, hours: int) -> list[dict]:
    head = int(rpc("eth_blockNumber", []), 16)
    start = max(0, head - hours * BLOCKS_PER_HOUR)
    out = []
    for lo in range(start, head + 1, LOG_SPAN):
        logs = rpc(
            "eth_getLogs",
            [
                {
                    "address": USDC,
                    "topics": [TRANSFER, None, topic_addr(receiver)],
                    "fromBlock": hex(lo),
                    "toBlock": hex(min(lo + LOG_SPAN - 1, head)),
                }
            ],
        )
        for lg in logs:
            out.append(
                {
                    "usdc": int(lg["data"], 16) / 1e6,
                    "payer": "0x" + lg["topics"][1][-40:],
                    "block": int(lg["blockNumber"], 16),
                    "tx": lg["transactionHash"],
                }
            )
    out.sort(key=lambda r: r["block"])
    return out


def report(rows: list[dict], self_payers: set[str]) -> dict:
    payers: dict[str, dict] = {}
    for r in rows:
        p = payers.setdefault(r["payer"], {"calls": 0, "usdc": 0.0})
        p["calls"] += 1
        p["usdc"] += r["usdc"]
    external = {a: v for a, v in payers.items() if a not in self_payers}
    by_endpoint: dict[str, int] = {}
    for r in rows:
        ep = PRICE_ENDPOINT.get(f"{r['usdc']:.2f}", f"${r['usdc']:.2f} (unknown price)")
        by_endpoint[ep] = by_endpoint.get(ep, 0) + 1
    return {
        "settlements": len(rows),
        "gross_usdc": round(sum(r["usdc"] for r in rows), 6),
        "distinct_payers": len(payers),
        "external_payers": len(external),
        "external_usdc": round(sum(v["usdc"] for v in external.values()), 6),
        "by_endpoint": by_endpoint,
        "payers": {
            a: {**v, "self": a in self_payers, "usdc": round(v["usdc"], 6)}
            for a, v in sorted(payers.items(), key=lambda kv: -kv[1]["usdc"])
        },
    }


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument(
        "--receiver",
        default=os.environ.get("X402_PAY_TO", "0x56d487318fB8570DB7C928dbD038c22aB53AAB91"),
    )
    p.add_argument("--hours", type=int, default=50)
    p.add_argument("--json", action="store_true")
    args = p.parse_args()

    self_payers = {
        a.strip().lower()
        for a in os.environ.get("CARRYDESK_SELF_PAYERS", "").split(",")
        if a.strip()
    }

    try:
        rows = settlements(args.receiver, args.hours)
    except Exception as e:  # noqa: BLE001
        print(f"could not read Base: {type(e).__name__}: {e}", file=sys.stderr)
        return 1

    rep = report(rows, self_payers)
    if args.json:
        print(json.dumps(rep, indent=2))
        return 0

    print(f"receiver {args.receiver}   last {args.hours}h\n")
    print(f"  settlements     {rep['settlements']}")
    print(f"  gross           ${rep['gross_usdc']:.2f} USDC")
    print(f"  distinct payers {rep['distinct_payers']}")
    if self_payers:
        print(f"  external payers {rep['external_payers']}  (${rep['external_usdc']:.2f})")
    else:
        print("  external payers unknown -- set CARRYDESK_SELF_PAYERS to attribute")
    if rep["by_endpoint"]:
        print("\n  bought:")
        for ep, n in sorted(rep["by_endpoint"].items(), key=lambda kv: -kv[1]):
            print(f"    {n:>3}x  {ep}")
    if rep["payers"]:
        print("\n  payers:")
        for a, v in rep["payers"].items():
            tag = "  (self-test)" if v["self"] else ""
            print(f"    {a}  {v['calls']:>3} calls  ${v['usdc']:.2f}{tag}")
    if rep["external_payers"] == 0 and self_payers:
        print("\n  NO EXTERNAL REVENUE YET. Every payment above is our own test")
        print("  wallet. The receiving balance is not traction.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
