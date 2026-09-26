"""Unit tests for API key dependency."""

from __future__ import annotations

import pytest
from fastapi import HTTPException

from backend.app.api.deps import require_api_key
from backend.app.core.settings import clear_settings_cache, get_settings


@pytest.fixture(autouse=True)
def _reset_settings(monkeypatch):
    clear_settings_cache()
    yield
    clear_settings_cache()


def test_api_key_missing_config(monkeypatch):
    monkeypatch.delenv("API_KEY", raising=False)
    clear_settings_cache()
    with pytest.raises(HTTPException) as exc:
        require_api_key(x_api_key="anything")
    assert exc.value.status_code == 503


def test_api_key_rejects_wrong_key(monkeypatch):
    monkeypatch.setenv("API_KEY", "secret-value")
    clear_settings_cache()
    with pytest.raises(HTTPException) as exc:
        require_api_key(x_api_key="wrong")
    assert exc.value.status_code == 401


def test_api_key_accepts_matching_key(monkeypatch):
    monkeypatch.setenv("API_KEY", "secret-value")
    clear_settings_cache()
    assert get_settings().api_key == "secret-value"
    require_api_key(x_api_key="secret-value")
