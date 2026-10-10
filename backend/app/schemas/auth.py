"""Esquemas de autenticación (email/password + JWT en cookie)."""

from pydantic import BaseModel, EmailStr, Field

from app.schemas.user import UserRead


class LoginRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=1, max_length=128)


class LoginResponse(BaseModel):
    message: str = "sesión iniciada"
    user: UserRead