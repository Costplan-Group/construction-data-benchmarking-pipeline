#!/usr/bin/env bash
# Apply staging schema, procedures, and DimLocation seed (Linux/macOS / Git Bash).
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
SERVER="${SQL_SERVER:-localhost,1433}"
USER="${SQL_UID:-sa}"
PASSWORD="${MSSQL_SA_PASSWORD:-${SQL_PWD:-Your_strong_Password123}}"
DATABASE="${SQL_DB:-Benchmarking}"

run_sql() {
  local file="$1"
  local db="${2:-$DATABASE}"
  echo "Applying $(basename "$file") -> $db ..."
  if command -v sqlcmd >/dev/null 2>&1; then
    sqlcmd -S "$SERVER" -U "$USER" -P "$PASSWORD" -C -d "$db" -b -i "$file"
  else
    local leaf
    leaf="$(basename "$file")"
    docker cp "$file" "benchmarking-sql:/tmp/$leaf"
    docker exec benchmarking-sql /opt/mssql-tools18/bin/sqlcmd \
      -S localhost -U "$USER" -P "$PASSWORD" -C -d "$db" -b -i "/tmp/$leaf"
  fi
}

run_sql "$ROOT/database/docker/00_create_database.sql" master
run_sql "$ROOT/database/schema/001_staging_schema.sql"
run_sql "$ROOT/database/procedures/001_usp_ValidateBatch.sql"
run_sql "$ROOT/database/procedures/002_usp_CommitBatch.sql"
run_sql "$ROOT/database/docker/003_seed_dim_location.sql"
run_sql "$ROOT/database/docker/004_seed_dim_sector.sql"
echo "Schema apply complete."
