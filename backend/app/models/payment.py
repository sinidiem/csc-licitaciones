"""Entidad payments: pagos registrados contra una licitación en por_cobrar.

Regla (CONTEXT.md §3.6): importe > 0 y menor/igual al saldo pendiente
(saldo = invoiced_total - SUM(payments.amount)); no se permite sobrepago.
"""

import uuid
from decimal import Decimal
from typing import Optional

from pydantic import AwareDatetime
from sqlalchemy import (
    CheckConstraint,
    Column,
    ForeignKey,
    Numeric,
    String,
    Text,
    Uuid,
)
from sqlmodel import Field, Relationship, SQLModel

from app.models.mixins import UuidPkMixin, utcnow


class Payment(SQLModel, UuidPkMixin, table=True):
    __tablename__ = "payments"

    tender_id: uuid.UUID = Field(
        sa_column=Column(Uuid(as_uuid=True), ForeignKey("tenders.id"), nullable=False, index=True)
    )
    amount: Decimal = Field(
        sa_column=Column(Numeric(14, 2), nullable=False, server_default="0.00")
    )
    paid_at: AwareDatetime = Field(default_factory=utcnow)
    reference: Optional[str] = Field(default=None, sa_column=Column(String(100)))
    notes: Optional[str] = Field(default=None, sa_column=Column(Text))

    created_by: Optional[uuid.UUID] = Field(
        default=None, foreign_key="users.id", sa_column_kwargs={"nullable": True}
    )
    created_at: AwareDatetime = Field(default_factory=utcnow)

    tender: "Tender" = Relationship(back_populates="payments")

    __table_args__ = (
        CheckConstraint("amount > 0", name="ck_payments_amount_positive"),
    )

    def __repr__(self) -> str:
        return f"<Payment {self.amount} tender={self.tender_id}>"