"""Engine y sesiones SQLModel (SQLAlchemy 2) para PostgreSQL."""

from collections.abc import Generator

from sqlmodel import Session, create_engine

from app.core.config import settings

engine = create_engine(
    settings.database_url,
    pool_pre_ping=True,
)


def get_session() -> Generator[Session, None, None]:
    """Dependencia FastAPI: una sesión por request."""
    with Session(engine) as session:
        yield session