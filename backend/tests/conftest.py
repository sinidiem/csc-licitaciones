"""Configuración de pruebas: PostgreSQL real aislado + migraciones Alembic.

- Crear la base de datos `licitaciones_test` si no existe (nunca toca la de
  desarrollo) y aplicarle las migraciones con `alembic upgrade head`
  (regla AGENTS.md: nunca `create_all`).
- Entre tests: TRUNCATE de todas las tablas (a excepción de alembic_version).
- Cliente HTTP real contra la app (TestClient de FastAPI) + admin de sesión.

Las variables de entorno tienen prioridad sobre `.env` en pydantic-settings:
la app (engine y Alembic) apunta SIEMPRE a la BD de test, y la key de Resend
queda vacía para que ningún test dispare un correo real.
"""

import os
import subprocess
import sys
from pathlib import Path
from typing import Iterator

BACKEND_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_DIR))

TEST_DATABASE_URL = os.environ.get(
    "TEST_DATABASE_URL",
    "postgresql://postgres:password@localhost:5432/licitaciones_test",
)
os.environ["DATABASE_URL"] = TEST_DATABASE_URL

# Integraciones reales desactivadas en pruebas: nunca enviar correos ni
# llamar al proveedor. El storage se mantiene en el adaptador local
# (licitaciones_test nunca depende de Supabase).
os.environ["RESEND_API_KEY"] = ""
os.environ["SUPABASE_URL"] = ""
os.environ["SUPABASE_SERVICE_KEY"] = ""

import pytest  # noqa: E402


def _ensure_test_database() -> None:
    """Crea la BD de test si no existe (idempotente).

    No se usa el context manager de la conexión (psycopg2 inicia una
    transacción implícita incompatible con CREATE DATABASE); se activa
    autocommit de inmediato y se cierra explícitamente.
    """
    import psycopg2

    admin_url = TEST_DATABASE_URL.rsplit("/", 1)[0] + "/postgres"
    dbname = TEST_DATABASE_URL.rsplit("/", 1)[1]
    conn = psycopg2.connect(admin_url)
    try:
        conn.autocommit = True
        with conn.cursor() as cur:
            cur.execute("SELECT 1 FROM pg_database WHERE datname = %s", (dbname,))
            if cur.fetchone() is None:
                cur.execute(f'CREATE DATABASE "{dbname}"')
    finally:
        conn.close()


@pytest.fixture(scope="session", autouse=True)
def _db_schema() -> None:
    """Una vez por sesión: BD existente + migraciones al head."""
    _ensure_test_database()
    subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", "head"],
        cwd=BACKEND_DIR,
        check=True,
        env={**os.environ, "DATABASE_URL": TEST_DATABASE_URL},
    )


@pytest.fixture(autouse=True)
def _clean_state(_db_schema) -> Iterator[None]:
    """Entre tests: vacía todas las tablas de negocio."""
    from sqlalchemy import text

    from app.db.engine import engine

    with engine.begin() as conn:
        conn.execute(
            text(
                "TRUNCATE TABLE users, clients, products, tenders, tender_items, "
                "proposal_files, payments, tender_status_history, email_outbox "
                "RESTART IDENTITY CASCADE"
            )
        )
    # Estado en memoria (limitador de login) limpio entre tests
    from app.core.ratelimit import clear_login_attempts

    clear_login_attempts()
    yield


@pytest.fixture()
def client() -> Iterator:
    from fastapi.testclient import TestClient

    from app.main import app

    with TestClient(app) as c:
        yield c


def _new_user(*, role: str, email: str) -> None:
    from sqlmodel import Session

    from app.core.security import hash_password
    from app.db.engine import engine
    from app.models.user import User

    with Session(engine) as s:
        s.add(
            User(
                name="Usuario Test",
                email=email,
                password_hash=hash_password("Passw0rd!"),
                role=role,
                is_active=True,
            )
        )
        s.commit()


@pytest.fixture()
def admin(client) -> dict:
    """Crea un admin con cookie de sesión activa en el cliente."""
    _new_user(role="admin", email="admin@example.com")
    r = client.post(
        "/api/v1/auth/login",
        json={"email": "admin@example.com", "password": "Passw0rd!"},
    )
    assert r.status_code == 200, r.text
    return r.json()["user"]