from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware

from .api.routes.ai import router as ai_router
from .api.routes.batches import router as batches_router
from .api.routes.health import router as health_router
from .api.routes.ingestion import router as ingestion_router
from .api.routes.reports import router as reports_router
from .core.rate_limit import limiter
from .core.settings import settings

app = FastAPI(
    title=settings.app_name,
    version=settings.app_version,
    description="API layer for the Excel ingestion pipeline and validation output.",
)

app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
app.add_middleware(SlowAPIMiddleware)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health_router, prefix=settings.api_prefix)
app.include_router(ingestion_router, prefix=settings.api_prefix)
app.include_router(batches_router, prefix=settings.api_prefix)
app.include_router(ai_router, prefix=settings.api_prefix)
app.include_router(reports_router, prefix=settings.api_prefix)
