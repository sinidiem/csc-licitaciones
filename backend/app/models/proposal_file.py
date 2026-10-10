"""Entidad proposal_files: metadatos del documento de propuesta subido a storage.

El objeto vive en el bucket (Supabase Storage, privado); aquí solo se guarda
la referencia de storage (provider/bucket/object_key). La URL firmada se
genera al descargar, nunca se persiste. `uploaded_by` es nullable: el sistema
también puede subir archivos.
"""

import uuid
from typing import List, Optional

from pydantic import AwareDatetime
from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    Column,
    ForeignKey,
    String,
    Uuid,
)
from sqlmodel import Field, Relationship, SQLModel

from app.models.mixins import UuidPkMixin, utcnow


class ProposalFile(SQLModel, UuidPkMixin, table=True):
    __tablename__ = "proposal_files"

    tender_id: uuid.UUID = Field(
        sa_column=Column(Uuid(as_uuid=True), ForeignKey("tenders.id"), nullable=False, index=True)
    )
    storage_provider: str = Field(
        sa_column=Column(String(50), nullable=False, server_default="supabase")
    )
    bucket: str = Field(sa_column=Column(String(100), nullable=False))
    object_key: str = Field(sa_column=Column(String(500), nullable=False))
    original_name: str = Field(sa_column=Column(String(255), nullable=False))
    content_type: str = Field(sa_column=Column(String(100), nullable=False))
    size_bytes: int = Field(
        sa_column=Column(BigInteger, nullable=False, server_default="0")
    )
    checksum: Optional[str] = Field(default=None, sa_column=Column(String(64)))

    uploaded_by: Optional[uuid.UUID] = Field(
        default=None, foreign_key="users.id", sa_column_kwargs={"nullable": True}
    )
    uploaded_at: AwareDatetime = Field(default_factory=utcnow)

    # Relaciones: la propuesta "actual" se enlaza desde tenders.proposal_file_id
    # (relación 1:1, viewonly); conservamos también filas históricas por tender.
    tender: "Tender" = Relationship(
        back_populates="proposal_files",
        sa_relationship_kwargs={
            "primaryjoin": "ProposalFile.tender_id == Tender.id",
            "foreign_keys": "[ProposalFile.tender_id]",
        },
    )
    # Contraparte de Tender.proposal: licitaciones que apuntan a este archivo.
    owner_tenders: List["Tender"] = Relationship(
        back_populates="proposal",
        sa_relationship_kwargs={
            "primaryjoin": "Tender.proposal_file_id == ProposalFile.id",
            "foreign_keys": "[Tender.proposal_file_id]",
            "viewonly": True,
        },
    )

    __table_args__ = (
        CheckConstraint("size_bytes >= 0", name="ck_proposal_files_size_non_neg"),
    )

    def __repr__(self) -> str:
        return f"<ProposalFile {self.original_name!r}>"