"""Servicios de dominio de licitaciones.

Reglas de negocio implementadas aquí ( §4 y plan §3-4):
- SUM(items.quantity * unit_price) <= budget_max, validado en transacción
  con FOR UPDATE sobre la licitación para evitar carreras concurrentes.
- Partidas SOLO editables en `draft` (decisión registrada en
  §11.1 y LOG.md). Los estados terminales (finished, to_collect, collected,
  lost) y `active` rechazan agregar/quitar partidas.
- La creación y cada transición registran `tender_status_history` en la
  MISMA transacción (source user|system).
"""

import uuid
from decimal import Decimal

from sqlalchemy import func
from sqlmodel import Session, select

from app.core.errors import business_error
from app.models.client import Client
from app.models.product import Product
from app.models.status_history import TenderStatusHistory
from app.models.tender import Tender, TenderStatus
from app.models.tender_item import TenderItem


def current_total(session: Session, tender_id: uuid.UUID) -> Decimal:
    """Suma actual de las partidas (Decimal, nunca float)."""
    row = session.exec(
        select(func.coalesce(func.sum(TenderItem.quantity * TenderItem.unit_price), 0))
        .where(TenderItem.tender_id == tender_id)
    ).one()
    return Decimal(str(row))


def _require_editable(tender: Tender) -> None:
    """Regla: partidas solo editables en borrador (decisión §11)."""
    if tender.status != TenderStatus.DRAFT.value:
        raise business_error(
            409,
            "INVALID_STATUS_TRANSITION",
            f"No se pueden modificar partidas en estado '{tender.status}'; "
            "solo en borrador (draft)",
        )


def create_tender(
    session: Session,
    *,
    client_id: uuid.UUID,
    title: str,
    reference: str | None,
    description: str | None,
    deadline_at,
    budget_max: Decimal,
    actor_user_id: uuid.UUID,
) -> Tender:
    client = session.get(Client, client_id)
    if client is None or client.deleted_at is not None:
        raise business_error(404, "CLIENT_NOT_FOUND", "Cliente no encontrado")

    tender = Tender(
        client_id=client_id,
        title=title,
        reference=reference,
        description=description,
        deadline_at=deadline_at,
        budget_max=budget_max,
        status=TenderStatus.DRAFT.value,
        created_by=actor_user_id,
    )
    session.add(tender)
    session.flush()  # asigna el id antes del historial

    # Historial de creación en la misma transacción (from_status NULL)
    session.add(
        TenderStatusHistory(
            tender_id=tender.id,
            from_status=None,
            to_status=TenderStatus.DRAFT.value,
            actor_user_id=actor_user_id,
            reason="Creación de licitación",
            source="user",
        )
    )
    session.commit()
    session.refresh(tender)
    return tender


def list_tenders(
    session: Session,
    *,
    status: str | None = None,
    client_id: uuid.UUID | None = None,
    limit: int = 20,
    offset: int = 0,
) -> list[Tender]:
    query = select(Tender)
    if status is not None:
        query = query.where(Tender.status == status)
    if client_id is not None:
        query = query.where(Tender.client_id == client_id)
    query = query.order_by(Tender.created_at.desc()).limit(limit).offset(offset)
    return list(session.exec(query))


def get_tender(session: Session, tender_id: uuid.UUID) -> Tender | None:
    return session.get(Tender, tender_id)


def add_item(
    session: Session,
    tender: Tender,
    *,
    product_id: uuid.UUID,
    quantity: int,
    unit_price: Decimal,
    actor_user_id: uuid.UUID,
) -> TenderItem:
    _require_editable(tender)

    product = session.get(Product, product_id)
    if product is None:
        raise business_error(404, "PRODUCT_NOT_FOUND", "Producto no encontrado")

    existing = session.exec(
        select(TenderItem).where(
            TenderItem.tender_id == tender.id,
            TenderItem.product_id == product_id,
        )
    ).first()
    if existing is not None:
        raise business_error(
            409, "DUPLICATE_ITEM", "Ese producto ya está en la licitación"
        )

    # Bloqueo de fila: serializa la suma contra actualizaciones concurrentes
    # (SELECT ... FOR UPDATE), de modo que la validación de presupuesto no
    # tenga carreras. El lock se libera en el COMMIT.
    locked = session.exec(
        select(Tender).where(Tender.id == tender.id).with_for_update()
    ).one()

    item = TenderItem(
        tender_id=tender.id,
        product_id=product_id,
        quantity=quantity,
        unit_price=unit_price,
    )
    session.add(item)
    session.flush()

    total = current_total(session, tender.id)
    if total > locked.budget_max:
        session.rollback()
        raise business_error(
            422,
            "BUDGET_EXCEEDED",
            f"El total de partidas ({total}) supera el presupuesto máximo "
            f"({locked.budget_max})",
        )

    session.commit()
    session.refresh(item)
    return item


def remove_item(
    session: Session,
    tender: Tender,
    item_id: uuid.UUID,
) -> None:
    _require_editable(tender)
    item = session.get(TenderItem, item_id)
    if item is None or item.tender_id != tender.id:
        raise business_error(404, "ITEM_NOT_FOUND", "Partida no encontrada")
    session.delete(item)
    session.commit()