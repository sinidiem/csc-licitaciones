"""Cierre de huecos de la revisión de calidad (2026-10-08): fuerza bruta en
login y acceso al listado de usuarios.

- `login_rate_limit`: ventana deslizante por IP (429 tras N intentos).
- `GET /users`: solo admin (403 para rol user); crear usuario ya lo era.
"""

import pytest
from fastapi import HTTPException

from app.core.ratelimit import clear_login_attempts, login_rate_limit
from typing import Any, cast


class _FakeRequest:
    def __init__(self, host: str):
        self.client = type("C", (), {"host": host})()


def _req(host: str) -> Any:
    return cast(Any, _FakeRequest(host))


# ---------------------------------------------------------------------------
# Rate limit (unitario, sin red)
# ---------------------------------------------------------------------------


def test_rate_limit_bloquea_tras_max_intentos():
    clear_login_attempts()
    try:
        req = _req("1.2.3.4")
        for _ in range(3):
            login_rate_limit(req, max_attempts=3, window_seconds=60)
        with pytest.raises(HTTPException) as e:
            login_rate_limit(req, max_attempts=3, window_seconds=60)
        assert e.value.status_code == 429
    finally:
        clear_login_attempts()


def test_rate_limit_ips_independientes():
    clear_login_attempts()
    try:
        for _ in range(3):
            login_rate_limit(_req("ip-a"), max_attempts=3, window_seconds=60)
        # La IP b no ha hecho intentos: entra sin problema
        login_rate_limit(_req("ip-b"), max_attempts=3, window_seconds=60)
    finally:
        clear_login_attempts()


def test_rate_limit_clear_resetea():
    clear_login_attempts()
    req = _req("ip-c")
    for _ in range(3):
        login_rate_limit(req, max_attempts=3, window_seconds=60)
    clear_login_attempts()
    # Tras clear, la misma IP vuelve a tener intentos disponibles
    login_rate_limit(req, max_attempts=3, window_seconds=60)


# ---------------------------------------------------------------------------
# GET /users solo admin (integración)
# ---------------------------------------------------------------------------


def test_listar_usuarios_requiere_admin(client, admin):
    r = client.post(
        "/api/v1/users",
        json={"name": "Normal", "email": "normal@example.com", "password": "Passw0rd!", "role": "user"},
    )
    assert r.status_code == 201, r.text
    r = client.post("/api/v1/auth/login", json={"email": "normal@example.com", "password": "Passw0rd!"})
    assert r.status_code == 200, r.text
    r = client.get("/api/v1/users")
    assert r.status_code == 403


def test_listar_usuarios_admin_ok(client, admin):
    r = client.get("/api/v1/users")
    assert r.status_code == 200