"""Pruebas del día 7 del plan: resolución (finish/lose), factura y cobros.

Cubre la matriz de transiciones (409 INVALID_STATUS_TRANSITION), el registro
de factura con importe distinto del total (decisión CONTEXT.md §11.3), los
pagos parciales sin sobrepago (422 OVERPAYMENT), la transición automática a
`collected` al saldar y el bloqueo de partidas en estados terminales.

El envío oficial (draft → active) usa un email SIMULADO (monkeypatch del
servicio): en pruebas nunca se llama al proveedor real (conftest vacía
RESEND_API_KEY).
"""

from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest


# ---------------------------------------------------------------------------
# Helpers de siembra (vía API, como usuario autenticado)
# ---------------------------------------------------------------------------

def _future_deadline(days: int = 10) -> str:
    return (datetime.now(UTC) + timedelta(days=days)).isoformat()


def _create_client(client, name: str = "Cliente de prueba") -> str:
    r = client.post(
        "/api/v1/clients/",
        json={"name": name, "company_email": f"{name.lower().replace(' ', '')}@example.com"},
    )
    assert r.status_code == 201, r.text
    return r.json()["id"]


def _create_product(client, name: str = "Acero estructural") -> str:
    r = client.post(
        "/api/v1/products/",
        json={"name": name, "default_unit_price": "150.00", "description": "kg"},
    )
    assert r.status_code == 201, r.text
    return r.json()["id"]


def _create_tender(client, client_id: str, budget_max: str = "10000.00") -> str:
    r = client.post(
        "/api/v1/tenders/",
        json={
            "client_id": client_id,
            "title": "Suministro equipos planta",
            "reference": "LIC-TEST-001",
            "deadline_at": _future_deadline(),
            "budget_max": budget_max,
        },
    )
    assert r.status_code == 201, r.text
    return r.json()["id"]


def _add_item(client, tender_id: str, product_id: str, quantity: int = 2, unit_price: str = "150.00") -> dict:
    r = client.post(
        f"/api/v1/tenders/{tender_id}/items",
        json={"product_id": product_id, "quantity": quantity, "unit_price": unit_price},
    )
    assert r.status_code == 201, r.text
    return r.json()


def _upload_proposal(client, tender_id: str) -> None:
    files = {"file": ("propuesta.pdf", b"%PDF-1.4 propuesta de prueba", "application/pdf")}
    r = client.post(f"/api/v1/tenders/{tender_id}/proposal", files=files)
    assert r.status_code == 201, r.text


def _mock_email_sent(monkeypatch) -> None:
    """Sustituye el envío real por un outbox aceptado (status='sent')."""

    class _FakeOutbox:
        status = "sent"

    def _fake_send(*args, **kwargs):  # noqa: ARG001
        return _FakeOutbox()

    monkeypatch.setattr("app.services.email.send_email", _fake_send)


def _send_tender(client, tender_id: str) -> dict:
    r = client.post(f"/api/v1/tenders/{tender_id}/send")
    assert r.status_code == 200, r.text
    return r.json()


def _seed_active_tender(client, **kwargs):
    """Cliente + producto + borrador con partida + propuesta + envío -> active."""
    cid = _create_client(client, kwargs.get("client_name", "Cliente de prueba"))
    pid = _create_product(client)
    tid = _create_tender(client, cid, budget_max=kwargs.get("budget_max", "10000.00"))
    _add_item(client, tid, pid, quantity=kwargs.get("quantity", 2))
    _upload_proposal(client, tid)
    detail = _send_tender(client, tid)
    assert detail["status"] == "active"
    return tid


def _seed_draft_tender(client, **kwargs) -> str:
    """Borrador sin propuesta ni envío (estado de partida para tests de
    transiciones inválidas desde 'draft')."""
    cid = _create_client(client, kwargs.get("client_name", "Cliente de prueba"))
    pid = _create_product(client)
    tid = _create_tender(client, cid, budget_max=kwargs.get("budget_max", "10000.00"))
    _add_item(client, tid, pid)
    assert client.get(f"/api/v1/tenders/{tid}").json()["status"] == "draft"
    return tid


def _finish(client, tender_id: str) -> dict:
    r = client.post(f"/api/v1/tenders/{tender_id}/transitions/finish", json={"reason": "Entrega completada"})
    assert r.status_code == 200, r.text
    return r.json()


def _invoice(client, tender_id: str, amount: str) -> dict:
    r = client.post(
        f"/api/v1/tenders/{tender_id}/invoice",
        json={"invoiced_total": amount},
    )
    assert r.status_code == 200, r.text
    return r.json()


def _code(r) -> str:
    return r.json()["detail"]["code"]


def _statuses(detail: dict) -> list[str]:
    return [h["to_status"] for h in detail["history"]]


# ---------------------------------------------------------------------------
# Flujo completo: borrador -> activa -> finalizada -> por_cobrar -> cobrada
# ---------------------------------------------------------------------------

def test_flujo_completo_hasta_cobrada(client, admin, monkeypatch):
    _mock_email_sent(monkeypatch)
    tid = _seed_active_tender(client)

    detail = _finish(client, tid)
    assert detail["status"] == "finished"

    # Factura por importe DISTINTO del total de partidas (300.00 -> 2500.00):
    # decisión §11.3 permite negociación; aquí facturamos 2500.00.
    detail = _invoice(client, tid, "2500.00")
    assert detail["status"] == "to_collect"
    assert detail["invoiced_total"] == "2500.00"
    assert detail["saldo_pendiente"] == "2500.00"

    # Pago parcial
    r = client.post(
        f"/api/v1/tenders/{tid}/payments",
        json={"amount": "1000.00", "reference": "TRF-001", "notes": "primer abono"},
    )
    assert r.status_code == 201, r.text
    detail = r.json()
    assert detail["status"] == "to_collect"
    assert detail["saldo_pendiente"] == "1500.00"
    assert len(detail["payments"]) == 1

    # Pago que salda -> transición automática a collected
    r = client.post(f"/api/v1/tenders/{tid}/payments", json={"amount": "1500.00"})
    assert r.status_code == 201, r.text
    detail = r.json()
    assert detail["status"] == "collected"
    assert detail["saldo_pendiente"] == "0.00"
    assert len(detail["payments"]) == 2

    # Historial completo y en orden
    assert _statuses(detail) == ["draft", "active", "finished", "to_collect", "collected"]
    assert all(h["source"] == "user" for h in detail["history"])


def test_flujo_perdida(client, admin, monkeypatch):
    _mock_email_sent(monkeypatch)
    tid = _seed_active_tender(client)
    r = client.post(f"/api/v1/tenders/{tid}/transitions/lose", json={"reason": "Ganó otro proveedor"})
    assert r.status_code == 200, r.text
    detail = r.json()
    assert detail["status"] == "lost"
    assert _statuses(detail) == ["draft", "active", "lost"]
    # Perdida es terminal: no facturable ni pagable
    assert _code(client.post(f"/api/v1/tenders/{tid}/invoice", json={"invoiced_total": "1.00"})) == "INVALID_STATUS_TRANSITION"
    assert _code(client.post(f"/api/v1/tenders/{tid}/payments", json={"amount": "1.00"})) == "INVALID_STATUS_TRANSITION"


# ---------------------------------------------------------------------------
# Matriz de transiciones inválidas
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "target_state,action",
    [
        ("draft", "finish"),
        ("draft", "lose"),
        ("draft", "invoice"),
        ("draft", "payments"),
        ("active", "invoice"),
        ("active", "payments"),
        ("active", "send"),
        ("finished", "lose"),
        ("finished", "payments"),
        ("finished", "send"),
        ("to_collect", "finish"),
        ("to_collect", "lose"),
        ("to_collect", "invoice"),
        ("to_collect", "send"),
        ("lost", "finish"),
        ("lost", "invoice"),
        ("lost", "payments"),
        ("collected", "payments"),
        ("collected", "finish"),
        ("collected", "invoice"),
    ],
)
def test_transiciones_invalidas(client, admin, monkeypatch, target_state, action):
    _mock_email_sent(monkeypatch)
    if target_state == "draft":
        tid = _seed_draft_tender(client)
    else:
        tid = _seed_active_tender(client)

    # Llevar la licitación al estado de partida pedido
    detail = None
    if target_state in ("draft", "active"):
        detail = {"status": target_state}
    elif target_state == "finished":
        detail = _finish(client, tid)
    elif target_state == "to_collect":
        _finish(client, tid)
        detail = _invoice(client, tid, "2500.00")
    elif target_state == "lost":
        r = client.post(f"/api/v1/tenders/{tid}/transitions/lose", json={})
        assert r.status_code == 200, r.text
        detail = r.json()
    elif target_state == "collected":
        _finish(client, tid)
        _invoice(client, tid, "2500.00")
        r = client.post(f"/api/v1/tenders/{tid}/payments", json={"amount": "2500.00"})
        assert r.status_code == 201, r.text
        detail = r.json()
    assert detail["status"] == target_state

    url_by_action = {
        "finish": f"/api/v1/tenders/{tid}/transitions/finish",
        "lose": f"/api/v1/tenders/{tid}/transitions/lose",
        "invoice": f"/api/v1/tenders/{tid}/invoice",
        "send": f"/api/v1/tenders/{tid}/send",
    }
    if action == "payments":
        r = client.post(f"/api/v1/tenders/{tid}/payments", json={"amount": "1.00"})
    else:
        payload = {"invoiced_total": "1.00"} if action == "invoice" else {}
        r = client.post(url_by_action[action], json=payload)
    assert r.status_code == 409, f"{target_state} + {action}: {r.text}"
    assert _code(r) == "INVALID_STATUS_TRANSITION"


# ---------------------------------------------------------------------------
# Factura (finalizada -> por_cobrar)
# ---------------------------------------------------------------------------

def test_invoice_importe_cero_o_negativo_rechazado(client, admin, monkeypatch):
    _mock_email_sent(monkeypatch)
    tid = _seed_active_tender(client)
    _finish(client, tid)
    assert client.post(f"/api/v1/tenders/{tid}/invoice", json={"invoiced_total": "0"}).status_code == 422
    assert client.post(f"/api/v1/tenders/{tid}/invoice", json={"invoiced_total": "-50.00"}).status_code == 422
    assert client.post(f"/api/v1/tenders/{tid}/invoice", json={"invoiced_total": "0.001"}).status_code == 422


def test_invoice_factura_doble_rechazada(client, admin, monkeypatch):
    _mock_email_sent(monkeypatch)
    tid = _seed_active_tender(client)
    _finish(client, tid)
    _invoice(client, tid, "2500.00")
    r = client.post(f"/api/v1/tenders/{tid}/invoice", json={"invoiced_total": "3000.00"})
    assert r.status_code == 409
    assert _code(r) == "INVALID_STATUS_TRANSITION"


def test_invoice_menor_a_pagos_existentes_rechazada(client, admin, monkeypatch):
    """Guardia de servicio INVOICE_BELOW_PAYMENTS (defensiva; vía API los pagos
    requieren to_collect, así que se fuerza insertando un pago directo)."""
    from uuid import UUID

    from fastapi import HTTPException
    from sqlmodel import Session

    from app.db.engine import engine
    from app.models.payment import Payment
    from app.models.tender import Tender
    from app.services import transitions as transitions_service

    _mock_email_sent(monkeypatch)
    tid = _seed_active_tender(client)
    _finish(client, tid)
    detail = client.get(f"/api/v1/tenders/{tid}").json()

    with Session(engine) as s:
        s.add(Payment(tender_id=UUID(tid), amount=Decimal("500.00"), created_by=UUID(detail["created_by"])))
        s.commit()
        tender = s.get(Tender, UUID(tid))
        assert tender is not None

        with pytest.raises(HTTPException) as exc:
            transitions_service.invoice_tender(
                s, tender, amount=Decimal("300.00"), actor_user_id=UUID(detail["created_by"])
            )
        assert exc.value.status_code == 422
        assert exc.value.detail["code"] == "INVOICE_BELOW_PAYMENTS"
        s.rollback()

        # La transacción se deshizo: sigue finished y sin factura
        tender2 = s.get(Tender, UUID(tid))
        assert tender2.status == "finished"
        assert tender2.invoiced_total is None


# ---------------------------------------------------------------------------
# Pagos (por_cobrar)
# ---------------------------------------------------------------------------

def _to_collect_tender(client, monkeypatch, invoiced: str = "2500.00") -> str:
    """Licitación ya en por_cobrar, lista para pagos."""
    _mock_email_sent(monkeypatch)
    tid = _seed_active_tender(client)
    _finish(client, tid)
    _invoice(client, tid, invoiced)
    return tid


def test_pago_sobrepago_rechazado_y_saldo_intacto(client, admin, monkeypatch):
    tid = _to_collect_tender(client, monkeypatch, invoiced="1000.00")

    r = client.post(f"/api/v1/tenders/{tid}/payments", json={"amount": "1000.01"})
    assert r.status_code == 422
    assert _code(r) == "OVERPAYMENT"

    # Sin efectos colaterales: sigue por_cobrar, sin pagos, saldo intacto
    detail = client.get(f"/api/v1/tenders/{tid}").json()
    assert detail["status"] == "to_collect"
    assert detail["payments"] == []
    assert detail["saldo_pendiente"] == "1000.00"


def test_pago_importe_invalido(client, admin, monkeypatch):
    tid = _to_collect_tender(client, monkeypatch)
    assert client.post(f"/api/v1/tenders/{tid}/payments", json={"amount": "0"}).status_code == 422
    assert client.post(f"/api/v1/tenders/{tid}/payments", json={"amount": "-5.00"}).status_code == 422


def test_ultimo_pago_transiciona_a_collected_en_la_misma_transaccion(client, admin, monkeypatch):
    tid = _to_collect_tender(client, monkeypatch, invoiced="2500.00")

    r = client.post(f"/api/v1/tenders/{tid}/payments", json={"amount": "2499.99"})
    assert r.status_code == 201
    assert r.json()["status"] == "to_collect"
    assert r.json()["saldo_pendiente"] == "0.01"

    r = client.post(f"/api/v1/tenders/{tid}/payments", json={"amount": "0.01"})
    assert r.status_code == 201
    detail = r.json()
    assert detail["status"] == "collected"
    assert detail["saldo_pendiente"] == "0.00"
    assert _statuses(detail) == ["draft", "active", "finished", "to_collect", "collected"]
    # El historial de la transición automática queda en la misma transacción
    last = detail["history"][-1]
    assert last["from_status"] == "to_collect" and last["to_status"] == "collected"
    assert last["source"] == "user"


def test_partidas_bloqueadas_tras_activar_y_en_terminales(client, admin, monkeypatch):
    """Regresión decisión §11.1: partidas solo editables en borrador."""
    _mock_email_sent(monkeypatch)
    cid = _create_client(client)
    pid = _create_product(client)
    tid = _create_tender(client, cid)
    _add_item(client, tid, pid)

    # Tras enviar (active): agregar/quitar partida -> 409
    _upload_proposal(client, tid)
    item_id = client.get(f"/api/v1/tenders/{tid}").json()["items"][0]["id"]
    _send_tender(client, tid)
    r = client.post(f"/api/v1/tenders/{tid}/items", json={"product_id": pid, "quantity": 1, "unit_price": "10.00"})
    assert r.status_code == 409 and _code(r) == "INVALID_STATUS_TRANSITION"
    r = client.delete(f"/api/v1/tenders/{tid}/items/{item_id}")
    assert r.status_code == 409 and _code(r) == "INVALID_STATUS_TRANSITION"

    # En 'finalizada' también
    _finish(client, tid)
    r = client.post(f"/api/v1/tenders/{tid}/items", json={"product_id": pid, "quantity": 1, "unit_price": "10.00"})
    assert r.status_code == 409 and _code(r) == "INVALID_STATUS_TRANSITION"


def test_pago_concurrente_no_sobrepasa(client, admin, monkeypatch):
    """Carrera: dos abonos por el saldo completo a la vez; el FOR UPDATE
    serializa y solo uno puede ganar (patrón probado en día 4 para partidas)."""
    from threading import Barrier, Thread

    from fastapi.testclient import TestClient

    from app.main import app

    tid = _to_collect_tender(client, monkeypatch, invoiced="2500.00")

    results: list[int] = []
    barrier = Barrier(2)

    def _pay():
        with TestClient(app) as c:
            r = c.post(
                "/api/v1/auth/login",
                json={"email": "admin@example.com", "password": "Passw0rd!"},
            )
            assert r.status_code == 200, r.text
            barrier.wait()
            r = c.post(f"/api/v1/tenders/{tid}/payments", json={"amount": "2500.00"})
            results.append(r.status_code)

    threads = [Thread(target=_pay) for _ in range(2)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    # El invariante: exactamente UN pago válido. El otro queda en 409
    # (estado ya cambiado tras el lock) o 422 OVERPAYMENT según el momento
    # exacto de lectura, pero nunca dos abonos aceptados.
    assert results.count(201) == 1
    assert all(s in (201, 409, 422) for s in results)

    detail = client.get(f"/api/v1/tenders/{tid}").json()
    assert detail["status"] == "collected"
    assert len(detail["payments"]) == 1
    assert detail["saldo_pendiente"] == "0.00"