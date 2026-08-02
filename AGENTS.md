# AGENTS.md — context for an AI agent picking up carrydesk

Read this first. It tells you what this repo is, what state it is in, what is
verified vs. assumed, and what you are allowed to do without asking.

---

## 1. What this is

**carrydesk sells the intermediate output of an existing live trading bot as a
metered API, paid per call in USDC.**

The owner (`pelazas`) runs a real-money market-neutral funding-carry bot on
Hyperliquid (separate repo: `~/Desktop/systematic-trading`, deployed on the
droplet `the-server`). That bot computes, every cycle, a **cross-sectional ranking
of ~40 liquid Hyperliquid perps by trailing 14-day mean funding rate**, then goes
long the most-negative and short the most-positive, dollar-neutral.

That ranking is valuable on its own and is derived entirely from **public** data.
carrydesk publishes it:

| Surface | Audience | Payment |
|---|---|---|
| `/v1/free/*` — top-5 each leg, delayed 24h | the funnel | none |
| `/v1/carry/*` — full live ranking + history | devs, bots | x402, USDC per call |
| MCP server — same data as agent tools | Claude/Cursor users | same, transparent |

**The edge is not being sold.** Funding rates are public; the ranking is a
transform of public data; the strategy is a documented structural risk premium,
not a secret. What is sold is the computation, the archive, and the reliability.

---

## 2. Status (2026-08-02)

**Working and verified locally. Not deployed. No revenue. No wallet configured.**

| Piece | State |
|---|---|
| Hyperliquid data client | ✅ verified against live API (177 perps, 38 above the $1m/day floor) |
| Carry ranking maths | ✅ 14 unit tests pass |
| FastAPI service | ✅ all endpoints return real data |
| x402 paywall | ✅ verified: 402 challenges with correct USDC amounts on Base Sepolia |
| MCP server | ✅ verified end-to-end: 6 tools over stdio, real data |
| Deployment | ❌ not done |
| Mainnet payments | ❌ blocked on a receiving wallet + CDP keys |
| Content/proof feed | ❌ not built |
| Ops monitor | ❌ not built |

See `STATUS.md` for the current blocking items and `DECISIONS.md` for why things
are the way they are.

---

## 3. Run it

```bash
cd ~/Desktop/carrydesk
uv venv --python 3.12 && uv pip install -e ".[dev]"

# Fully open, no paywall (this is the dev default when X402_PAY_TO is unset)
.venv/bin/python -m uvicorn carrydesk.api:app --port 8000 --reload

# With the paywall on
X402_PAY_TO=0xYourAddress .venv/bin/python -m uvicorn carrydesk.api:app --port 8000

.venv/bin/python -m pytest -q          # 14 tests, no network needed
CARRYDESK_API_BASE=http://127.0.0.1:8000 .venv/bin/python -m carrydesk.mcp_server
```

First boot takes ~5s: it fetches 38 coins' worth of funding history before
serving. `/health` reports `has_snapshot: false` until that lands.

---

## 4. Code map

```
carrydesk/
  config.py      all knobs, env-overridable. Signal params mirror the trading bot.
  hl.py          Hyperliquid public REST client. Read-only, no credentials.
  carry.py       THE PRODUCT. Pure functions: ranking, leg assignment, spread maths.
  store.py       snapshot cache, validation gate, JSONL archive, delayed free view.
  api.py         FastAPI app + x402 paywall + paywall self-check.
  mcp_server.py  MCP tools over the HTTP API. Optional auto-payment.
tests/
  test_carry.py    ranking maths, no network
  test_paywall.py  regression guard for the paywall-bypass bug (see §6)
```

Data flows one way: `hl.py` → `carry.py` → `store.py` → (`api.py` | `mcp_server.py`).
`carry.py` never does I/O, which is why it is the only part with real test coverage.

---

## 5. Hard-won gotchas (each cost a debugging cycle — don't rediscover them)

1. **x402 networks are CAIP-2 ids, not friendly names.** `base-sepolia` fails
   route validation with `No scheme for "exact" on "base-sepolia"`. Use
   `eip155:84532` (Base Sepolia) or `eip155:8453` (Base mainnet). Verified
   against `https://x402.org/facilitator/supported`.

2. **The EVM `exact` scheme is not registered by default.** You must call
   `register_exact_evm_server(server)` or every protected route 500s on first
   request. `payment_middleware_from_config` does *not* do this for you.

3. **x402 route patterns use `[param]` / `:param` / `*`, NOT FastAPI's
   `{param}`.** This is the dangerous one — see §6.

4. **x402 v2 returns an empty JSON body on 402.** The payment requirements are
   base64 in the `payment-required` **header**. An empty `{}` body is correct,
   not a bug.

5. **The public facilitator (`x402.org/facilitator`) is testnet-only.** Base
   mainnet USDC needs a CDP-backed facilitator and Coinbase CDP API keys.

6. **Hyperliquid funding is hourly**, so annualized = rate × 24 × 365, and a
   14-day lookback is 336 points. Coins with <50% coverage are dropped.

---

## 6. The paywall-bypass bug — read before touching `api.py`

Writing a route key as `"GET /v1/carry/history/{coin}"` (FastAPI style) makes
x402 `re.escape` it to `^/v1/carry/history/\{coin\}$`, which **never matches a
real request**. The endpoint then returns **200 and serves paid data for free**,
with nothing in the logs and no error anywhere.

This shipped and was caught only because the endpoint was manually curl'd.

Two guards now exist and **must not be removed**:

- `_assert_routes_match()` in `api.py` — the service **refuses to boot** if any
  paid route's pattern fails to match its own sample URL.
- `tests/test_paywall.py` — the same assertion in CI, plus a test that the guard
  itself fails on a deliberately broken pattern.

If you add a paid route, you must add it to `PAYWALL_SELF_CHECK` in `api.py`.
The self-check fails closed on any route without a sample.

---

## 7. Rules for an agent working on this

1. **Never put an LLM in the data path, the pricing path, or the payment path.**
   Those are deterministic on purpose. Agents belong in content and support only.
2. **Never weaken the validation gate** in `store.py`. Publishing a wrong number
   unattended is worse than publishing nothing — a bad snapshot must raise and
   let the previous good one keep serving.
3. **Never commit `.env`, a private key, or a wallet seed.** `CARRYDESK_PRIVATE_KEY`
   is for the MCP *client* to spend from; it is a hot wallet and should hold only
   small amounts.
4. **Do not touch `~/Desktop/systematic-trading`** unless asked. That repo trades
   real money. carrydesk only *mirrors* its signal parameters; it does not import
   from it and must not connect to the bot's wallet.
5. **The archive is append-only.** `data/snapshots/*.jsonl` is the track record.
   Rewriting history destroys the only thing that makes the product credible.
6. **Be honest in published numbers.** The headline carry spread is routinely
   dominated by one or two illiquid coins; that is why `carry_spread_annualized_trimmed`
   and `outlier_dominated` exist and are shown in the free tier too. Do not
   quietly drop them to make the number look better.

---

## 8. What is NOT verified

Stated plainly so nobody builds on sand:

- **No mainnet payment has ever settled.** The paywall is verified on Base
  Sepolia with a dummy `payTo`. Real USDC settlement is untested.
- **No deployment exists.** Nothing has run longer than a few minutes.
- **The archive is one day old at most**, so `/v1/carry/history/*` is nearly
  empty and the free tier falls back to live data until 24h of snapshots exist.
- **`api.carrydesk.xyz` is a placeholder.** No domain is registered.
- **Backtest numbers are not republished here.** The Sharpe ~1.0 / ~15%/yr
  figures live in the trading repo's `RESULTS.md` and describe the *strategy*,
  not this API's uptime or data quality.
