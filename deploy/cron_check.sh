#!/usr/bin/env bash
# Cron entrypoint for the ops probe. Alerts to Telegram only on failure.
#
#   */10 * * * * $HOME/carrydesk/deploy/cron_check.sh
#
# Delivery goes straight to the Telegram Bot API, not through hermes:
#   - deterministic and instant; no LLM in the alerting path (see DECISIONS D5)
#   - hermes' CLI needs a subcommand, so `hermes "msg" --deliver ...` is a
#     silent no-op. That exact mistake shipped here once and was only caught by
#     capturing stderr, which is why this script now logs delivery failures.
#
# The token is read from hermes' env file and is never printed or copied.
set -uo pipefail

HOME_DIR="${CARRYDESK_HOME:-$HOME/carrydesk}"
ENV_FILE="${HERMES_ENV:-$HOME/.hermes/.env}"
CHAT_ID="${TELEGRAM_CHAT_ID:-<chat-id>}"
URL="${CARRYDESK_URL:-http://127.0.0.1:8000}"
STATE="$HOME_DIR/.last_alert_state"
ALERT_LOG="$HOME_DIR/alert.log"

notify() {
  local msg="$1" token http
  token="$(grep -m1 '^TELEGRAM_BOT_TOKEN=' "$ENV_FILE" 2>/dev/null | cut -d= -f2- | tr -d '"'"'"' \r')"
  if [ -z "$token" ]; then
    echo "$(date -u +%FT%TZ) DELIVERY FAILED: no TELEGRAM_BOT_TOKEN in $ENV_FILE" >> "$ALERT_LOG"
    return 1
  fi
  http="$(curl -s -o /dev/null -w '%{http_code}' --max-time 20 \
    "https://api.telegram.org/bot${token}/sendMessage" \
    --data-urlencode "chat_id=${CHAT_ID}" \
    --data-urlencode "text=${msg}")"
  if [ "$http" != "200" ]; then
    # A broken alerter must never fail silently -- that is strictly worse than
    # no alerter at all, because it looks like everything is fine.
    echo "$(date -u +%FT%TZ) DELIVERY FAILED http=$http msg=${msg:0:120}" >> "$ALERT_LOG"
    return 1
  fi
  return 0
}

out="$("$HOME_DIR/.venv/bin/python" "$HOME_DIR/scripts/ops_check.py" --url "$URL" 2>&1)"
code=$?

prev="$(cat "$STATE" 2>/dev/null || echo 0)"
echo "$code" > "$STATE"

if [ "$code" -eq 0 ]; then
  # Only announce recovery if we actually alerted -- otherwise every healthy
  # run after a blip is noise.
  [ "$prev" != "0" ] && notify "carrydesk recovered: health is green again."
  exit 0
fi

# Alert on the transition, then re-alert hourly while still broken: a persistent
# outage must not be forgotten, but must not spam every 10 minutes either.
minute="$(date +%M)"
if [ "$prev" = "0" ] || [ "$minute" -lt 10 ]; then
  notify "carrydesk alert (exit $code): $out"
fi

exit "$code"
