# STATUS

Updated every working session. Newest first. If you are an agent picking this up,
this file plus `AGENTS.md` is the whole picture.

---

## 2026-08-02 — iteration 2: DEPLOYED to the-server

**Live.** `carrydesk.service` runs as `systemd --user` on `the-server` alongside
`other-services.service` and `hermes-gateway.service`. Linger + enabled, so it
survives reboot. 53 MB against a 512 MB cap. The archive is accumulating —
**the track record started today.**

Owner decisions taken this iteration: deploy to the-server, testnet payments first,
and yes to publishing the ranking the bot trades.

| | |
|---|---|
| Bind | `127.0.0.1:8000` only — **not publicly reachable yet** (no domain, no TLS) |
| Paywall | **OFF** (`X402_PAY_TO` blank). Service runs fully open. |
| Monitoring | ops probe every 10min → Telegram; verified with a real alert + recovery |
| Archive | committed and pushed to this repo daily at 03:00 UTC by the box itself |
| Daily post | rendered to `posts/YYYY-MM-DD.md` at 08:05 UTC; **not** auto-published |

**Bug found and fixed: alerting was silently dead.** The first cron wrapper
called `hermes "msg" --deliver telegram:<id>`, which is not valid hermes CLI
syntax — hermes needs a subcommand, so every alert was a no-op, and the
`>/dev/null` wrapper hid it. Now posts directly to the Telegram Bot API with
curl and appends any delivery failure to `alert.log`. A silently-broken alerter
is strictly worse than none, because it looks exactly like health.

**Deploy key** `the-server (write: archive commits)` added to this repo with write
access so the box can push its own archive.

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
- Ops probe (`scripts/ops_check.py`) — exit 0/1/2 verified against healthy, dead
  and stale targets. Also probes that a paid route still answers 402, because an
  open paywall is a revenue leak no uptime check would catch.
- Daily proof-post generator (`scripts/daily_post.py`) — markdown and X formats,
  behind a gate that verified-rejects empty legs, tiny universes, insane spreads
  and stale snapshots. Renders only; publishing stays a deliberate step.
- Deploy artifacts (`deploy/`) — systemd `--user` unit, `ctl.sh`, and DEPLOY.md
  mirroring the trading bot's existing pattern on `the-server`.

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

## 2026-08-02 — iteration 5: **LIVE at https://carry.pelazas.com**

Production Let's Encrypt certificate issued (valid to 2026-10-31). Verified
externally from outside the box:

| Endpoint | |
|---|---|
| `/health`, `/v1/free/carry`, `/v1/method`, `/docs` | 200 |
| `/v1/carry/rankings`, `/v1/universe`, `/v1/carry/history/BTC` | 402 |
| `http://` → `https://` | 308 redirect |

The payment challenge correctly advertises
`resource: https://carry.pelazas.com/v1/carry/rankings` — confirming uvicorn's
`--proxy-headers` is doing its job. Without it x402 would have advertised
`http://127.0.0.1:8000` to buyers.

**Remaining to earn anything:** nobody has paid yet, and no distribution has
happened. See "Next up".

---

## 2026-08-02 — iteration 4: TLS, and three layers of firewall/config failure

`carry.pelazas.com` is served by Caddy on the droplet. Getting there hit three
separate failures, each of which looked like the previous one:

1. **Caddy exited 9ms after start**: `open /var/log/caddy/carrydesk.log:
   permission denied`. The Debian caddy unit is sandboxed and cannot write
   `/var/log/caddy` even when that dir is chowned to the caddy user. It never
   reached the point of requesting a certificate, so the symptom read as an
   ACME problem. Fix: no file log — Caddy logs to journald by default.
2. **DigitalOcean Cloud Firewall** was dropping inbound 80/443 at the network
   edge, before the droplet. ufw allowing them was irrelevant. Signature:
   connections *time out* rather than being refused, while SSH works. Fixed by
   adding inbound rules in the DO panel.
3. **Let's Encrypt rate limit**: the 5 failed validations from (2) tripped LE's
   cap of 5 failed authorizations per hostname per hour, and Caddy had also
   fallen back to the **staging** CA (whose certs are not publicly trusted).
   Pinned the automation policy to the production CA via Caddy's admin API
   (`POST 127.0.0.1:2019/load`, no sudo needed). Waiting out the window.

**Diagnostic note:** macOS has no `timeout` command, so `timeout N bash -c
'... /dev/tcp/...'` port probes silently report everything as filtered. Use
`curl --max-time` instead. This produced one wrong conclusion before it was
caught.

**Sudo on this box:** `pelazas` is in the `sudo` group but there is no
passwordless sudo, no docker, and `net.ipv4.ip_unprivileged_port_start=1024`.
Anything touching :80/:443 or system units needs the owner to run it. Caddy's
admin API on `127.0.0.1:2019` is the sudo-free escape hatch for config changes.

---

## 2026-08-02 — iteration 3: domain + paywall live

- `carry.pelazas.com` → `the-server`, DNS-only, propagated.
- **Paywall ON.** `X402_PAY_TO=0x56d487318fB8570DB7C928dbD038c22aB53AAB91`,
  network `eip155:84532` (Base Sepolia). Verified: free routes 200, all three
  paid routes 402, and the decoded challenge carries the correct address and
  price. Address checksum validated (EIP-55) before use.
- `scripts/test_payment.py` written: generates a throwaway buyer, detects the
  challenge, pays, and reports the settlement tx. Step 1 verified against a real
  paywalled server; full settlement still needs testnet USDC in a buyer wallet.
- `deploy/setup_tls.sh` written (Caddy, automatic Let's Encrypt).

**Blocked:** the box has **no passwordless sudo, no docker, and
`net.ipv4.ip_unprivileged_port_start=1024`**, so nothing I can do binds :443.
TLS needs the owner to run `sudo bash ~/carrydesk/deploy/setup_tls.sh` once.

Resolved: deploy target (the-server), payments (testnet first), publishing the
ranking (yes), domain (carry.pelazas.com), receiving address.

---

## Next up (in order)

1. **Domain + nginx + TLS.** The archive is accumulating, but nothing is
   reachable from outside. This is the only thing standing between "running"
   and "usable".
2. Turn the paywall on with a real address, on Base Sepolia, and settle one real
   testnet payment end to end.
3. Publish the free snapshot daily. `posts/*.md` renders already; publishing is
   still a deliberate human step by design for the first couple of weeks.
4. Mainnet: needs Coinbase CDP API keys, since the public facilitator is
   testnet-only.
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
