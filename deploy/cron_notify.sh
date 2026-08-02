#!/usr/bin/env bash
# Send one message to Telegram. Shared by every alerting path so there is a
# single place where delivery can be fixed -- and a single place that logs when
# delivery fails, which is the failure mode that matters most: an alerter that
# silently does nothing looks exactly like everything being fine.
#
#   ./deploy/cron_notify.sh "some message"
#
# Reads HERMES_ENV (a file containing TELEGRAM_BOT_TOKEN=...) and
# TELEGRAM_CHAT_ID from the repo's .env. Without them it logs and exits 1
# rather than failing whatever called it.
set -uo pipefail

HOME_DIR="${CARRYDESK_HOME:-$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)}"
[ -f "$HOME_DIR/.env" ] && { set -a; . "$HOME_DIR/.env"; set +a; }

ENV_FILE="${HERMES_ENV:-}"
CHAT_ID="${TELEGRAM_CHAT_ID:-}"
ALERT_LOG="$HOME_DIR/alert.log"
MSG="${1:-}"

[ -z "$MSG" ] && { echo "usage: cron_notify.sh <message>" >&2; exit 2; }

stamp() { date -u +%FT%TZ; }

if [ -z "$ENV_FILE" ] || [ -z "$CHAT_ID" ]; then
  echo "$(stamp) NOT DELIVERED (HERMES_ENV/TELEGRAM_CHAT_ID unset): ${MSG:0:160}" >> "$ALERT_LOG"
  exit 1
fi

TOKEN="$(grep -m1 '^TELEGRAM_BOT_TOKEN=' "$ENV_FILE" 2>/dev/null | cut -d= -f2- | tr -d '"'"'"' \r')"
if [ -z "$TOKEN" ]; then
  echo "$(stamp) DELIVERY FAILED: no TELEGRAM_BOT_TOKEN in $ENV_FILE" >> "$ALERT_LOG"
  exit 1
fi

HTTP="$(curl -s -o /dev/null -w '%{http_code}' --max-time 20 \
  "https://api.telegram.org/bot${TOKEN}/sendMessage" \
  --data-urlencode "chat_id=${CHAT_ID}" \
  --data-urlencode "text=${MSG}")"

if [ "$HTTP" != "200" ]; then
  echo "$(stamp) DELIVERY FAILED http=$HTTP msg=${MSG:0:120}" >> "$ALERT_LOG"
  exit 1
fi
exit 0
