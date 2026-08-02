#!/usr/bin/env bash
# One-time TLS setup for carry.pelazas.com. MUST be run with sudo.
#
#   sudo bash ~/carrydesk/deploy/setup_tls.sh
#
# This is the only step on this box that needs root, because binding :80/:443
# does (net.ipv4.ip_unprivileged_port_start is 1024 here).
#
# WHAT IT DOES, exactly:
#   1. apt-get install caddy from Caddy's official repo
#   2. writes /etc/caddy/Caddyfile with a single reverse-proxy rule
#   3. opens 80/443 in ufw, only if ufw is already active
#   4. enables + starts caddy
#
# WHAT IT DOES NOT DO: it never touches other-services, hermes, the carrydesk
# service, any user data, or any existing firewall rule other than adding
# 80/443. It is idempotent -- running it twice is harmless.
#
# Caddy over nginx+certbot on purpose: Caddy obtains AND renews Let's Encrypt
# certificates itself, so there is no renewal cron to silently expire in 90 days.
set -euo pipefail

DOMAIN="${DOMAIN:-carry.pelazas.com}"
UPSTREAM="${UPSTREAM:-127.0.0.1:8000}"

if [ "$EUID" -ne 0 ]; then
  echo "must run as root: sudo bash $0" >&2
  exit 1
fi

echo "==> target: https://$DOMAIN -> $UPSTREAM"

# --- 1. install caddy -------------------------------------------------------
if ! command -v caddy >/dev/null 2>&1; then
  echo "==> installing caddy"
  apt-get install -y -qq debian-keyring debian-archive-keyring apt-transport-https curl gnupg >/dev/null
  curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/gpg.key' \
    | gpg --dearmor -o /usr/share/keyrings/caddy-stable-archive-keyring.gpg
  curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/debian.deb.txt' \
    | tee /etc/apt/sources.list.d/caddy-stable.list >/dev/null
  apt-get update -qq
  apt-get install -y -qq caddy
else
  echo "==> caddy already installed: $(caddy version | head -1)"
fi

# --- 2. configure -----------------------------------------------------------
echo "==> writing /etc/caddy/Caddyfile"
[ -f /etc/caddy/Caddyfile ] && cp /etc/caddy/Caddyfile "/etc/caddy/Caddyfile.bak.$(date +%s)"
# No `log` block on purpose. The Debian caddy unit is sandboxed (ProtectSystem)
# and cannot write to /var/log/caddy even when that directory is chowned to the
# caddy user -- it fails with "permission denied" and exits BEFORE ever
# requesting a certificate. Caddy's default logging goes to stderr -> journald,
# which loses nothing: read it with `sudo journalctl -u caddy`.
#
# No header_up lines either. Caddy v2's reverse_proxy already preserves Host and
# sets X-Forwarded-Proto/-For; caddy validate warns that restating them is
# redundant. Uvicorn is started with --proxy-headers so the app sees the real
# external scheme, which is what x402 puts in the payment challenge.
cat > /etc/caddy/Caddyfile <<CADDY
$DOMAIN {
	reverse_proxy $UPSTREAM
	encode gzip
}
CADDY
caddy validate --config /etc/caddy/Caddyfile --adapter caddyfile 2>&1 | grep -Ei "^error|error:" && exit 1
echo "==> Caddyfile valid"

# --- 3. firewall (only if already in use) -----------------------------------
if command -v ufw >/dev/null 2>&1 && ufw status 2>/dev/null | grep -q "Status: active"; then
  echo "==> ufw active, allowing 80/443"
  ufw allow 80/tcp  >/dev/null
  ufw allow 443/tcp >/dev/null
else
  echo "==> ufw not active, leaving firewall alone"
fi

# --- 4. start ---------------------------------------------------------------
systemctl enable caddy >/dev/null 2>&1 || true
systemctl restart caddy
sleep 8

echo "==> caddy: $(systemctl is-active caddy)"
echo "==> waiting for certificate (Let's Encrypt HTTP-01, usually <30s)"
for i in $(seq 1 12); do
  code="$(curl -s -o /dev/null -w '%{http_code}' --max-time 10 "https://$DOMAIN/health" 2>/dev/null || echo 000)"
  if [ "$code" = "200" ] || [ "$code" = "503" ]; then
    echo "==> TLS OK: https://$DOMAIN/health -> $code"
    exit 0
  fi
  sleep 5
done

echo "==> certificate not ready yet. Check: journalctl -u caddy -n 40 --no-pager" >&2
exit 1
