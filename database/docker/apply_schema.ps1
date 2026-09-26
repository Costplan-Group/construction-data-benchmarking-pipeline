# Apply staging schema, procedures, and DimLocation / DimSector seeds to Docker SQL Server.
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
$DockerDir = Join-Path $RepoRoot "database\docker"
$SchemaDir = Join-Path $RepoRoot "database\schema"
$ProcDir = Join-Path $RepoRoot "database\procedures"

function Find-SqlCmd {
    $cmd = Get-Command sqlcmd -ErrorAction SilentlyContinue
    if ($cmd) { return $cmd.Source }
    $candidates = @(
        "${env:ProgramFiles}\Microsoft SQL Server\Client SDK\ODBC\170\Tools\Binn\SQLCMD.EXE",
        "${env:ProgramFiles}\Microsoft SQL Server\Client SDK\ODBC\180\Tools\Binn\SQLCMD.EXE",
        "${env:ProgramFiles(x86)}\Microsoft SQL Server\Client SDK\ODBC\170\Tools\Binn\SQLCMD.EXE"
    )
    foreach ($path in $candidates) {
        if (Test-Path $path) { return $path }
    }
    return $null
}

function Invoke-SqlFile {
    param(
        [Parameter(Mandatory = $true)][string]$SqlCmdPath,
        [Parameter(Mandatory = $true)][string]$FilePath,
        [string]$DbName = $Database
    )
    if (-not (Test-Path $FilePath)) {
        throw "SQL file not found: $FilePath"
    }
    Write-Host "Applying $(Split-Path $FilePath -Leaf) -> $DbName ..."
    & $SqlCmdPath -S $Server -U $User -P $SaPassword -d $DbName -C -b -i $FilePath
    if ($LASTEXITCODE -ne 0) {
        throw "sqlcmd failed ($LASTEXITCODE) for $FilePath"
    }
}

$SqlCmd = Find-SqlCmd
if (-not $SqlCmd) {
    Write-Host "Host sqlcmd not found; using docker exec into benchmarking-sql ..."
    $files = @(
        (Join-Path $DockerDir "00_create_database.sql"),
        (Join-Path $SchemaDir "001_staging_schema.sql"),
        (Join-Path $ProcDir "001_usp_ValidateBatch.sql"),
        (Join-Path $ProcDir "002_usp_CommitBatch.sql"),
        (Join-Path $DockerDir "003_seed_dim_location.sql"),
        (Join-Path $DockerDir "004_seed_dim_sector.sql")
    )
    foreach ($file in $files) {
        $leaf = Split-Path $file -Leaf
        $dest = "/tmp/$leaf"
        Write-Host "Copying $leaf into container ..."
        docker cp $file "benchmarking-sql:$dest"
        $dbArg = if ($leaf -eq "00_create_database.sql") { "master" } else { $Database }
        Write-Host "Applying $leaf -> $dbArg ..."
        docker exec benchmarking-sql /opt/mssql-tools18/bin/sqlcmd `
            -S localhost -U $User -P $SaPassword -C -d $dbArg -b -i $dest
        if ($LASTEXITCODE -ne 0) {
            throw "docker sqlcmd failed ($LASTEXITCODE) for $leaf"
        }
    }
    Write-Host "Schema apply complete."
    exit 0
}

Write-Host "Using sqlcmd: $SqlCmd"
Invoke-SqlFile -SqlCmdPath $SqlCmd -FilePath (Join-Path $DockerDir "00_create_database.sql") -DbName "master"
Invoke-SqlFile -SqlCmdPath $SqlCmd -FilePath (Join-Path $SchemaDir "001_staging_schema.sql")
Invoke-SqlFile -SqlCmdPath $SqlCmd -FilePath (Join-Path $ProcDir "001_usp_ValidateBatch.sql")
Invoke-SqlFile -SqlCmdPath $SqlCmd -FilePath (Join-Path $ProcDir "002_usp_CommitBatch.sql")
Invoke-SqlFile -SqlCmdPath $SqlCmd -FilePath (Join-Path $DockerDir "003_seed_dim_location.sql")
Invoke-SqlFile -SqlCmdPath $SqlCmd -FilePath (Join-Path $DockerDir "004_seed_dim_sector.sql")
Write-Host "Schema apply complete."
