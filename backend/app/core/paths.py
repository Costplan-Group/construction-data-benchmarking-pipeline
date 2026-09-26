"""Resolve repo-root and runtime data directories (drafts / exports)."""

from __future__ import annotations

from pathlib import Path

from backend.app.core.settings import get_settings

# backend/app/core/paths.py → repo root is parents[3]
REPO_ROOT = Path(__file__).resolve().parents[3]


def get_data_dir() -> Path:
    """
    Absolute data directory for runtime artifacts.

    DATA_DIR may be absolute or relative to the repository root (default: data/).
    """
    raw = (get_settings().data_dir or "data").strip() or "data"
    path = Path(raw)
    if not path.is_absolute():
        path = REPO_ROOT / path
    return path.resolve()


def get_saved_drafts_dir() -> Path:
    return get_data_dir() / "saved_drafts"


def get_exports_dir() -> Path:
    return get_data_dir() / "exports"
