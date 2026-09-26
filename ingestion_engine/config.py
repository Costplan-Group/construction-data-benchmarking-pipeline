"""Ingestion engine configuration via pydantic-settings."""

from __future__ import annotations

from functools import lru_cache
from typing import Any

from pydantic import computed_field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


def _strip_env_quotes(value: Any) -> Any:
    """Allow .env values like r\"SERVER\\INSTANCE\" or \"SERVER\"."""
    if not isinstance(value, str):
        return value
    text = value.strip()
    if len(text) >= 3 and text[0] == "r" and text[1] in {'"', "'"} and text[-1] == text[1]:
        text = text[2:-1]
    if len(text) >= 2 and text[0] in {'"', "'"} and text[-1] == text[0]:
        text = text[1:-1]
    return text.strip()


class IngestionConfig(BaseSettings):
    """
    Env-driven settings for Excel ingestion and SQL connectivity.

    Prefer a full connection string, or build one from SQL_SERVER + SQL_DB.
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    local_test_file_path: str = ""
    process_adjustments: bool = False
    debug_level2: bool = False
    db_lock_timeout_ms: int = 15000

    sql_server: str | None = None
    sql_db: str | None = None
    sql_driver: str = "ODBC Driver 17 for SQL Server"
    sql_trusted_connection: bool = True
    sql_uid: str | None = None
    sql_pwd: str | None = None
    sql_encrypt: bool | None = None
    sql_trust_server_certificate: bool = True

    # Full ODBC string overrides (either name is accepted).
    sql_connection_string: str | None = None
    azure_sql_connection_string: str | None = None

    @field_validator("sql_server", "sql_db", "sql_uid", "sql_pwd", "sql_driver", mode="before")
    @classmethod
    def _clean_sql_text(cls, value: Any) -> Any:
        cleaned = _strip_env_quotes(value)
        if isinstance(cleaned, str) and cleaned == "":
            return None
        return cleaned

    @field_validator("sql_connection_string", "azure_sql_connection_string", mode="before")
    @classmethod
    def _clean_connection_override(cls, value: Any) -> Any:
        if value is None:
            return None
        cleaned = _strip_env_quotes(value)
        if isinstance(cleaned, str) and cleaned == "":
            return None
        return cleaned

    @field_validator("local_test_file_path", mode="before")
    @classmethod
    def _clean_local_path(cls, value: Any) -> Any:
        if value is None:
            return ""
        cleaned = _strip_env_quotes(value)
        return cleaned if isinstance(cleaned, str) else ""

    @computed_field  # type: ignore[prop-decorator]
    @property
    def connection_string(self) -> str:
        explicit = (self.sql_connection_string or self.azure_sql_connection_string or "").strip()
        if explicit:
            return explicit

        if not self.sql_server or not self.sql_db:
            raise ValueError(
                "Database connection is not configured. Set SQL_CONNECTION_STRING "
                "(or AZURE_SQL_CONNECTION_STRING), or both SQL_SERVER and SQL_DB in .env."
            )

        parts = [
            f"DRIVER={{{self.sql_driver}}};",
            f"SERVER={self.sql_server};",
            f"DATABASE={self.sql_db};",
        ]

        use_trusted = self.sql_trusted_connection and not self.sql_uid
        if use_trusted:
            parts.append("Trusted_Connection=yes;")
        else:
            if not self.sql_uid or not self.sql_pwd:
                raise ValueError(
                    "SQL auth requires SQL_UID and SQL_PWD when SQL_TRUSTED_CONNECTION "
                    "is false or SQL_UID is set."
                )
            parts.append(f"UID={self.sql_uid};")
            parts.append(f"PWD={self.sql_pwd};")

        if self.sql_encrypt is True:
            parts.append("Encrypt=yes;")
        elif self.sql_encrypt is False:
            parts.append("Encrypt=no;")

        if self.sql_trust_server_certificate:
            parts.append("TrustServerCertificate=yes;")

        return "".join(parts)


@lru_cache
def get_ingestion_config() -> IngestionConfig:
    return IngestionConfig()


def clear_ingestion_config_cache() -> None:
    get_ingestion_config.cache_clear()
