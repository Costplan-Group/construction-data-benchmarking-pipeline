"""CLI entry point for Excel ingestion."""

from __future__ import annotations

import argparse
import logging
import sys

from ingestion_engine.enums import BatchStatus
from ingestion_engine.excel_file_ingestion import process_local_file

logger = logging.getLogger(__name__)


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
    )
    parser = argparse.ArgumentParser(
        description="Ingest a tender comparison Excel workbook into SQL Server."
    )
    parser.add_argument("file", help="Path to .xlsx workbook")
    args = parser.parse_args(argv)

    result = process_local_file(args.file)
    logger.info(
        "CLI ingestion result load_batch_id=%s status=%s error_count=%s exception=%s",
        result.load_batch_id,
        result.status.value if hasattr(result.status, "value") else result.status,
        result.error_count,
        result.exception,
        extra={
            "load_batch_id": result.load_batch_id,
            "status": (result.status.value if hasattr(result.status, "value") else result.status),
            "error_count": result.error_count,
        },
    )
    return 0 if result.status == BatchStatus.COMMITTED else 1


if __name__ == "__main__":
    sys.exit(main())
