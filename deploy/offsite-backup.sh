#!/usr/bin/env bash
# Copy the newest database dumps to storage OUTSIDE this server, using rclone.
# A backup that lives on the same disk as the database is not a backup.
#
# One-time setup:
#   1. install rclone (https://rclone.org/install/) and run `rclone config` to add a
#      remote: Backblaze B2, Cloudflare R2, Google Drive, S3, ... (many have a free tier)
#   2. test:   RCLONE_REMOTE=myremote:supermarket-backups bash deploy/offsite-backup.sh
#   3. cron (daily, after the 00:00 UTC dump):
#        30 1 * * *  cd /path/to/supermarket-prices && RCLONE_REMOTE=myremote:supermarket-backups bash deploy/offsite-backup.sh >> /var/log/offsite-backup.log 2>&1
#
# Set HEALTHCHECK_OFFSITE_URL (a healthchecks.io check) to get an alert if this stops running.

set -euo pipefail
: "${RCLONE_REMOTE:?set RCLONE_REMOTE, e.g. myremote:supermarket-backups}"
KEEP_REMOTE_DAYS="${KEEP_REMOTE_DAYS:-30}"

cd "$(cd "$(dirname "$0")/.." && pwd)"
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
