"""Unit tests for database migration discovery / versioning helpers."""

from __future__ import annotations

from pathlib import Path

import pytest
from database.migrate import Migration, _file_checksum, discover_migrations


def test_discover_migrations_orders_by_version(tmp_path: Path):
    (tmp_path / "002_b.sql").write_text("B", encoding="utf-8")
    (tmp_path / "001_a.sql").write_text("A", encoding="utf-8")
    (tmp_path / "010_j.sql").write_text("J", encoding="utf-8")

    migrations = discover_migrations(tmp_path)
    assert [m.version for m in migrations] == [1, 2, 10]
    assert migrations[0].script_name == "001_a.sql"
    assert migrations[0].checksum == _file_checksum(tmp_path / "001_a.sql")


def test_discover_migrations_rejects_bad_names(tmp_path: Path):
    (tmp_path / "nope.sql").write_text("x", encoding="utf-8")
    with pytest.raises(ValueError, match="NNN_name"):
        discover_migrations(tmp_path)


def test_discover_migrations_rejects_duplicates(tmp_path: Path):
    (tmp_path / "001_a.sql").write_text("a", encoding="utf-8")
    (tmp_path / "001_b.sql").write_text("b", encoding="utf-8")
    with pytest.raises(ValueError, match="Duplicate"):
        discover_migrations(tmp_path)


def test_migration_dataclass():
    path = Path("001_demo.sql")
    m = Migration(version=1, path=path, checksum="abc")
    assert m.script_name == "001_demo.sql"
