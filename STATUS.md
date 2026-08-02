# STATUS

Newest first. This file plus `AGENTS.md` is the whole picture.

---

## 2026-08-02 — MAINNET: real USDC settled

**carrydesk takes real money.** Two settlements on Base mainnet:

| Endpoint | Price | Transaction |
|---|---|---|
| `/v1/universe` | $0.01 | [`0x6f524f…7a190`](https://basescan.org/tx/0x6f524f9de5b713a3e88507f590c518cce69479036fa7491551c5e22ff2d7a190) |
| `/v1/carry/rankings` | $0.05 | [`0xfe6004…06060c`](https://basescan.org/tx/0xfe6004c4cbacc64eda9c9a0f1a876898bbda8ff4f7e5a5a6b3b71e509606060c) |

Receiving wallet holds **0.06 USDC on Base mainnet**. Real USDC contract
`0x8335…2913`, buyer paid no gas (facilitator sponsors via EIP-3009).

**Bug: the CDP JWT binds the HTTP method, not just the path.** Signing all four
facilitator endpoints as POST made `/supported` return 401, which surfaced as
every paid route 500ing on *first request* rather than at startup, because the
paywall middleware initializes lazily. `get_supported` and bazaar discovery are
GET; `verify` and `settle` are POST.

**Bazaar: registered but not yet indexed.** The discovery extension is active
and CDP's index holds 14,820 resources, but ours is not among the first 3,000
and `/discovery/search` returns 0 hits for terms that demonstrably exist in the
index — so search is not a reliable signal either way. Presumed asynchronous;
recheck later.

---

## 2026-08-02 — Tier 1 distribution: findable without a human

Everything that can make the service discoverable *without* a person posting
about it is now live and verified:

| Surface | |
|---|---|
| `/llms.txt` | plain-text description of the service for an LLM |
| `/robots.txt` | explicitly welcomes named AI crawlers, not just a wildcard |
| `/sitemap.xml` | the free pages worth indexing |
| JSON-LD | schema.org `Dataset` markup on the public page |
| `/archive` | every snapshot ever published, browsable |
| GitHub | 10 topics, homepage, and a description written for search |
| `weekly_audit.py` | Mondays 09:00 UTC → Telegram only on failure |

The weekly audit covers what a 10-minute liveness probe never sees: certificate
expiry, an archive that quietly stopped growing, and — most importantly — the
free tier losing its `trimmed` / `median` / `outlier_dominated` fields, which
would be the most damaging silent regression available.

All alerting now shares one `cron_notify.sh`, so there is a single delivery path
and a single `alert.log`.

**Bazaar: confirmed we cannot self-list.** Full scan of all 14,826 indexed
resources — absent. Two mainnet settlements did not trigger indexing. The SDK
has no register/declare call. See `BACKLOG.md`.

**What Tier 1 does not do:** create anyone who looks. Passive discovery without
an active seed reliably produces close to zero. The remaining highest-leverage
action is a human posting once, and it cannot be delegated.

---

## 2026-08-02 — cron hardening (what survives after the session ends)

Ran every cron job under a stripped cron environment (`env -i`, minimal PATH,
no profile) rather than an interactive shell, because that is how they will
actually run once nobody is watching.

**Found: the archive push failed whenever the box was behind origin.** The push
was rejected, the script exited 1, and the crontab discarded output — so the
archive would have stopped being preserved *silently*. That is the precise
failure mode the entire track record depends on avoiding, and the detached-HEAD
guard did not cover it, because divergence is a different path.

Fixed: fetch, rebase with `--autostash`, retry once. Every failure branch now
writes a dated line to stderr, and the crontab routes it to Telegram instead of
`/dev/null`.

The other four jobs (ops probe, daily post, weekly audit, notifier) all pass
under the same stripped environment.

---

## 2026-08-02 — published to the official MCP Registry

`io.github.pelazas/carrydesk` v0.1.2 is live in
<https://registry.modelcontextprotocol.io>, which superseded the retired
third-party list in `modelcontextprotocol/servers` and is the highest-credibility
MCP listing available.

Getting there needed three things in order:

1. **A published package.** The registry accepts PyPI/npm/OCI, not a git URL.
   `carrydesk` is on PyPI; install is `uvx --from carrydesk carrydesk-mcp`.
2. **An ownership token.** The registry proves you control the PyPI package by
   requiring the literal string `mcp-name: io.github.pelazas/carrydesk` in the
   **published package README**, followed by a boundary. Confirmed by reading
   `internal/validators/registries/pypi.go` in the registry source rather than
   guessing — the GitHub device-flow login that follows is owner-only, so
   discovering this afterwards would have wasted it. Lives in an HTML comment:
   an accepted boundary, invisible when rendered, present where the validator
   looks.
3. **GitHub device-flow auth**, which only the owner can complete.

**Bug caught before registering:** the MCP server had its version hardcoded at
`0.1.0`, so after the 0.1.1 release every client's introspection reported a
version the server was not. Now derived from `carrydesk.__version__`.

**Diagnostic note:** a freshly published version can appear absent for minutes —
`uv` caches the simple index, and `uv pip install carrydesk==0.1.2` failed with
"no version of carrydesk==0.1.2" while PyPI plainly had the files. `uv cache
clean carrydesk` resolves it. Do not assume a broken build.

---

## 2026-08-02 — listed on Glama

https://glama.ai/mcp/servers/pelazas/carrydesk — approved and scored.

`awesome-mcp-servers` requires a Glama listing before merge, and Glama's check
is that the server starts in a container and answers introspection. Added a
Dockerfile and verified it: image builds, container runs non-root, all six tools
enumerate, live API call succeeds from inside. Score badge pushed to PR #11378.

**Where automation stopped:** Glama's "Add Server" is an account signup with a
ToS acceptance and an "I'm not a robot" checkbox. Playwright drove the site
fine, but accepting terms in the owner's name and defeating an explicit
anti-automation control are not things to do on someone's behalf — the owner
completed those two clicks.

---

## 2026-08-02 — first curated-list submissions

Two PRs open, both following each repo's contribution guidelines and both
disclosing that an agent prepared them:

| List | | PR |
|---|---|---|
| punkpeye/awesome-mcp-servers | ★91.7k | [#11378](https://github.com/punkpeye/awesome-mcp-servers/pull/11378) |
| xpaysh/awesome-x402 | ★272 | [#1106](https://github.com/xpaysh/awesome-x402/pull/1106) |

**Unblocked this first:** installing the MCP server took a clone plus three
commands, while every comparable listing is a one-liner. Added a
`carrydesk-mcp` console script, so it is now
`uvx --from git+https://github.com/pelazas/carrydesk carrydesk-mcp` —
verified from a clean environment: 105 packages in 345ms, six tools, live data.

**Two planned targets did not survive contact:** no Hyperliquid curated list
exists, and the official MCP servers repo retired its third-party list in favour
of a registry that requires a published package. Both recorded in `BACKLOG.md`.

---

## Where it stands — 2026-08-02

**Live at https://carry.pelazas.com, settling real USDC on Base mainnet.**

| | |
|---|---|
| Service | `carrydesk.service`, `systemd --user`, survives reboot, ~53 MB / 512 MB cap |
| TLS | Caddy + Let's Encrypt production cert, auto-renewing |
| Paywall | ON — **Base mainnet** (`eip155:8453`), real USDC |
| Revenue to date | **0.06 USDC on mainnet** (our own two test payments) |
| Monitoring | ops probe every 10 min → Telegram, verified with a real alert + recovery |
| Archive | append-only, auto-committed daily at 03:00 UTC |
| Distribution | **none** — nothing published or listed anywhere |

---

## 2026-08-02 — public repo + public page

**Repo is public**: https://github.com/pelazas/carrydesk — so the MCP server is
installable, which was the point.

**Public page at `/`** — server-rendered from the same snapshot the API serves,
no JS and no external requests. Content-negotiated: HTML for browsers, the JSON
index for API clients (also at `/api`). It shows trimmed and median spread
beside the headline plus the outlier flag, because publishing the number that
makes us look worse is what makes the rest credible.

**Repo hygiene incident.** The repo was made public *before* the sanitized
history was force-pushed, so unsanitized commits were retrievable by SHA for
about two minutes. No credentials were ever committed — `.env` and keys were
gitignored from the first commit, verified across all history — and the most
sensitive item (the droplet IP) was already public via DNS. Resolved properly by
deleting and recreating the repo, since force-pushing does not remove orphaned
commits from GitHub. Verified from a fresh anonymous clone: zero leaks, 19
commits, archive intact.

**Deploy key gotcha:** recreating the repo silently downgraded the old deploy key
to read-only, which would have made the 03:00 archive push fail quietly. New key
issued, and the path now comes from `.env` rather than being hardcoded.

---

## 2026-08-02 — first payments settled on-chain

Proven end to end, both entry paths:

| Path | Price | Result |
|---|---|---|
| Direct HTTP → `/v1/universe` | $0.01 | settled, [tx `0x89e868…c80350`](https://sepolia.basescan.org/tx/0x89e86827e68bed37bdc27376f10cd8c325ff3447dc9325ec3641a51cf6c80350) |
| MCP tool `carry_rankings` | $0.05 | settled, data returned |

Receiving wallet went 0 → 0.0600 USDC. The buyer signed only; the facilitator
broadcast and paid gas (EIP-3009 `TransferWithAuthorization`) — confirmed by the
buyer wallet holding zero native currency. That property is what makes agent
payments practical.

Cost two rounds: Circle's faucet remembers the last network chosen, so USDC
landed on Arbitrum Sepolia and then Ethereum Sepolia before Base Sepolia. The
public facilitator supports exactly one EVM network.

## 2026-08-02 — TLS, after three stacked failures

Each failure disguised the next:

1. **Caddy exited 9ms after start** — `open /var/log/caddy/…: permission
   denied`. Its systemd unit is sandboxed. It never reached the point of
   requesting a certificate, so it read as an ACME problem. Fix: no file log.
2. **A DigitalOcean Cloud Firewall** dropped inbound 80/443 at the network edge,
   before the VM. `ufw` allowing them was irrelevant. Signature: connections
   *time out* rather than being refused, while SSH works.
3. **Let's Encrypt rate limit** — the 5 failed validations from (2) tripped the
   cap of 5 failed authorizations per hostname per hour, and Caddy had fallen
   back to the untrusted **staging** CA. Re-pinned production via Caddy's admin
   API (`POST 127.0.0.1:2019/load`), which needs no sudo.

Verified after: free routes 200, all three paid routes 402, `http→https` 308,
and the payment challenge advertises the real external URL — confirming
uvicorn's `--proxy-headers` works. Without it x402 would have advertised
`http://127.0.0.1:8000` to buyers.

## 2026-08-02 — deployed

Deployed as a `systemd --user` service alongside existing workloads, with
`MemoryMax=512M` and `CPUWeight=50` so it can never starve them. Deploy key with
write access added so the box can push its own archive.

**Bug: alerting was silently dead.** The first cron wrapper called
`hermes "msg" --deliver telegram:<id>`, which is not valid hermes CLI syntax —
hermes needs a subcommand, so every alert was a no-op, and `>/dev/null` hid it.
Now posts directly to the Telegram Bot API and appends delivery failures to
`alert.log`. A silently-broken alerter is worse than none: it looks like health.

**Bug: the checkout drifted into detached HEAD** after a failed rebase, where
commits land nowhere and pushes silently no-op — the archive would have looked
healthy while not being preserved. Restored with all snapshots intact;
`cron_archive.sh` now refuses to run off `master`, and `.gitattributes` sets
`merge=union` on the archive so concurrent appends never conflict.

## 2026-08-02 — core built

Hyperliquid client, ranking maths (14 tests), snapshot store with validation
gate and append-only archive, FastAPI service, x402 paywall, MCP server, ops
probe, daily-post generator, deploy artifacts.

**Three bugs found while building:**

1. **Paywall bypass** — `/v1/carry/history/{coin}` used FastAPI brace syntax,
   which x402 escapes literally, so the route never matched and served paid data
   for free with HTTP 200. Fixed, plus a boot-time self-check that fails closed
   and a test that the guard itself fails on a broken pattern.
2. **`No scheme for "exact"`** — x402 needs CAIP-2 network ids *and* an explicit
   `register_exact_evm_server()`.
3. **`/v1/universe` sorted by funding rank** rather than liquidity, despite being
   the liquidity endpoint.

**Data-quality finding that shaped the product.** The headline carry spread is
routinely dominated by one or two illiquid names — the first live reading was
39%/yr headline vs 22%/yr trimmed vs 9.6%/yr median, with two coins funding at
+199%/yr and +95%/yr carrying most of it. Publishing the headline alone would be
misleading and would burn credibility the first time a buyer sized into them.
Added `carry_spread_annualized_trimmed`, `_median` and `outlier_dominated`, all
exposed in the **free** tier as well as paid.

---

## Next up (in order)

The build is done. Everything below is distribution.

1. **Publish the daily snapshot.** `scripts/daily_post.py` renders and gates it;
   nothing is posted anywhere. The archive only converts into anything if it is
   visible. Decision taken: a static page on the service's own domain first.
2. **Make the repo public** so the MCP server is installable — the strongest
   channel available. Decision taken: yes, after sanitizing host specifics.
3. **Mainnet payments.** Needs Coinbase CDP API keys; the public facilitator is
   testnet-only. Worth doing once someone actually wants the data.
4. **Listings** — x402 bazaar, MCP directories. Blocked on (2).
5. **Cross-venue funding.** The natural second product, but one venue done well
   beats two done badly. Hold until there is demand.

## Deliberately not built

- **`POST /v1/backtest`** (the $5–20 tier) — needs sandboxing before accepting
  user-supplied strategy code. Not worth the attack surface until the cheap
  endpoints prove demand.
- **Agent-to-agent discovery** — real infrastructure, negligible volume today.
