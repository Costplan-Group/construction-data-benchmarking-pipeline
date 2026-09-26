"""Unit tests for API key dependency."""

from __future__ import annotations

import pytest
from fastapi import HTTPException

from backend.app.api.deps import require_api_key
from backend.app.core.settings import Settings, clear_settings_cache


@pytest.fixture(autouse=True)
def _reset_settings():
    clear_settings_cache()
    yield
    clear_settings_cache()


def test_api_key_missing_config(monkeypatch):
    monkeypatch.setattr(
        "backend.app.api.deps.get_settings",
        lambda: Settings(api_key=None, _env_file=None),
    )
    with pytest.raises(HTTPException) as exc:
        require_api_key(x_api_key="anything")
    assert exc.value.status_code == 503


def test_api_key_rejects_wrong_key(monkeypatch):
    monkeypatch.setattr(
        "backend.app.api.deps.get_settings",
        lambda: Settings(api_key="secret-value", _env_file=None),
    )
    with pytest.raises(HTTPException) as exc:
        require_api_key(x_api_key="wrong")
    assert exc.value.status_code == 401


def test_api_key_accepts_matching_key(monkeypatch):
    monkeypatch.setattr(
        "backend.app.api.deps.get_settings",
        lambda: Settings(api_key="secret-value", _env_file=None),
    )
    require_api_key(x_api_key="secret-value")
