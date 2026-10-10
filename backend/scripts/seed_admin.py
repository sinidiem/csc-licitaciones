"""Seed controlado del primer admin (CONTEXT.md plan, día 2).

Crea el usuario admin inicial si no existe. Es idempotente: si el email ya
existe, no hace nada y avisa.

Uso (desde backend/, con .env configurado):
    ./venv/bin/python -m scripts.seed_admin
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlmodel import Session, select  # noqa: E402

from app.core.config import settings  # noqa: E402
from app.core.security import hash_password  # noqa: E402
from app.db.engine import engine  # noqa: E402
from app.models.user import User  # noqa: E402


def seed_admin() -> None:
    with Session(engine) as session:
        existing = session.exec(
            select(User).where(User.email == settings.admin_email)
        ).first()
        if existing is not None:
            print(f"Admin ya existe: {existing.email} (nada que hacer)")
            return
        admin = User(
            name=settings.admin_name,
            email=settings.admin_email,
            password_hash=hash_password(settings.admin_password),
            role="admin",
            is_active=True,
        )
        session.add(admin)
        session.commit()
        session.refresh(admin)
        print(f"Admin creado: {admin.email} (id={admin.id})")


if __name__ == "__main__":
    seed_admin()