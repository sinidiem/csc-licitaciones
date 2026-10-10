"""Punto de entrada FastAPI.

Uso (desde backend/):
    ./venv/bin/uvicorn app.main:app --reload
"""

from fastapi import FastAPI

from app.api.v1.endpoints.internal import router as internal_router
from app.api.v1.router import api_router
from app.core.config import settings

app = FastAPI(
    title=settings.app_name,
    version="0.1.0",
    description="Sistema de Gestión de Licitaciones (CSC). API REST /api/v1.",
    docs_url="/docs" if settings.environment != "production" else None,
    redoc_url=None,
    openapi_url="/openapi.json" if settings.environment != "production" else None,
)

app.include_router(api_router, prefix=settings.api_v1_prefix)
# Endpoints internos de cron: ruta plana /internal/... (sin /api/v1),
# ocultos del esquema OpenAPI (include_in_schema=False) y protegidos por
# secreto; el cron del VPS los invoca con header X-Cron-Secret.
app.include_router(internal_router)


@app.get("/", include_in_schema=False)
def root() -> dict:
    return {"app": settings.app_name, "docs": "/docs", "api": settings.api_v1_prefix}