"""Natural-language → guarded SQL → committed Fact/Dim → narrative answer.

AI SQL Assistant = knowledge base over warehouse (Dim/Fact).
AI Report writing stays on staging (latest project) in ai_report_service.
"""

from __future__ import annotations

import json
import re

import pandas as pd
from fastapi import HTTPException

from backend.app.core.settings import get_settings
from backend.app.services.ai_sql_connection import (
    get_ai_query_connection,
    require_ai_sql_configured,
)
from backend.app.services.ai_sql_guard import GuardedSql, guard_ai_sql
from backend.app.services.llm import LLMClient, get_llm_client
from ingestion_engine.connection import get_connection, module_db

MAX_AI_SQL_ATTEMPTS = 3
TECHNICAL_KEY_COLUMN_PATTERN = re.compile(r"key$", re.IGNORECASE)

# Fallback schema if INFORMATION_SCHEMA introspection is unavailable.
WAREHOUSE_SCHEMA_FALLBACK: list[str] = [
    "- dbo.DimProject (ProjectKey, ProjectID, ProjectName, ClientName, LocationKey, SectorKey, SpecLevel, SiteType, NrOfStoreys, TotalHeightGroundToRoof, BasementArea, BasementHeight, ComplexityRating, AccessConstraints, Occupied, Demolition, NewBuild, Refurbishment, HorizontalExtension, VerticalExtension, Basement, Asbestos, Contamination, CreatedAt, UpdatedAt)",
    "- dbo.DimCostSet (CostSetKey, ProjectKey, ProjectID, ContractorKey, CostStage, SourceCostSetIdentifier, BaseDate, Currency, GIFA, SourceFile, UploadedAt, ...)",
    "- dbo.DimSector (SectorKey, SectorCode, SectorName, SortOrder, IsActive)",
    "- dbo.DimLocation (LocationKey, LocationLabel)",
    "- dbo.DimContractor (ContractorKey, ContractorName, IsActive)",
    "- dbo.DimElementL2 (ElementL2Key, ElementSystemKey, L1Code, L1Name, L2Code, L2Name, SortOrder, IsActive)",
    "- dbo.DimAdjustmentType (AdjustmentTypeKey, AdjCategory, AdjSubType)",
    "- dbo.FactElementCostL2 (costSetKey, elementL2Key, TotalCost, CreatedAt, Comment)",
    "- dbo.FactElementQuantL2 (costSetKey, elementL2Key, QuantTypeKey, qty, Unit, comment)",
    "- dbo.FactCostSetSummary (costSetKey, measuredWorksTotal, buildingWorksEstimate, totalInclRisk, totalInclInflation, grandTotal)",
    "- dbo.FactCostAdjustment (CostSetKey, adjustmentTypeKey, Amount, Method, RatePercent, appliedToBase, includedInComparison)",
    "- dbo.FactProjectQuant (FactProjectQuantKey, CostSetKey, LoadBatchID, ProjectQuantCode, ProjectQuantName, Qty, Unit, Comment)",
    "- dbo.FactCostSetProjectQuant (CostSetKey, ProjectQuantTypeKey, qty, unit, comment, createdAt)",
    "- dbo.factLineItem_L3 (LineItemKey, costSetKey, elementL2Key, LineID, itemDescription, Quantity, Unit, Rate, totalCost, RowType)",
]


def _build_warehouse_context() -> str:
    """Prefer live Dim/Fact columns; fall back to a static map."""
    sql = """
        SELECT
            TABLE_SCHEMA,
            TABLE_NAME,
            COLUMN_NAME,
            ORDINAL_POSITION
        FROM INFORMATION_SCHEMA.COLUMNS
        WHERE TABLE_SCHEMA = 'dbo'
          AND (
                TABLE_NAME LIKE 'Dim%'
             OR TABLE_NAME LIKE 'Fact%'
             OR TABLE_NAME LIKE 'fact%'
          )
        ORDER BY TABLE_NAME, ORDINAL_POSITION
    """
    try:
        rows = module_db(connection_factory=get_connection).fetch_all(sql)
    except Exception:
        return "\n".join(WAREHOUSE_SCHEMA_FALLBACK)

    if not rows:
        return "\n".join(WAREHOUSE_SCHEMA_FALLBACK)

    grouped: dict[str, list[str]] = {}
    for row in rows:
        table = f"{row.get('TABLE_SCHEMA')}.{row.get('TABLE_NAME')}"
        grouped.setdefault(table, []).append(str(row.get("COLUMN_NAME")))

    lines = []
    for table_name, cols in grouped.items():
        col_list = ", ".join(cols)
        lines.append(f"- {table_name} ({col_list})")
    return "\n".join(lines)


def _extract_sql(text: str) -> str:
    cleaned = (text or "").strip()
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```[a-zA-Z]*\n?", "", cleaned)
        cleaned = re.sub(r"\n?```$", "", cleaned)
        cleaned = cleaned.strip()
    return cleaned


def _remove_technical_key_columns(rows: list[dict]) -> list[dict]:
    filtered_rows: list[dict] = []
    for row in rows:
        if not isinstance(row, dict):
            filtered_rows.append(row)
            continue
        filtered = {
            key: value
            for key, value in row.items()
            if not TECHNICAL_KEY_COLUMN_PATTERN.search(str(key))
        }
        filtered_rows.append(filtered if filtered else row)
    return filtered_rows


def _fallback_narrative_answer(question: str, rows: list[dict]) -> str:
    if not rows:
        return "I could not find any matching records for that question."
    first_row = rows[0]
    if not isinstance(first_row, dict) or not first_row:
        return f"I found {len(rows)} matching record(s) for your question."
    preview_pairs: list[str] = []
    for key, value in list(first_row.items())[:3]:
        preview_pairs.append(f"{key}={value}")
    preview_text = ", ".join(preview_pairs)
    return (
        f"I found {len(rows)} matching record(s) for your question: '{question}'. "
        f"The top result includes {preview_text}."
    )


def _generate_narrative_answer(
    question: str,
    rows: list[dict],
    row_count: int,
    llm: LLMClient | None = None,
) -> str:
    fallback = _fallback_narrative_answer(question, rows)
    try:
        client = llm or get_llm_client()
    except Exception:
        return fallback

    sample_rows = rows[:20]
    prompt = (
        "Write a concise, client-friendly answer in plain English based ONLY on the SQL result data.\n"
        "Rules:\n"
        "1. Use only facts present in the provided result rows.\n"
        "2. Do not invent values, assumptions, or extra metrics.\n"
        "3. If row_count is 0, state that no matching data was found.\n"
        "4. Keep to 2-4 sentences.\n"
        "5. Do not mention SQL, database internals, or technical implementation.\n\n"
        f"Question:\n{question}\n\n"
        f"row_count: {row_count}\n"
        f"result_rows_sample:\n{json.dumps(sample_rows, ensure_ascii=True)}\n"
    )
    try:
        content = client.complete(
            [
                {
                    "role": "system",
                    "content": "You are a helpful quantity surveying analytics assistant.",
                },
                {"role": "user", "content": prompt},
            ],
            temperature=get_settings().groq_temperature_narrative,
        )
        return content or fallback
    except Exception:
        return fallback


def _sql_system_prompt(*, repair: bool = False) -> str:
    warehouse = _build_warehouse_context()
    repair_blurb = (
        "The previous SQL failed. Fix it using the exact schema below.\n\n" if repair else ""
    )
    return f"""
You are an expert SQL assistant for a construction cost benchmarking knowledge base.
Return only one read-only SQL SELECT statement and nothing else.

{repair_blurb}Committed warehouse tables only (dbo.Dim* and dbo.Fact* — never stg.*, never vw_BI_*):
{warehouse}

Join guidance:
- DimProject.ProjectKey = DimCostSet.ProjectKey
- DimCostSet.CostSetKey = Fact*.CostSetKey / costSetKey (column casing may vary)
- DimProject.SectorKey = DimSector.SectorKey
- DimProject.LocationKey = DimLocation.LocationKey
- FactElementCostL2.elementL2Key = DimElementL2.ElementL2Key
- DimProject.SpecLevel is 'Low'/'Medium'/'High'; SiteType is 'Greenfield'/'Brownfield'; ComplexityRating is an integer 1-5; site flags (NewBuild, Refurbishment, Demolition, Basement, ...) are BIT 0/1
- DimCostSet has one row per (ProjectID, ContractorKey, CostStage); every row is current, so filter by CostStage rather than a current flag
- Cost per m2: TotalCost / NULLIF(GIFA, 0) using FactElementCostL2 (or FactCostSetSummary) with DimCostSet.GIFA

Rules:
1. Return ONLY SQL, no explanation.
2. Use only dbo.Dim* and dbo.Fact* tables and columns listed above.
3. Never generate INSERT/UPDATE/DELETE/DDL/procedure calls or SELECT INTO.
4. Prefer TOP for broad queries (a hard TOP cap is applied server-side if missing).
5. Use LIKE for flexible text search on names/labels.
6. Never invent column names or join keys.
7. In SELECT output, avoid technical key columns ending in "Key" unless explicitly requested.
""".strip()


def generate_sql_from_question(question: str, llm: LLMClient | None = None) -> GuardedSql:
    if not question.strip():
        raise HTTPException(status_code=400, detail="Question cannot be empty.")

    client = llm or get_llm_client()
    content = client.complete(
        [
            {"role": "system", "content": _sql_system_prompt(repair=False)},
            {"role": "user", "content": question},
        ],
        temperature=get_settings().groq_temperature_sql,
    )
    return guard_ai_sql(_extract_sql(content))


def regenerate_sql_from_error(
    question: str,
    failed_sql: str,
    db_error: str,
    llm: LLMClient | None = None,
) -> GuardedSql:
    client = llm or get_llm_client()
    content = client.complete(
        [
            {"role": "system", "content": _sql_system_prompt(repair=True)},
            {
                "role": "user",
                "content": (
                    f"Question: {question}\n\n"
                    f"Failed SQL:\n{failed_sql}\n\n"
                    f"Database error:\n{db_error}\n\n"
                    "Rewrite the SQL so it runs successfully and follows the rules."
                ),
            },
        ],
        temperature=get_settings().groq_temperature_sql_strict,
    )
    return guard_ai_sql(_extract_sql(content))


def _execute_guarded(conn, guarded: GuardedSql, question: str) -> dict:
    settings = get_settings()
    df = pd.read_sql_query(guarded.sql, conn)
    rows = _remove_technical_key_columns(df.to_dict(orient="records"))
    truncated = guarded.truncated or len(rows) >= settings.ai_sql_max_rows
    answer_text = _generate_narrative_answer(question=question, rows=rows, row_count=len(rows))
    return {
        "question": question,
        "generated_sql": guarded.sql,
        "row_count": len(rows),
        "truncated": truncated,
        "answer_text": answer_text,
        "rows": rows,
    }


def run_ai_query(question: str) -> dict:
    require_ai_sql_configured()
    guarded = generate_sql_from_question(question)
    try:
        conn = get_ai_query_connection()
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(
            status_code=503,
            detail=f"AI SQL connection failed: {exc}",
        ) from exc
    try:
        current = guarded
        try:
            return _execute_guarded(conn, current, question)
        except HTTPException:
            raise
        except Exception as first_exc:
            last_exc = first_exc
            for _ in range(1, MAX_AI_SQL_ATTEMPTS):
                repaired = regenerate_sql_from_error(
                    question=question,
                    failed_sql=current.sql,
                    db_error=str(last_exc),
                )
                try:
                    return _execute_guarded(conn, repaired, question)
                except HTTPException:
                    raise
                except Exception as repair_exc:
                    current = repaired
                    last_exc = repair_exc

            raise HTTPException(
                status_code=400, detail=f"Error running query: {last_exc}"
            ) from last_exc
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Error running query: {exc}") from exc
    finally:
        conn.close()
