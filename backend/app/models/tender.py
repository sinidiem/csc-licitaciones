"""Entidad tenders: la licitación, corazón del dominio.

Estados (códigos ingleses en BD, mapeo documentado en CONTEXT.md §3.1):
- draft       -> borrador (implícito, antes de enviar)
- active      -> activa (enviada oficialmente)
- finished    -> finalizada (ganada y entregada)
- to_collect  -> por_cobrar (facturada, pendiente de cobro)
- collected   -> cobrada (saldo = 0)
- lost        -> perdida (manual o por vencimiento)

Matriz de transiciones válidas y reglas de negocio se ejecutan en la capa
de servicios (app/services), no aquí; este módulo solo modela el dato.
"""

import uuid
from datetime import datetime
from decimal import Decimal
from enum import Enum
from typing import List, Optional

from sqlalchemy import (
    CheckConstraint,
    Column,
    DateTime,
    Numeric,
    String,
    Text,
    Uuid,
    ForeignKey,
)
from sqlmodel import Field, Relationship, SQLModel

from app.models.mixins import AuditMixin, UuidPkMixin


class TenderStatus(str, Enum):
    """Códigos internos (inglés) con su mapeo al español del producto."""

    DRAFT = "draft"  # borrador
    ACTIVE = "active"  # activa
    FINISHED = "finished"  # finalizada
    TO_COLLECT = "to_collect"  # por_cobrar
    COLLECTED = "collected"  # cobrada
    LOST = "lost"  # perdida


STATUS_ALLOWED = tuple(s.value for s in TenderStatus)

# Transiciones válidas (CONTEXT.md "Tabla de Transiciones"): cualquier otra
# combinación debe rechazarse con error (HTTP 409 INVALID_STATUS_TRANSITION).
VALID_TRANSITIONS: dict[TenderStatus, set[TenderStatus]] = {
    TenderStatus.DRAFT: {TenderStatus.ACTIVE},
    TenderStatus.ACTIVE: {TenderStatus.FINISHED, TenderStatus.LOST},
    TenderStatus.FINISHED: {TenderStatus.TO_COLLECT},
    TenderStatus.TO_COLLECT: {TenderStatus.COLLECTED},
    TenderStatus.COLLECTED: set(),
    TenderStatus.LOST: set(),
}

STATUS_SQL = ", ".join(f"'{s}'" for s in STATUS_ALLOWED)


def can_transition(current: TenderStatus, target: TenderStatus) -> bool:
    return target in VALID_TRANSITIONS.get(current, set())


class Tender(SQLModel, AuditMixin, UuidPkMixin, table=True):
    __tablename__ = "tenders"

    client_id: uuid.UUID = Field(
        sa_column=Column(Uuid(as_uuid=True), ForeignKey("clients.id"), nullable=False, index=True)
    )
    title: str = Field(sa_column=Column(String(200), nullable=False, index=True))
    reference: Optional[str] = Field(default=None, sa_column=Column(String(50)))
    description: Optional[str] = Field(default=None, sa_column=Column(Text))

    status: str = Field(
        sa_column=Column(
            String(20), nullable=False, server_default=TenderStatus.DRAFT.value
        )
    )
    budget_max: Decimal = Field(
        sa_column=Column(Numeric(14, 2), nullable=False, server_default="0.00")
    )
    deadline_at: datetime = Field(
        sa_column=Column(DateTime(timezone=True), nullable=False)
    )

    proposal_file_id: Optional[uuid.UUID] = Field(
        default=None,
        sa_column=Column(
            Uuid(as_uuid=True),
            # use_alter: evita el ciclo de FKs tenders <-> proposal_files
            # (la constraint se crea por ALTER TABLE tras existir ambas tablas).
            ForeignKey("proposal_files.id", use_alter=True, name="fk_tenders_proposal_file_id"),
            nullable=True,
        ),
    )
    invoiced_total: Optional[Decimal] = Field(
        default=None, sa_column=Column(Numeric(14, 2), nullable=True)
    )
    reminder_sent_at: Optional[datetime] = Field(
        default=None, sa_column=Column(DateTime(timezone=True), nullable=True)
    )
    submitted_at: Optional[datetime] = Field(
        default=None, sa_column=Column(DateTime(timezone=True), nullable=True)
    )

    # Relaciones
    client: "Client" = Relationship(back_populates="tenders")
    items: List["TenderItem"] = Relationship(
        back_populates="tender", sa_relationship_kwargs={"cascade": "all, delete-orphan"}
    )
    # Propuesta actual (1 licitación -> 1 archivo actual), FK en tenders.
    proposal: Optional["ProposalFile"] = Relationship(
        back_populates="owner_tenders",
        sa_relationship_kwargs={
            "primaryjoin": "Tender.proposal_file_id == ProposalFile.id",
            "foreign_keys": "[Tender.proposal_file_id]",
            "uselist": False,
            "viewonly": True,
        },
    )
    # Todas las propuestas subidas para la licitación, FK en proposal_files.
    proposal_files: List["ProposalFile"] = Relationship(
        back_populates="tender",
        sa_relationship_kwargs={
            "primaryjoin": "Tender.id == ProposalFile.tender_id",
            "foreign_keys": "[ProposalFile.tender_id]",
        },
    )
    payments: List["Payment"] = Relationship(
        back_populates="tender", sa_relationship_kwargs={"cascade": "all, delete-orphan"}
    )
    history: List["TenderStatusHistory"] = Relationship(
        back_populates="tender", sa_relationship_kwargs={"cascade": "all, delete-orphan"}
    )

    __table_args__ = (
        CheckConstraint(f"status IN ({STATUS_SQL})", name="ck_tenders_status"),
        CheckConstraint("budget_max >= 0", name="ck_tenders_budget_max_non_neg"),
        CheckConstraint(
            "invoiced_total IS NULL OR invoiced_total > 0",
            name="ck_tenders_invoiced_total_positive",
        ),
    )

    def __repr__(self) -> str:
        return f"<Tender {self.title!r} status={self.status}>"