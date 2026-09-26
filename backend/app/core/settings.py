from functools import lru_cache

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

_DEFAULT_CORS_ORIGINS = [
    "http://localhost:5173",
    "http://127.0.0.1:5173",
]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    app_name: str = "Cost Benchmarking API"
    api_prefix: str = "/api"
    app_version: str = "0.1.0"
    cors_origins: list[str] = Field(default_factory=lambda: list(_DEFAULT_CORS_ORIGINS))

    # Comma-separated override, e.g. FASTAPI_CORS_ORIGINS=http://127.0.0.1:5173
    fastapi_cors_origins: str = ""

    # Basic API protection (X-API-Key on /api/ai/* and upload).
    api_key: str | None = None
    upload_max_bytes: int = 20 * 1024 * 1024  # 20 MiB
    api_rate_limit_ai: str = "20/minute"
    api_rate_limit_upload: str = "10/minute"

    # Runtime artifacts (drafts / exports) outside the package. Relative = repo root.
    data_dir: str = "data"

    groq_api_key: str | None = None
    groq_model: str = "openai/gpt-oss-120b"
    groq_temperature_narrative: float = 0.2
    groq_temperature_sql: float = 0.1
    groq_temperature_sql_strict: float = 0.0

    # Dedicated read-only SQL login for AI query execution (no ingestion fallback).
    ai_sql_user: str | None = None
    ai_sql_password: str | None = None
    ai_sql_server: str | None = None
    ai_sql_database: str | None = None
    ai_sql_driver: str = "ODBC Driver 17 for SQL Server"
    ai_sql_max_rows: int = 500
    ai_sql_query_timeout_s: int = 30

    @field_validator("cors_origins", mode="before")
    @classmethod
    def _split_cors(cls, value):
        if value is None or value == "":
            return list(_DEFAULT_CORS_ORIGINS)
        if isinstance(value, str):
            parts = [origin.strip() for origin in value.split(",") if origin.strip()]
            return parts or list(_DEFAULT_CORS_ORIGINS)
        return value

    def model_post_init(self, __context) -> None:
        raw = (self.fastapi_cors_origins or "").strip()
        if raw:
            self.cors_origins = [origin.strip() for origin in raw.split(",") if origin.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()


def clear_settings_cache() -> None:
    get_settings.cache_clear()


settings = get_settings()
