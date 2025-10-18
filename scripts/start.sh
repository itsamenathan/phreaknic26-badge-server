#!/usr/bin/env bash
set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

if command -v docker >/dev/null 2>&1 && docker compose version >/dev/null 2>&1; then
    COMPOSE_CMD=(docker compose)
elif command -v docker-compose >/dev/null 2>&1; then
    COMPOSE_CMD=(docker-compose)
else
    echo "Error: docker compose plugin (or docker-compose) is required." >&2
    exit 1
fi

export DATABASE_URL="${DATABASE_URL:-postgresql+asyncpg://badge_user:badge_pass@localhost:5432/badge_db}"
export WORK_BASIC_AUTH_USERNAME="${WORK_BASIC_AUTH_USERNAME:-queue_worker}"
export WORK_BASIC_AUTH_PASSWORD="${WORK_BASIC_AUTH_PASSWORD:-super-secret-password}"
export DB_POOL_MIN_SIZE="${DB_POOL_MIN_SIZE:-1}"
export DB_POOL_MAX_SIZE="${DB_POOL_MAX_SIZE:-10}"

cd "$PROJECT_ROOT"

echo "Starting PostgreSQL container..."
"${COMPOSE_CMD[@]}" -f docker-compose.yml up -d db

echo "Waiting for database to become ready..."
until "${COMPOSE_CMD[@]}" -f docker-compose.yml exec -T db pg_isready \
    -U badge_user -d badge_db >/dev/null 2>&1; do
    sleep 1
done

echo "Database is ready."

APP_CMD=()
RELOAD_ARGS=(
    --reload
    --reload-dir app
    --host 0.0.0.0
    --port 8000
    --proxy-headers
    --forwarded-allow-ips '*'
)

if command -v uv >/dev/null 2>&1; then
    APP_CMD=(uv run uvicorn app.main:app "${RELOAD_ARGS[@]}")
elif command -v uvicorn >/dev/null 2>&1; then
    APP_CMD=(uvicorn app.main:app "${RELOAD_ARGS[@]}")
else
    echo "Error: install 'uv' (preferred) or 'uvicorn' to run the application." >&2
    exit 1
fi

echo "Starting FastAPI app with command: ${APP_CMD[*]}"
exec "${APP_CMD[@]}"
