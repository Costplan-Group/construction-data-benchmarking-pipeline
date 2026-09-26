#!/usr/bin/env bash
# Thin wrapper: apply numbered migrations via database/migrate.py
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
export PATH="/opt/mssql-tools18/bin:${PATH}"

if command -v python >/dev/null 2>&1; then
  PY=python
elif command -v python3 >/dev/null 2>&1; then
  PY=python3
else
  echo "python is required to run migrations" >&2
  exit 1
fi

exec "$PY" "$ROOT/database/migrate.py" "$@"
