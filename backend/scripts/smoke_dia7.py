"""Smoke test del día 7 contra un uvicorn en ejecución (evidencia real).

Recorre el flujo completo por HTTP contra PostgreSQL real:
borrador -> partida -> propuesta -> ENVÍO real (Resend, email + adjunto)
-> finalizada -> por_cobrar (factura distinta del total, decisión §11.3)
-> pagos parciales + sobrepago rechazado -> cobrada con historial completo.

Requisitos: uvicorn corriendo (./venv/bin/uvicorn app.main:app) y credenciales
en backend/.env (admin + RESEND_API_KEY + RESEND_TEST_TO). No imprime
secretos; los lee vía settings.

Uso: ./venv/bin/python -m scripts.smoke_dia7 [base_url]
"""

import sys
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import httpx

from app.core.config import settings

BASE_URL = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8000"

PASS, FAIL = "ok  ", "FALLO"


def main() -> int:
    results: list[tuple[str, bool, str]] = []

    def check(name: str, ok: bool, extra: str = "") -> None:
        results.append((name, ok, extra))
        print(f"[{PASS if ok else FAIL}] {name} {extra}")

    with httpx.Client(base_url=BASE_URL, timeout=30) as c:
        # --- Auth ---------------------------------------------------------
        r = c.post("/api/v1/auth/login", json={
            "email": settings.admin_email, "password": settings.admin_password,
        })
        check("login admin", r.status_code == 200, f"({r.status_code})")

        # --- Datos maestros ----------------------------------------------
        ref = datetime.now(UTC).strftime("%H%M%S")
        client_name = f"Consultoria Smoke {ref}"
        delivery_email = settings.resend_test_to or "no-enviar@example.com"
        # El email de entrega del sandbox es único y puede existir de una
        # corrida anterior: se reutiliza (evita 409 DUPLICATE y garantiza
        # entrega verificada).
        existing = c.get("/api/v1/clients", params={"limit": 100}).json()
        client_hit = next(
            (x for x in existing if x.get("company_email") == delivery_email), None
        )
        if client_hit is not None:
            client_id = client_hit["id"]
            check("reutilizar cliente del sandbox (email único)",
                  bool(client_id), f"({client_hit['name']})")
        else:
            r = c.post("/api/v1/clients", json={
                "name": client_name,
                "company_email": delivery_email,
            })
            ok = r.status_code == 201
            client_id = r.json().get("id", "") if ok else ""
            check("crear cliente (email de entrega del sandbox)", ok, f"({r.status_code})")

        r = c.post("/api/v1/products", json={
            "name": f"Servicio {ref}", "default_unit_price": "1500.00",
        })
        ok = r.status_code == 201
        product_id = r.json().get("id", "") if ok else ""
        check("crear producto", ok, f"({r.status_code})")

        r = c.post("/api/v1/tenders", json={
            "client_id": client_id,
            "title": f"Licitación smoke día 7 ({ref})",
            "reference": f"SMK-{ref}",
            "deadline_at": (datetime.now(UTC) + timedelta(days=12)).isoformat(),
            "budget_max": "8000.00",
        })
        ok = r.status_code == 201
        tender_id = r.json().get("id", "") if ok else ""
        check("crear licitación (draft)", ok, f"({r.status_code})")
        assert ok, "No se pudo crear licitación; abortando."

        # --- Partidas -----------------------------------------------------
        r = c.post(f"/api/v1/tenders/{tender_id}/items", json={
            "product_id": product_id, "quantity": 2, "unit_price": "1500.00",
        })
        check("añadir partida (2 x 1500.00 = 3000.00)", r.status_code == 201, f"({r.status_code})")

        # --- Propuesta + envío REAL --------------------------------------
        r = c.post(f"/api/v1/tenders/{tender_id}/proposal", files={
            "file": ("propuesta-smoke.pdf", b"%PDF-1.4 smoke day 7 evidence pdf", "application/pdf"),
        })
        check("subir propuesta", r.status_code == 201, f"({r.status_code})")

        r = c.post(f"/api/v1/tenders/{tender_id}/send")
        check("ENVÍO oficial (draft -> active, correo Resend real)",
              r.status_code == 200 and r.json()["status"] == "active", f"({r.status_code})")
        if r.status_code != 200:
            print("  detalle:", r.text[:300])
            return 1

        # --- Resolución ---------------------------------------------------
        r = c.post(f"/api/v1/tenders/{tender_id}/transitions/finish", json={"reason": "Entrega completada"})
        check("finalizar (active -> finished)", r.status_code == 200 and r.json()["status"] == "finished", f"({r.status_code})")

        # Transición inválida: finish sobre finished
        r = c.post(f"/api/v1/tenders/{tender_id}/transitions/finish", json={})
        check("finish repetido -> 409", r.status_code == 409, f"({r.status_code})")

        # --- Factura (importe distinto del total: 3000 -> 3500, §11.3) ----
        r = c.post(f"/api/v1/tenders/{tender_id}/invoice", json={"invoiced_total": "3500.00", "reason": "Se incluyen fletes"})
        d = r.json() if r.status_code == 200 else {}
        check("facturar (finished -> to_collect, 3500.00)", r.status_code == 200 and d.get("status") == "to_collect", f"({r.status_code})")
        check("invoiced_total == 3500.00 (≠ total 3000.00 ok)", d.get("invoiced_total") == "3500.00", "")
        check("saldo pendiente == 3500.00", d.get("saldo_pendiente") == "3500.00", "")

        r = c.post(f"/api/v1/tenders/{tender_id}/invoice", json={"invoiced_total": "1.00"})
        check("factura doble -> 409", r.status_code == 409, f"({r.status_code})")

        # --- Pagos --------------------------------------------------------
        r = c.post(f"/api/v1/tenders/{tender_id}/payments", json={"amount": "2000.00", "reference": "TRF-SMK-1", "notes": "abono 1"})
        d = r.json() if r.status_code == 201 else {}
        check("pago parcial 2000.00", r.status_code == 201 and d.get("saldo_pendiente") == "1500.00", f"({r.status_code})")

        r = c.post(f"/api/v1/tenders/{tender_id}/payments", json={"amount": "1500.01"})
        check("sobrepago 1500.01 -> 422 OVERPAYMENT",
              r.status_code == 422 and r.json()["detail"]["code"] == "OVERPAYMENT", f"({r.status_code})")

        r = c.post(f"/api/v1/tenders/{tender_id}/payments", json={"amount": "1500.00", "reference": "TRF-SMK-2"})
        d = r.json() if r.status_code == 201 else {}
        check("pago final 1500.00 -> cobrada automática", r.status_code == 201 and d.get("status") == "collected", f"({r.status_code})")

        # --- Detalle final ------------------------------------------------
        r = c.get(f"/api/v1/tenders/{tender_id}")
        d = r.json()
        chain = [h["to_status"] for h in d["history"]]
        check("historial completo", chain == ["draft", "active", "finished", "to_collect", "collected"], str(chain))
        check("saldo final 0.00 y 2 pagos", d["saldo_pendiente"] == "0.00" and len(d["payments"]) == 2, "")
        check("todos los actores user", all(h["source"] == "user" for h in d["history"]), "")

    # --- Evidencia del proveedor (fila de outbox) --------------------------
    try:
        import psycopg2
        conn = psycopg2.connect(settings.database_url)
        with conn.cursor() as cur:
            cur.execute(
                "SELECT email_type, status, provider_message_id FROM email_outbox "
                "WHERE tender_id = %s ORDER BY created_at DESC LIMIT 1",
                (tender_id,),
            )
            row = cur.fetchone()
        conn.close()
        if row:
            print(f"\nEvidencia proveedor: type={row[0]} status={row[1]} id={row[2]}")
            check("outbox sent con id de proveedor", row[1] == "sent" and bool(row[2]), "")
        else:
            check("outbox registrado", False, "sin fila")
    except Exception as exc:  # noqa: BLE001
        check("lectura de outbox", False, str(exc)[:200])

    failed = [n for n, ok, _ in results if not ok]
    print(f"\n{len(results) - len(failed)}/{len(results)} verificaciones ok")
    print(f"Tender de referencia: {tender_id}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())