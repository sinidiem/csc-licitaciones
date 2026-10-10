"""Endpoint de usuarios: listado y creación.

Regla : solo los admins pueden crear otros usuarios.
El rol solo lo asigna el admin; el usuario normal se crea con rol "user".
"""

from fastapi import APIRouter, HTTPException, status
from sqlmodel import select

from app.api.v1.deps import AdminUser, CurrentUser, SessionDep
from app.core.security import hash_password
from app.models.user import User
from app.schemas.user import UserCreate, UserRead

router = APIRouter(prefix="/users", tags=["users"])


@router.get("", response_model=list[UserRead])
def list_users(user: AdminUser, session: SessionDep) -> list[User]:
    return list(session.exec(select(User).order_by(User.created_at)))


@router.post("", response_model=UserRead, status_code=status.HTTP_201_CREATED)
def create_user(
    payload: UserCreate,
    admin: AdminUser,
    session: SessionDep,
) -> User:
    existing = session.exec(select(User).where(User.email == payload.email)).first()
    if existing is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Ya existe un usuario con ese email",
        )
    user = User(
        name=payload.name,
        email=payload.email,
        password_hash=hash_password(payload.password),
        role=payload.role,
        is_active=True,
        created_by=admin.id,
    )
    session.add(user)
    session.commit()
    session.refresh(user)
    return user