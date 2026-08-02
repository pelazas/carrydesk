# DEPLOY

Deploys to any Ubuntu box with `systemd --user`. Host-specific values live in
`.env` on the server and are deliberately not in this repo.

The service is read-only against a public API and idles near zero CPU between
hourly refreshes, so it co-exists happily with other workloads. If it shares a
host with anything you care about, keep the memory ceiling in step 3 — it is not
optional.

---

## 1. Install

```bash
git clone <this-repo> ~/carrydesk && cd ~/carrydesk
uv venv --python 3.12
uv pip install -e .
```

## 2. Configure

```bash
cp .env.example .env && chmod 600 .env
$EDITOR .env
```

Leave `X402_PAY_TO` blank to run open while testing — the service will not gate
anything without it, and `/health` reports `paywall_active: false`.

`X402_PAY_TO` is a **receiving** address. The service never signs anything and
holds no key. Never put a private key in this file.

## 3. Run it

```bash
mkdir -p ~/.config/systemd/user
cp deploy/carrydesk.service ~/.config/systemd/user/
chmod +x deploy/*.sh

export XDG_RUNTIME_DIR=/run/user/$(id -u)
systemctl --user daemon-reload
systemctl --user enable --now carrydesk.service
loginctl enable-linger "$USER"        # survive reboot

./deploy/ctl.sh status && ./deploy/ctl.sh health
```

The unit ships with `MemoryMax=512M` and `CPUWeight=50`, and runs a **single
worker** on purpose: the snapshot store is in-process memory and the background
refresher must not run N times against the upstream API. Scale with a cache in
front, not with workers.

## 4. TLS

```bash
sudo bash deploy/setup_tls.sh          # DOMAIN=... UPSTREAM=... to override
```

Caddy obtains and renews the Let's Encrypt certificate itself, so there is no
renewal cron to silently expire in 90 days.

**Three things that will waste your afternoon — check them before blaming ACME:**

1. **A cloud firewall in front of the VM** (DigitalOcean, AWS SG, Hetzner) blocks
   80/443 independently of `ufw`. Symptom: connections **time out** rather than
   being refused, while SSH still works. Fix it in the provider's console, not
   on the box.
2. **Caddy cannot write to `/var/log/caddy`** — its systemd unit is sandboxed.
   A `log` block makes it exit ~9ms after start, *before* it ever requests a
   certificate, so the symptom reads as an ACME failure. Leave logging to
   journald: `sudo journalctl -u caddy`.
3. **Let's Encrypt allows 5 failed validations per hostname per hour.** Burning
   them (e.g. while a firewall is shut) locks you out for the rest of the hour,
   and Caddy may latch onto the untrusted **staging** CA. Re-pin production
   without sudo via Caddy's admin API:
   `POST http://127.0.0.1:2019/load` with an explicit
   `apps.tls.automation.policies[].issuers[].ca`.

`PUBLIC_URL` must match the external URL, and the unit runs uvicorn with
`--proxy-headers`. Together these make x402 advertise the real
`https://host/...` in the payment challenge rather than `http://127.0.0.1:8000`.

## 5. Monitoring

Set `HERMES_ENV` (a file containing `TELEGRAM_BOT_TOKEN=...`) and
`TELEGRAM_CHAT_ID` in `.env`. Without them alerting degrades to a line in
`alert.log` rather than failing.

```cron
*/10 * * * * $HOME/carrydesk/deploy/cron_check.sh
0 3 * * *    $HOME/carrydesk/deploy/cron_archive.sh
5 8 * * *    cd $HOME/carrydesk && ./.venv/bin/python scripts/daily_post.py \
               --url http://127.0.0.1:8000 --out posts/$(date -u +\%F).md
```

`ops_check.py` exits 1 (degraded) or 2 (down) and prints one line. It also
probes that a paid route still answers 402 — **an open paywall is a silent
revenue leak that no uptime check would catch.**

Alerting sends straight to the Telegram Bot API rather than through an agent:
deterministic, instant, and no LLM in the alerting path. Delivery failures are
appended to `alert.log`, because an alerter that fails silently is strictly
worse than none.

## 6. The archive

`data/snapshots/*.jsonl` is gitignored for local dev. **On the server it is the
asset** — `cron_archive.sh` force-adds and pushes it, and refuses to run off
`master` (a failed rebase once left a checkout detached, where commits land
nowhere and pushes silently no-op).

`.gitattributes` sets `merge=union` on those files so concurrent appends from
the server and a workstation never conflict.

It cannot be backfilled. Every day the service is not running is a day of proof
permanently lost.

## 7. Rollback

```bash
git log --oneline -5 && git checkout <sha> && ./deploy/ctl.sh restart
```

No database, no migrations. State is the append-only archive, so rolling code
back is always safe.
