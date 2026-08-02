# STATUS

Newest first. This file plus `AGENTS.md` is the whole picture.

---

## Where it stands — 2026-08-02

**Live at https://carry.pelazas.com, taking real payments on Base Sepolia.**

| | |
|---|---|
| Service | `carrydesk.service`, `systemd --user`, survives reboot, ~53 MB / 512 MB cap |
| TLS | Caddy + Let's Encrypt production cert, auto-renewing |
| Paywall | ON — Base Sepolia (`eip155:84532`) |
| Revenue to date | **0.06 USDC** (our own two test payments) |
| Monitoring | ops probe every 10 min → Telegram, verified with a real alert + recovery |
| Archive | append-only, auto-committed daily at 03:00 UTC |
| Distribution | **none** — nothing published or listed anywhere |

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
