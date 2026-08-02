# AGENTS.md — context for an AI agent picking up carrydesk

Read this first. It tells you what this repo is, what state it is in, what is
verified vs. assumed, and what you may do without asking.

---

## 1. What this is

**carrydesk publishes a cross-sectional funding-carry ranking for Hyperliquid
perpetuals and sells it per call in USDC.**

Every rebalance, rank the liquid Hyperliquid perp universe by trailing 14-day
mean funding. The most negative names pay you to hold them long; the most
positive pay you to short them. The spread between the two legs is the carry —
a structural risk premium, not a prediction.

The same signal is traded by a live market-neutral book, which is why the
parameters are what they are. That book is a separate, private project; this
repo neither imports from it nor connects to it.

| Surface | Audience | Payment |
|---|---|---|
| `/v1/free/*` — top-5 each leg, delayed 24h | the funnel | none |
| `/v1/carry/*` — full live ranking + history | devs, bots | x402, USDC per call |
| MCP server — the same data as agent tools | Claude/Cursor users | same, transparent |

**No edge is being sold.** Funding rates are public, the ranking is a transform
of public data, and the strategy is a documented premium. What is sold is the
computation, the archive, and the reliability.

---

## 2. Status

**Live on Base mainnet, settling real USDC. Distribution barely started.**

| Piece | State |
|---|---|
| Hyperliquid data client | ✅ verified live (177 perps, ~38 above the $1m/day floor) |
| Carry ranking maths | ✅ 14 unit tests |
| FastAPI service | ✅ deployed, HTTPS, real data |
| x402 paywall | ✅ **real USDC settled on Base mainnet** |
| MCP server | ✅ 6 tools, verified against production, paid path works |
| Ops monitor | ✅ every 10 min → Telegram, verified with a real alert |
| Snapshot archive | ✅ append-only, auto-committed daily |
| Mainnet payments | ✅ live, two settlements confirmed on-chain |
| Discovery surfaces | ✅ llms.txt, robots.txt, sitemap, JSON-LD, /archive |
| Distribution | ⚠️ passive only — nothing posted or listed by a human |

`STATUS.md` has the running log; `DECISIONS.md` has the reasoning.

---

## 3. Run it

```bash
uv venv --python 3.12 && uv pip install -e ".[dev]"

# Fully open, no paywall — the dev default when X402_PAY_TO is unset
.venv/bin/python -m uvicorn carrydesk.api:app --port 8000 --reload

# With the paywall on
X402_PAY_TO=0xYourAddress .venv/bin/python -m uvicorn carrydesk.api:app --port 8000

.venv/bin/python -m pytest -q          # 14 tests, no network needed
CARRYDESK_API_BASE=http://127.0.0.1:8000 .venv/bin/python -m carrydesk.mcp_server

# what a stranger runs (no clone):
# claude mcp add carrydesk -- uvx --from git+https://github.com/pelazas/carrydesk carrydesk-mcp
```

First boot takes a few seconds: it fetches the whole universe's funding history
before serving. `/health` reports `has_snapshot: false` until that lands.

Host-specific deployment values live in `.env` on the server and are
deliberately not in this repo. See `deploy/DEPLOY.md`.

---

## 4. Code map

```
carrydesk/
  config.py      all knobs, env-overridable
  hl.py          Hyperliquid public REST client. Read-only, no credentials.
  carry.py       THE PRODUCT. Pure functions: ranking, legs, spread maths.
  store.py       snapshot cache, validation gate, JSONL archive, delayed view
  api.py         FastAPI app + x402 paywall + paywall self-check
  mcp_server.py  MCP tools over the HTTP API. Optional auto-payment.
  discovery.py   llms.txt / robots.txt / sitemap / JSON-LD, all from config
  web.py         the public page and the archive page
scripts/
  ops_check.py     health probe, exit 0/1/2
  weekly_audit.py  slower checks: cert expiry, archive growth, honesty flags
  daily_post.py    renders the proof post; does NOT publish
  test_payment.py  end-to-end 402 -> pay -> data
tests/
  test_carry.py    ranking maths, no network
  test_paywall.py  regression guard for the paywall-bypass bug (§6)
```

Data flows one way: `hl.py` → `carry.py` → `store.py` → (`api.py` | `mcp_server.py`).
`carry.py` never does I/O, which is why it carries the real test coverage.

---

## 5. Hard-won gotchas — don't rediscover these

1. **x402 networks are CAIP-2 ids, not friendly names.** `base-sepolia` fails
   route validation with `No scheme for "exact" on "base-sepolia"`. Use
   `eip155:84532` (Base Sepolia) or `eip155:8453` (Base mainnet).
2. **The EVM `exact` scheme is not registered by default.** Call
   `register_exact_evm_server(server)` or every protected route 500s on first
   request. `payment_middleware_from_config` does *not* do it for you.
3. **x402 route patterns use `[param]` / `:param` / `*`, NOT FastAPI's
   `{param}`.** The dangerous one — see §6.
4. **x402 v2 returns an empty JSON body on 402.** The requirements are base64
   in the `payment-required` **header**. An empty `{}` body is correct.
5. **The public facilitator is testnet-only** and supports exactly one EVM
   network, `eip155:84532`. Mainnet needs a CDP-backed facilitator + API keys.
6. **Buyers need no ETH.** The `exact` scheme uses EIP-3009
   `transferWithAuthorization`: the buyer signs, the facilitator broadcasts and
   pays gas. Verified — our test buyer holds zero native currency.
7. **Circle's faucet remembers the last network you chose.** A correct Base
   Sepolia drip appears on `sepolia.basescan.org`, not `sepolia.etherscan.io`.
8. **Hyperliquid funding is hourly**: annualized = rate × 24 × 365, and a
   14-day lookback is 336 points. Coins under 50% coverage are dropped.
9. **macOS has no `timeout`**, so `timeout N bash -c '… /dev/tcp/…'` port probes
   report everything as filtered whether or not it is. Use `curl --max-time`.

Deployment/TLS gotchas live in `deploy/DEPLOY.md` §4.

---

## 6. The paywall-bypass bug — read before touching `api.py`

Writing a route key as `"GET /v1/carry/history/{coin}"` (FastAPI style) makes
x402 `re.escape` it to `^/v1/carry/history/\{coin\}$`, which **never matches a
real request**. The endpoint then returns **200 and serves paid data for free**,
with nothing in the logs and no error anywhere.

This shipped, and was caught only because the endpoint was manually curl'd.

Two guards now exist and **must not be removed**:

- `_assert_routes_match()` in `api.py` — the service **refuses to boot** if any
  paid route's pattern fails to match its own sample URL.
- `tests/test_paywall.py` — the same assertion in CI, plus a test that the guard
  itself fails on a deliberately broken pattern.

Adding a paid route means adding it to `PAYWALL_SELF_CHECK` in `api.py`. The
check fails closed on any route without a sample.

---

## 7. Rules for an agent working on this

1. **Never put an LLM in the data path, the pricing path, or the payment path.**
   Those are deterministic on purpose. Agents belong in content and support.
2. **Never weaken the validation gate** in `store.py`. A bad snapshot must raise
   and let the previous good one keep serving. Publishing a wrong number
   unattended costs more than publishing nothing.
3. **Never commit `.env`, a private key, or a seed phrase.**
   `CARRYDESK_PRIVATE_KEY` is a *client-side* hot wallet for spending; it should
   hold small amounts. `X402_PAY_TO` is receive-only and needs no key at all.
4. **The archive is append-only.** `data/snapshots/*.jsonl` is the track record
   and cannot be backfilled. Rewriting it destroys the only thing that makes the
   product credible.
5. **Be honest in published numbers.** The headline spread is routinely
   dominated by one or two illiquid coins — that is why
   `carry_spread_annualized_trimmed`, `_median` and `outlier_dominated` exist
   and appear in the free tier too. Do not quietly drop them to look better.
6. **Keep host specifics out of this repo.** It is public. Server addresses,
   chat ids, key paths and secret file locations belong in `.env` on the box.

---

## 8. What is NOT verified

Stated plainly so nobody builds on sand:

- **Nobody outside has ever bought this.** All payments so far were our own.
- **Not indexed in CDP's bazaar yet** despite the extension being registered.
- **No distribution has happened.** Nothing is listed or published anywhere.
- **The archive is days old at most**, so `/v1/carry/history/*` is thin and the
  free tier falls back to live data until 24h of snapshots exist.
- **Uptime is unproven.** The service has not run long enough to have a record.
- **Strategy backtest numbers are not republished here.** They describe the
  strategy, not this API's data quality or availability.

---

## 9. Going to Base mainnet

One env var. `X402_NETWORK=eip155:8453` switches the facilitator to CDP
automatically; `CDP_API_KEY_ID` / `CDP_API_KEY_SECRET` come from
<https://cdp.coinbase.com> → project → API keys.

The service **refuses to start** on mainnet without those keys rather than
serving payment challenges it cannot settle. Verified: testnet path unchanged
and unauthenticated; mainnet without keys raises at startup; mainnet with keys
mints a signed EdDSA JWT per facilitator endpoint (verify / settle / supported /
bazaar), since the JWTs are short-lived and cannot be cached.

Not yet verified: an actual mainnet settlement. Nobody has run one.
