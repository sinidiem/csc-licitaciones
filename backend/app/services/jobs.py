"""Jobs programados (CONTEXT.md §6): vencimientos y recordatorios 48h.

Endpoints internos invocados por el cron del VPS (nunca expuestos al
público; autenticación por secreto con comparación segura en la capa API).

Idempotencia por licitación (AGENTS.md §7):
- Los candidatos se leen con `SELECT ... FOR UPDATE` en UNA transacción.
  PostgreSQL, bajo READ COMMITTED, re-evalúa el WHERE sobre la versión de
  fila vigente tras esperar el lock (EvalPlanQual), así que una corrida
  concurrente ve el estado ya actualizado y no duplica transición ni
  recordatorio.
- El recordatorio inserta su outbox (`pending`) DENTRO de la transacción
  que protege la licitación: dos corridas concurrentes jamás crean dos
  intenciones; la segunda ve la `pending`/`sent` existente y la salta.
  El envío real al proveedor ocurre DESPUÉS, fuera de esa transacción
  (`email_service.dispatch_outbox`), y `reminder_sent_at` solo se marca
  cuando el proveedor acepta (sent).
- El recordatorio NO toca licitaciones vencidas: su predicado exige
  `deadline_at > now()`, y las vencidas se procesan primero en `lost`.
"""

import uuid
from datetime import datetime, timedelta

from sqlmodel import Session, select

from app.models.client import Client
from app.models.email_outbox import EmailOutbox
from app.models.mixins import utcnow
from app.models.product import Product
from app.models.status_history import TenderStatusHistory
from app.models.tender import Tender, TenderStatus
from app.models.tender_item import TenderItem
from app.services import email as email_service
from app.services.tenders import current_total

EMAIL_TYPE_REMINDER = "tender_reminder"
REMINDER_WINDOW_HOURS = 48


def run_tender_jobs(session: Session) -> dict:
    """Ejecuta ambas fases. Devuelve métricas para el log del cron."""
    now = utcnow()
    expired = _expire_overdue(session, now)
    reminders = _send_reminders(session, now)
    return {"expired": expired, **reminders}


def _expire_overdue(session: Session, now: datetime) -> int:
    """status=active AND deadline_at <= now() → lost (actor system)."""
    rows = session.exec(
        select(Tender)
        .where(
            Tender.status == TenderStatus.ACTIVE.value,
            Tender.deadline_at <= now,
        )
        .with_for_update()
    ).all()
    for tender in rows:
        tender.status = TenderStatus.LOST.value
        tender.updated_by = None
        session.add(
            TenderStatusHistory(
                tender_id=tender.id,
                from_status=TenderStatus.ACTIVE.value,
                to_status=TenderStatus.LOST.value,
                actor_user_id=None,
                reason="Fecha límite vencida sin resolución (transición automática)",
                source="system",
            )
        )
    if rows:
        session.commit()
    return len(rows)


def _send_reminders(session: Session, now: datetime) -> dict:
    """status=active AND now < deadline_at <= now+48h AND reminder_sent_at NULL.

    Un único correo de recordatorio (sin adjunto) y `reminder_sent_at` solo
    cuando el proveedor acepta. Devuelve contadores por estado.
    """
    window_end = now + timedelta(hours=REMINDER_WINDOW_HOURS)
    rows = session.exec(
        select(Tender)
        .where(
            Tender.status == TenderStatus.ACTIVE.value,
            Tender.deadline_at > now,
            Tender.deadline_at <= window_end,
            # SQLAlchemy convierte `== None` en `IS NULL` y la fila en la
            # versión bloqueada sigue cumpliendo el predicado si otra
            # corrida la marcó (EvalPlanQual).
            Tender.reminder_sent_at == None,  # noqa: E711
        )
        .with_for_update()
    ).all()

    scheduled: list[tuple[EmailOutbox, uuid.UUID]] = []  # (outbox, tender_id)
    duplicated = 0
    skipped = 0
    for tender in rows:
        client = session.get(Client, tender.client_id)
        if client is None or not client.company_email:
            # Defensivo: la BD exige company_email NOT NULL; si cambiara el
            # esquema, el recordatorio se omite sin romper la corrida.
            skipped += 1
            continue
        existing = session.exec(
            select(EmailOutbox).where(
                EmailOutbox.tender_id == tender.id,
                EmailOutbox.email_type == EMAIL_TYPE_REMINDER,
            )
        ).all()
        if any(o.status in ("pending", "sent") for o in existing):
            duplicated += 1  # ya programado/enviado en una corrida previa
            continue
        outbox = EmailOutbox(
            tender_id=tender.id,
            email_type=EMAIL_TYPE_REMINDER,
            to_email=client.company_email,
            subject=f"[CSC] Recordatorio: {tender.reference or tender.title} — {client.name}",
            body_html=_reminder_html(session, tender, client.name),
            status="pending",
            attempt_count=0,
        )
        session.add(outbox)
        session.flush()  # asigna id sin cerrar el lock
        scheduled.append((outbox, tender.id))

    if scheduled:
        # Libera el lock de la licitación; las intenciones pending persisten.
        session.commit()

    sent = failed = 0
    for outbox, tender_id in scheduled:
        # Envío real FUERA de la transacción (patrón outbox, CONTEXT.md §4).
        dispatched = email_service.dispatch_outbox(session, outbox)
        if dispatched.status != "sent":
            failed += 1
            continue  # se reintentará en la próxima corrida (outbox failed)
        sent += 1
        tender = session.get(Tender, tender_id)
        if tender is not None:
            tender.reminder_sent_at = utcnow()
            session.commit()

    return {
        "reminders_sent": sent,
        "reminders_failed": failed,
        "reminders_duplicated": duplicated,
        "reminders_skipped_no_client": skipped,
    }


def _reminder_html(session: Session, tender: Tender, client_name: str) -> str:
    """Resumen de partidas/presupuesto/deadline para el correo (sin adjunto)."""
    items = list(session.exec(select(TenderItem).where(TenderItem.tender_id == tender.id)))
    products = {
        p.id: p.name
        for p in session.exec(
            select(Product).where(Product.id.in_([i.product_id for i in items]))
        )
    }
    total = current_total(session, tender.id)
    return email_service.build_tender_summary_html(
        title=f"Recordatorio: {tender.title} — {client_name}",
        items=[
            (
                products.get(i.product_id, "¿?"),
                str(i.quantity),
                f"{i.subtotal():.2f}",
            )
            for i in items
        ],
        total=f"{total:.2f}",
        budget_max=f"{tender.budget_max:.2f}",
        deadline_at=tender.deadline_at.strftime("%Y-%m-%d %H:%M UTC"),
    )