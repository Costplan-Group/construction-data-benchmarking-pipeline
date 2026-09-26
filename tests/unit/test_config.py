"""Unit tests for IngestionConfig connection-string building."""

from __future__ import annotations

import pytest

from ingestion_engine.config import (
    IngestionConfig,
    _strip_env_quotes,
    clear_ingestion_config_cache,
)


def test_strip_env_quotes():
    assert _strip_env_quotes(r'"SERVER\INSTANCE"') == r"SERVER\INSTANCE"
    assert _strip_env_quotes('r"SERVER"') == "SERVER"
    assert _strip_env_quotes(12) == 12


def test_connection_string_explicit_and_trusted():
    explicit = IngestionConfig(
        sql_connection_string="DRIVER={x};SERVER=s;DATABASE=d;",
        _env_file=None,
    )
    assert explicit.connection_string.startswith("DRIVER=")

    trusted = IngestionConfig(
        sql_server="LOCAL",
        sql_db="DemoDB",
        sql_trusted_connection=True,
        sql_trust_server_certificate=True,
        _env_file=None,
    )
    cs = trusted.connection_string
    assert "SERVER=LOCAL" in cs
    assert "DATABASE=DemoDB" in cs
    assert "Trusted_Connection=yes" in cs
    assert "UID=" not in cs

    # Trusted mode must not require credentials even if UID/PWD are present.
    trusted_with_uid = IngestionConfig(
        sql_server="LOCAL",
        sql_db="DemoDB",
        sql_trusted_connection=True,
        sql_uid="sa",
        sql_pwd="",
        _env_file=None,
    )
    assert "Trusted_Connection=yes" in trusted_with_uid.connection_string
    assert "UID=" not in trusted_with_uid.connection_string


def test_connection_string_sql_auth_and_encrypt():
    cfg = IngestionConfig(
        sql_server="S",
        sql_db="D",
        sql_trusted_connection=False,
        sql_uid="u",
        sql_pwd="p",
        sql_encrypt=True,
        _env_file=None,
    )
    cs = cfg.connection_string
    assert "UID=u" in cs
    assert "PWD=p" in cs
    assert "Encrypt=yes" in cs


def test_connection_string_sql_auth_requires_credentials():
    with pytest.raises(ValueError, match="SQL_UID and SQL_PWD"):
        _ = IngestionConfig(
            sql_server="S",
            sql_db="D",
            sql_trusted_connection=False,
            _env_file=None,
        ).connection_string


def test_connection_string_requires_server_db():
    # Server/DB check must win over auth credential checks.
    with pytest.raises(ValueError, match="SQL_SERVER"):
        _ = IngestionConfig(
            sql_server=None,
            sql_db=None,
            sql_trusted_connection=False,
            _env_file=None,
        ).connection_string


def test_clear_ingestion_config_cache():
    clear_ingestion_config_cache()
