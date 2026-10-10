"""Hub de modelos para SQLModel/Alembic.

Importar este módulo registra TODAS las tablas en `SQLModel.metadata`.
Alembic (alembic/env.py) usa `Base.metadata` como target_metadata para
autogenerate. Nunca definir modelos fuera del paquete app.models sin
importarlos aquí.
"""

from sqlmodel import SQLModel

from app import models  # noqa: F401  (registro de tablas)
from app.models import (  # noqa: F401
    Client,
    EmailOutbox,
    Payment,
    Product,
    ProposalFile,
    Tender,
    TenderItem,
    TenderStatus,
    TenderStatusHistory,
    User,
)

Base = SQLModel
metadata = SQLModel.metadata