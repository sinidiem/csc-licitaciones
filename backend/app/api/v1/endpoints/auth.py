"""Endpoints de autenticación: login/logout/me (JWT en cookie HttpOnly)."""

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlmodel import select

from app.api.v1.deps import CurrentUser, SessionDep
from app.core.config import settings
from app.core.ratelimit import login_rate_limit
from app.core.security import create_access_token, verify_password
from app.models.user import User
from app.schemas.auth import LoginRequest, LoginResponse
from app.schemas.user import UserRead

router = APIRouter(prefix="/auth", tags=["auth"])


def _set_session_cookie(response: Response, user: User) -> None:
    token = create_access_token(subject=user.id, role=user.role)
    response.set_cookie(
        key=settings.cookie_name,
        value=token,
        httponly=True,  # el JS del navegador no puede leer el token (anti-XSS)
        secure=settings.cookie_secure,
        samesite=settings.cookie_samesite,
        max_age=settings.access_token_expire_minutes * 60,
        path="/",
    )


@router.post("/login", response_model=LoginResponse)
def login(
    payload: LoginRequest,
    response: Response,
    session: SessionDep,
    _rate: None = Depends(login_rate_limit),
) -> LoginResponse:
    user = session.exec(select(User).where(User.email == payload.email)).first()
    if user is None or not verify_password(payload.password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Credenciales inválidas",
        )
    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Usuario inactivo",
        )
    _set_session_cookie(response, user)
    return LoginResponse(user=UserRead.model_validate(user))


@router.post("/logout")
def logout(response: Response) -> dict:
    response.delete_cookie(key=settings.cookie_name, path="/")
    return {"message": "sesión cerrada"}


@router.get("/me", response_model=UserRead)
def me(user: CurrentUser) -> User:
    return user