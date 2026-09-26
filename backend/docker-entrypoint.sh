#!/usr/bin/env bash
set -euo pipefail
exec uvicorn backend.app.main:app --host 0.0.0.0 --port 8001
