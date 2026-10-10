"""Servicio de transiciones de estado de licitaciones (CONTEXT.md §4-5).

Cada comando valida el estado actual, aplica restricciones y registra
`tender_status_history` en la MISMA transacción. Transiciones inválidas →
HTTP 409 `INVALID_STATUS_TRANSITION`.

Envío oficial (draft → active):
1. Valida borrador, propuesta cargada y destinatario (client.company_email).
2. Crea OUTBOX (pending) ANTES de tocar al proveedor.
3. Envía el correo real (Resend) FUERA de la transacción SQL.
4. Solo cuando el proveedor ACEPTA: transición a `active` + `submitted_at` +
   historial en una única transacción. Si el envío falla, la licitación
   permanece en `draft` y el outbox queda `failed` (recuperable, sin duplicados:
   la clave (tender_id, email_type) impide reenvíos ante timeouts ambiguos).
"""

import uuid
from decimal import Decimal

from sqlalchemy import func
from sqlmodel import Session, select

from app.core.errors import business_error
from app.models.client import Client
from app.models.email_outbox import EmailOutbox
from app.models.mixins import utcnow
from app.models.payment import Payment
from app.models.product import Product
from app.models.proposal_file import ProposalFile
from app.models.status_history import TenderStatusHistory
from app.models.tender import Tender, TenderStatus, can_transition
from app.models.tender_item import TenderItem
from app.services import email as email_service
from app.services import storage as storage_service
from app.services.tenders import current_total

EMAIL_TYPE_SUBMIT = "tender_submitted"


def _lock_tender(session: Session, tender: Tender) -> Tender:
    """Recarga la licitación con SELECT ... FOR UPDATE (CONTEXT.md plan §6).

    Serializa transiciones/pagos concurrentes sobre la misma licitación: la
    segunda transacción espera a que la primera COMMIT/ROLLBACK y revalida
    el estado ya actualizado. El lock se libera en el COMMIT/ROLLBACK.
    """
    return session.exec(
        select(Tender).where(Tender.id == tender.id).with_for_update()
    ).one()


def _transition_with_history(
    session: Session,
    tender: Tender,
    *,
    target: TenderStatus,
    actor_user_id: uuid.UUID,
    reason: str,
    source: str = "user",
) -> Tender:
    """Transición con validación de matriz + historial, en UNA transacción.

    El estado se revalida sobre la fila bloqueada (FOR UPDATE), de modo que
    el chequeo `can_transition` es seguro bajo concurrencia.
    """
    locked = _lock_tender(session, tender)
    current = TenderStatus(locked.status)
    if not can_transition(current, target):
        raise business_error(
            409,
            "INVALID_STATUS_TRANSITION",
            f"Transición inválida: '{current.value}' → '{target.value}'",
        )
    from_status = locked.status
    locked.status = target.value
    locked.updated_by = actor_user_id if source == "user" else None
    session.add(
        TenderStatusHistory(
            tender_id=locked.id,
            from_status=from_status,
            to_status=target.value,
            actor_user_id=actor_user_id,
            reason=reason,
            source=source,
        )
    )
    session.commit()
    session.refresh(locked)
    return locked


def finish_tender(
    session: Session, tender: Tender, *, actor_user_id: uuid.UUID, reason: str | None = None
) -> Tender:
    """active → finished: la empresa ganó y completó la entrega."""
    return _transition_with_history(
        session,
        tender,
        target=TenderStatus.FINISHED,
        actor_user_id=actor_user_id,
        reason=reason or "La empresa ganó y completó la entrega",
    )


def lose_tender(
    session: Session, tender: Tender, *, actor_user_id: uuid.UUID, reason: str | None = None
) -> Tender:
    """active → lost: resolución manual (no se ganó la licitación)."""
    return _transition_with_history(
        session,
        tender,
        target=TenderStatus.LOST,
        actor_user_id=actor_user_id,
        reason=reason or "Licitación no ganada (resolución manual)",
    )


def invoice_tender(
    session: Session,
    tender: Tender,
    *,
    amount: Decimal,
    actor_user_id: uuid.UUID,
    reason: str | None = None,
) -> Tender:
    """finished → to_collect: registra el importe facturado (decisión §11.3).

    El importe facturado puede diferir del total de partidas (negociación),
    pero debe ser estrictamente positivo y no inferior a los pagos ya
    registrados. La transición y el historial se aplican en la misma
    transacción, sobre la fila bloqueada.
    """
    locked = _lock_tender(session, tender)
    current = TenderStatus(locked.status)
    if not can_transition(current, TenderStatus.TO_COLLECT):
        raise business_error(
            409,
            "INVALID_STATUS_TRANSITION",
            f"Transición inválida: '{current.value}' → 'to_collect' "
            "(solo desde 'finished')",
        )
    if amount <= 0:
        raise business_error(
            422, "INVOICE_AMOUNT_INVALID", "El importe facturado debe ser positivo"
        )
    paid = Decimal(
        str(
            session.exec(
                select(func.coalesce(func.sum(Payment.amount), 0)).where(
                    Payment.tender_id == locked.id
                )
            ).one()
        )
    )
    if amount < paid:
        raise business_error(
            422,
            "INVOICE_BELOW_PAYMENTS",
            f"El importe facturado ({amount:.2f}) no puede ser inferior a los "
            f"pagos ya registrados ({paid:.2f})",
        )
    from_status = locked.status
    locked.status = TenderStatus.TO_COLLECT.value
    locked.invoiced_total = amount
    locked.updated_by = actor_user_id
    session.add(
        TenderStatusHistory(
            tender_id=locked.id,
            from_status=from_status,
            to_status=TenderStatus.TO_COLLECT.value,
            actor_user_id=actor_user_id,
            reason=reason or f"Facturación registrada por {amount:.2f}",
            source="user",
        )
    )
    session.commit()
    session.refresh(locked)
    return locked


def _require_transition(tender: Tender, target: TenderStatus) -> None:
    current = TenderStatus(tender.status)
    if not can_transition(current, target):
        raise business_error(
            409,
            "INVALID_STATUS_TRANSITION",
            f"Transición inválida: '{current.value}' → '{target.value}'",
        )


def _require_draft_items_editable(tender: Tender) -> None:
    """Guardas para comandos que mutan partidas (decisión CONTEXT.md §11.1)."""
    if tender.status != TenderStatus.DRAFT.value:
        raise business_error(
            409,
            "INVALID_STATUS_TRANSITION",
            f"No se pueden modificar partidas en estado '{tender.status}'",
        )


def send_tender(session: Session, tender: Tender, *, actor_user_id: uuid.UUID) -> Tender:
    """Valida y ejecuta el envío oficial (draft → active) con correo real."""
    _require_transition(tender, TenderStatus.ACTIVE)

    if tender.proposal_file_id is None:
        raise business_error(
            409, "PROPOSAL_REQUIRED",
            "No se puede enviar sin el documento de propuesta subido",
        )
    proposal = session.get(ProposalFile, tender.proposal_file_id)
    if proposal is None:
        raise business_error(409, "PROPOSAL_REQUIRED", "La propuesta referenciada no existe")

    client = session.get(Client, tender.client_id)
    if client is None or not client.company_email:
        raise business_error(
            409, "CLIENT_EMAIL_REQUIRED",
            "El cliente no tiene correo de empresa para recibir la propuesta",
        )

    # Idempotencia: un solo outbox pendiente/enviado por (tender, tipo).
    existing = session.exec(
        select(EmailOutbox).where(
            EmailOutbox.tender_id == tender.id,
            EmailOutbox.email_type == EMAIL_TYPE_SUBMIT,
        )
    ).first()
    if existing is not None and existing.status in ("pending", "sent"):
        raise business_error(
            409, "EMAIL_ALREADY_SCHEDULED",
            f"Ya existe un envío {existing.status} para esta licitación",
        )

    items = list(session.exec(select(TenderItem).where(TenderItem.tender_id == tender.id)))
    total = current_total(session, tender.id)
    summary = email_service.build_tender_summary_html(
        title=f"{tender.title} — {tender.reference or 'sin referencia'}",
        items=[
            (
                _product_name(session, i.product_id),
                str(i.quantity),
                f"{i.subtotal():.2f}",
            )
            for i in items
        ],
        total=f"{total:.2f}",
        budget_max=f"{tender.budget_max:.2f}",
        deadline_at=tender.deadline_at.strftime("%Y-%m-%d %H:%M UTC"),
    )

    attachment = storage_service.get_storage().get_bytes(
        bucket=proposal.bucket, object_key=proposal.object_key
    )

    outbox = email_service.send_email(
        session,
        to_email=client.company_email,
        subject=f"[CSC] Propuesta {tender.reference or tender.title} — {client.name}",
        html_body=summary,
        email_type=EMAIL_TYPE_SUBMIT,
        tender_id=tender.id,
        attachment_content=attachment,
        attachment_filename=proposal.original_name,
    )

    if outbox.status != "sent":
        # El proveedor NO aceptó: la licitación sigue en draft (recuperable).
        raise business_error(
            502, "EMAIL_PROVIDER_FAILED",
            "El proveedor de correo rechazó el envío; reintente más tarde",
        )

    # Solo aquí: transición + submitted_at + historial en UNA transacción.
    tender.status = TenderStatus.ACTIVE.value
    tender.submitted_at = utcnow()
    session.add(
        TenderStatusHistory(
            tender_id=tender.id,
            from_status=TenderStatus.DRAFT.value,
            to_status=TenderStatus.ACTIVE.value,
            actor_user_id=actor_user_id,
            reason="Envío oficial con propuesta y correo aceptado por el proveedor",
            source="user",
        )
    )
    session.commit()
    session.refresh(tender)
    return tender


def _product_name(session: Session, product_id: uuid.UUID) -> str:
    p = session.get(Product, product_id)
    return p.name if p else str(product_id)