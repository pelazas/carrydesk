#!/usr/bin/env bash
# Control wrapper for the carrydesk service.
#
# Exists for the same reason the trading bot's ctl.sh does: `systemctl --user`
# needs XDG_RUNTIME_DIR, which a plain non-interactive ssh does not set. Calling
# systemctl directly over ssh fails confusingly; this does not.
set -euo pipefail

export XDG_RUNTIME_DIR="/run/user/$(id -u)"
UNIT=carrydesk.service
HOME_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

case "${1:-status}" in
  status)  systemctl --user status "$UNIT" --no-pager ;;
  start)   systemctl --user start "$UNIT" && echo "started" ;;
  stop)    systemctl --user stop "$UNIT" && echo "stopped" ;;
  restart) systemctl --user restart "$UNIT" && echo "restarted" ;;
  log)     tail -n "${2:-60}" "$HOME_DIR/carrydesk.log" ;;
  health)  curl -s http://127.0.0.1:8000/health | python3 -m json.tool ;;
  check)   "$HOME_DIR/.venv/bin/python" "$HOME_DIR/scripts/ops_check.py" \
             --url http://127.0.0.1:8000 && echo "healthy" ;;
  post)    "$HOME_DIR/.venv/bin/python" "$HOME_DIR/scripts/daily_post.py" \
             --url http://127.0.0.1:8000 --format "${2:-md}" ;;
  *) echo "usage: ctl.sh {status|start|stop|restart|log [n]|health|check|post [md|x]}" >&2
     exit 1 ;;
esac
