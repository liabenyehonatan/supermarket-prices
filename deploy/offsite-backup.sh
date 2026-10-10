#!/usr/bin/env bash
# Copy the newest database dumps to storage OUTSIDE this server, using rclone.
# A backup that lives on the same disk as the database is not a backup.
#
# Backblaze B2 (recommended): put these in .env (deploy/set-env.sh does it safely) and nothing else:
#   B2_BUCKET=<bucket name>
#   B2_APPLICATION_KEY_ID=<key id>        # an application key limited to that one bucket
#   B2_APPLICATION_KEY=<application key>
# No rclone.conf is needed; the script hands the key to rclone through environment variables.
#
# Any other rclone remote: run `rclone config`, then set RCLONE_REMOTE=<remote>:<folder> in .env.
#
# Test:  bash deploy/offsite-backup.sh
# Cron (daily, after the 00:00 UTC dump):
#        30 1 * * *  cd /path/to/supermarket-prices && bash deploy/offsite-backup.sh >> /var/log/offsite-backup.log 2>&1
#
# Set HEALTHCHECK_OFFSITE_URL (a healthchecks.io check) to get an alert if this stops running.

set -euo pipefail

cd "$(cd "$(dirname "$0")/.." && pwd)"

# Under cron the shell has no .env; read just the keys this script needs.
env_value() { [ -f .env ] && grep -E "^$1=" .env | tail -1 | cut -d= -f2- || true; }
B2_BUCKET="${B2_BUCKET:-$(env_value B2_BUCKET)}"
B2_APPLICATION_KEY_ID="${B2_APPLICATION_KEY_ID:-$(env_value B2_APPLICATION_KEY_ID)}"
B2_APPLICATION_KEY="${B2_APPLICATION_KEY:-$(env_value B2_APPLICATION_KEY)}"
if [ -n "$B2_BUCKET" ] && [ -n "$B2_APPLICATION_KEY_ID" ] && [ -n "$B2_APPLICATION_KEY" ]; then
  export RCLONE_CONFIG_B2_TYPE=b2 RCLONE_CONFIG_B2_ACCOUNT="$B2_APPLICATION_KEY_ID" \
         RCLONE_CONFIG_B2_KEY="$B2_APPLICATION_KEY" \
         RCLONE_CONFIG_B2_HARD_DELETE=true       # a delete really deletes; B2 would otherwise only hide the file
  RCLONE_REMOTE="b2:${B2_BUCKET}"
fi
RCLONE_REMOTE="${RCLONE_REMOTE:-$(env_value RCLONE_REMOTE)}"
HEALTHCHECK_OFFSITE_URL="${HEALTHCHECK_OFFSITE_URL:-$(env_value HEALTHCHECK_OFFSITE_URL)}"
KEEP_REMOTE_DAYS="${KEEP_REMOTE_DAYS:-$(env_value KEEP_REMOTE_DAYS)}"; KEEP_REMOTE_DAYS="${KEEP_REMOTE_DAYS:-7}"
: "${RCLONE_REMOTE:?set the B2_* keys (or RCLONE_REMOTE) in .env}"
command -v rclone >/dev/null || { echo "rclone is not installed" >&2; exit 1; }
SUDO=""; docker info >/dev/null 2>&1 || SUDO="sudo"

tmp="$(mktemp -d)"
trap 'rm -rf "$tmp"' EXIT

ping() { [ -n "${HEALTHCHECK_OFFSITE_URL:-}" ] && curl -fsS -m 10 -o /dev/null "${HEALTHCHECK_OFFSITE_URL}$1" || true; }
ping /start
if $SUDO docker compose cp backup:/backups/. "$tmp" \
   && [ -n "$(ls -A "$tmp"/*.dump 2>/dev/null)" ] \
   && rclone copy "$tmp" "$RCLONE_REMOTE" --include "*.dump" --max-age 3d \
   && rclone delete "$RCLONE_REMOTE" --min-age "${KEEP_REMOTE_DAYS}d" --include "*.dump"; then
  echo "offsite backup ok: $(ls "$tmp" | wc -l) local dump(s) considered"
  ping ""
else
  echo "offsite backup FAILED" >&2
  ping /fail
  exit 1
fi
