#!/usr/bin/env bash
set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$PROJECT_ROOT"

ALEMBIC_CONFIG="$PROJECT_ROOT/alembic.ini"
if [[ ! -f "$ALEMBIC_CONFIG" ]]; then
    echo "alembic.ini not found; skipping migration check."
    exit 0
fi

run_alembic() {
    if command -v uv >/dev/null 2>&1; then
        uv run alembic "$@"
    elif command -v alembic >/dev/null 2>&1; then
        alembic "$@"
    else
        echo "Error: Alembic is not installed. Install project dependencies first." >&2
        exit 1
    fi
}

extract_revision() {
    awk '/^Rev: / { print $2; exit }'
}

HEADS_OUTPUT="$(run_alembic heads --verbose)"
HEAD_REVISION="$(printf '%s\n' "$HEADS_OUTPUT" | extract_revision || true)"

if [[ -z "$HEAD_REVISION" ]]; then
    echo "Unable to determine Alembic head revision; skipping migration check."
    exit 0
fi

CURRENT_OUTPUT="$(run_alembic current --verbose || true)"
CURRENT_REVISION="$(printf '%s\n' "$CURRENT_OUTPUT" | extract_revision || true)"

if [[ -z "$CURRENT_REVISION" ]]; then
    echo "Database has no recorded revision; running migrations..."
    run_alembic upgrade head
    exit 0
fi

if [[ "$CURRENT_REVISION" == "$HEAD_REVISION" ]]; then
    echo "Database already at head revision ($HEAD_REVISION); no migration needed."
    exit 0
fi

echo "Database at revision $CURRENT_REVISION; upgrading to $HEAD_REVISION..."
run_alembic upgrade head
