"""Structured result returned by an ingestion run."""

from __future__ import annotations

from dataclasses import asdict, dataclass

from ingestion_engine.enums import BatchStatus


@dataclass
class IngestionResult:
    load_batch_id: str
    status: BatchStatus
    error_count: int = 0
    source_file_name: str | None = None
    exception: str | None = None
    content_hash: str | None = None
    duplicate: bool = False

    def as_dict(self) -> dict:
        """API-friendly dict (enum values as strings)."""
        payload = asdict(self)
        payload["status"] = (
            self.status.value if isinstance(self.status, BatchStatus) else self.status
        )
        return payload
