"""Edición y borrado lógico de clientes (decisión 2026-10-08, ).

Cubre:
- PATCH /clients/{id}: actualización parcial, unicidad de correo (409),
  404 si no existe o está borrado, 422 si no se envían campos.
- DELETE /clients/{id}: SOFT DELETE — la fila permanece en BD (licitaciones
  e historial intactos) pero desaparece del listado público y no admite
  nuevas licitaciones; borrar dos veces → 404.
- Las licitaciones de un cliente borrado siguen visibles con su nombre.
"""

from datetime import UTC, datetime, timedelta


def _future_deadline(days: int = 10) -> str:
    return (datetime.now(UTC) + timedelta(days=days)).isoformat()


def _create_client(client, name: str = "Cliente soft") -> str:
    r = client.post(
        "/api/v1/clients",
        json={"name": name, "company_email": f"{name.lower().replace(' ', '')}@example.com"},
    )
    assert r.status_code == 201, r.text
    return r.json()["id"]


# ---------------------------------------------------------------------------
# PATCH
# ---------------------------------------------------------------------------


def test_patch_renombra_y_actualiza_contactos(client, admin):
    cid = _create_client(client, "Empresa Uno")
    r = client.patch(
        f"/api/v1/clients/{cid}",
        json={"name": "Empresa Uno Editada", "contact_name": "Ana Torres"},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["name"] == "Empresa Uno Editada"
    assert body["contact_name"] == "Ana Torres"
    assert body["company_email"] == "empresauno@example.com"  # intacto

    lista = {c["name"] for c in client.get("/api/v1/clients").json()}
    assert "Empresa Uno Editada" in lista
    assert "Empresa Uno" not in lista


def test_patch_correo_duplicado_409(client, admin):
    a = _create_client(client, "Empresa A")
    b = _create_client(client, "Empresa B")
    ea = client.get("/api/v1/clients").json()
    email_a = next(c["company_email"] for c in ea if c["id"] == a)
    r = client.patch(f"/api/v1/clients/{b}", json={"company_email": email_a})
    assert r.status_code == 409
    assert "ya existe un cliente" in r.json()["detail"].lower()


def test_patch_con_mismo_correo_ok(client, admin):
    cid = _create_client(client, "Empresa Misma")
    email = next(c["company_email"] for c in client.get("/api/v1/clients").json() if c["id"] == cid)
    r = client.patch(f"/api/v1/clients/{cid}", json={"company_email": email})
    assert r.status_code == 200, r.text


def test_patch_sin_campos_422(client, admin):
    cid = _create_client(client, "Empresa Vacia")
    r = client.patch(f"/api/v1/clients/{cid}", json={})
    assert r.status_code == 422


def test_patch_404_inexistente(client, admin):
    r = client.patch(
        "/api/v1/clients/00000000-0000-0000-0000-000000000000",
        json={"name": "X"},
    )
    assert r.status_code == 404


def test_patch_404_cliente_borrado(client, admin):
    cid = _create_client(client, "Empresa Borrada")
    assert client.delete(f"/api/v1/clients/{cid}").status_code == 200
    r = client.patch(f"/api/v1/clients/{cid}", json={"name": "X"})
    assert r.status_code == 404


# ---------------------------------------------------------------------------
# DELETE (soft)
# ---------------------------------------------------------------------------


def test_delete_soft_desaparece_de_listas(client, admin):
    cid = _create_client(client, "Empresa A Borrar")
    r = client.delete(f"/api/v1/clients/{cid}")
    assert r.status_code == 200, r.text

    lista = [c["id"] for c in client.get("/api/v1/clients").json()]
    assert cid not in lista


def test_delete_dos_veces_404(client, admin):
    cid = _create_client(client, "Empresa B Borrar")
    assert client.delete(f"/api/v1/clients/{cid}").status_code == 200
    assert client.delete(f"/api/v1/clients/{cid}").status_code == 404


def test_cliente_borrado_no_acepta_nuevas_licitaciones(client, admin):
    cid = _create_client(client, "Empresa Bloqueo")
    assert client.delete(f"/api/v1/clients/{cid}").status_code == 200

    r = client.post(
        "/api/v1/tenders",
        json={
            "client_id": cid,
            "title": "No deberia crearse",
            "reference": "NOPE-001",
            "deadline_at": _future_deadline(),
            "budget_max": "1000.00",
        },
    )
    assert r.status_code == 404
    assert r.json()["detail"]["code"] == "CLIENT_NOT_FOUND"


def test_licitaciones_de_cliente_borrado_siguen_visibles(client, admin):
    cid = _create_client(client, "Empresa Historica")
    r = client.post(
        "/api/v1/tenders",
        json={
            "client_id": cid,
            "title": "Licitacion historica",
            "reference": "HIST-001",
            "deadline_at": _future_deadline(),
            "budget_max": "5000.00",
        },
    )
    assert r.status_code == 201, r.text
    tid = r.json()["id"]

    assert client.delete(f"/api/v1/clients/{cid}").status_code == 200

    lista = client.get("/api/v1/tenders?limit=100").json()
    assert any(t["id"] == tid for t in lista)
    detalle = client.get(f"/api/v1/tenders/{tid}").json()
    assert detalle["client_name"] == "Empresa Historica"
    assert detalle["company_email"] == "empresahistorica@example.com"