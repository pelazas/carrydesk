# BACKLOG

Things deliberately deferred, with enough context to pick up cold. Not a wish
list — everything here has been considered and postponed for a stated reason.

---

## Curated lists — DONE 2026-08-02, two PRs open

- **punkpeye/awesome-mcp-servers** (★91.7k) →
  [PR #11378](https://github.com/punkpeye/awesome-mcp-servers/pull/11378),
  added to *Finance & Fintech*. Glama listing + score badge done as their bot
  required; awaiting maintainer review. Their CONTRIBUTING explicitly invites agent PRs
  via a `🤖🤖🤖` title marker, which this PR uses and discloses.
- **xpaysh/awesome-x402** (★272) →
  [PR #1106](https://github.com/xpaysh/awesome-x402/pull/1106),
  added to *Data & Social APIs*.

**Two targets did not survive contact:**

- *Hyperliquid tooling lists* — **no such curated list exists.** Searching
  returns trading bots and SDKs, not awesome-lists. Dropped rather than forced.
- *Official MCP servers repo* — **retired its third-party list.** It now points
  at the [MCP Server Registry](https://github.com/modelcontextprotocol/registry),
  which is a better target but needs a **published package** (PyPI/npm/OCI); a
  git URL is not an accepted source. See below.

**Optional, not done:** `wong2/awesome-mcp-servers` (★4.2k) and
`appcypher/awesome-mcp-servers` (★5.7k) are separately maintained and would
accept a similar entry. Held back deliberately — two PRs across genuinely
different lists reads as a contribution; five near-duplicate ones read as spam.

---

## Channels evaluated and rejected (2026-08-02)

Checked against each list's own rules rather than assumed. Recorded so they do
not get re-suggested.

**Blocked by an explicit rule — revisit on a date:**

- **awesome-selfhosted** (★310k) — requires the project to have been *first
  released more than 4 months ago*, with tagged releases. carrydesk is hours
  old. Genuinely eligible around **2026-12**; it is self-hostable, MIT, and
  depends on no specific cloud provider, so it should qualify then.
- **awesome-claude-code** (★51.5k) — good fit in principle, but its CONTRIBUTING
  says recommendations **must be made by a human through the web issue form**,
  that submitting via `gh` CLI risks being *restricted from the repository*, and
  that the right order is "build it → get users → submit". So: not by an agent,
  and not yet. Revisit once carrydesk has real users.

**Wrong list — do not submit:**

- **awesome-rust** — carrydesk is Python.
- **awesome-cli-apps** — it is an API and MCP server, not a CLI app.
- **awesome-terminal / awesome-macos-command-line** — not a terminal tool.

**Wrong audience, negligible return:**

- **AlternativeTo** — a consumer-software directory where users arrive searching
  "alternative to <product>". carrydesk has no anchor product to be an
  alternative *to*, and the audience is not people who write trading bots.
- **Slant** — a "what are the best X" recommendation site with little remaining
  traffic and no category this fits.

**The general rule this encodes:** two PRs to lists we genuinely belong on read
as contributing; seven submissions across lists we do not fit read as spam, and
it is the owner's GitHub identity attached to every one of them. Maintainers
remember names. Fit first, volume never.

## Carry-spread chart — DONE 2026-08-02

Live on both the front page and `/archive`. Server-rendered inline SVG, no JS
and no external requests, plotting **mean and median together** because the gap
between them is the point: the first live reading showed +45.6% mean against
+10.3% median, and a chart of the flattering line alone would undo the reason
anyone should trust the rest.

Colours are categorical slots 1 and 2 from the validated reference palette,
checked with the palette validator against both the light and dark page
surfaces — lightness band, chroma floor, CVD separation, normal-vision floor
and contrast all pass in both modes. Do not substitute by eye.

Hover tooltips use SVG's native `<title>`, so they work with zero script.
Endpoint-only direct labels; a number on every point is unreadable.

Tracked in Notion: <https://app.notion.com/p/3b089b3ff699819b8e32e4596c829ebc>

---

## PyPI + official MCP Registry — DONE 2026-08-02

- **PyPI:** <https://pypi.org/project/carrydesk/> — `uvx --from carrydesk carrydesk-mcp`
- **Registry:** `io.github.pelazas/carrydesk` v0.1.2, live at
  <https://registry.modelcontextprotocol.io>

Ownership proof for PyPI is the literal `mcp-name: io.github.pelazas/carrydesk`
in the published README (HTML comment). Keep it there — removing it breaks
future republishes.

To ship a new version: bump `pyproject.toml` + `carrydesk/__init__.py`, `uv build`,
`uv publish`, bump both version fields in `server.json`, then `mcp-publisher publish`
(re-login with `mcp-publisher login github` if the token has expired).

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

**Investigated 2026-08-02, and the answer is: nothing more we can do from here.**
A full scan of all 14,826 indexed resources confirms we are absent, and two real
mainnet settlements did not change that. The x402 SDK's bazaar client exposes
only `list_resources` and `search` — there is **no register, declare or publish
call**. The `Declare*DiscoveryConfig` helpers enrich what a route advertises in
its own 402 challenge; they do not push anything to CDP.

So indexing is Coinbase's to do. We have already done everything available:
the resource server extension is registered, and each paid route declares
`service_name`, `tags` and a human-readable `description`.

**Recheck occasionally.** If it stays absent for weeks, ask CDP directly rather
than guessing further.
