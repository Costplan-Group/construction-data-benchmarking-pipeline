from fastapi import APIRouter, Depends, Request
from fastapi.responses import FileResponse

from ...api.deps import require_api_key
from ...core.rate_limit import limiter
from ...core.settings import settings
from ...schemas.ingestion import AIReportExportRequest
from ...services.report_export_service import export_report_docx, export_report_pdf

router = APIRouter(tags=["reports"], dependencies=[Depends(require_api_key)])


@router.post("/ai/report-export/docx")
@limiter.limit(settings.api_rate_limit_ai)
def export_ai_report_docx(request: Request, payload: AIReportExportRequest) -> FileResponse:
    output_path = export_report_docx(payload.model_dump())
    return FileResponse(
        path=output_path,
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        filename=output_path.name,
    )


@router.post("/ai/report-export/pdf")
@limiter.limit(settings.api_rate_limit_ai)
def export_ai_report_pdf(request: Request, payload: AIReportExportRequest) -> FileResponse:
    output_path = export_report_pdf(payload.model_dump())
    return FileResponse(
        path=output_path,
        media_type="application/pdf",
        filename=output_path.name,
    )
