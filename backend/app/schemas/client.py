"""Esquemas Pydantic de clientes (empresa cliente)."""

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr, Field


class ClientBase(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    company_email: EmailStr
    contact_name: str | None = Field(default=None, max_length=150)
    contact_phone: str | None = Field(default=None, max_length=50)
    address: str | None = Field(default=None, max_length=500)


class ClientCreate(ClientBase):
    pass


class ClientRead(ClientBase):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    created_at: datetime
    created_by: uuid.UUID | None = None
    updated_at: datetime | None = None
    updated_by: uuid.UUID | None = None
    # Soft delete: null = activo. El frontend nunca recibe clientes borrados
    # (el listado los excluye); el campo existe para trazabilidad.
    deleted_at: datetime | None = None


class ClientUpdate(BaseModel):
    """Actualización parcial de un cliente (solo los campos enviados)."""

    name: str | None = Field(default=None, min_length=1, max_length=200)
    company_email: EmailStr | None = None
    contact_name: str | None = Field(default=None, max_length=150)
    contact_phone: str | None = Field(default=None, max_length=50)
    address: str | None = Field(default=None, max_length=500)