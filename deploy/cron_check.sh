#!/usr/bin/env bash
# Cron entrypoint for the ops probe. Alerts to Telegram only on failure.
#
#   */10 * * * * ${CARRYDESK_HOME}/deploy/cron_check.sh
#
# Delivery goes straight to the Telegram Bot API, not through hermes:
#   - deterministic and instant; no LLM in the alerting path (see DECISIONS D5)
#   - hermes' CLI needs a subcommand, so `hermes "msg" --deliver ...` is a
#     silent no-op. That exact mistake shipped here once and was only caught by
#     capturing stderr, which is why this script now logs delivery failures.
#
# The token is read from hermes' env file and is never printed or copied.
set -uo pipefail

# Defaults to the repo this script lives in, so it works on any host.
HOME_DIR="${CARRYDESK_HOME:-$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)}"

# Host-specific values (where the Telegram bot token lives, which chat to alert)
# come from the server's .env, which is never committed. Alerting degrades to a
# log line if they are unset rather than failing the health check itself.
if [ -f "$HOME_DIR/.env" ]; then
  set -a; . "$HOME_DIR/.env"; set +a
fi
ENV_FILE="${HERMES_ENV:-}"
CHAT_ID="${TELEGRAM_CHAT_ID:-}"
URL="${CARRYDESK_URL:-http://127.0.0.1:8000}"
STATE="$HOME_DIR/.last_alert_state"
ALERT_LOG="$HOME_DIR/alert.log"

notify() {
  # Delegates to the shared notifier so there is one delivery path to fix.
  "$HOME_DIR/deploy/cron_notify.sh" "$1"
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
