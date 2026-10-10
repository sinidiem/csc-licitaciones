"""Registro de modelos para SQLModel.metadata.

Importar este paquete (o `from app.db.base import metadata`) basta para que
Alembic autogenerate vea todas las tablas.
"""

from app.models.client import Client
from app.models.email_outbox import EmailOutbox
from app.models.payment import Payment
from app.models.product import Product
from app.models.proposal_file import ProposalFile
from app.models.status_history import TenderStatusHistory
from app.models.tender import Tender, TenderStatus, can_transition
from app.models.tender_item import TenderItem
from app.models.user import User

__all__ = [
    "Client",
    "EmailOutbox",
    "Payment",
    "Product",
    "ProposalFile",
    "Tender",
    "TenderItem",
    "TenderStatus",
    "TenderStatusHistory",
    "User",
    "can_transition",
]