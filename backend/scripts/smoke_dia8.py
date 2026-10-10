"""Smoke test del día 8 contra un uvicorn en ejecución (evidencia real).

Crea dos licitaciones activas (correo real de Resend en el envío):
- una con deadline dentro de 48h  -> el job envía el RECORDATORIO real y
  marca reminder_sent_at;
- una con deadline YA vencido      -> el job la transiciona a `lost` con
  actor system y registra historial.

Luego ejecuta POST /internal/jobs/tenders con el secreto y verifica ambos
efectos + la fila de outbox del recordatorio con ID de proveedor.

Uso: ./venv/bin/python -m scripts.smoke_dia8 [base_url]
"""

import sys
from datetime import UTC, datetime, timedelta

import httpx

from app.core.config import settings

BASE_URL = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8000"
PASS, FAIL = "ok  ", "FALLO"


def main() -> int:
    results: list[tuple[str, bool, str]] = []

    def check(name: str, ok: bool, extra: str = "") -> None:
        results.append((name, ok, extra))
        print(f"[{PASS if ok else FAIL}] {name} {extra}")

    with httpx.Client(base_url=BASE_URL, timeout=40) as c:
        r = c.post("/api/v1/auth/login", json={
            "email": settings.admin_email, "password": settings.admin_password,
        })
        check("login admin", r.status_code == 200, f"({r.status_code})")

        # El endpoint requiere secreto
        r = c.post("/internal/jobs/tenders")
        check("job sin secreto -> 401", r.status_code == 401, f"({r.status_code})")
        r = c.post("/internal/jobs/tenders", headers={"X-Cron-Secret": "mal-secreto"})
        check("job con secreto inválido -> 401", r.status_code == 401, f"({r.status_code})")

        # Cliente con email de entrega del sandbox (único, se reutiliza)
        delivery_email = settings.resend_test_to or "no-enviar@example.com"
        clients = c.get("/api/v1/clients", params={"limit": 100}).json()
        hit = next((x for x in clients if x.get("company_email") == delivery_email), None)
        if hit:
            client_id = hit["id"]
        else:
            r = c.post("/api/v1/clients", json={
                "name": "Consultoria Smoke Jobs", "company_email": delivery_email,
            })
            client_id = r.json()["id"]
        check("cliente del sandbox listo", bool(client_id), "")

        ref = datetime.now(UTC).strftime("%H%M%S")

        def _active_tender(reference: str, delta: timedelta) -> str:
            r = c.post("/api/v1/products", json={
                "name": f"Servicio {reference}", "default_unit_price": "100.00",
            })
            product_id = r.json()["id"]
            r = c.post("/api/v1/tenders", json={
                "client_id": client_id,
                "title": f"Licitación jobs {reference}",
                "reference": reference,
                "deadline_at": (datetime.now(UTC) + delta).isoformat(),
                "budget_max": "5000.00",
            })
            tender_id = r.json()["id"]
            r = c.post(f"/api/v1/tenders/{tender_id}/items", json={
                "product_id": product_id, "quantity": 2, "unit_price": "100.00",
            })
            assert r.status_code == 201, r.text
            r = c.post(f"/api/v1/tenders/{tender_id}/proposal", files={
                "file": ("propuesta-jobs.pdf", b"%PDF-1.4 smoke dia 8", "application/pdf"),
            })
            assert r.status_code == 201, r.text
            r = c.post(f"/api/v1/tenders/{tender_id}/send")
            assert r.status_code == 200, r.text
            return tender_id

        # A: vence en 12h -> recordatorio; B: vencida hace 2h -> lost
        tender_reminder = _active_tender(f"SMK-JOB-R-{ref}", timedelta(hours=12))
        tender_expired = _active_tender(f"SMK-JOB-E-{ref}", timedelta(hours=-2))
        check("2 licitaciones activas creadas (envío real)", bool(tender_reminder and tender_expired), "")

        # Ejecutar el job como lo haría el cron del VPS
        r = c.post("/internal/jobs/tenders", headers={"X-Cron-Secret": settings.cron_secret})
        ok = r.status_code == 200
        data = r.json() if ok else {}
        check("job ejecutado (200)", ok, f"({r.status_code})")
        if ok:
            check("vencida  -> lost (expired=1)", data.get("expired") == 1, str(data.get("expired")))
            check("recordatorio 48h enviado (reminders_sent=1)", data.get("reminders_sent") == 1, str(data.get("reminders_sent")))
            check("sin duplicados", data.get("reminders_duplicated") == 0, "")

        d = c.get(f"/api/v1/tenders/{tender_reminder}").json()
        check("recordatorio: sigue active", d["status"] == "active", "")
        check("recordatorio: reminder_sent_at marcado", d["reminder_sent_at"] is not None, str(d["reminder_sent_at"]))
        check("recordatorio: NO transicionó", d["status"] == "active", "")

        d = c.get(f"/api/v1/tenders/{tender_expired}").json()
        check("vencida: status lost", d["status"] == "lost", "")
        last = d["history"][-1]
        check("vencida: historial source=system, actor NULL",
              last["source"] == "system" and last["actor_user_id"] is None,
              f"{last['from_status']}->{last['to_status']}")

        # Segunda corrida: idempotente
        r = c.post("/internal/jobs/tenders", headers={"X-Cron-Secret": settings.cron_secret})
        data2 = r.json()
        check("segunda corrida: cero efectos",
              data2["expired"] == 0 and data2["reminders_sent"] == 0 and data2["reminders_duplicated"] == 0,
              str(data2))

    # --- Evidencia del proveedor (outbox + estado en Resend) -------------
    try:
        import psycopg2
        conn = psycopg2.connect(settings.database_url)
        with conn.cursor() as cur:
            cur.execute(
                "SELECT email_type, status, provider_message_id FROM email_outbox "
                "WHERE tender_id = %s AND email_type = 'tender_reminder' "
                "ORDER BY created_at DESC LIMIT 1",
                (tender_reminder,),
            )
            row = cur.fetchone()
        conn.close()
        if row:
            print(f"\nEvidencia proveedor (recordatorio): type={row[0]} status={row[1]} id={row[2]}")
            check("outbox recordatorio sent con id", row[1] == "sent" and bool(row[2]), "")
        else:
            check("outbox recordatorio", False, "sin fila")
    except Exception as exc:  # noqa: BLE001
        check("lectura de outbox", False, str(exc)[:200])

    failed = [n for n, ok, _ in results if not ok]
    print(f"\n{len(results) - len(failed)}/{len(results)} verificaciones ok")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())