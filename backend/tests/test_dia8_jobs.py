"""Pruebas del día 8 del plan: jobs de vencimiento y recordatorio 48h.

Cubre:
- Autenticación del endpoint interno (401 sin/secreto inválido; 200 con
  el correcto).
- Vencimiento automático: active + deadline vencido → lost (actor system),
  idempotente (una sola transición aunque se corra dos veces o en paralelo).
- Recordatorio: active dentro de 48h → UN solo correo (outbox
  tender_reminder) y `reminder_sent_at` marcado solo cuando el proveedor
  acepta; sin tocar vencidas ni las que faltan > 48h.
- Correos simulados (dispatch_outbox monkeypatcheado): nunca se llama al
  proveedor real en pruebas (conftest vacía RESEND_API_KEY igualmente).
"""

from datetime import timedelta
from uuid import UUID

import pytest

from app.core.config import settings


# ---------------------------------------------------------------------------
# Helpers locales (mismos contratos que en test_dia7, con deadline libre)
# ---------------------------------------------------------------------------

def _future_deadline(days: int = 10) -> str:
    from datetime import UTC, datetime

    return (datetime.now(UTC) + timedelta(days=days)).isoformat()


def _create_client(client) -> str:
    r = client.post(
        "/api/v1/clients/",
        json={"name": "Minera Los Andes", "company_email": "minera@example.com"},
    )
    assert r.status_code == 201, r.text
    return r.json()["id"]


def _create_product(client) -> str:
    r = client.post(
        "/api/v1/products/",
        json={"name": "Bomba hidráulica", "default_unit_price": "250.00"},
    )
    assert r.status_code == 201, r.text
    return r.json()["id"]


def _create_tender(client, client_id: str, deadline_at: str) -> str:
    r = client.post(
        "/api/v1/tenders/",
        json={
            "client_id": client_id,
            "title": "Repuestos planta 3",
            "reference": "LIC-JOB-TEST",
            "deadline_at": deadline_at,
            "budget_max": "5000.00",
        },
    )
    assert r.status_code == 201, r.text
    return r.json()["id"]


def _active_tender(client, monkeypatch, deadline_at: str) -> str:
    """Cliente + producto + borrador activado con email simulado."""

    def _mock_send_email(*args, **kwargs):
        class _Ok:
            status = "sent"

        return _Ok()

    monkeypatch.setattr("app.services.email.send_email", _mock_send_email)

    cid = _create_client(client)
    pid = _create_product(client)
    tid = _create_tender(client, cid, deadline_at)
    r = client.post(
        f"/api/v1/tenders/{tid}/items",
        json={"product_id": pid, "quantity": 3, "unit_price": "250.00"},
    )
    assert r.status_code == 201, r.text
    files = {"file": ("propuesta.pdf", b"%PDF-1.4 prueba jobs", "application/pdf")}
    r = client.post(f"/api/v1/tenders/{tid}/proposal", files=files)
    assert r.status_code == 201, r.text
    r = client.post(f"/api/v1/tenders/{tid}/send")
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "active"
    return tid


def _mock_dispatch_sent(monkeypatch) -> None:
    """El job programa el outbox y aquí el proveedor SIEMPRE acepta."""

    def _fake_dispatch(session, outbox):
        outbox.status = "sent"
        outbox.provider_message_id = "fake-job-id"
        outbox.attempt_count += 1
        session.commit()
        return outbox

    monkeypatch.setattr("app.services.email.dispatch_outbox", _fake_dispatch)


def _run_jobs(client, secret: str | None = None):
    headers = {} if secret is None else {"X-Cron-Secret": secret}
    return client.post("/internal/jobs/tenders", headers=headers)


def _deadline(delta: timedelta) -> str:
    from datetime import UTC, datetime

    return (datetime.now(UTC) + delta).isoformat()


def _outbox_count(tender_id: str, email_type: str = "tender_reminder") -> int:
    from sqlmodel import Session, select

    from app.db.engine import engine
    from app.models.email_outbox import EmailOutbox

    with Session(engine) as s:
        return len(
            s.exec(
                select(EmailOutbox).where(
                    EmailOutbox.tender_id == UUID(tender_id),
                    EmailOutbox.email_type == email_type,
                )
            ).all()
        )


# ---------------------------------------------------------------------------
# Autenticación del endpoint
# ---------------------------------------------------------------------------

def test_job_requiere_secreto(client, admin):
    assert _run_jobs(client).status_code == 401
    assert _run_jobs(client, secret="secreto-equivocado").status_code == 401
    assert _run_jobs(client, secret=settings.cron_secret).status_code == 200


# ---------------------------------------------------------------------------
# Vencimiento automático
# ---------------------------------------------------------------------------

def test_vencimiento_automatico_y_idempotente(client, admin, monkeypatch):
    tid = _active_tender(client, monkeypatch, _deadline(timedelta(hours=-2)))

    result = _run_jobs(client, secret=settings.cron_secret)
    assert result.status_code == 200
    assert result.json() == {"expired": 1, "reminders_sent": 0, "reminders_failed": 0,
                             "reminders_duplicated": 0, "reminders_skipped_no_client": 0}

    detail = client.get(f"/api/v1/tenders/{tid}").json()
    assert detail["status"] == "lost"
    last = detail["history"][-1]
    assert last["from_status"] == "active" and last["to_status"] == "lost"
    assert last["source"] == "system"
    assert last["actor_user_id"] is None

    # Segunda corrida: sin efecto
    assert _run_jobs(client, secret=settings.cron_secret).json()["expired"] == 0
    detail = client.get(f"/api/v1/tenders/{tid}").json()
    assert detail["status"] == "lost"
    assert sum(1 for h in detail["history"] if h["to_status"] == "lost") == 1


def test_vencimiento_no_toca_no_vencidas(client, admin, monkeypatch):
    tid = _active_tender(client, monkeypatch, _deadline(timedelta(days=3)))
    result = _run_jobs(client, secret=settings.cron_secret).json()
    assert result["expired"] == 0
    assert client.get(f"/api/v1/tenders/{tid}").json()["status"] == "active"


def test_vencimiento_concurrente_una_sola_transicion(client, admin, monkeypatch):
    from threading import Barrier, Thread

    from fastapi.testclient import TestClient

    from app.main import app

    tid = _active_tender(client, monkeypatch, _deadline(timedelta(hours=-1)))
    barrier = Barrier(2)

    def _run():
        with TestClient(app) as c:
            barrier.wait()
            r = c.post("/internal/jobs/tenders", headers={"X-Cron-Secret": settings.cron_secret})
            assert r.status_code == 200

    threads = [Thread(target=_run) for _ in range(2)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    detail = client.get(f"/api/v1/tenders/{tid}").json()
    assert detail["status"] == "lost"
    assert sum(1 for h in detail["history"] if h["to_status"] == "lost") == 1


# ---------------------------------------------------------------------------
# Recordatorio 48h
# ---------------------------------------------------------------------------

def test_recordatorio_dentro_de_48h_una_sola_vez(client, admin, monkeypatch):
    _mock_dispatch_sent(monkeypatch)
    tid = _active_tender(client, monkeypatch, _deadline(timedelta(hours=24)))

    result = _run_jobs(client, secret=settings.cron_secret)
    assert result.status_code == 200
    assert result.json()["reminders_sent"] == 1

    detail = client.get(f"/api/v1/tenders/{tid}").json()
    assert detail["reminder_sent_at"] is not None
    assert detail["status"] == "active"
    assert _outbox_count(tid) == 1

    # Segunda corrida: ni reenvío ni duplicado
    result2 = _run_jobs(client, secret=settings.cron_secret).json()
    assert result2["reminders_sent"] == 0
    assert result2["reminders_duplicated"] == 0  # ya no es candidato (reminder_sent_at)
    assert _outbox_count(tid) == 1


def test_recordatorio_no_antes_de_48h(client, admin, monkeypatch):
    _mock_dispatch_sent(monkeypatch)
    tid = _active_tender(client, monkeypatch, _deadline(timedelta(hours=72)))

    result = _run_jobs(client, secret=settings.cron_secret).json()
    assert result["reminders_sent"] == 0
    assert result["expired"] == 0
    detail = client.get(f"/api/v1/tenders/{tid}").json()
    assert detail["reminder_sent_at"] is None
    assert _outbox_count(tid) == 0
    assert detail["status"] == "active"


def test_recordatorio_no_toca_vencidas(client, admin, monkeypatch):
    _mock_dispatch_sent(monkeypatch)
    tid = _active_tender(client, monkeypatch, _deadline(timedelta(hours=-1)))

    result = _run_jobs(client, secret=settings.cron_secret).json()
    assert result["expired"] == 1
    assert result["reminders_sent"] == 0
    assert _outbox_count(tid) == 0
    assert client.get(f"/api/v1/tenders/{tid}").json()["status"] == "lost"


def test_recordatorio_concurrente_un_solo_correo(client, admin, monkeypatch):
    from threading import Barrier, Thread

    from fastapi.testclient import TestClient

    from app.main import app

    _mock_dispatch_sent(monkeypatch)
    tid = _active_tender(client, monkeypatch, _deadline(timedelta(hours=12)))
    barrier = Barrier(2)

    def _run():
        with TestClient(app) as c:
            barrier.wait()
            r = c.post("/internal/jobs/tenders", headers={"X-Cron-Secret": settings.cron_secret})
            assert r.status_code == 200

    threads = [Thread(target=_run) for _ in range(2)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    total = sum(
        _outbox_count(tid, t)
        for t in ("tender_reminder",)
    )
    assert total == 1
    detail = client.get(f"/api/v1/tenders/{tid}").json()
    assert detail["reminder_sent_at"] is not None
    assert detail["status"] == "active"