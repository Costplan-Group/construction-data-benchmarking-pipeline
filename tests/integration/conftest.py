"""
SQL Server integration tests (Docker).

Skipped unless RUN_SQL_INTEGRATION=1 and the database is reachable.

CI settings:
- SQL_SCHEMA_APPLIED=1: schema was applied by an earlier step; do not run apply scripts.
- SQL_INTEGRATION_STRICT=1: fail instead of skip when SQL is unavailable.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
APPLY_SCHEMA_PS1 = REPO_ROOT / "database" / "docker" / "apply_schema.ps1"
APPLY_SCHEMA_SH = REPO_ROOT / "database" / "docker" / "apply_schema.sh"

# Forced when RUN_SQL_INTEGRATION=1 (overrides local .env for the test process).
DOCKER_SQL_ENV = {
    "SQL_SERVER": "localhost,1433",
    "SQL_DB": "Benchmarking",
    "SQL_DRIVER": os.getenv("SQL_DRIVER") or "ODBC Driver 17 for SQL Server",
    "SQL_TRUSTED_CONNECTION": "false",
    "SQL_UID": "sa",
    "SQL_PWD": os.getenv("MSSQL_SA_PASSWORD") or os.getenv("SQL_PWD") or "Your_strong_Password123",
    "SQL_TRUST_SERVER_CERTIFICATE": "true",
    "SQL_ENCRYPT": "false",
    "PROCESS_ADJUSTMENTS": "0",
    # Clear full-string overrides so built connection string is used.
    "SQL_CONNECTION_STRING": "",
    "AZURE_SQL_CONNECTION_STRING": "",
}


def _env_flag(name: str) -> bool:
    return os.getenv(name, "").strip().lower() in {"1", "true", "yes"}


def _integration_enabled() -> bool:
    return _env_flag("RUN_SQL_INTEGRATION")


def _unavailable(message: str) -> None:
    if _env_flag("SQL_INTEGRATION_STRICT"):
        pytest.fail(message, pytrace=False)
    pytest.skip(message)


@pytest.fixture(scope="session")
def monkeypatch_session():
    from _pytest.monkeypatch import MonkeyPatch

    mp = MonkeyPatch()
    yield mp
    mp.undo()


@pytest.fixture(scope="session")
def sql_env(monkeypatch_session):
    if not _integration_enabled():
        pytest.skip("Set RUN_SQL_INTEGRATION=1 to run SQL integration tests")

    for key, value in DOCKER_SQL_ENV.items():
        monkeypatch_session.setenv(key, value)

    from ingestion_engine.config import clear_ingestion_config_cache

    clear_ingestion_config_cache()
    yield DOCKER_SQL_ENV
    clear_ingestion_config_cache()


def _sql_reachable() -> bool:
    try:
        import pyodbc

        from ingestion_engine.config import IngestionConfig, clear_ingestion_config_cache

        clear_ingestion_config_cache()
        cfg = IngestionConfig(
            sql_server=os.environ["SQL_SERVER"],
            sql_db=os.environ["SQL_DB"],
            sql_driver=os.environ.get("SQL_DRIVER", "ODBC Driver 17 for SQL Server"),
            sql_trusted_connection=False,
            sql_uid=os.environ.get("SQL_UID", "sa"),
            sql_pwd=os.environ.get("SQL_PWD", "Your_strong_Password123"),
            sql_trust_server_certificate=True,
            sql_encrypt=False,
            sql_connection_string=None,
            azure_sql_connection_string=None,
            _env_file=None,
        )
        conn = pyodbc.connect(cfg.connection_string, timeout=5)
        conn.close()
        return True
    except Exception:
        return False


def _apply_schema() -> subprocess.CompletedProcess[str]:
    if sys.platform == "win32":
        command = [
            "powershell",
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(APPLY_SCHEMA_PS1),
        ]
    else:
        command = ["bash", str(APPLY_SCHEMA_SH)]
    return subprocess.run(
        command,
        cwd=str(REPO_ROOT),
        capture_output=True,
        text=True,
        env={**os.environ, **DOCKER_SQL_ENV, "MSSQL_SA_PASSWORD": DOCKER_SQL_ENV["SQL_PWD"]},
    )


@pytest.fixture(scope="session")
def applied_schema(sql_env):
    if _env_flag("SQL_SCHEMA_APPLIED"):
        if not _sql_reachable():
            _unavailable(
                f"SQL Server not reachable on {os.environ['SQL_SERVER']} "
                f"(database {os.environ['SQL_DB']})"
            )
    elif not _sql_reachable():
        result = _apply_schema()
        if result.returncode != 0 or not _sql_reachable():
            detail = (result.stderr or result.stdout or "").strip()
            _unavailable(
                "SQL Server not reachable. Run: docker compose up -d && "
                f".\\database\\docker\\apply_schema.ps1\n{detail}"
            )
    else:
        result = _apply_schema()
        if result.returncode != 0:
            _unavailable(f"Schema apply failed: {result.stderr or result.stdout}")

    from ingestion_engine.config import clear_ingestion_config_cache

    clear_ingestion_config_cache()
    yield


@pytest.fixture
def db_connection(applied_schema):
    import pyodbc

    from ingestion_engine.config import clear_ingestion_config_cache, get_ingestion_config

    clear_ingestion_config_cache()
    cfg = get_ingestion_config()
    conn = pyodbc.connect(cfg.connection_string, timeout=10)
    yield conn
    conn.close()
    clear_ingestion_config_cache()


@pytest.fixture(autouse=True)
def truncate_staging(db_connection):
    """Isolate each test by clearing staging tables."""
    cur = db_connection.cursor()
    tables = [
        "stg.ValidationError",
        "stg.ProjectTenderer",
        "stg.LineItem_L3",
        "stg.Level2",
        "stg.ElementQuants_L2",
        "stg.ProjectQuants",
        "stg.ProjectInformation",
        "stg.Adjustments",
        "stg.LoadBatch",
    ]
    for table in tables:
        try:
            cur.execute(f"DELETE FROM {table}")
        except Exception:
            pass
    db_connection.commit()
    yield
