"""Ingestion status and validation enums."""

from __future__ import annotations

from enum import StrEnum


class BatchStatus(StrEnum):
    RECEIVED = "RECEIVED"
    STAGED = "STAGED"
    VALIDATED = "VALIDATED"
    COMMITTED = "COMMITTED"
    FAILED = "FAILED"


class Severity(StrEnum):
    ERROR = "ERROR"
    WARNING = "WARNING"


class ErrorType(StrEnum):
    VALIDATION = "VALIDATION"
    MISSING_COLUMN = "MISSING_COLUMN"
    ROW_COUNT = "ROW_COUNT"
    INVALID_NUMBER = "INVALID_NUMBER"
    DOMAIN = "DOMAIN"
    MISSING_TOTALCOST_SKIPPED = "MISSING_TOTALCOST_SKIPPED"
    DECIMAL_PRECISION = "DECIMAL_PRECISION"
    EXCEPTION = "EXCEPTION"
