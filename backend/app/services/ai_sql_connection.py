"""Dedicated read-only SQL connection for the AI SQL assistant."""

from __future__ import annotations

import pyodbc
from fastapi import HTTPException

from backend.app.core.settings import Settings, get_settings

AI_SQL_NOT_CONFIGURED = (
    "AI SQL is not configured. Set AI_SQL_USER, AI_SQL_PASSWORD, "
    "AI_SQL_SERVER, and AI_SQL_DATABASE in the environment "
    "(see database/security/001_ai_readonly_login.sql)."
)


def ai_sql_configured(settings: Settings | None = None) -> bool:
    cfg = settings or get_settings()
    return all(
        [
            (cfg.ai_sql_user or "").strip(),
            (cfg.ai_sql_password or "").strip(),
            (cfg.ai_sql_server or "").strip(),
            (cfg.ai_sql_database or "").strip(),
        ]
    )


def require_ai_sql_configured(settings: Settings | None = None) -> Settings:
    cfg = settings or get_settings()
    if not ai_sql_configured(cfg):
        raise HTTPException(status_code=503, detail=AI_SQL_NOT_CONFIGURED)
    return cfg


def build_ai_sql_connection_string(settings: Settings | None = None) -> str:
    cfg = require_ai_sql_configured(settings)
    parts = [
        f"DRIVER={{{cfg.ai_sql_driver}}};",
        f"SERVER={cfg.ai_sql_server};",
        f"DATABASE={cfg.ai_sql_database};",
        f"UID={cfg.ai_sql_user};",
        f"PWD={cfg.ai_sql_password};",
        "TrustServerCertificate=yes;",
    ]
    return "".join(parts)


def get_ai_query_connection(settings: Settings | None = None) -> pyodbc.Connection:
    """
    Open a pyodbc connection using the dedicated AI read-only login.

    Never falls back to the ingestion / Trusted_Connection login.
    """
    cfg = require_ai_sql_configured(settings)
    conn = pyodbc.connect(build_ai_sql_connection_string(cfg), timeout=cfg.ai_sql_query_timeout_s)
    conn.timeout = cfg.ai_sql_query_timeout_s
    return conn
