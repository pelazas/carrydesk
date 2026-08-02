#!/usr/bin/env bash
# Safe deploy: pull the latest code without losing archive lines.
#
#   ./deploy/update.sh          # update + restart
#   ./deploy/update.sh --no-restart
#
# WHY THIS EXISTS. The obvious deploy is `git fetch && git reset --hard
# origin/master`, and it silently destroys data: the refresher appends a
# snapshot roughly hourly, and anything appended since the last
# cron_archive.sh run is uncommitted. A hard reset throws those lines away.
# It happened -- one snapshot was lost this way before anyone noticed, because
# nothing errors and the file simply comes back shorter.
#
# The archive cannot be backfilled, so the order below is not optional:
#   1. commit + push whatever the refresher has appended
#   2. only then fast-forward the working tree
#   3. restart
set -uo pipefail

HOME_DIR="${CARRYDESK_HOME:-$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)}"
cd "$HOME_DIR" || exit 1
RESTART=1
[ "${1:-}" = "--no-restart" ] && RESTART=0

# 1. Preserve the archive FIRST. If this fails, stop -- do not touch the tree.
if ! ./deploy/cron_archive.sh; then
  echo "ARCHIVE STEP FAILED -- refusing to update, so nothing is lost." >&2
  exit 1
fi

# 2. Belt and braces: if anything is still uncommitted, stash rather than discard.
if ! git diff --quiet || ! git diff --cached --quiet; then
  echo "note: uncommitted changes remain; stashing rather than discarding"
  git stash push -u -m "update.sh $(date -u +%FT%TZ)" >/dev/null 2>&1
fi

# 3. Fast-forward. `merge --ff-only` refuses rather than rewriting local history,
#    which is the point: a divergence should be looked at, not steamrolled.
git fetch -q origin || { echo "fetch failed" >&2; exit 1; }
if ! git merge --ff-only -q origin/master; then
  echo "NOT a fast-forward -- local and origin have diverged. Resolve by hand." >&2
  exit 1
fi
chmod +x deploy/*.sh scripts/*.py 2>/dev/null

echo "updated to: $(git log --oneline -1)"
echo "archive:    $(cat data/snapshots/*.jsonl 2>/dev/null | wc -l | tr -d ' ') snapshots"

# 4. Restart.
if [ "$RESTART" = "1" ]; then
  export XDG_RUNTIME_DIR="/run/user/$(id -u)"
  systemctl --user restart carrydesk.service || exit 1
  sleep 12
  printf 'service:    %s\n' "$(systemctl --user is-active carrydesk.service)"
  curl -s --max-time 20 http://127.0.0.1:8000/health | head -c 120; echo
fi
