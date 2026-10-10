"""Mixins y utilidades compartidas para los modelos SQLModel.

Convenciones (sección 3):
- UUID como identificador.
- timestamptz (UTC) para fechas.
- Decimal para importes (nunca float).
- Auditoría (creador/fecha, modificador/fecha) en entidades mutables.

Nota: NO usar `sa_column=Column(...)` en mixins — el objeto Column se
compartiría entre todas las clases hijas ("Column object already assigned
to Table"). SQLModel ya mapea uuid.UUID -> Uuid (UUID en PostgreSQL) y
AwareDatetime -> UTCDateTime (timezone=True), así que basta la anotación.
"""

import uuid
from datetime import UTC, datetime
from typing import Optional

from pydantic import AwareDatetime
from sqlalchemy import func
from sqlmodel import Field


def utcnow() -> datetime:
    """Instante actual con zona horaria UTC (inequívoco)."""
    return datetime.now(UTC)


class AuditMixin:
    """Campos de auditoría exigidos por el PDF: quién creó/modificó y cuándo.

    `created_by` / `updated_by` apuntan a users.id y son nullables porque
    existen actores de sistema (jobs/cron) que no se autentican como usuario.
    """

    created_at: AwareDatetime = Field(
        default_factory=utcnow,
        sa_column_kwargs={"server_default": func.now()},
    )
    created_by: Optional[uuid.UUID] = Field(
        default=None, foreign_key="users.id"
    )
    updated_at: Optional[AwareDatetime] = Field(default=None)
    updated_by: Optional[uuid.UUID] = Field(
        default=None, foreign_key="users.id"
    )


class UuidPkMixin:
    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)