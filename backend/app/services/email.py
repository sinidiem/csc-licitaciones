"""Servicio de envío de email con patrón Outbox (CONTEXT.md §4).

Diseño: el envío real a Resend se hace FUERA de la transacción SQL.
1) Se persiste la intención (outbox pending) y se hace COMMIT.
2) Se llama al proveedor externo.
3) Se confirma el resultado (sent + provider_message_id | failed) en otra
   transacción corta.

Así un timeout ambiguo del proveedor nunca deja la BD en un estado
inconsistente y el reintento es seguro (idempotencia por fila de outbox).
En ningún caso se loguean secretos, tokens ni contenido de propuestas.
"""

import logging
import uuid
from typing import Any, Optional

import resend
from sqlmodel import Session

from app.core.config import settings
from app.models.email_outbox import EmailOutbox
from app.models.mixins import utcnow

logger = logging.getLogger(__name__)


def _configure_resend_sdk() -> bool:
    """Activa la key del SDK y devuelve False si no está configurada."""
    if not settings.resend_api_key:
        return False
    resend.api_key = settings.resend_api_key
    return True


def _deliver(outbox: EmailOutbox, params: Any) -> EmailOutbox:
    """Llama al proveedor con `params` y confirma sent/failed en la fila.

    Sin transacción abierta (el INSERT/COMMIT previo ya cerró la suya): el
    proveedor se llama FUERA de cualquier transacción SQL (CONTEXT.md §4).
    """
    try:
        response = resend.Emails.send(params)
    except Exception as exc:  # noqa: BLE001 - errores del proveedor externo
        logger.warning("Resend falló (outbox %s): %s", outbox.id, exc)
        outbox.status = "failed"
        outbox.error_summary = f"{type(exc).__name__}: {exc}"[:2000]
    else:
        outbox.status = "sent"
        outbox.provider_message_id = getattr(response, "id", None)
        outbox.sent_at = utcnow()
    outbox.attempt_count += 1
    return outbox


def send_email(
    session: Session,
    *,
    to_email: str,
    subject: str,
    html_body: str,
    email_type: str,
    tender_id: Optional[uuid.UUID] = None,
    attachment_content: Optional[bytes] = None,
    attachment_filename: Optional[str] = None,
) -> EmailOutbox:
    """Crea el registro outbox y dispara el envío real (si hay key).

    Devuelve la fila de outbox ya persistida (sent/failed). Si no hay key
    configurada, queda en `failed` con error_summary claro — útil para
    desarrollo sin exponer la integración.
    """
    # 1) Intención persistida en transacción corta.
    outbox = EmailOutbox(
        tender_id=tender_id,
        email_type=email_type,
        to_email=to_email,
        subject=subject,
        body_html=html_body,
        status="pending",
        attempt_count=0,
    )
    session.add(outbox)
    session.commit()
    session.refresh(outbox)

    if not _configure_resend_sdk():
        outbox.status = "failed"
        outbox.error_summary = "RESEND_API_KEY no configurada en el entorno"
        session.commit()
        session.refresh(outbox)
        return outbox

    params: dict = {
        "from": settings.resend_from,
        "to": [to_email],
        "subject": subject,
        "html": html_body,
    }
    if attachment_content is not None and attachment_filename:
        params["attachments"] = [
            {
                "filename": attachment_filename,
                "content": list(attachment_content),
            }
        ]

    _deliver(outbox, params)

    # 3) Confirmación del resultado en transacción corta.
    session.commit()
    session.refresh(outbox)
    return outbox


def dispatch_outbox(session: Session, outbox: EmailOutbox) -> EmailOutbox:
    """Fase proveedor para una fila outbox YA creada (patrón outbox, §4).

    Lo usan los jobs (recordatorio 48h): la intención (status='pending') se
    inserta DENTRO de la transacción que protege la licitación (idempotencia
    ante corridas concurrentes del cron), y aquí se dispara el envío real
    fuera de esa transacción. Sin adjuntos. No reenvía filas ya `sent`.
    """
    if outbox.status == "sent":
        return outbox  # idempotente
    if not _configure_resend_sdk():
        outbox.status = "failed"
        outbox.error_summary = "RESEND_API_KEY no configurada en el entorno"
        session.commit()
        session.refresh(outbox)
        return outbox

    _deliver(
        outbox,
        {
            "from": settings.resend_from,
            "to": [outbox.to_email],
            "subject": outbox.subject,
            "html": outbox.body_html or "",
        },
    )
    session.commit()
    session.refresh(outbox)
    return outbox


def build_tender_summary_html(*, title: str, items: list[tuple[str, int, str]], total: str, budget_max: str, deadline_at: str) -> str:
    """Resumen del correo de licitación: productos, presupuesto, fecha límite.

    Recibe los importes YA formateados como string (Decimal nunca se
    serializa de otra forma); los items son (nombre, cantidad, subtotal).
    """
    rows = "".join(
        f"<tr><td>{name}</td><td align='right'>{qty}</td>"
        f"<td align='right'>{subtotal}</td></tr>"
        for name, qty, subtotal in items
    )
    return f"""
    <html><body style="font-family: sans-serif">
      <h2>{title}</h2>
      <table border="1" cellpadding="6" cellspacing="0" style="border-collapse: collapse">
        <tr><th>Producto</th><th>Cantidad</th><th>Subtotal</th></tr>
        {rows}
        <tr><td colspan="2"><strong>Total</strong></td>
            <td align="right"><strong>{total}</strong></td></tr>
      </table>
      <p>Presupuesto máximo: <strong>{budget_max}</strong></p>
      <p>Fecha límite: <strong>{deadline_at}</strong></p>
    </body></html>
    """