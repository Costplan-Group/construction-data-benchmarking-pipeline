"""CLI entry point for Excel ingestion."""

from __future__ import annotations

import argparse
import sys

from ingestion_engine.excel_file_ingestion import process_local_file


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Ingest a tender comparison Excel workbook into SQL Server."
    )
    parser.add_argument("file", help="Path to .xlsx workbook")
    args = parser.parse_args(argv)

    result = process_local_file(args.file)
    print(result.as_dict())
    from ingestion_engine.enums import BatchStatus

    return 0 if result.status == BatchStatus.COMMITTED else 1


if __name__ == "__main__":
    sys.exit(main())
