#!/usr/bin/env bash
# Set or update values in .env without editing it by hand. Safe to run again.
#
#   bash deploy/set-env.sh HEALTHCHECK_URL=https://hc-ping.com/xxxx HEALTHCHECK_BACKUP_URL=https://hc-ping.com/yyyy
#
# Existing keys (including commented-out examples such as "# DOMAIN=...") are
# replaced; keys that are not there yet are appended. The file stays mode 600.

set -euo pipefail
cd "$(cd "$(dirname "$0")/.." && pwd)"
[ -f .env ] || { echo ".env does not exist yet; run deploy/setup-server.sh first (or copy .env.example)." >&2; exit 1; }
[ "$#" -gt 0 ] || { echo "usage: bash deploy/set-env.sh KEY=VALUE [KEY=VALUE ...]" >&2; exit 2; }

for pair in "$@"; do
  case "$pair" in
    [A-Z_]*=*) ;;
    *) echo "not a KEY=VALUE pair (key must be UPPER_CASE): ${pair%%=*}" >&2; exit 2 ;;
  esac
  key="${pair%%=*}"; value="${pair#*=}"
  tmp="$(mktemp)"
  awk -v key="$key" -v value="$value" '
    BEGIN { done = 0 }
    {
      line = $0
      sub(/^# */, "", line)
      split(line, kv, "=")
      if (kv[1] == key && !done) { print key "=" value; done = 1; next }
      if (kv[1] == key && done && $0 !~ /^#/) next      # drop a stale duplicate
      print
    }
    END { if (!done) print key "=" value }
  ' .env > "$tmp"
  cat "$tmp" > .env && rm -f "$tmp"
  echo "set $key"
done
chmod 600 .env
