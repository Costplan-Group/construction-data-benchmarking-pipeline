# Thin wrapper: apply numbered migrations via database/migrate.py
# Prerequisites: docker compose up -d (container healthy), sqlcmd on PATH or use container sqlcmd.
#
# Usage (from repo root):
#   .\database\docker\apply_schema.ps1
#   .\database\docker\apply_schema.ps1 -SaPassword 'Your_strong_Password123' -Server 'localhost,1433'

param(
    [string]$Server = $(if ($env:SQL_SERVER) { $env:SQL_SERVER } else { "localhost,1433" }),
    [string]$SaPassword = $(if ($env:MSSQL_SA_PASSWORD) { $env:MSSQL_SA_PASSWORD } elseif ($env:SQL_PWD) { $env:SQL_PWD } else { "Your_strong_Password123" }),
    [string]$Database = $(if ($env:SQL_DB) { $env:SQL_DB } else { "Benchmarking" }),
    [string]$User = $(if ($env:SQL_UID) { $env:SQL_UID } else { "sa" })
)

$ErrorActionPreference = "Stop"
$RepoRoot = Resolve-Path (Join-Path $PSScriptRoot "..\..")

$env:SQL_SERVER = $Server
$env:MSSQL_SA_PASSWORD = $SaPassword
$env:SQL_PWD = $SaPassword
$env:SQL_DB = $Database
$env:SQL_UID = $User

$python = Get-Command python -ErrorAction SilentlyContinue
if (-not $python) {
    $python = Get-Command py -ErrorAction SilentlyContinue
}
if (-not $python) {
    throw "python is required to run migrations"
}

& $python.Source (Join-Path $RepoRoot "database\migrate.py") @args
if ($LASTEXITCODE -ne 0) {
    throw "migrate.py failed with exit code $LASTEXITCODE"
}
