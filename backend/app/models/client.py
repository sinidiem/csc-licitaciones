"""Entidad clients: empresa cliente de la licitación."""

import uuid
from typing import List, Optional

from pydantic import AwareDatetime
from sqlalchemy import Column, String
from sqlmodel import Field, Relationship, SQLModel

from app.models.mixins import AuditMixin, UuidPkMixin


class Client(SQLModel, AuditMixin, UuidPkMixin, table=True):
    __tablename__ = "clients"

    name: str = Field(sa_column=Column(String(200), nullable=False, index=True))
    # Obligatorio para el envío oficial (regla CONTEXT.md §5). Un correo de
    # empresa = un cliente: único en BD + validación en app (409).
    company_email: str = Field(
        sa_column=Column(String(320), nullable=False, unique=True, index=True)
    )
    contact_name: Optional[str] = Field(default=None, sa_column=Column(String(150)))
    contact_phone: Optional[str] = Field(default=None, sa_column=Column(String(50)))
    address: Optional[str] = Field(default=None, sa_column=Column(String(500)))
    # Soft delete (borrado lógico): la fila permanece en BD (licitaciones y
    # auditoría intactas) pero no aparece en listas ni en la web. La unicidad
    # del correo sigue aplicando a TODAS las filas, borradas incluidas.
    # Decisión registrada en CONTEXT.md (2026-10-08).
    deleted_at: Optional[AwareDatetime] = Field(default=None, index=True)

    tenders: List["Tender"] = Relationship(back_populates="client")

    def __repr__(self) -> str:
        return f"<Client {self.name!r}>"


# Solo para tipado en relaciones (evita import circular en runtime)
from app.models.tender import Tender  # noqa: E402, F401