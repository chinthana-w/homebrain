#!/usr/bin/env bash
# DRAFT ONLY — Homebrain deploy script, run on the Mac home server.
# Idempotent and safe: pulls main (fast-forward only), restarts the
# Docker stack, waits for the health endpoint, prints status.
# It never deletes data, never overwrites .env, and never prunes volumes.
#
# Usage:
#   bash scripts/deploy.sh [checkout-path]
#   HOMEBRAIN_CHECKOUT_PATH=~/projects/homebrain bash scripts/deploy.sh
#
# Called by .github/workflows/deploy.yml (self-hosted runner path),
# or by hand over SSH when testing.

set -euo pipefail

REPO_DIR="${1:-${HOMEBRAIN_CHECKOUT_PATH:-$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)}}"
HEALTH_URL="${HOMEBRAIN_HEALTH_URL:-http://localhost:8787/api/v1/health}"
WAIT_SECONDS="${HOMEBRAIN_HEALTH_WAIT_SECONDS:-120}"

echo "Deploying Homebrain from: $REPO_DIR"
cd "$REPO_DIR"

# --- Sanity checks (fail loudly, change nothing) -------------------
command -v git >/dev/null 2>&1 || { echo "ERROR: git is not installed." >&2; exit 1; }
command -v docker >/dev/null 2>&1 || { echo "ERROR: docker is not installed (is Docker Desktop running?)." >&2; exit 1; }
[ -f docker-compose.yml ] || { echo "ERROR: docker-compose.yml not found in $REPO_DIR." >&2; exit 1; }
[ -f scripts/deploy.sh ] || { echo "ERROR: scripts/deploy.sh not found in $REPO_DIR." >&2; exit 1; }

# Warn (do not fail) if remote access is not locked down yet.
if ! grep -q '^HOMEBRAIN_API_TOKEN=[^[:space:]]' .env 2>/dev/null && ! grep -q '^[[:space:]]*HOMEBRAIN_API_TOKEN:' docker-compose.yml 2>/dev/null; then
  echo "WARNING: HOMEBRAIN_API_TOKEN is not set. Set it before allowing remote access (see DEPLOY.md)."
fi

# --- Pull latest main, fast-forward only ---------------------------
# --ff-only refuses if the Mac has local commits; that is deliberate —
# it stops a deploy rather than silently merging or overwriting work.
echo "Pulling latest main..."
git fetch origin main
git checkout main
git pull --ff-only origin main
echo "Now at: $(git rev-parse --short HEAD) $(git log -1 --format=%s)"

# --- Restart the stack ---------------------------------------------
echo "Starting Docker stack..."
docker compose up -d

# --- Wait for health ------------------------------------------------
echo "Waiting for $HEALTH_URL (up to ${WAIT_SECONDS}s)..."
STARTED_AT=$(date +%s)
until curl --fail --silent "$HEALTH_URL" >/dev/null 2>&1; do
  if [ "$(( $(date +%s) - STARTED_AT ))" -ge "$WAIT_SECONDS" ]; then
    echo "ERROR: Homebrain did not become healthy within ${WAIT_SECONDS}s." >&2
    docker compose ps || true
    docker compose logs --tail=100 homebrain || true
    exit 1
  fi
  sleep 4
done

echo "Homebrain is healthy: $(curl --silent "$HEALTH_URL")"
docker compose ps
echo "Deploy complete."
