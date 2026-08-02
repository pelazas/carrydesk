# DECISIONS

Why things are the way they are. Append, don't rewrite — a reversed decision is
more useful with its original reasoning intact.

---

### D1. Sell the bot's intermediate output, not the bot

**Decision:** publish the cross-sectional funding-carry ranking; never offer
managed accounts, copy-trading, or discretionary advice.

**Why:** the ranking is a transform of public funding data, so selling it gives
away nothing proprietary and carries no custody, no fiduciary duty, and no
regulator. Managed money is a different business with a different legal surface.

**Consequence:** all published language is descriptive ("funding is X, this leg
ranks Y"), never directive ("buy X"). The `caveats` block in `/v1/method` is
part of the product, not boilerplate.

---

### D2. x402 over Stripe

**Decision:** charge per call in USDC via x402 rather than subscriptions.

**Why:** the goal is minimum human-in-the-loop. x402 removes account creation,
invoicing, KYC-per-customer, dunning, refunds, and chargebacks — the entire
support surface of a normal SaaS. It also makes the API callable by other agents
with no human present, which is the only distribution channel that could grow
while the owner sleeps.

**Cost accepted:** the buyer pool is smaller today than a card-paying pool. That
is a bet on direction, and the free tier + MCP hedge it.

---

### D3. Free tier withholds breadth and freshness, never quality

**Decision:** free = top-5 each leg, delayed 24h, with the same headline numbers
and the same honesty flags as paid.

**Why:** the free tier is the demo, the daily proof post, and the answer to every
Discord question. Crippling its *quality* would make it useless as all three. What
paid buys is the other ~28 coins, live timing, history, and parameter control.

---

### D4. Publish outlier-robust spread variants alongside the headline

**Decision:** always ship `carry_spread_annualized_trimmed`, `_median`, and
`outlier_dominated` — including in the free tier.

**Why:** on the first live run the headline read 39%/yr while the median read
9.6%/yr, because SAGA (+199%/yr) and CASHCAT (+95%/yr) dominated the short leg.
A buyer who sized into that on the headline alone would have been hurt, and would
have been right to blame us. The plain mean stays the headline because it is what
an equal-weighted book actually earns — but never alone.

**This is the product's main differentiator.** Anyone can compute a funding mean.
Publishing the number that makes you look worse is what makes the rest credible.

---

### D5. No LLM in the data, pricing, or payment path

**Decision:** agents may write content and triage support. Everything from
Hyperliquid to the USDC settlement is deterministic code.

**Why:** a model in the billing path is a liability with no upside. The failure
modes (hallucinated prices, non-deterministic gating) are exactly the ones that
lose money or trust.

---

### D6. Validation gate fails closed

**Decision:** a snapshot that fails validation raises; the previous good snapshot
keeps serving; `/health` reports the error.

**Why:** this service is meant to run unattended and publish automatically. An
unattended bot posting a wrong number at 3am costs more credibility than a missed
day costs attention. Serving slightly stale data is strictly better than serving
wrong data.

**Bands:** universe ≥ 2k coins, |spread| < 500%/yr, per-coin coverage ≥ 50%.

---

### D7. MCP is the primary distribution channel

**Decision:** build the MCP server in v1, not later.

**Why:** it distributes into an existing install base (Claude Code, Claude
Desktop, Cursor) instead of asking anyone to sign up. The install *is* the
onboarding, and traders who use Claude for research are precisely the buyer.
x402 makes payment invisible inside that flow.

---

### D8. The archive is append-only and starts as early as possible

**Decision:** every snapshot is written to `data/snapshots/YYYY-MM-DD.jsonl` and
never modified.

**Why:** the cold-start problem here is trust, and trust is bought with a
timestamped record that the ranking was published *in advance*. That record
cannot be backfilled or reconstructed — **every day not deployed is a day of
proof permanently lost.** This is why deployment ranks above every feature.

---

### D9. Mirror the trading bot's parameters, don't import its code

**Decision:** `config.py` restates `MIN_DAILY_VOLUME`, `MAX_UNIVERSE`,
`LOOKBACK_HOURS`, `K_PER_LEG`; carrydesk never imports from the trading repo.

**Why:** the selling point is that the published ranking is the one a real book
trades. But coupling the two repos would mean a bug here could reach a
real-money system, and a deploy there could silently change what customers get.
The values are documented in both places with a pointer; drift is a review item,
not a runtime dependency.

---

### D10. UGC/creator marketing was considered and rejected

**Decision:** distribution is MCP + founder-published proof + bot-builder
communities. No paid creator content.

**Why:** the buyer pool is tens of thousands of technical people globally, a JSON
API has no visual demo, and crypto UGC reliably attracts gamblers rather than
integrators — the worst customers available. Founder content has the same channel
and opposite economics: costs time not money, and self-selects the audience.

**Revisit if:** the product ever becomes consumer-facing (e.g. a no-code Telegram
bot). That is a different product, not a marketing change.

---

### D11. Every published number must be traceable. Nothing is ever invented.

**Decision:** any figure that appears on the site, in the API, or in a listing
must trace to either (a) live data carrydesk computed and archived, or (b) a
named document with the methodology attached. If a number cannot be traced, it
does not get published — regardless of who asks or how good it would look.

**Why:** the entire product is one claim — *our numbers are checkable*. The
archive, the git-mirrored timestamps, the median printed beside the mean, the
`outlier_dominated` flag: all of it exists to support that single claim. One
fabricated figure does not sit alongside those; it retroactively converts them
into marketing. And someone could size real money into it.

**This was tested on 2026-08-02**, when the owner asked for backtest results
"as if they were real" at gross 2.0. The answer was no — and the better answer
turned out to be publishing the *actual* 6.89-year backtest from
`systematic-trading/10-live/RESULTS.md`, which already contained gross 2.0
figures (+36% full sample, −37.7% max drawdown, Sharpe flat at 1.22 because
leverage scales return and drawdown identically) plus the justification that
quarter-Kelly lands at 2.05×.

**The general lesson:** when the honest version of a request looks weaker than
the invented one, that is usually a failure of research, not a real trade-off.
Here the real numbers were stronger, because they came with the caveats that
make a quant believe the rest.

**Consequences that follow from this:**

- Backtest figures on the page are labelled as simulated, for the *strategy*,
  not carrydesk's performance and not a live record.
- Out-of-sample leads; every return sits beside its drawdown.
- The "why you should discount it" section is not optional. Train→test
  degradation, the forty-parameter multiple-testing problem, 2021's outsized
  contribution and the Binance-vs-Hyperliquid mismatch all stay.
- If any figure in `web.py`'s `BACKTEST` block is edited, re-verify it against
  `RESULTS.md` first. Each one was checked before publishing.
