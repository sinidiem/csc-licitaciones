"""Servicio de pagos contra licitaciones en `por_cobrar` ( §4.6).

Reglas:
- Pagos SOLO en `to_collect` (409 INVALID_STATUS_TRANSITION en otro estado).
- Importe estrictamente positivo y menor/igual al saldo pendiente
  (saldo = invoiced_total - SUM(payments)); sobrepago → 422 OVERPAYMENT.
- El pago y la transición automática a `collected` cuando el saldo llega a
  cero ocurren en la MISMA transacción.
- SELECT ... FOR UPDATE sobre la licitación: dos pagos concurrentes se
  serializan, de modo que el chequeo de saldo nunca permite sobrepago por
  carrera (mismo patrón que add_item en app/services/tenders.py).
"""

import uuid
from decimal import Decimal

from pydantic import AwareDatetime
from sqlalchemy import func
from sqlmodel import Session, select

from app.core.errors import business_error
from app.models.mixins import utcnow
from app.models.payment import Payment
from app.models.status_history import TenderStatusHistory
from app.models.tender import Tender, TenderStatus


def payments_sum(session: Session, tender_id: uuid.UUID) -> Decimal:
    """Suma de pagos registrados (Decimal, nunca float)."""
    row = session.exec(
        select(func.coalesce(func.sum(Payment.amount), 0)).where(
            Payment.tender_id == tender_id
        )
    ).one()
    return Decimal(str(row))


def pending_balance(session: Session, tender: Tender) -> Decimal | None:
    """Saldo pendiente: invoiced_total - SUM(payments). None si no hay factura."""
    if tender.invoiced_total is None:
        return None
    return tender.invoiced_total - payments_sum(session, tender.id)


def register_payment(
    session: Session,
    tender: Tender,
    *,
    amount: Decimal,
    paid_at: AwareDatetime | None,
    reference: str | None,
    notes: str | None,
    actor_user_id: uuid.UUID,
) -> Payment:
    """Registra un abono y, si el saldo queda en cero, pasa a `collected`.

    Todo ocurre en una única transacción sobre la licitación bloqueada
    (FOR UPDATE): insertar el pago, recalcular saldo y transicionar.
    """
    if TenderStatus(tender.status) is not TenderStatus.TO_COLLECT:
        raise business_error(
            409,
            "INVALID_STATUS_TRANSITION",
            f"Pagos solo permitidos en estado 'por_cobrar' "
            f"(estado actual: '{tender.status}')",
        )
    if amount <= 0:
        raise business_error(
            422, "PAYMENT_AMOUNT_INVALID", "El importe del pago debe ser positivo"
        )

    locked = session.exec(
        select(Tender).where(Tender.id == tender.id).with_for_update()
    ).one()
    # Revalidación sobre la fila bloqueada: si otra transacción ya cambió el
    # estado (ej. concurrencia), el pago se rechaza aquí, no sobre un dato
    # leído antes del lock.
    if TenderStatus(locked.status) is not TenderStatus.TO_COLLECT:
        session.rollback()
        raise business_error(
            409,
            "INVALID_STATUS_TRANSITION",
            f"Pagos solo permitidos en estado 'por_cobrar' "
            f"(estado actual: '{locked.status}')",
        )
    if locked.invoiced_total is None:
        raise business_error(
            409, "TENDER_NOT_INVOICED", "La licitación no tiene factura registrada"
        )

    saldo = locked.invoiced_total - payments_sum(session, locked.id)
    if amount > saldo:
        session.rollback()  # libera el lock de inmediato
        raise business_error(
            422,
            "OVERPAYMENT",
            f"El pago ({amount:.2f}) supera el saldo pendiente ({saldo:.2f})",
        )

    payment = Payment(
        tender_id=locked.id,
        amount=amount,
        paid_at=paid_at or utcnow(),
        reference=reference,
        notes=notes,
        created_by=actor_user_id,
    )
    session.add(payment)
    session.flush()

    from_status = locked.status
    new_saldo = saldo - amount
    if new_saldo == 0:
        # Saldo saldado: transición automática en la MISMA transacción del
 # último pago (, matriz to_collect -> collected).
        locked.status = TenderStatus.COLLECTED.value
        session.add(
            TenderStatusHistory(
                tender_id=locked.id,
                from_status=from_status,
                to_status=TenderStatus.COLLECTED.value,
                actor_user_id=actor_user_id,
                reason="Saldo pendiente saldado al registrar el último pago",
                source="user",
            )
        )
    locked.updated_by = actor_user_id
    session.commit()
    session.refresh(payment)
    return payment