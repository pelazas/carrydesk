# STATUS

Updated every working session. Newest first. If you are an agent picking this up,
this file plus `AGENTS.md` is the whole picture.

---

## 2026-08-02 — iteration 1: core built and verified locally

**Built and verified**

- Hyperliquid public REST client (`hl.py`). Live check: 177 perps, 38 above the
  $1m/day floor, 38 funding series fetched concurrently in ~2.4s.
- Carry ranking (`carry.py`) mirroring the live bot's `signal.py`. 14 unit tests.
- Snapshot store with a validation gate and append-only JSONL archive (`store.py`).
- FastAPI service (`api.py`): 3 free endpoints, 3 paid.
- x402 paywall verified on Base Sepolia — 402 challenges carry the correct USDC
  amounts ($0.05 / $0.02 / $0.01) against the real USDC asset address.
- MCP server (`mcp_server.py`) verified end-to-end over stdio: 6 tools, live data.

**Bugs found and fixed this iteration**

1. **Paywall bypass** — `/v1/carry/history/{coin}` used FastAPI brace syntax,
   which x402 escapes literally, so the route never matched and served paid data
   for free (HTTP 200). Fixed to `[coin]`; added a boot-time self-check that
   fails closed, plus `tests/test_paywall.py`.
2. **`No scheme for "exact"`** — x402 needs CAIP-2 network ids *and* explicit
   `register_exact_evm_server()`. Both fixed and documented.
3. **`/v1/universe` sorted by funding rank** instead of liquidity, despite being
   the liquidity endpoint. Now sorted by volume with `carry_rank` alongside.

**Data-quality finding worth acting on**

The headline carry spread is routinely dominated by one or two illiquid names —
on 2026-08-02 the live reading was **39%/yr headline vs 22%/yr trimmed vs
9.6%/yr median**, with SAGA at +199%/yr and CASHCAT at +95%/yr carrying most of
it. Publishing the headline alone would be misleading and would burn credibility
the first time a buyer sized into SAGA. Added `carry_spread_annualized_trimmed`,
`carry_spread_annualized_median` and an `outlier_dominated` flag, all exposed in
the **free** tier as well as paid.

---

## Blocked on the owner

| # | Need | Why | Unblocks |
|---|---|---|---|
| 1 | A receiving wallet address (Base) | `X402_PAY_TO`; without it the API runs fully open | any revenue |
| 2 | Decision: testnet first, or straight to mainnet | mainnet needs Coinbase CDP API keys; the public facilitator is testnet-only | real USDC settlement |
| 3 | Where to deploy | existing `the-server` droplet vs. a new box | public URL, uptime, archive accumulation |
| 4 | A domain | `api.carrydesk.xyz` is a placeholder in `mcp_server.py` | MCP install instructions, listings |
| 5 | OK to publish the ranking the live bot trades | capacity/crowding call — at ~$300 book size it is almost certainly fine, but it is the owner's call | going public at all |

---

## Next up (in order)

1. Deploy somewhere with a stable URL so the archive starts accumulating. The
   track record cannot be backfilled — every day not deployed is a day of proof
   permanently lost. **This is the single highest-value action.**
2. Ops monitor: page on stale data, failed refresh, or a snapshot that trips the
   validation gate.
3. Content agent: one automated daily post of the free snapshot, behind the same
   validation gate, human-approved for the first ~2 weeks.
4. Mainnet payments once 1–4 above are answered.
5. Passive listings (x402 bazaar, RapidAPI) — cheap, one-time, low volume.

---

## Deliberately not built yet

- **`POST /v1/backtest`** (the $5–20 tier). Needs sandboxing before it can accept
  user-supplied strategy code. Not worth the attack surface until the cheap
  endpoints prove demand.
- **Cross-venue funding** (Binance, Bybit). The trading repo already has Binance
  collectors, so this is the natural second product — but one venue done well
  beats two done badly, and the archive is the moat either way.
- **Agent-to-agent discovery.** Real infrastructure, negligible volume today.
