#!/usr/bin/env bash
# Commit and push the day's snapshot archive.
#
# The archive is the product's only real moat: a timestamped, append-only record
# that the ranking was published in advance. It cannot be backfilled, so this
# running reliably matters more than any feature.
#
#   0 3 * * * ${CARRYDESK_HOME}/deploy/cron_archive.sh
set -uo pipefail

# Defaults to the repo this script lives in, so it works on any host.
HOME_DIR="${CARRYDESK_HOME:-$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)}"
cd "$HOME_DIR" || exit 1

# Deploy key path comes from .env so rotating the key never means editing code.
# Unset: fall back to whatever ssh/git is already configured.
if [ -f "$HOME_DIR/.env" ]; then
  set -a; . "$HOME_DIR/.env"; set +a
fi
if [ -n "${CARRYDESK_DEPLOY_KEY:-}" ]; then
  export GIT_SSH_COMMAND="ssh -i ${CARRYDESK_DEPLOY_KEY} -o IdentitiesOnly=yes"
fi

# Refuse to run off master. A failed rebase once left this checkout in detached
# HEAD, where commits land nowhere and pushes silently do nothing -- the archive
# would have looked healthy while quietly not being preserved.
branch="$(git rev-parse --abbrev-ref HEAD 2>/dev/null || echo unknown)"
if [ "$branch" != "master" ]; then
  echo "$(date -u +%FT%TZ) REFUSING: on '$branch', not master. Archive NOT committed." >&2
  exit 1
fi

# -f because data/snapshots/*.jsonl is gitignored for local dev. On the server
# it is the asset, and this is the one place that override is correct.
git add -f data/snapshots/*.jsonl 2>/dev/null

if git diff --cached --quiet 2>/dev/null; then
  exit 0   # nothing new; not an error
fi

n="$(git diff --cached --numstat | wc -l | tr -d ' ')"
git -c user.name="carrydesk" -c user.email="carrydesk@localhost" \
    commit -q -m "archive $(date -u +%F): $n snapshot file(s)" || exit 1
git push -q origin master || exit 1
