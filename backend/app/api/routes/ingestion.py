from fastapi import APIRouter, Depends, File, Request, UploadFile

from ...api.deps import require_api_key
from ...core.rate_limit import limiter
from ...core.settings import settings
from ...schemas.ingestion import IngestionRunResponse
from ...services.ingestion_service import run_ingestion_from_upload

router = APIRouter(tags=["ingestion"], dependencies=[Depends(require_api_key)])


@router.post("/ingestion/upload", response_model=IngestionRunResponse)
@limiter.limit(settings.api_rate_limit_upload)
async def trigger_ingestion_from_upload(
    request: Request,
    file: UploadFile = File(...),
) -> IngestionRunResponse:
    result = await run_ingestion_from_upload(file)
    return IngestionRunResponse(**result)
