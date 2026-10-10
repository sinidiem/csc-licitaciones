"""Entidad tender_items: partidas producto/cantidad/precio de cada licitación.

Reglas (CONTEXT.md §3): cantidad > 0, unit_price >= 0, único por
licitación/producto, y SUBTOTAL = cantidad × precio.
El total de partidas no debe superar budget_max (se valida en servicios
dentro de una transacción, no en el modelo).
"""

import uuid
from decimal import Decimal
from typing import Optional

from sqlalchemy import (
    CheckConstraint,
    Column,
    ForeignKey,
    Integer,
    Numeric,
    UniqueConstraint,
    Uuid,
)
from sqlmodel import Field, Relationship, SQLModel

from app.models.mixins import UuidPkMixin


class TenderItem(SQLModel, UuidPkMixin, table=True):
    __tablename__ = "tender_items"

    tender_id: uuid.UUID = Field(
        sa_column=Column(Uuid(as_uuid=True), ForeignKey("tenders.id"), nullable=False, index=True)
    )
    product_id: uuid.UUID = Field(
        sa_column=Column(Uuid(as_uuid=True), ForeignKey("products.id"), nullable=False, index=True)
    )
    quantity: int = Field(
        sa_column=Column(Integer, nullable=False)
    )
    unit_price: Decimal = Field(
        sa_column=Column(Numeric(14, 2), nullable=False, server_default="0.00")
    )

    tender: "Tender" = Relationship(back_populates="items")
    product: "Product" = Relationship(back_populates="tender_items")

    __table_args__ = (
        CheckConstraint("quantity > 0", name="ck_tender_items_quantity_positive"),
        CheckConstraint("unit_price >= 0", name="ck_tender_items_unit_price_non_neg"),
        UniqueConstraint("tender_id", "product_id", name="uq_tender_items_tender_product"),
    )

    def subtotal(self) -> Decimal:
        return self.quantity * self.unit_price

    def __repr__(self) -> str:
        return f"<TenderItem tender={self.tender_id} product={self.product_id} qty={self.quantity}>"