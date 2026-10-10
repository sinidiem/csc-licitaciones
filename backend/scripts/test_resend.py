"""Verificación REAL del envío de email con Resend (patrón outbox).

Uso (desde backend/):
    RESEND_API_KEY=re_*** RESEND_TEST_TO=tu@email.com ./venv/bin/python -m scripts.test_resend

O mejor: pon RESEND_API_KEY y RESEND_TEST_TO en el .env (gitignored) y ejecuta:
    ./venv/bin/python -m scripts.test_resend

Qué hace:
1. Envía un correo de prueba real vía el servicio outbox (app.services.email).
2. Muestra el id del proveedor (evidencia verificable) y el estado en BD.
No imprime ni guarda la API key. Según CONTEXT.md §8, el email requiere
evidencia del entorno real: el provider_message_id mostrado aquí es esa
evidencia.
"""

import uuid

from sqlmodel import Session, select

from app.core.config import settings
from app.db.engine import engine
from app.models.email_outbox import EmailOutbox
from app.services.email import build_tender_summary_html, send_email


def main() -> None:
    if not settings.resend_api_key:
        print("ERROR: RESEND_API_KEY no está en el entorno/.env.")
        print("Ponla en backend/.env (gitignored) y vuelve a ejecutar.")
        raise SystemExit(1)
    if not settings.resend_test_to:
        print("ERROR: RESEND_TEST_TO vacío. En sandbox debe ser el email")
        print("verificado de tu cuenta de Resend.")
        raise SystemExit(1)

    summary = build_tender_summary_html(
        title="Prueba CSC - Licitación ejemplo",
        items=[("Desarrollo web a medida", 1, "2500.00"), ("Auditoría de seguridad", 2, "2200.00")],
        total="4250.00",
        budget_max="5000.00",
        deadline_at="2026-10-20 23:59 UTC",
    )

    with Session(engine) as session:
        outbox = send_email(
            session,
            to_email=settings.resend_test_to,
            subject="[CSC] Prueba de envío Resend",
            html_body=summary,
            email_type="test",
        )
        print(f"Outbox row:    {outbox.id}  status={outbox.status}")
        print(f"Provider id:   {outbox.provider_message_id or '(ninguno)'}")
        print(f"Error summary: {outbox.error_summary or '(ninguno)'}")

        if outbox.status != "sent":
            print("\nFALLO: el correo no se envió. Revisa la key y el dominio.")
            raise SystemExit(1)

        # Verificación de persistencia en BD (patrón outbox)
        row = session.exec(select(EmailOutbox).where(EmailOutbox.id == outbox.id)).one()
        assert row.status == "sent" and row.provider_message_id
        print(f"\nOK  — persistido en email_outbox  attempts={row.attempt_count}")
        print(f"      sent_at={row.sent_at}  type={row.email_type}")
        print("\nRevisa tu bandeja de entrada:", settings.resend_test_to)


if __name__ == "__main__":
    main()