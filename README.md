# cost-benchmarking-poc

POC scaffold for a React frontend, FastAPI backend, Excel ingestion engine, and database assets.

## Overview

This repository is structured so the backend API can be built first, with the frontend added on top once the ingestion and batch-reporting endpoints are stable.

Current backend capabilities:

- upload an Excel workbook for ingestion
- create and track a load batch
- return batch summary and validation errors
- download validation errors as CSV
- ask natural-language database questions via GROQ AI SQL Assistant
- generate and export AI tender comparison report drafts (Word/PDF)

The ingestion flow supports uploaded files and local file testing only.

## Setup

Create and activate a virtual environment from the repository root.

```powershell
py -3 -m venv venv
.\venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

For tests and git hooks (dev tools):

```powershell
python -m pip install -r requirements-dev.txt
```

Dependencies are declared and pinned in `pyproject.toml`. `requirements.txt` / `requirements-dev.txt` are locked exports (runtime vs dev). The full resolver lock is `uv.lock`. Preferred install with [uv](https://github.com/astral-sh/uv):

```powershell
uv sync --group dev
```

After changing pins in `pyproject.toml`, refresh the lock and exports:

```powershell
uv lock
uv export --no-dev --no-hashes -o requirements.txt
uv export --only-group dev --no-hashes -o requirements-dev.txt
```

If PowerShell blocks activation, run:

```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
```

### Full stack (Docker)

One compose file runs SQL Server, the FastAPI backend (ODBC Driver 18, SQL auth), and an nginx frontend.

```powershell
copy .env.docker.example .env.docker
# Edit .env.docker: set MSSQL_SA_PASSWORD and API_KEY (frontend build uses the same API_KEY)

docker compose --env-file .env.docker up --build -d
```

- UI: http://localhost:8080
- API docs: http://localhost:8001/docs
- Health: http://localhost:8080/api/health (via nginx) or http://localhost:8001/api/health

Schema, procedures, and DimLocation / DimSector seeds are applied automatically by the `db-init` service via [`database/migrate.py`](database/migrate.py) (numbered scripts in [`database/migrations/`](database/migrations/), tracked in `dbo.SchemaVersion`). Trusted Connection is not used; the backend connects as `sa` over the Docker network (`sqlserver,1433`).

### Database migrations

Numbered, idempotent SQL scripts live in `database/migrations/` (`001_….sql`, `002_….sql`, …). The runner records each applied version in `dbo.SchemaVersion` (name, sha256 checksum, timestamp) and skips already-applied scripts.

```powershell
# Apply pending migrations (create DB if needed)
python database/migrate.py

# Or via wrappers (same env vars as Docker SQL)
.\database\docker\apply_schema.ps1

# Show applied vs pending
python database/migrate.py --status
```

Add a new change as the next number, e.g. `006_my_change.sql`. Prefer `IF NOT EXISTS` / `CREATE OR ALTER` so scripts stay re-runnable. Reporting views and AI/PBI security scripts stay separate (password parameters) and are not auto-migrated.

Stop / reset:

```powershell
docker compose --env-file .env.docker down
# wipe SQL volume too:
# docker compose --env-file .env.docker down -v
```

### SQL Server integration tests (host pytest)

Unit and characterization tests need no database. Optional end-to-end tests run the real ingestion pipeline against the compose SQL Server from the host.

```powershell
# 1) Start the stack (or at least SQL + db-init)
docker compose --env-file .env.docker up --build -d

# 2) Run integration tests only (schema already applied by db-init)
$env:RUN_SQL_INTEGRATION = "1"
$env:SQL_SCHEMA_APPLIED = "1"
$env:SQL_DRIVER = "ODBC Driver 18 for SQL Server"
pytest tests/integration -m integration
```

Defaults match `docker-compose.yml` / `.env.docker.example` (`sa` / `Your_strong_Password123`, database `Benchmarking`). Override with `MSSQL_SA_PASSWORD` / `SQL_*` env vars if needed.

Without `RUN_SQL_INTEGRATION=1`, integration tests are skipped. Reporting views and AI/PBI security scripts are not applied by this path.

### Secret scanning and code quality hooks

Install git hooks once per clone (after `pip install -r requirements-dev.txt` or `uv sync --group dev`):

```powershell
pre-commit install
```

Hooks on every commit:

- **ruff** / **ruff-format** — lint and format Python
- **mypy** — type-check `backend` (stricter on newer modules)
- **gitleaks** — block secrets from being committed

Useful commands:

```powershell
# Run all hooks on staged files
pre-commit run

# Run all hooks on the whole repo
pre-commit run --all-files

# Individual tools
ruff check .
ruff format .
mypy
pre-commit run gitleaks --all-files

# Emergency skip (use sparingly)
# SKIP=gitleaks git commit -m "message"
```

Config: `.pre-commit-config.yaml`, `.gitleaks.toml`, and `[tool.ruff]` / `[tool.mypy]` in `pyproject.toml`.

### Continuous integration (GitHub Actions)

`.github/workflows/ci.yml` runs on pushes to `main`, on pull requests, and manually (`workflow_dispatch`). It has three parallel jobs:

- **Lint & type-check** — `ruff check`, `ruff format --check`, `mypy`
- **Tests (with SQL Server)** — starts a `mssql/server:2022` service container, installs ODBC Driver 18 + `sqlcmd`, applies migrations with `python database/migrate.py`, then runs unit/characterization tests (with coverage on `ingestion_engine`) and the integration tests
- **Frontend build** — `npm ci && npm run build` in `frontend/`

In CI the integration tests run with `SQL_SCHEMA_APPLIED=1` (skip the in-test schema apply) and `SQL_INTEGRATION_STRICT=1` (fail instead of skip if SQL Server is unreachable). The SA password in the workflow is a throwaway for the ephemeral container, not a real credential.

## Run The Frontend

From the repository root:

```powershell
cd frontend
npm install
npm run dev
```

Open in browser:

- `http://127.0.0.1:5173`

Notes:

- Keep the backend running on `http://127.0.0.1:8001` while using the frontend.
- Vite (`frontend/vite.config.ts`) proxies `/api` to `http://127.0.0.1:8001`.
- CORS defaults allow the Vite origins `http://localhost:5173` and `http://127.0.0.1:5173`.

## Run The Backend

Copy `.env.example` to `.env` and set SQL connectivity (either a full ODBC string or `SQL_SERVER` + `SQL_DB`). The ingestion engine builds the connection string from those values via `IngestionConfig` (`ingestion_engine/config.py`).

Start the FastAPI app from the repository root:

```powershell
python -m uvicorn backend.app.main:app --reload --reload-dir backend --reload-dir ingestion_engine --port 8001
```

Open the API docs in your browser:

- `http://127.0.0.1:8001/docs`
- `http://127.0.0.1:8001/redoc`

Health check:

- `http://127.0.0.1:8001/api/health`

## API protection

Upload and all `/api/ai/*` routes require an API key and are rate-limited.

| Control | Detail |
|---------|--------|
| API key | Header `X-API-Key` must match backend `API_KEY`. Missing config → **503**; wrong/missing key → **401**. |
| Upload size | Rejects bodies larger than `UPLOAD_MAX_BYTES` (default 20 MiB) with **413**. |
| Rate limits | `API_RATE_LIMIT_AI` (default `20/minute`) on AI routes; `API_RATE_LIMIT_UPLOAD` (default `10/minute`) on upload. |

```env
API_KEY=change-me-local-api-key
UPLOAD_MAX_BYTES=20971520
API_RATE_LIMIT_AI=20/minute
API_RATE_LIMIT_UPLOAD=10/minute
```

Frontend: set the same value in `frontend/.env` as `VITE_API_KEY` (see `frontend/.env.example`), then restart Vite.

Batch/health endpoints stay open for local POC batch inspection after upload.

## AI SQL Assistant (GROQ)

The backend includes an AI SQL Assistant that converts natural-language questions
to SQL and executes them against the **committed warehouse** (`dbo.Dim*` / `dbo.Fact*`).
This is the knowledge-base path. **AI Report writing** still reads **staging** for the
latest project batch.

### Environment variables

```env
GROQ_API_KEY=your_groq_api_key

# Dedicated read-only SQL login for AI queries (required — no ingestion fallback)
AI_SQL_USER=ai_readonly
AI_SQL_PASSWORD=your_ai_readonly_password
AI_SQL_SERVER=YOUR_SERVER\INSTANCE
AI_SQL_DATABASE=YOUR_DATABASE
# Optional overrides:
# AI_SQL_MAX_ROWS=500
# AI_SQL_QUERY_TIMEOUT_S=30
```

If any of `AI_SQL_USER`, `AI_SQL_PASSWORD`, `AI_SQL_SERVER`, or `AI_SQL_DATABASE`
are missing, `POST /api/ai/query` returns **503** and does not use the ingestion
SQL connection.

### DBA: create the read-only login

Per environment, a DBA runs [`database/security/001_ai_readonly_login.sql`](database/security/001_ai_readonly_login.sql).
The script is idempotent. The login name is a variable (default `ai_readonly`);
the password is passed at run time and is never stored in git:

```powershell
sqlcmd -S your_server -d your_database -E -i database/security/001_ai_readonly_login.sql -v LoginName=ai_readonly -v Password=REPLACE_ME
```

It grants `SELECT` on all `dbo.Dim*` / `dbo.Fact*` tables. Then set the four
`AI_SQL_*` values in `.env` to match that login and database.

### Backend endpoint

- `POST /api/ai/query`

Example request body:

```json
{
  "question": "Show top 10 Level2 elements by total cost"
}
```

Example response shape:

```json
{
  "question": "Show top 10 Level2 elements by total cost",
  "generated_sql": "SELECT TOP 10 e.L2Name, SUM(f.TotalCost) AS TotalCost FROM dbo.FactElementCostL2 f JOIN dbo.DimElementL2 e ON e.ElementL2Key = f.elementL2Key GROUP BY e.L2Name ORDER BY TotalCost DESC",
  "row_count": 10,
  "truncated": false,
  "answer_text": "...",
  "rows": [
    {
      "L2Name": "Frame",
      "TotalCost": 1050875.0
    }
  ]
}
```

### AI assistant security model

Four layers protect the company database:

1. **sqlglot parse (T-SQL)** — only a single `SELECT` / `WITH ... SELECT` is accepted; `INTO`, DML/DDL, and non-allowlisted functions (e.g. `OPENROWSET`) are rejected. Unparseable SQL is rejected.
2. **Warehouse allowlist** — queries may only reference `dbo.Dim*` and `dbo.Fact*` (committed knowledge-base data). Staging (`stg.*`), BI views, and system tables are rejected. Report generation continues to use staging separately.
3. **Row cap + timeout** — missing or excessive `TOP` is rewritten to `TOP 500` (configurable); the AI connection uses a query timeout; responses include `truncated: true` when capped.
4. **Dedicated read-only SQL login** — execution uses `AI_SQL_*` credentials with `SELECT` on Dim/Fact only. There is no fallback to the ingestion / Trusted_Connection login.

Smoke-check after creating the login: confirm the AI user can `SELECT` from Dim/Fact and cannot read `stg.*` or run writes.

### Frontend usage

The React app includes a dedicated **AI QS Assistant** page where users can:

- enter natural-language questions
- submit the question with the enter button
- inspect generated SQL and returned rows
- see a note when results are truncated

### Suggested query options

Examples you can ask in AI QS Assistant (committed Dim/Fact data):

- List projects and their sector names.
- Show top 10 Level2 elements by total cost across cost sets.
- What is the average GIFA by sector?
- Which projects have the highest grand total?
- Compare measured works vs building works estimate by project.
- Show cost per m2 by project (TotalCost / GIFA).
- List locations and how many projects sit in each.
- Show adjustment amounts by AdjCategory.

## AI Report Draft Endpoint

The backend includes a draft-report endpoint used by the frontend **AI Report Generation** page.

### Backend endpoint

- `POST /api/ai/report-draft`

Example request body (preferred):

```json
{
  "project_id": "P2402"
}
```

Optional fallback request body:

```json
{
  "load_batch_id": "8d5f3dcb-2f4f-4e22-9d30-123456789abc"
}
```

Example response shape:

```json
{
  "project_id": "P2402",
  "load_batch_id": "8d5f3dcb-2f4f-4e22-9d30-123456789abc",
  "source_file_name": "P2402_benchmark.xlsx",
  "report_context": {
    "project": {
      "project_id": "P2402"
    },
    "audit": {
      "load_batch_id": "8d5f3dcb-2f4f-4e22-9d30-123456789abc"
    }
  }
}
```

Saved report drafts and generated Word/PDF exports are written under the configured data directory (default `data/` at the repo root: `data/saved_drafts/` and `data/exports/`). Override with `DATA_DIR` in `.env` (relative to the repo root, or absolute). Templates and branding assets remain under `backend/app/reporting/`.

## Backend API

Current backend endpoints:

- `POST /api/ingestion/upload`
- `GET /api/batches/{load_batch_id}/summary`
- `GET /api/batches/{load_batch_id}/error-counts`
- `GET /api/batches/{load_batch_id}/error-details`
- `GET /api/batches/{load_batch_id}/error-rows`
- `GET /api/batches/{load_batch_id}/download-errors`
- `POST /api/ai/query`
- `POST /api/ai/report-draft`
- `POST /api/ai/report-draft/save`
- `POST /api/ai/report-export/docx`
- `POST /api/ai/report-export/pdf`

## How To Test The Backend

Recommended smoke-test flow:

1. Start the backend server.
2. Open `http://127.0.0.1:8001/docs`.
3. Run `POST /api/ingestion/upload` with a test `.xlsx` file.
4. Copy the returned `load_batch_id`.
5. Use that `load_batch_id` in the batch endpoints.

Example PowerShell upload:

```powershell
curl -X POST "http://127.0.0.1:8001/api/ingestion/upload" `
  -H "accept: application/json" `
  -H "Content-Type: multipart/form-data" `
  -F "file=@C:/path/to/your/test.xlsx"
```

Expected upload response shape:

```json
{
  "load_batch_id": "8d5f3dcb-2f4f-4e22-9d30-123456789abc",
  "status": "COMMITTED",
  "error_count": 0,
  "source_file_name": "test.xlsx"
}
```

Then query the batch:

```powershell
curl "http://127.0.0.1:8001/api/batches/<load_batch_id>/summary"
curl "http://127.0.0.1:8001/api/batches/<load_batch_id>/error-counts"
curl "http://127.0.0.1:8001/api/batches/<load_batch_id>/error-details"
curl "http://127.0.0.1:8001/api/batches/<load_batch_id>/error-rows"
curl -OJ "http://127.0.0.1:8001/api/batches/<load_batch_id>/download-errors"
```

AI query example:

```powershell
curl -X POST "http://127.0.0.1:8001/api/ai/query" `
  -H "Content-Type: application/json" `
  -d "{\"question\":\"Show top 10 Level2 elements by total cost\"}"
```

AI report draft example:

```powershell
curl -X POST "http://127.0.0.1:8001/api/ai/report-draft" `
  -H "Content-Type: application/json" `
  -d "{\"project_id\":\"P2402\"}"
```

## Notes

- The upload form field name must be `file`.
- `load_batch_id` is returned by the upload endpoint and is required for all batch endpoints.
- `project_id` is the preferred key for `POST /api/ai/report-draft`; backend resolves the latest matching batch.
- Validation errors can be inspected via JSON endpoints or downloaded as CSV.
- `error-rows` includes `RowData` for row-level troubleshooting and mapped SUMMARY cell references when available.
- AI query endpoint uses parsed SQL, a Dim/Fact warehouse allowlist, a row cap, and a dedicated read-only login (see AI assistant security model).
- Excel ingestion is implemented under `ingestion_engine/` (`workbook/`, `validation/`, `staging/`, `pipeline.py`). `excel_file_ingestion.py` is a thin compatibility façade; CLI: `python -m benchmarking.ingest path/to/file.xlsx`.
- The frontend scaffold is present but backend-first development is the current focus.

## Power BI reporting (Fact / Dim)

Power BI connects to **committed warehouse** data (`dbo.Dim*` / `dbo.Fact*`) via curated
`dbo.vw_BI_*` views. This is separate from the AI SQL assistant login and from staging
(used only for AI report drafts of the latest project).

### 1) Create / refresh reporting views

Warehouse tables are created by migration `007_warehouse_tables.sql` and loaded by
`stg.usp_CommitBatch` (`008`): `DimProject`, `DimCostSet`, `DimContractor`, `DimElementL2`,
`DimAdjustmentType`, `FactProjectQuant`, `FactElementCostL2`, `FactCostAdjustment`,
`FactCostSetSummary`. The views also expect `DimLocation.DisplayLabel/Country/Region` and
`DimCostSet.IsCurrent/DataStatus`, which the migration schema does not create; add those
columns first on a fresh database.

After Dim/Fact tables exist (e.g. after a successful commit):

```powershell
sqlcmd -S YOUR_SERVER\INSTANCE -d YOUR_DATABASE -E -i database/schema/002_reporting_views.sql
```

Views:

| View | Contents |
|------|----------|
| `dbo.vw_BI_ProjectOverview` | Project + sector + location + current cost set |
| `dbo.vw_BI_Level2CostBreakdown` | L1/L2 element costs (with optional cost/m²) |
| `dbo.vw_BI_AdjustmentSummary` | Cost adjustments by category / subtype |
| `dbo.vw_BI_CostSetSummary` | Measured works / grand total style totals |

### 2) Create the Power BI read-only login

```powershell
sqlcmd -S YOUR_SERVER\INSTANCE -d YOUR_DATABASE -E -i database/security/002_pbi_readonly_login.sql -v LoginName=pbi_readonly -v Password=REPLACE_ME
```

Grants `SELECT` on all `dbo.Dim*` / `dbo.Fact*` tables and on `dbo.vw_BI_*` views.
Does **not** grant `stg.*`. Use a different password from `ai_readonly`.

### 3) Connect Power BI Desktop

1. Get data → **SQL Server**.
2. Server: your instance (e.g. `PRISCILLA_BAIYA\SQLEXPRESS`); Database: your DB.
3. Data Connectivity mode: **Import** (typical) or **DirectQuery**.
4. Authentication: **Database** → user `pbi_readonly` and the password you set.
5. Select the four `vw_BI_*` views first (recommended). Advanced authors can also load Dim/Fact tables.

### 4) Suggested model

- Start with the views as ready-made star slices (keys such as `ProjectKey`, `CostSetKey`, `ElementL2Key` are included for relationships).
- Or load `DimProject`, `DimCostSet`, `DimElementL2`, `DimSector`, `DimLocation` as dimensions and relate them to fact views / tables on those keys.
- Prefer filtering `CostSetIsCurrent = 1` (or `IsCurrent = 1` on `DimCostSet`) when analysing the current cost set only.

### 5) Power BI Service (optional)

To refresh in the Power BI Service against on-premises SQL Server, install an **on-premises data gateway** and map the dataset credentials to `pbi_readonly`. Gateway setup is environment-specific and not scripted in this repo.

## Structure

```text
cost-benchmarking-poc/
├── pyproject.toml
├── uv.lock
├── requirements.txt
├── requirements-dev.txt
├── docker-compose.yml
├── .env.docker.example
├── .dockerignore
├── frontend/
│   ├── Dockerfile
│   ├── nginx.conf
│   ├── src/
│   │   ├── api/
│   │   ├── components/
│   │   ├── pages/
│   │   ├── hooks/
│   │   ├── types/
│   │   ├── App.tsx
│   │   └── main.tsx
│   └── package.json
├── backend/
│   ├── Dockerfile
│   ├── docker-entrypoint.sh
│   ├── app/
│   │   ├── main.py
│   │   ├── api/
│   │   ├── services/
│   │   ├── repositories/
│   │   └── schemas/
├── ingestion_engine/
│   ├── config.py
│   ├── pipeline.py
│   ├── workbook/
│   ├── validation/
│   ├── staging/
│   └── excel_file_ingestion.py
├── benchmarking/
│   └── ingest.py
├── database/
│   ├── migrate.py
│   ├── migrations/
│   ├── schema/
│   ├── procedures/
│   ├── security/
│   └── docker/
├── tests/
│   ├── unit/
│   ├── characterization/
│   └── integration/
└── README.md
```
