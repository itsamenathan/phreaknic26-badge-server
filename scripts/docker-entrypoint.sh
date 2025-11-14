#!/usr/bin/env bash
set -euo pipefail

PROJECT_ROOT="/app"
cd "$PROJECT_ROOT"

if [[ -x "$PROJECT_ROOT/scripts/migrate-if-needed.sh" ]]; then
    echo "Ensuring database schema is up to date..."
    "$PROJECT_ROOT/scripts/migrate-if-needed.sh"
else
    echo "Migration helper not found; skipping migration check."
fi

if [[ $# -gt 0 ]]; then
    APP_CMD=("$@")
else
    HOST_VALUE="${UVICORN_HOST:-0.0.0.0}"
    PORT_VALUE="${UVICORN_PORT:-8000}"
    APP_CMD=(
        uv
        run
        uvicorn
        app.main:app
        --host "$HOST_VALUE"
        --port "$PORT_VALUE"
        --proxy-headers
        --forwarded-allow-ips '*'
    )
fi

echo "Starting application with command: ${APP_CMD[*]}"
exec "${APP_CMD[@]}"
