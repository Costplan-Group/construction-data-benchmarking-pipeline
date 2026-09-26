#!/usr/bin/env bash
# Wait for SQL Server, then apply numbered migrations.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
SERVER="${SQL_SERVER:-sqlserver,1433}"
USER="${SQL_UID:-sa}"
PASSWORD="${MSSQL_SA_PASSWORD:-${SQL_PWD:-Your_strong_Password123}}"

export PATH="/opt/mssql-tools18/bin:${PATH}"

echo "Waiting for SQL Server at ${SERVER} ..."
for attempt in $(seq 1 60); do
  if sqlcmd -S "$SERVER" -U "$USER" -P "$PASSWORD" -C -Q "SELECT 1" -b -o /dev/null 2>/dev/null; then
    echo "SQL Server is ready."
    break
  fi
  if [[ "$attempt" -eq 60 ]]; then
    echo "Timed out waiting for SQL Server." >&2
    exit 1
  fi
  sleep 2
done

bash "$ROOT/database/docker/apply_schema.sh"
