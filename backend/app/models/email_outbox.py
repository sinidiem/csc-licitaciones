"""Entidad email_outbox: persistencia del patrón Outbox para correos.

CONTEXT.md §4: el envío de email tiene un efecto externo imposible de incluir
en una transacción SQL. Este tabla permite recuperación segura: se registra
intención (pending), se confirma (sent) o se marca fallo (failed) con
reintentos, sin duplicar envíos ante timeouts ambiguos.
"""

import uuid
from typing import Optional

from pydantic import AwareDatetime
from sqlalchemy import (
    CheckConstraint,
    Column,
    ForeignKey,
    Integer,
    String,
    Text,
    Uuid,
)
from sqlmodel import Field, SQLModel

from app.models.mixins import UuidPkMixin, utcnow


class EmailOutbox(SQLModel, UuidPkMixin, table=True):
    __tablename__ = "email_outbox"

    tender_id: Optional[uuid.UUID] = Field(
        default=None,
        sa_column=Column(Uuid(as_uuid=True), ForeignKey("tenders.id"), nullable=True, index=True),
    )
    email_type: str = Field(
        sa_column=Column(String(50), nullable=False)
    )  # ej: tender_submitted, tender_reminder
    to_email: str = Field(sa_column=Column(String(320), nullable=False))
    subject: str = Field(sa_column=Column(String(300), nullable=False))
    body_html: Optional[str] = Field(default=None, sa_column=Column(Text))

    status: str = Field(
        sa_column=Column(String(20), nullable=False, server_default="pending")
    )  # pending | sent | failed
    attempt_count: int = Field(
        sa_column=Column(Integer, nullable=False, server_default="0")
    )
    next_attempt_at: Optional[AwareDatetime] = Field(default=None)
    provider_message_id: Optional[str] = Field(
        default=None, sa_column=Column(String(200))
    )
    error_summary: Optional[str] = Field(
        default=None, sa_column=Column(Text)
    )  # sin secretos ni datos sensibles

    created_at: AwareDatetime = Field(default_factory=utcnow)
    sent_at: Optional[AwareDatetime] = Field(default=None)

    __table_args__ = (
        CheckConstraint(
            "status IN ('pending', 'sent', 'failed')", name="ck_email_outbox_status"
        ),
        CheckConstraint(
            "attempt_count >= 0", name="ck_email_outbox_attempt_count_non_neg"
        ),
    )

    def __repr__(self) -> str:
        return f"<EmailOutbox {self.email_type} -> {self.to_email} ({self.status})>"