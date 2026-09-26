"""Shared SQL Server access for ingestion (one connection per batch when held)."""

from __future__ import annotations

from collections.abc import Callable, Iterator
from contextlib import contextmanager
from typing import Any

import pyodbc

from ingestion_engine.config import get_ingestion_config

ConnectionFactory = Callable[[], Any]


class Database:
    """
    Thin pyodbc wrapper.

    Prefer holding one instance per ingestion batch and using transaction()
    around staging + SQL validate/commit. Module-level helpers may still
    construct short-lived instances during the migration façade period.
    """

    def __init__(
        self,
        connection_string: str | None = None,
        lock_timeout_ms: int = 15000,
        *,
        connection_factory: ConnectionFactory | None = None,
    ):
        self._connection_string = connection_string
        self._lock_timeout_ms = max(0, int(lock_timeout_ms))
        self._connection_factory = connection_factory
        self._conn: Any | None = None
        self._in_transaction = False

    @classmethod
    def from_config(cls, *, connection_factory: ConnectionFactory | None = None) -> Database:
        cfg = get_ingestion_config()
        return cls(
            cfg.connection_string,
            cfg.db_lock_timeout_ms,
            connection_factory=connection_factory,
        )

    def connect(self) -> Any:
        """Open a new connection (does not store it on the instance)."""
        if self._connection_factory is not None:
            return self._connection_factory()
        if not self._connection_string:
            raise ValueError("Database requires connection_string or connection_factory.")
        conn = pyodbc.connect(self._connection_string)
        cur = conn.cursor()
        cur.execute(f"SET LOCK_TIMEOUT {self._lock_timeout_ms}")
        cur.close()
        return conn

    def _acquire(self) -> tuple[Any, bool]:
        """Return (connection, should_close)."""
        if self._conn is not None:
            return self._conn, False
        return self.connect(), True

    def execute(self, sql: str, params: Any = None, *, commit: bool | None = None) -> None:
        should_commit = (not self._in_transaction) if commit is None else commit
        conn, should_close = self._acquire()
        try:
            cur = conn.cursor()
            if params is not None:
                cur.execute(sql, params)
            else:
                cur.execute(sql)
            cur.close()
            if should_commit:
                conn.commit()
        finally:
            if should_close and not self._in_transaction:
                conn.close()

    def fetch_one(self, sql: str, params: Any = None) -> Any:
        conn, should_close = self._acquire()
        try:
            cur = conn.cursor()
            if params is not None:
                cur.execute(sql, params)
            else:
                cur.execute(sql)
            row = cur.fetchone()
            cur.close()
            return row
        finally:
            if should_close and not self._in_transaction:
                conn.close()

    def fetch_all(self, sql: str, params: Any = None) -> list[dict]:
        conn, should_close = self._acquire()
        try:
            cur = conn.cursor()
            if params is not None:
                cur.execute(sql, params)
            else:
                cur.execute(sql)
            columns = [c[0] for c in cur.description] if cur.description else []
            rows = cur.fetchall()
            cur.close()
            return [dict(zip(columns, row, strict=False)) for row in rows]
        finally:
            if should_close and not self._in_transaction:
                conn.close()

    def commit(self) -> None:
        if self._conn is not None:
            self._conn.commit()

    def rollback(self) -> None:
        if self._conn is not None:
            self._conn.rollback()

    def close(self) -> None:
        if self._conn is not None:
            try:
                self._conn.close()
            finally:
                self._conn = None
                self._in_transaction = False

    def open(self) -> Database:
        """Hold a single connection on this instance until close()."""
        if self._conn is None:
            self._conn = self.connect()
        return self

    @property
    def connection(self) -> Any:
        """Active pyodbc connection when open(); otherwise opens transiently for callers that need it."""
        if self._conn is None:
            return self.connect()
        return self._conn

    @contextmanager
    def transaction(self) -> Iterator[Database]:
        """
        Run work on one connection; commit on success, rollback on error.
        Nested use reuses the same connection without nested SQL transactions.
        """
        outer = self._conn is not None
        if not outer:
            self.open()
        already = self._in_transaction
        self._in_transaction = True
        try:
            yield self
            if not already:
                self.commit()
        except Exception:
            if not already:
                self.rollback()
            raise
        finally:
            self._in_transaction = already
            if not outer and not already:
                self.close()
