"""Entidad tender_status_history: historial inmutable de transiciones.

Cada cambio de estado genera un registro: estado anterior, estado nuevo,
actor (usuario o sistema), razón, fecha/hora y fuente (user|system).
`from_status` es NULL cuando se crea el borrador (no hay estado previo).
`actor_user_id` es NULL solo cuando el actor es el sistema (jobs).
"""

import uuid
from typing import Optional

from pydantic import AwareDatetime
from sqlalchemy import (
    CheckConstraint,
    Column,
    ForeignKey,
    String,
    Text,
    Uuid,
)
from sqlmodel import Field, Relationship, SQLModel

from app.models.mixins import UuidPkMixin, utcnow
from app.models.tender import STATUS_ALLOWED, STATUS_SQL


class TenderStatusHistory(SQLModel, UuidPkMixin, table=True):
    __tablename__ = "tender_status_history"

    tender_id: uuid.UUID = Field(
        sa_column=Column(Uuid(as_uuid=True), ForeignKey("tenders.id"), nullable=False, index=True)
    )
    from_status: Optional[str] = Field(
        default=None, sa_column=Column(String(20), nullable=True)
    )
    to_status: str = Field(sa_column=Column(String(20), nullable=False))
    actor_user_id: Optional[uuid.UUID] = Field(
        default=None, foreign_key="users.id", sa_column_kwargs={"nullable": True}
    )
    reason: Optional[str] = Field(default=None, sa_column=Column(Text))
    source: str = Field(
        sa_column=Column(String(10), nullable=False, server_default="user")
    )
    created_at: AwareDatetime = Field(default_factory=utcnow)

    tender: "Tender" = Relationship(back_populates="history")

    __table_args__ = (
        CheckConstraint(
            f"to_status IN ({STATUS_SQL})", name="ck_tender_status_history_to_status"
        ),
        CheckConstraint(
            f"from_status IS NULL OR from_status IN ({STATUS_SQL})",
            name="ck_tender_status_history_from_status",
        ),
        CheckConstraint(
            "source IN ('user', 'system')", name="ck_tender_status_history_source"
        ),
    )

    def __repr__(self) -> str:
        return f"<History {self.from_status} -> {self.to_status} ({self.source})>"