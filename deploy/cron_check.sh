#!/usr/bin/env bash
# Cron entrypoint for the ops probe. Alerts to Telegram only on failure.
#
# Lives in a script rather than inline in crontab because cron mangles % and
# has almost no PATH -- both of which have silently broken alerting on this box
# before. Everything here uses absolute paths on purpose.
#
#   */10 * * * * $HOME/carrydesk/deploy/cron_check.sh
#
# Alert delivery notes (learned the hard way on the trading bot):
#   hermes --deliver telegram          -> silently does nothing
#   hermes --deliver telegram:<chat_id> -> works
set -uo pipefail

HOME_DIR="${CARRYDESK_HOME:-$HOME/carrydesk}"
HERMES="${HERMES_BIN:-$HOME/.local/bin/hermes}"
CHAT_ID="${TELEGRAM_CHAT_ID:-<chat-id>}"
URL="${CARRYDESK_URL:-http://127.0.0.1:8000}"
STATE="$HOME_DIR/.last_alert_state"

out="$("$HOME_DIR/.venv/bin/python" "$HOME_DIR/scripts/ops_check.py" --url "$URL" 2>&1)"
code=$?

prev="$(cat "$STATE" 2>/dev/null || echo 0)"
echo "$code" > "$STATE"

if [ "$code" -eq 0 ]; then
  # Only announce recovery if we had actually alerted -- otherwise every
  # healthy run after a blip would be noise.
  if [ "$prev" != "0" ]; then
    "$HERMES" "carrydesk recovered: health is green again." \
      --deliver "telegram:$CHAT_ID" >/dev/null 2>&1
  fi
  exit 0
fi

# Alert on the transition, and re-alert hourly while still broken, so a
# persistent outage cannot be forgotten but does not spam every 10 minutes.
minute="$(date +%M)"
if [ "$prev" = "0" ] || [ "$minute" -lt 10 ]; then
  "$HERMES" "carrydesk alert (exit $code): $out" \
    --deliver "telegram:$CHAT_ID" >/dev/null 2>&1
fi

exit "$code"
