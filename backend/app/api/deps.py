"""Shared FastAPI dependencies for basic API protection."""

from __future__ import annotations

import hmac

from fastapi import Header, HTTPException

from backend.app.core.settings import get_settings


def require_api_key(x_api_key: str | None = Header(default=None, alias="X-API-Key")) -> None:
    """
    Require a matching X-API-Key header.

    If API_KEY is unset in the environment, protected routes return 503
    (fail closed — do not silently allow open access).
    """
    expected = (get_settings().api_key or "").strip()
    if not expected:
        raise HTTPException(
            status_code=503,
            detail="API_KEY is not configured. Set API_KEY in the environment.",
        )
    provided = (x_api_key or "").strip()
    if not provided or not _constant_time_equal(provided, expected):
        raise HTTPException(
            status_code=401,
            detail="Invalid or missing API key. Provide header X-API-Key.",
        )


def _constant_time_equal(left: str, right: str) -> bool:
    left_b = left.encode("utf-8")
    right_b = right.encode("utf-8")
    if len(left_b) != len(right_b):
        return False
    return hmac.compare_digest(left_b, right_b)
