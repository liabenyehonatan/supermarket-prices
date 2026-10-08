#!/usr/bin/env bash
# One-shot setup for a fresh Linux server (Debian/Ubuntu). Run it from a clone of
# the repository, as a user that can use sudo:
#
#   git clone https://github.com/liabenyehonatan/supermarket-prices.git
#   cd supermarket-prices && bash deploy/setup-server.sh
#
# What it does, in order:
#   1. installs Docker if missing
#   2. creates .env with two random database passwords (never overwrites one)
#   3. builds the image and runs the PREFLIGHT: can this server's IP download
#      from every chain? If not, it stops, before anything else is started.
#   4. starts the whole stack and waits until it is healthy
#
# Flags:  --skip-preflight   do not run the reachability check
#         --force            continue even if the preflight reports problems
#         --env-only         only create .env, then stop (useful for testing)

set -euo pipefail

SKIP_PREFLIGHT=0; FORCE=0; ENV_ONLY=0
for arg in "$@"; do
  case "$arg" in
    --skip-preflight) SKIP_PREFLIGHT=1 ;;
    --force) FORCE=1 ;;
    --env-only) ENV_ONLY=1 ;;
    -h|--help) sed -n '2,19p' "$0"; exit 0 ;;
    *) echo "unknown flag: $arg" >&2; exit 2 ;;
  esac
done

cd "$(cd "$(dirname "$0")/.." && pwd)"
say() { printf '\n== %s\n' "$*"; }
SUDO=""; [ "$(id -u)" -eq 0 ] || SUDO="sudo"

# ── 2. .env ──────────────────────────────────────────────────────────────────
make_env() {
  if [ -f .env ]; then echo ".env already exists; leaving it alone."; return; fi
  [ -f .env.example ] || { echo ".env.example is missing; run this from the repository." >&2; exit 1; }
  local owner api
  owner="$(head -c 32 /dev/urandom | od -An -tx1 | tr -d ' \n')"
  api="$(head -c 32 /dev/urandom | od -An -tx1 | tr -d ' \n')"
  sed -e "s/^POSTGRES_PASSWORD=.*/POSTGRES_PASSWORD=${owner}/" \
      -e "s/^API_DB_PASSWORD=.*/API_DB_PASSWORD=${api}/" .env.example > .env
  chmod 600 .env
  echo "Created .env with fresh random passwords (kept only on this server)."
}

if [ "$ENV_ONLY" -eq 1 ]; then say ".env"; make_env; exit 0; fi

# ── 0. sanity ────────────────────────────────────────────────────────────────
say "Checking the machine"
[ "$(uname -s)" = "Linux" ] || { echo "This script is for Linux servers." >&2; exit 1; }
mem_mb=$(awk '/MemTotal/ {printf "%d", $2/1024}' /proc/meminfo)
free_gb=$(df -BG --output=avail . | tail -1 | tr -dc '0-9')
echo "Memory: ${mem_mb} MB, free disk here: ${free_gb} GB"
[ "$mem_mb" -ge 3500 ] || echo "WARNING: under 4 GB of RAM. Lower PG_SHARED_BUFFERS in .env (e.g. 512MB)."
[ "$free_gb" -ge 30 ]  || echo "WARNING: under 30 GB free disk; the database and one batch of downloads need room."
echo "Public IP / country: $(curl -s -m 8 https://ipinfo.io/json | tr -d '\n ' | sed -E 's/.*"ip":"([^"]*)".*"country":"([^"]*)".*/\1 \2/' || true)"

# ── 1. Docker ────────────────────────────────────────────────────────────────
say "Docker"
if ! command -v docker >/dev/null 2>&1; then
  echo "Installing Docker with the official convenience script (https://get.docker.com)..."
  curl -fsSL https://get.docker.com | $SUDO sh
  $SUDO systemctl enable --now docker
fi
DOCKER="docker"
if ! docker info >/dev/null 2>&1; then DOCKER="$SUDO docker"; fi
$DOCKER compose version >/dev/null || { echo "Docker Compose plugin is missing." >&2; exit 1; }
echo "$($DOCKER --version)"

say ".env"; make_env

# ── 3. build + preflight ─────────────────────────────────────────────────────
say "Building the image (first time takes several minutes)"
$DOCKER compose build worker

if [ "$SKIP_PREFLIGHT" -eq 0 ]; then
  say "Preflight: can this server's IP reach the chains?"
  set +e
  $DOCKER compose run --rm --no-deps -T worker python -m app.scraper.preflight
  status=$?
  set -e
  if [ "$status" -ne 0 ]; then
    echo
    echo "Preflight reported problems (above). A chain that fails here will fail in production too."
    echo "Most likely this provider's IP range is refused. Consider another provider (and ask for a refund)."
    if [ "$FORCE" -eq 0 ]; then echo "Stopping. Re-run with --force to continue anyway."; exit 3; fi
    echo "--force given: continuing."
  fi
fi

# ── 4. start ─────────────────────────────────────────────────────────────────
say "Starting the stack"
# nginx depends on api and frontend, which depend on migrate and db: starting it starts them all.
$DOCKER compose up -d --build --wait nginx
$DOCKER compose up -d worker backup
sleep 5
$DOCKER compose ps
code=$(curl -s -o /dev/null -w '%{http_code}' -m 8 http://localhost/health || true)
echo "GET /health -> ${code}"

cat <<'EOT'

Done. Next:
  * Watch the first cycle (hours; it downloads every chain):
        docker compose logs -f worker
  * Data freshness check (503 until the first cycle finishes):
        curl -i http://localhost/health/data
  * Copy backups off this server (see deploy/offsite-backup.sh) and put TLS in front
    (Cloudflare or Caddy). Details: docs/deployment.md
EOT
