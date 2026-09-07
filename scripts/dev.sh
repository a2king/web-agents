#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
export DATABASE_URL="${DATABASE_URL:-sqlite:///${ROOT}/data/webagent.db}"
export REDIS_URL="${REDIS_URL:-}"
export WORKER_INLINE="${WORKER_INLINE:-1}"
export DATA_DIR="${DATA_DIR:-${ROOT}/data}"
export PORT="${PORT:-5000}"
mkdir -p "$DATA_DIR"
cd "$ROOT/backend"
uv run python wsgi.py
