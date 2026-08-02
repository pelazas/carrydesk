# DEPLOY

Target: the existing DigitalOcean droplet `the-server` (`the-server`, fra1),
alongside the carry bot and hermes. Same `systemd --user` pattern the bot already
uses, so there is one operational model to remember instead of two.

**Why the same box:** carrydesk is read-only against a public API and idles near
zero CPU between hourly refreshes. A second droplet buys isolation the service
does not need yet, and costs a second thing to maintain. Revisit if carrydesk
ever gets real traffic — at which point it should move *off* the box the trading
bot runs on, not the other way around.

**Risk to be explicit about:** the trading bot runs real money on this box. A
runaway carrydesk process competing for memory could affect it. Mitigations
below (`MemoryMax`, one worker) are not optional.

---

## 1. Ship the code

```bash
ssh -i ~/.ssh/<ssh-key> pelazas@the-server
git clone https://github.com/pelazas/carrydesk.git ~/carrydesk
cd ~/carrydesk
~/.local/bin/uv venv --python 3.12
~/.local/bin/uv pip install -e .
```

The repo is private, so the clone needs auth — either a deploy key or
`gh auth login` on the box.

---

## 2. Configure

```bash
cp .env.example .env && chmod 600 .env
$EDITOR .env    # set X402_PAY_TO, X402_NETWORK, PUBLIC_URL
```

Leave `X402_PAY_TO` blank to run open while testing. **The service will not gate
anything without it** — `/health` reports `paywall_active: false` and
`scripts/ops_check.py` skips the leak probe.

Never paste a private key here. `X402_PAY_TO` is a *receiving* address; the
service never signs anything and holds no key.

---

## 3. Install the unit

```bash
mkdir -p ~/.config/systemd/user
cp deploy/carrydesk.service ~/.config/systemd/user/
chmod +x deploy/ctl.sh

export XDG_RUNTIME_DIR=/run/user/$(id -u)
systemctl --user daemon-reload
systemctl --user enable --now carrydesk.service
loginctl enable-linger pelazas    # already on for the bot; harmless to repeat

./deploy/ctl.sh status
./deploy/ctl.sh health
```

Add a memory ceiling so this can never starve the trading bot:

```bash
systemctl --user edit carrydesk.service
# [Service]
# MemoryMax=512M
```

---

## 4. Expose it

The unit binds `127.0.0.1:8000` only. Caddy terminates TLS in front of it:

```bash
sudo bash ~/carrydesk/deploy/setup_tls.sh     # idempotent
```

Live at **https://carry.pelazas.com**. Caddy obtains and renews the Let's
Encrypt certificate itself, so there is no renewal cron to expire.

**Three things that bit us here — check them before blaming ACME:**

1. **A DigitalOcean Cloud Firewall sits in front of the droplet** and blocks
   80/443 by default. ufw allowing them is not enough. Symptom: connections
   *time out* rather than being refused, while SSH still works. Fix in the DO
   panel: Networking → Firewalls → Inbound Rules → add TCP 80 and 443.
2. **Caddy cannot write to `/var/log/caddy`** — its systemd unit is sandboxed.
   A `log` block makes it exit before it ever requests a certificate. Leave
   logging to journald: `sudo journalctl -u caddy`.
3. **Let's Encrypt allows 5 failed validations per hostname per hour.** Burning
   them (e.g. while the firewall is shut) locks you out for the rest of the hour
   and can leave Caddy latched onto the untrusted *staging* CA. Re-pin the
   production CA without sudo through Caddy's admin API:
   `POST http://127.0.0.1:2019/load` with an explicit
   `apps.tls.automation.policies[].issuers[].ca`.

`PUBLIC_URL` in `.env` must match the external URL, and uvicorn runs with
`--proxy-headers` — together these make x402 advertise
`https://carry.pelazas.com/...` in the payment challenge rather than
`http://127.0.0.1:8000/...`.

---

## 5. Monitoring

Mirrors the bot's existing Telegram setup (chat id `<chat-id>`; remember hermes
needs `--deliver telegram:<chat_id>`, the bare `telegram` target fails silently).

```cron
# alert only on failure
*/10 * * * * cd ~/carrydesk && ./deploy/ctl.sh check >/dev/null 2>>/tmp/cd_check.err || \
  hermes "$(cat /tmp/cd_check.err | tail -1)" --deliver telegram:<chat-id>

# daily proof post, rendered not published — review before it goes out
5 8 * * * cd ~/carrydesk && ./deploy/ctl.sh post md > ~/carrydesk/posts/$(date +\%F).md
```

`ops_check.py` exits 1 (degraded) or 2 (down) and prints one line. It also probes
that a paid route still answers 402 — an open paywall is a silent revenue leak
that no uptime check would catch.

---

## 6. The archive

`data/snapshots/*.jsonl` is the track record and is gitignored by default, since
the local dev copy is noise. **On the server it is the asset.** Once deployed,
commit it on a schedule or sync it somewhere durable:

```cron
0 3 * * * cd ~/carrydesk && git add -f data/snapshots && \
  git commit -q -m "archive $(date +\%F)" && git push -q
```

It cannot be backfilled. Every day the service is not running is a day of proof
permanently lost.

---

## 7. Rollback

```bash
cd ~/carrydesk && git log --oneline -5
git checkout <sha> && ./deploy/ctl.sh restart
```

There is no database and no migration. State is the snapshot archive, which is
append-only, so rolling code back is always safe.
