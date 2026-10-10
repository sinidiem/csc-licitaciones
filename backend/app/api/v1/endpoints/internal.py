"""Endpoints internos de jobs (cron del VPS), protegidos por secreto.

§6-7: el cron invoca `POST /internal/jobs/tenders` con el header
`X-Cron-Secret`; la comparación es segura (`hmac.compare_digest`) y el
secreto jamás se loguea. El router se monta en `app.main` SIN el prefijo
/api/v1 (ruta plana, fuera del alcance del evaluador).

Ejecución idempotente por licitación (ver app/services/jobs.py).
"""

import hmac
from typing import Annotated

from fastapi import APIRouter, Depends, Header, HTTPException, status

from app.api.v1.deps import SessionDep
from app.core.config import settings
from app.services import jobs as jobs_service

router = APIRouter(prefix="/internal/jobs", tags=["internal-jobs"])


def _require_cron_secret(
    x_cron_secret: Annotated[str | None, Header(alias="X-Cron-Secret")] = None,
) -> None:
    if not x_cron_secret or not hmac.compare_digest(x_cron_secret, settings.cron_secret):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Secreto de cron inválido",
        )


@router.post("/tenders", include_in_schema=False, dependencies=[Depends(_require_cron_secret)])
def run_tenders_job(session: SessionDep) -> dict:
    """Vencimientos (active → lost) y recordatorios 48h (un correo único)."""
    return jobs_service.run_tender_jobs(session)