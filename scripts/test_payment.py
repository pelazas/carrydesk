#!/usr/bin/env python3
"""End-to-end x402 payment test: 402 -> pay -> retry -> data.

Proves the whole loop with real (testnet) USDC. Until this passes, the paywall
is only *theoretically* collecting money.

    # 1. make a throwaway buyer wallet
    python scripts/test_payment.py --new-wallet

    # 2. fund it with Base Sepolia USDC (see --new-wallet output for faucets)

    # 3. spend
    CARRYDESK_BUYER_KEY=0x... python scripts/test_payment.py \
        --url https://carry.pelazas.com --endpoint /v1/universe

No ETH needed. The `exact` scheme uses EIP-3009 transferWithAuthorization: the
buyer only signs, and the facilitator broadcasts and pays the gas. A wallet
holding nothing but USDC can still pay.

NEVER put a mainnet key in here. This is a throwaway buyer, not the receiving
wallet -- the receiving side (X402_PAY_TO) never needs a key at all.
"""
from __future__ import annotations

import argparse
import asyncio
import base64
import json
import os
import sys

import httpx

FAUCETS = [
    "https://faucet.circle.com  (select Base Sepolia, gives USDC)",
    "https://www.alchemy.com/faucets/base-sepolia  (ETH, only if you want gas)",
]


def new_wallet() -> int:
    from eth_account import Account

    acct = Account.create()
    # eth-account returns the hex without a 0x prefix; normalise so the line
    # below is directly copy-pasteable.
    key = acct.key.hex()
    key = key if key.startswith("0x") else f"0x{key}"
    print("Throwaway BUYER wallet (testnet only — never fund this on mainnet):\n")
    print(f"  address     {acct.address}")
    print(f"  private key {key}\n")
    print("Fund the address with Base Sepolia USDC:")
    for f in FAUCETS:
        print(f"  - {f}")
    print("\nThen:")
    print(f"  CARRYDESK_BUYER_KEY={key} \\")
    print("    python scripts/test_payment.py --url https://carry.pelazas.com")
    return 0


def decode_challenge(r: httpx.Response) -> dict | None:
    hdr = r.headers.get("payment-required")
    if not hdr:
        return None
    try:
        return json.loads(base64.b64decode(hdr + "=" * (-len(hdr) % 4)))
    except Exception:  # noqa: BLE001
        return None


async def run(url: str, endpoint: str, key: str) -> int:
    from eth_account import Account
    from x402.client import x402Client
    from x402.http.clients.httpx import wrapHttpxWithPayment
    from x402.mechanisms.evm import EthAccountSigner
    from x402.mechanisms.evm.exact import register_exact_evm_client

    base = url.rstrip("/")
    target = f"{base}{endpoint}"
    acct = Account.from_key(key)
    print(f"buyer   {acct.address}")
    print(f"target  {target}\n")

    # 1. unpaid request -- see what is being asked for
    async with httpx.AsyncClient(timeout=30) as plain:
        r = await plain.get(target)
    print(f"[1] unpaid request -> HTTP {r.status_code}")
    if r.status_code != 402:
        print(f"    expected 402. Body: {r.text[:300]}")
        if r.status_code == 200:
            print("    !! endpoint is NOT gated -- paid data served for free")
        return 1
    ch = decode_challenge(r)
    if not ch:
        print("    !! 402 with no payment-required header")
        return 1
    acc = ch["accepts"][0]
    print(f"    price   ${int(acc['amount']) / 1e6:.4f} USDC")
    print(f"    network {acc['network']}")
    print(f"    payTo   {acc['payTo']}\n")

    # 2. paid request -- x402 signs, facilitator settles, server serves
    client = x402Client()
    register_exact_evm_client(client, EthAccountSigner(acct))
    async with wrapHttpxWithPayment(client, timeout=90) as paid:
        try:
            r2 = await paid.get(target)
        except Exception as e:  # noqa: BLE001
            print(f"[2] paid request FAILED: {type(e).__name__}: {e}")
            print("    Most common cause: buyer wallet has no testnet USDC.")
            return 1

    print(f"[2] paid request -> HTTP {r2.status_code}")
    if r2.status_code != 200:
        if r2.status_code == 402:
            # Overwhelmingly the cause: the buyer signed fine but has no USDC,
            # so the facilitator refuses to settle and the server re-challenges.
            # A bare "402 {}" is useless to whoever is running this, so say it.
            print("    still 402 after paying -- the buyer wallet almost certainly")
            print(f"    holds no Base Sepolia USDC. Fund {acct.address} at:")
            for f in FAUCETS:
                print(f"      - {f}")
        else:
            print(f"    body: {r2.text[:400]}")
        return 1

    resp = r2.headers.get("payment-response")
    if resp:
        try:
            s = json.loads(base64.b64decode(resp + "=" * (-len(resp) % 4)))
            print(f"    settled  : {s.get('success')}")
            print(f"    tx       : {s.get('transaction')}")
            print(f"    payer    : {s.get('payer')}")
            if s.get("transaction"):
                print(f"    explorer : https://sepolia.basescan.org/tx/{s['transaction']}")
        except Exception:  # noqa: BLE001
            pass

    data = r2.json()
    keys = list(data)[:8]
    print(f"\n[3] data received: {len(json.dumps(data))} bytes, keys={keys}")
    print("\nPAYMENT LOOP VERIFIED END TO END.")
    return 0


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--new-wallet", action="store_true", help="generate a throwaway buyer")
    p.add_argument("--url", default="https://carry.pelazas.com")
    p.add_argument("--endpoint", default="/v1/universe", help="cheapest endpoint by default")
    args = p.parse_args()

    if args.new_wallet:
        return new_wallet()

    key = os.getenv("CARRYDESK_BUYER_KEY", "").strip()
    if not key:
        print("set CARRYDESK_BUYER_KEY, or run with --new-wallet first", file=sys.stderr)
        return 2
    return asyncio.run(run(args.url, args.endpoint, key))


if __name__ == "__main__":
    sys.exit(main())
