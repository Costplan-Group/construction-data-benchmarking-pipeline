"""Database connection helpers (no import-time DB access)."""

from __future__ import annotations

import pyodbc

from ingestion_engine.config import get_ingestion_config
from ingestion_engine.database import Database


def get_connection():
    """Open a raw pyodbc connection (patch point for characterization tests)."""
    cfg = get_ingestion_config()
    conn = pyodbc.connect(cfg.connection_string)
    lock_timeout_ms = max(0, int(cfg.db_lock_timeout_ms))
    cur = conn.cursor()
    cur.execute(f"SET LOCK_TIMEOUT {lock_timeout_ms}")
    cur.close()
    return conn


def module_db(*, connection_factory=get_connection) -> Database:
    """Short-lived Database that opens via connection_factory."""
    cfg = get_ingestion_config()
    return Database(
        cfg.connection_string,
        cfg.db_lock_timeout_ms,
        connection_factory=connection_factory,
    )
