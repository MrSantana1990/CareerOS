import logging
import uuid

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest
from sqlalchemy import text
from starlette.responses import Response

from .config import get_settings
from .auth import require_admin
from .career import router as career_router
from .database import SessionLocal, engine
from .logging_config import configure_logging

settings = get_settings()
configure_logging(settings.log_level)
logger = logging.getLogger("careeros.api")

app = FastAPI(title=settings.app_name, version="0.1.0", docs_url="/docs")
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.allowed_origins,
    allow_credentials=False,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
    allow_headers=["Authorization", "Content-Type", "X-Correlation-ID", "X-Organization-Slug"],
)


@app.middleware("http")
async def correlation_id(request: Request, call_next):
    request_id = request.headers.get("X-Correlation-ID", str(uuid.uuid4()))
    response = await call_next(request)
    response.headers["X-Correlation-ID"] = request_id
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    return response


@app.get("/health/live", tags=["health"])
async def live() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/health/ready", tags=["health"])
async def ready() -> JSONResponse:
    checks: dict[str, str] = {}
    try:
        async with engine.connect() as connection:
            await connection.execute(text("SELECT 1"))
        checks["database"] = "ok"
    except Exception:
        logger.exception("readiness_dependency_failed", extra={"dependency": "database"})
        checks["database"] = "unavailable"
    status = 200 if all(value == "ok" for value in checks.values()) else 503
    return JSONResponse({"status": "ok" if status == 200 else "degraded", "checks": checks}, status_code=status)


@app.get("/api/v1/system/status", tags=["system"])
async def system_status() -> dict[str, object]:
    return {
        "name": settings.app_name,
        "environment": settings.app_env,
        "auto_apply_enabled": settings.effective_auto_apply_enabled,
        "minimum_match_score": settings.minimum_match_score,
        "daily_application_target": settings.daily_application_target,
        "blocked_platforms": ["gupy"],
        "product_name": "HelpSystem Carreira",
        "saas_ready": True,
    }


@app.get("/api/v1/workspace", tags=["workspace"])
async def workspace(organization_slug: str = Depends(require_admin)) -> dict[str, object]:
    query = text(
        """
        SELECT o.id, o.name, o.slug,
               (SELECT count(*) FROM jobs j WHERE j.organization_id = o.id) AS jobs,
               (SELECT count(*) FROM applications a WHERE a.organization_id = o.id) AS applications,
               (SELECT count(*) FROM decision_inbox d
                WHERE d.organization_id = o.id AND d.status = 'PENDING') AS pending_decisions
        FROM organizations o
        WHERE o.slug = :slug AND o.deleted_at IS NULL
        """
    )
    async with SessionLocal() as session:
        row = (await session.execute(query, {"slug": organization_slug})).mappings().first()
    if not row:
        raise HTTPException(status_code=404, detail="Organização não encontrada.")
    return dict(row)


app.include_router(career_router)


@app.get("/metrics", include_in_schema=False)
async def metrics() -> Response:
    return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)
