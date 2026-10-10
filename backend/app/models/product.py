"""Entidad products: catálogo de productos (precio de referencia)."""

import uuid
from decimal import Decimal
from typing import List, Optional

from sqlalchemy import Boolean, CheckConstraint, Column, Numeric, String, Text
from sqlmodel import Field, Relationship, SQLModel

from app.models.mixins import AuditMixin, UuidPkMixin


class Product(SQLModel, AuditMixin, UuidPkMixin, table=True):
    __tablename__ = "products"

    name: str = Field(sa_column=Column(String(200), nullable=False, index=True))
    description: Optional[str] = Field(default=None, sa_column=Column(Text))
    # Precio de referencia; la licitación conserva el precio acordado en la partida.
    default_unit_price: Decimal = Field(
        sa_column=Column(Numeric(14, 2), nullable=False, server_default="0.00")
    )
    is_active: bool = Field(
        sa_column=Column(Boolean, nullable=False, server_default="true")
    )

    __table_args__ = (
        CheckConstraint(
            "default_unit_price >= 0", name="ck_products_default_unit_price_non_neg"
        ),
    )

    tender_items: List["TenderItem"] = Relationship(back_populates="product")

    def __repr__(self) -> str:
        return f"<Product {self.name!r}>"


from app.models.tender_item import TenderItem  # noqa: E402, F401