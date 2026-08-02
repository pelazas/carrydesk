# BACKLOG

Things deliberately deferred, with enough context to pick up cold. Not a wish
list — everything here has been considered and postponed for a stated reason.

---

## Submit to curated lists (needs owner's yes)

**Status: approved in principle, deferred. Owner said "maybe we can do that
later" on 2026-08-02.**

PRs to public lists where the service would be discovered:

- `awesome-mcp-servers` and the official MCP servers registry — carrydesk is an
  installable MCP server, which is the strongest channel available
- x402 ecosystem lists — a live, paying x402 resource is still rare enough to be
  interesting on its own
- Hyperliquid tooling lists — smallest audience, highest intent

**Why it needs a human yes rather than just doing it:** these PRs appear under
the owner's GitHub identity in other people's repositories, and a maintainer's
first impression of them is worth a deliberate decision. Mechanically it is a
few minutes of work.

**Do it when:** the archive has a few weeks of history. A listing that leads to
20 snapshots converts worse than one that leads to 500, and you only get one
first impression per list.

---

## Post the daily snapshot publicly (needs the owner personally)

`scripts/daily_post.py` renders a gated post in markdown and short form. Nothing
publishes it. This is the highest-leverage remaining action and it cannot be
delegated: the whole pitch is that a person who actually runs the book publishes
what it trades. An automated account posting the same numbers reads as
automated within about three posts.

---

## `POST /v1/backtest` — the $5–20 tier

Accept a strategy in natural language, run it against the archive, return a
report. Highest revenue per call by an order of magnitude.

**Blocked on:** sandboxing. It means executing user-supplied strategy logic, and
the current box also runs a real-money trading bot. Not worth the attack surface
until the cheap endpoints demonstrate that anyone wants this at all.

---

## Cross-venue funding (Binance, Bybit)

The natural second product: the same carry ranking computed across venues, plus
the basis between them. Collectors for Binance funding already exist in the
owner's separate trading repo.

**Deferred because:** one venue done well beats two done badly, and the archive
is the moat either way. Adding a venue restarts the archive's credibility clock
for the new data.

---

## Rotate the CDP API key

The current key was pasted into a chat transcript. Nothing is publicly exposed
and the key only authorizes facilitator calls — it cannot move funds — but
rotating it at <https://portal.cdp.coinbase.com/api-keys/secret> is good
hygiene. Two-minute swap in the server's `.env`.

---

## Bazaar indexing

The discovery extension is registered and mainnet payments have settled, but
carrydesk does not appear in CDP's index (14,820 resources; not in the first
3,000). Their `/discovery/search` returns 0 hits even for resources visibly
present in the listing, so it is not a usable signal.

**Next step if it stays absent:** work out whether CDP requires an explicit
declaration call rather than inferring resources from settled payments.
