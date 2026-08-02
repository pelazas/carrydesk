# carrydesk

**Cross-sectional funding-carry rankings for Hyperliquid perpetuals, sold per call in USDC.**

Every hour, rank the liquid Hyperliquid perp universe by trailing 14-day mean
funding. The most negative names pay you to hold them long; the most positive pay
you to short them. The spread between those two legs is the carry — a structural
risk premium, not a prediction.

This is the same signal a live market-neutral book trades, published as an API.

---

## Endpoints

| | Endpoint | Price |
|---|---|---|
| free | `GET /v1/free/carry` — top 5 each leg, delayed 24h | — |
| free | `GET /v1/method` — how it is computed, and the caveats | — |
| free | `GET /health` | — |
| paid | `GET /v1/carry/rankings` — full live ranking, tunable `k` | $0.05 |
| paid | `GET /v1/carry/history/{coin}` — archived rank + funding | $0.02 |
| paid | `GET /v1/universe` — liquid perps by volume, OI, funding | $0.01 |

Paid endpoints are metered with [x402](https://x402.org): the server answers
`402` with payment requirements, your client pays USDC on Base, retries, and gets
the data. No account, no API key, no invoice.

---

## Quick start

```bash
curl -s https://carry.pelazas.com/v1/free/carry | jq
```

```json
{
  "carry_spread_annualized": 0.3901,
  "carry_spread_annualized_trimmed": 0.2231,
  "carry_spread_annualized_median": 0.0955,
  "outlier_dominated": false,
  "longs":  [{"coin": "PENGU", "mean_funding_annualized": -0.0636}, ...],
  "shorts": [{"coin": "SAGA",  "mean_funding_annualized":  1.9886}, ...]
}
```

Three spread numbers, always. The headline mean is what an equal-weighted book
earns; the trimmed and median readings tell you whether one illiquid name is
carrying it. On the reading above, SAGA alone accounts for most of the gap — that
is exactly the kind of thing a single number would hide.

---

## MCP

```bash
claude mcp add carrydesk -- uvx --from git+https://github.com/pelazas/carrydesk carrydesk-mcp
```

No clone, no virtualenv — `uvx` fetches and runs it.

Six tools: `carry_snapshot`, `carry_method`, `carry_health` (free) and
`carry_rankings`, `carry_history`, `carry_universe` (paid). It talks to
`https://carry.pelazas.com` by default — override with `CARRYDESK_API_BASE`.

Set `CARRYDESK_PRIVATE_KEY` to let the agent pay automatically. Without it the
free tools work and paid tools return the price instead of failing, so a
wallet-less install is still useful.

---

## Local development

```bash
uv venv --python 3.12 && uv pip install -e ".[dev]"
.venv/bin/python -m uvicorn carrydesk.api:app --reload   # open, no paywall
.venv/bin/python -m pytest -q                            # 14 tests, no network
```

With `X402_PAY_TO` unset the service runs fully open — that is the dev default.
Set it to turn the paywall on. See `.env.example`.

---

## For agents and crawlers

`/llms.txt` describes the whole service in plain text. `/openapi.json` is the
full spec, `/archive` is every snapshot ever published, and the public page
carries schema.org `Dataset` markup. Crawlers are explicitly welcome — the free
tier exists to be read, indexed and quoted.

## Honest limitations

- The carry spread **can and does go negative**. This is compensation for
  absorbing crowded leverage, not a forecast.
- All figures are **gross of fees, slippage and borrow**. Taker fees alone can
  erase the edge; the reference book is maker-only for that reason.
- Funding is **Hyperliquid's own**, with no cross-venue reconciliation yet.
- Illiquid names dominate the headline spread more often than not. Read the
  trimmed and median variants before sizing anything.
- **Informational only. Not investment advice.**

---

## Repo docs

| File | What |
|---|---|
| `BACKLOG.md` | Deliberately deferred work, with the reason for each |
| `AGENTS.md` | Onboarding for an AI agent picking this up cold — gotchas, rules, what is unverified |
| `STATUS.md` | Current state, what is blocked, what is next |
| `DECISIONS.md` | Why each significant choice was made |
