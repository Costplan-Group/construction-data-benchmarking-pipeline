"""
Apply numbered SQL migrations with dbo.SchemaVersion tracking.

Usage (from repo root):
  python database/migrate.py
  python database/migrate.py --status

Env (same as apply_schema / Docker):
  SQL_SERVER, SQL_UID, SQL_PWD or MSSQL_SA_PASSWORD, SQL_DB
"""

from __future__ import annotations

import argparse
import hashlib
import os
import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MIGRATIONS_DIR = Path(__file__).resolve().parent / "migrations"
CREATE_DB_SCRIPT = Path(__file__).resolve().parent / "docker" / "00_create_database.sql"

VERSION_TABLE_SQL = """
IF OBJECT_ID(N'dbo.SchemaVersion', N'U') IS NULL
BEGIN
    CREATE TABLE dbo.SchemaVersion (
        Version     INT            NOT NULL PRIMARY KEY,
        ScriptName  NVARCHAR(255)  NOT NULL,
        Checksum    CHAR(64)       NOT NULL,
        AppliedAt   DATETIME2(0)   NOT NULL
            CONSTRAINT DF_SchemaVersion_AppliedAt DEFAULT (SYSUTCDATETIME())
    );
END;
"""

RECORD_SQL = """
IF NOT EXISTS (SELECT 1 FROM dbo.SchemaVersion WHERE Version = {version})
BEGIN
    INSERT INTO dbo.SchemaVersion (Version, ScriptName, Checksum)
    VALUES ({version}, N'{script_name}', '{checksum}');
END;
"""

_VERSION_RE = re.compile(r"^(\d+)[_.].+\.sql$", re.IGNORECASE)


@dataclass(frozen=True)
class Migration:
    version: int
    path: Path
    checksum: str

    @property
    def script_name(self) -> str:
        return self.path.name


def _env(name: str, default: str = "") -> str:
    return (os.getenv(name) or default).strip()


def _connection_settings() -> tuple[str, str, str, str]:
    server = _env("SQL_SERVER", "localhost,1433")
    user = _env("SQL_UID", "sa")
    password = _env("MSSQL_SA_PASSWORD") or _env("SQL_PWD") or "Your_strong_Password123"
    database = _env("SQL_DB", "Benchmarking")
    return server, user, password, database


def _file_checksum(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def discover_migrations(migrations_dir: Path = MIGRATIONS_DIR) -> list[Migration]:
    if not migrations_dir.is_dir():
        raise FileNotFoundError(f"Migrations directory not found: {migrations_dir}")

    found: list[Migration] = []
    for path in sorted(migrations_dir.glob("*.sql")):
        match = _VERSION_RE.match(path.name)
        if not match:
            raise ValueError(f"Migration filename must be NNN_name.sql (got {path.name!r})")
        version = int(match.group(1))
        found.append(Migration(version=version, path=path, checksum=_file_checksum(path)))

    versions = [m.version for m in found]
    if len(versions) != len(set(versions)):
        raise ValueError(f"Duplicate migration versions in {migrations_dir}")

    return sorted(found, key=lambda m: m.version)


def _sqlcmd_base(server: str, user: str, password: str) -> list[str]:
    import shutil

    if shutil.which("sqlcmd"):
        return ["sqlcmd", "-S", server, "-U", user, "-P", password, "-C", "-b", "-I"]

    # Fallback: sqlcmd inside the compose SQL container.
    if shutil.which("docker"):
        return [
            "docker",
            "exec",
            "-i",
            "benchmarking-sql",
            "/opt/mssql-tools18/bin/sqlcmd",
            "-S",
            "localhost",
            "-U",
            user,
            "-P",
            password,
            "-C",
            "-b",
            "-I",
        ]

    raise RuntimeError(
        "Neither sqlcmd nor docker is available on PATH. "
        "Install mssql-tools or start the compose SQL container."
    )


def _run_sqlcmd(
    base: list[str],
    *,
    database: str,
    query: str | None = None,
    input_file: Path | None = None,
) -> None:
    cmd = [*base, "-d", database]
    if input_file is not None:
        if base[0] == "docker":
            # Stream file through docker exec -i so we don't need docker cp.
            with input_file.open("rb") as handle:
                result = subprocess.run(cmd, input=handle.read(), capture_output=True)
        else:
            result = subprocess.run([*cmd, "-i", str(input_file)], capture_output=True)
    else:
        assert query is not None
        result = subprocess.run([*cmd, "-Q", query], capture_output=True)

    if result.returncode != 0:
        stderr = (result.stderr or b"").decode("utf-8", errors="replace")
        stdout = (result.stdout or b"").decode("utf-8", errors="replace")
        detail = (stderr or stdout).strip() or f"exit {result.returncode}"
        raise RuntimeError(detail)


def _sqlcmd_available(base: list[str]) -> bool:
    try:
        result = subprocess.run(
            [*base, "-d", "master", "-Q", "SELECT 1"],
            capture_output=True,
            timeout=30,
        )
        return result.returncode == 0
    except (FileNotFoundError, subprocess.TimeoutExpired, OSError):
        return False


def ensure_database(base: list[str], create_db_script: Path = CREATE_DB_SCRIPT) -> None:
    if not create_db_script.is_file():
        raise FileNotFoundError(f"Missing create-database script: {create_db_script}")
    print(f"Ensuring database exists ({create_db_script.name}) ...")
    _run_sqlcmd(base, database="master", input_file=create_db_script)


def ensure_version_table(base: list[str], database: str) -> None:
    _run_sqlcmd(base, database=database, query=VERSION_TABLE_SQL)


def applied_versions(base: list[str], database: str) -> dict[int, str]:
    query = "SET NOCOUNT ON; SELECT Version, Checksum FROM dbo.SchemaVersion ORDER BY Version;"
    cmd = [*base, "-d", database, "-Q", query, "-h", "-1", "-W"]
    result = subprocess.run(cmd, capture_output=True)
    if result.returncode != 0:
        stderr = (result.stderr or b"").decode("utf-8", errors="replace")
        stdout = (result.stdout or b"").decode("utf-8", errors="replace")
        raise RuntimeError((stderr or stdout).strip() or "failed to read SchemaVersion")

    rows: dict[int, str] = {}
    text = (result.stdout or b"").decode("utf-8", errors="replace")
    for line in text.splitlines():
        parts = line.split()
        if len(parts) >= 2 and parts[0].isdigit() and len(parts[1]) == 64:
            rows[int(parts[0])] = parts[1].lower()
    return rows


def record_migration(base: list[str], database: str, migration: Migration) -> None:
    safe_name = migration.script_name.replace("'", "''")
    query = RECORD_SQL.format(
        version=migration.version,
        script_name=safe_name,
        checksum=migration.checksum,
    )
    _run_sqlcmd(base, database=database, query=query)


def migrate(
    *,
    migrations_dir: Path = MIGRATIONS_DIR,
    dry_run: bool = False,
    status_only: bool = False,
) -> int:
    server, user, password, database = _connection_settings()
    base = _sqlcmd_base(server, user, password)

    if not _sqlcmd_available(base):
        print(
            "Cannot reach SQL Server with sqlcmd. "
            f"Tried server={server!r} user={user!r} database={database!r}.",
            file=sys.stderr,
        )
        return 2

    migrations = discover_migrations(migrations_dir)

    if not dry_run:
        ensure_database(base)
        ensure_version_table(base, database)

    applied = {} if dry_run else applied_versions(base, database)

    if status_only or dry_run:
        print(f"Database: {database} @ {server}")
        for migration in migrations:
            state = "applied" if migration.version in applied else "pending"
            if migration.version in applied and applied[migration.version] != migration.checksum:
                state = "DRIFT"
            print(f"  {migration.version:04d}  {state:8}  {migration.script_name}")
        if status_only:
            return 0

    pending = [m for m in migrations if m.version not in applied]
    if not pending:
        print("No pending migrations.")
        return 0

    for migration in pending:
        if migration.version in applied:
            continue
        print(f"Applying {migration.script_name} ...")
        if dry_run:
            continue
        _run_sqlcmd(base, database=database, input_file=migration.path)
        record_migration(base, database, migration)
        print(f"  recorded version {migration.version}")

    # Detect checksum drift on already-applied scripts.
    for migration in migrations:
        if migration.version in applied and applied[migration.version] != migration.checksum:
            print(
                f"WARNING: checksum drift for {migration.script_name} "
                f"(db={applied[migration.version][:12]}… file={migration.checksum[:12]}…)",
                file=sys.stderr,
            )

    print("Migrations complete.")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Apply numbered SQL migrations.")
    parser.add_argument(
        "--migrations-dir",
        type=Path,
        default=MIGRATIONS_DIR,
        help="Directory of NNN_name.sql files",
    )
    parser.add_argument(
        "--status",
        action="store_true",
        help="Show applied/pending migrations and exit",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="List pending migrations without applying",
    )
    args = parser.parse_args(argv)
    try:
        return migrate(
            migrations_dir=args.migrations_dir,
            dry_run=args.dry_run,
            status_only=args.status,
        )
    except Exception as exc:
        print(f"Migration failed: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
