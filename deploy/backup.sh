#!/bin/sh
# Nightly logical backup of the database to /backups, keeping BACKUP_KEEP_DAYS.
# Runs inside the `backup` service (postgres image). Copy /backups off the host
# (rclone, rsync, object storage) -- a backup on the same disk is not a backup.
set -eu

: "${PGHOST:?}" "${PGUSER:?}" "${PGPASSWORD:?}" "${PGDATABASE:?}"
KEEP_DAYS="${BACKUP_KEEP_DAYS:-7}"
HOUR="${BACKUP_HOUR_UTC:-0}"

while true; do
  now_h=$(date -u +%H | sed 's/^0//'); now_h=${now_h:-0}
  if [ "$now_h" -eq "$HOUR" ]; then
    stamp=$(date -u +%Y%m%d-%H%M)
    out="/backups/${PGDATABASE}-${stamp}.dump"
    echo "backup: writing $out"
    if pg_dump --format=custom --file="$out.tmp" && mv "$out.tmp" "$out"; then
      echo "backup: ok ($(du -h "$out" | cut -f1))"
      find /backups -name '*.dump' -mtime +"$KEEP_DAYS" -delete
      [ -n "${HEALTHCHECK_BACKUP_URL:-}" ] && wget -q -O /dev/null "$HEALTHCHECK_BACKUP_URL" || true
    else
      echo "backup: FAILED" >&2
      rm -f "$out.tmp"
      [ -n "${HEALTHCHECK_BACKUP_URL:-}" ] && wget -q -O /dev/null "$HEALTHCHECK_BACKUP_URL/fail" || true
    fi
    sleep 3700   # skip the rest of this hour
  fi
  sleep 600
done
