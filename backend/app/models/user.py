"""Entidad users (autenticación, roles admin/user, auditoría)."""

import uuid
from typing import Optional

from sqlalchemy import Boolean, CheckConstraint, Column, String, Text
from sqlmodel import Field, SQLModel

from app.models.mixins import AuditMixin, UuidPkMixin


class User(SQLModel, AuditMixin, UuidPkMixin, table=True):
    __tablename__ = "users"

    name: str = Field(sa_column=Column(String(150), nullable=False))
    email: str = Field(
        sa_column=Column(String(320), nullable=False, unique=True, index=True)
    )
    password_hash: str = Field(sa_column=Column(Text, nullable=False))
    role: str = Field(
        sa_column=Column(String(10), nullable=False, server_default="user")
    )
    is_active: bool = Field(
        sa_column=Column(Boolean, nullable=False, server_default="true")
    )

    __table_args__ = (
        CheckConstraint("role IN ('admin', 'user')", name="ck_users_role"),
    )

    def __repr__(self) -> str:
        return f"<User {self.email!r} role={self.role}>"