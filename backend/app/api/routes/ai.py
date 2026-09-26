from fastapi import APIRouter, Depends, Request

from ...api.deps import require_api_key
from ...core.rate_limit import limiter
from ...core.settings import settings
from ...schemas.ingestion import (
    AIQueryRequest,
    AIQueryResponse,
    AIReportDraftRequest,
    AIReportDraftResponse,
    AIReportDraftSaveRequest,
    AIReportDraftSaveResponse,
)
from ...services.ai_query_service import run_ai_query
from ...services.ai_report_service import build_report_draft, save_report_draft_state

router = APIRouter(tags=["ai"], dependencies=[Depends(require_api_key)])


@router.post("/ai/query", response_model=AIQueryResponse)
@limiter.limit(settings.api_rate_limit_ai)
def run_ai_sql_query(request: Request, payload: AIQueryRequest) -> AIQueryResponse:
    result = run_ai_query(payload.question)
    return AIQueryResponse(**result)


@router.post("/ai/report-draft", response_model=AIReportDraftResponse)
@limiter.limit(settings.api_rate_limit_ai)
def create_ai_report_draft(
    request: Request, payload: AIReportDraftRequest
) -> AIReportDraftResponse:
    result = build_report_draft(
        project_id=payload.project_id,
        load_batch_id=payload.load_batch_id,
        use_saved_draft=not payload.regenerate_fresh,
    )
    return AIReportDraftResponse(**result)


@router.post("/ai/report-draft/save", response_model=AIReportDraftSaveResponse)
@limiter.limit(settings.api_rate_limit_ai)
def save_ai_report_draft(
    request: Request, payload: AIReportDraftSaveRequest
) -> AIReportDraftSaveResponse:
    result = save_report_draft_state(
        load_batch_id=payload.load_batch_id,
        project_id=payload.project_id,
        source_file_name=payload.source_file_name,
        draft_sections=payload.draft_sections,
    )
    return AIReportDraftSaveResponse(**result)
