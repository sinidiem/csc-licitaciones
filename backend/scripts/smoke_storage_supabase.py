"""Smoke test del adaptador Supabase Storage contra un uvicorn en ejecución.

Evidencia real (día 9, decisión §11.2): sube una propuesta (bucket privado),
la descarga vía URL firmada (endpoint /download/signed → 307) y verifica que
el objeto firmado devuelve exactamente los bytes originales; además dispara
el envío oficial (draft → active) cuyo adjunto se descarga de Supabase.

No imprime la key ni el token firmado (solo la parte pública de la URL).

Uso: ./venv/bin/python -m scripts.smoke_storage_supabase [base_url]
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

    if not (settings.supabase_url and settings.supabase_service_key):
        print("SUPABASE_URL/SERVICE_KEY no configuradas; no hay nada que verificar.")
        return 1

    with httpx.Client(base_url=BASE_URL, timeout=40) as c:
        r = c.post("/api/v1/auth/login", json={
            "email": settings.admin_email, "password": settings.admin_password,
        })
        check("login admin", r.status_code == 200, f"({r.status_code})")

        delivery_email = settings.resend_test_to or "no-enviar@example.com"
        clients = c.get("/api/v1/clients", params={"limit": 100}).json()
        hit = next((x for x in clients if x.get("company_email") == delivery_email), None)
        client_id = hit["id"] if hit else c.post(
            "/api/v1/clients", json={"name": "Smoke Supabase", "company_email": delivery_email}
        ).json()["id"]
        check("cliente del sandbox listo", bool(client_id), "")

        ref = datetime.now(UTC).strftime("%H%M%S")
        r = c.post("/api/v1/products", json={"name": f"Servicio {ref}", "default_unit_price": "800.00"})
        product_id = r.json()["id"]
        r = c.post("/api/v1/tenders", json={
            "client_id": client_id,
            "title": f"Supabase storage {ref}",
            "reference": f"SBX-{ref}",
            "deadline_at": (datetime.now(UTC) + timedelta(days=15)).isoformat(),
            "budget_max": "10000.00",
        })
        tender_id = r.json()["id"]
        r = c.post(f"/api/v1/tenders/{tender_id}/items", json={
            "product_id": product_id, "quantity": 1, "unit_price": "800.00",
        })
        check("partida añadida", r.status_code == 201, f"({r.status_code})")

        # --- Upload a Supabase (bucket privado) ---
        original = b"%PDF-1.4 Supabase signed-url evidence 42" + bytes(range(256))
        r = c.post(f"/api/v1/tenders/{tender_id}/proposal", files={
            "file": ("propuesta-supabase.pdf", original, "application/pdf"),
        })
        d = r.json() if r.status_code == 201 else {}
        check("subir propuesta -> Supabase", r.status_code == 201, f"({r.status_code})")

        import psycopg2
        from sqlmodel import Session, select
        from app.models.proposal_file import ProposalFile
        conn = psycopg2.connect(settings.database_url)
        with conn.cursor() as cur:
            cur.execute(
                "SELECT storage_provider, bucket, object_key FROM proposal_files "
                "WHERE tender_id = %s ORDER BY uploaded_at DESC LIMIT 1", (tender_id,),
            )
            row = cur.fetchone()
            assert row is not None, "no hay fila en proposal_files"
            provider, bucket, object_key = row
        conn.close()
        check("provider == supabase en BD", provider == "supabase", f"provider={provider} bucket={bucket}")

        # --- Descarga por URL firmada (307 + bytes idénticos) ---
        with httpx.Client(base_url=BASE_URL, timeout=40) as c2:
            login = c2.post("/api/v1/auth/login", json={
                "email": settings.admin_email, "password": settings.admin_password,
            })
            if login.status_code != 200:
                return 1
            r = c2.get(f"/api/v1/tenders/{tender_id}/proposal/download/signed")
            check("endpoint firmado -> 307", r.status_code == 307, f"({r.status_code})")
            signed = r.headers.get("location", "")
            public_part = signed.split("?")[0]
            check("Location apunta a Supabase", signed.startswith(settings.supabase_url), public_part)
            r = httpx.get(signed, timeout=40)  # GET directo al objeto firmado
            check("objeto firmado accesible (200)", r.status_code == 200, f"({r.status_code})")
            check("bytes idénticos al original", r.content == original, f"{len(r.content)} bytes")

        # --- Envío oficial: el adjunto también viaja desde Supabase ---
        r = c.post(f"/api/v1/tenders/{tender_id}/send")
        check("envío oficial (adjunto desde Supabase)", r.status_code == 200, f"({r.status_code})")
        if r.status_code == 200:
            detail = r.json()
            check("status active + submitted_at", detail["status"] == "active" and detail["submitted_at"], "")

    failed = [n for n, ok, _ in results if not ok]
    print(f"\n{len(results) - len(failed)}/{len(results)} verificaciones ok")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())