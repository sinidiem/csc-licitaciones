"""Esquemas Pydantic de productos (catálogo, precio de referencia)."""

import uuid
from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field


class ProductBase(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=2000)
    default_unit_price: Decimal = Field(
        ge=0, max_digits=14, decimal_places=2
    )


class ProductCreate(ProductBase):
    is_active: bool = True


class ProductRead(ProductBase):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    is_active: bool
    created_at: datetime
    created_by: uuid.UUID | None = None
    updated_at: datetime | None = None
    updated_by: uuid.UUID | None = None