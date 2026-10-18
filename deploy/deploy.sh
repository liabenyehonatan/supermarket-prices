#!/usr/bin/env bash
# Update this server to a commit of main and restart what changed. Run on the server (the deploy workflow does it
# over SSH after CI passes on main); safe to run by hand too:
#
#   bash deploy/deploy.sh            # latest origin/main
#   bash deploy/deploy.sh <sha>      # a specific commit that is already on main
#
# The worker is left alone: it may be in the middle of a cycle (it is resumable, but a restart wastes the cycle's
# work). It picks up new code at its next restart: `docker compose up -d --build worker` when no cycle is running.
# Rollback: `git checkout <previous sha>` printed below, then run this script again with that sha.

set -euo pipefail
cd "$(cd "$(dirname "$0")/.." && pwd)"

target="${1:-origin/main}"
case "$target" in
  origin/main|[0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f]*) ;;
  *) echo "not a commit: $target" >&2; exit 2 ;;
esac

DOCKER="docker"
docker info >/dev/null 2>&1 || DOCKER="sudo -n docker"

before="$(git rev-parse HEAD)"
git fetch --quiet origin main
git merge --ff-only "$target"
after="$(git rev-parse HEAD)"
echo "deploying $before -> $after"

if [ "$before" = "$after" ] && [ -z "${FORCE:-}" ]; then
  echo "already up to date"
  exit 0
fi

changed="$(git diff --name-only "$before" "$after")"
services=()
if echo "$changed" | grep -qE '^(app/|main\.py|migrations/|alembic\.ini|requirements.*\.txt|Dockerfile|docker-compose\.yml)'; then
  services+=(api)
fi
if echo "$changed" | grep -qE '^(frontend/|docker-compose\.yml)'; then
  services+=(frontend)
fi

if [ "${#services[@]}" -gt 0 ]; then
  # api first pulls in `migrate` (schema changes run as the owner role before the new api starts)
  $DOCKER compose up -d --build "${services[@]}"
fi
if [ "${#services[@]}" -gt 0 ] || echo "$changed" | grep -qE '^nginx/'; then
  # nginx keeps the old containers' addresses until restarted
  $DOCKER compose restart nginx
fi

# The site must answer: the API through nginx, and a page with its own title (search-engine head tags)
for attempt in $(seq 1 30); do
  if $DOCKER compose exec -T nginx wget -qO- http://localhost/health >/dev/null 2>&1 \
     && $DOCKER compose exec -T nginx wget -qO- http://localhost/promotions 2>/dev/null | grep -q '<title>'; then
    echo "deployed $after (rebuilt: ${services[*]:-nothing}; the worker was not restarted)"
    exit 0
  fi
  sleep 3
done
echo "DEPLOY CHECK FAILED for $after. Previous commit: $before" >&2
$DOCKER compose ps >&2 || true
exit 1
