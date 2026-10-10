"""Tests unitarios del adaptador de storage ( §11.2) — sin red real.

- LocalStorageAdapter: upload/get_bytes/errores 404 y URL firmada no
  disponible (409 SIGNED_URL_UNAVAILABLE).
- SupabaseStorageAdapter: contrato REST mockeado con httpx.MockTransport
  (ensure bucket privado, upload, get_bytes, URL firmada + errores 502/404
  con códigos estables).
- Selección del adaptador activo y validación de uploads.
"""

import re
import uuid
from pathlib import Path

import httpx
import pytest
from fastapi import HTTPException

from app.core.config import settings
from app.services import storage as storage_mod
from app.services.storage import (
    LocalStorageAdapter,
    SupabaseStorageAdapter,
    get_storage,
    random_object_key,
    safe_original_name,
    sha256_checksum,
    validate_upload,
)

BASE = "https://proyecto.supabase.co"


def http_mock(handler) -> httpx.Client:
    return httpx.Client(transport=httpx.MockTransport(handler), base_url=BASE)


def supabase(handler) -> SupabaseStorageAdapter:
    return SupabaseStorageAdapter(
        base_url=BASE, service_key="sb_secret_test", http=http_mock(handler)
    )


def err_code(exc: HTTPException) -> str:
    detail = getattr(exc, "detail")
    assert isinstance(detail, dict), detail
    return str(detail["code"])


# ---------- LocalStorageAdapter ----------


def test_local_upload_get_bytes(tmp_path):
    a = LocalStorageAdapter(tmp_path)
    a.upload(bucket="b", object_key="abc.txt", content=b"hola")
    assert (tmp_path / "b" / "abc.txt").read_bytes() == b"hola"
    assert a.get_bytes(bucket="b", object_key="abc.txt") == b"hola"


def test_local_missing_object_404(tmp_path):
    a = LocalStorageAdapter(tmp_path)
    with pytest.raises(HTTPException) as e:
        a.get_bytes(bucket="b", object_key="nope.txt")
    assert e.value.status_code == 404
    assert err_code(e.value) == "STORAGE_OBJECT_NOT_FOUND"


def test_local_signed_url_no_disponible(tmp_path):
    a = LocalStorageAdapter(tmp_path)
    with pytest.raises(HTTPException) as e:
        a.create_signed_url(bucket="b", object_key="x.txt")
    assert e.value.status_code == 409
    assert err_code(e.value) == "SIGNED_URL_UNAVAILABLE"


# ---------- SupabaseStorageAdapter (con MockTransport) ----------


def test_supabase_init_crea_bucket_privado():
    creado = {}

    def handler(req):
        if req.method == "GET" and req.url.path == "/storage/v1/bucket":
            return httpx.Response(200, json=[])
        if req.method == "POST" and req.url.path == "/storage/v1/bucket":
            creado["body"] = req.content
            return httpx.Response(200, json={"name": "proposals"})
        raise AssertionError(f"ruta inesperada: {req.method} {req.url.path}")

    supabase(handler)
    import json

    body = json.loads(creado["body"])
    assert body == {"name": "proposals", "public": False}


def test_supabase_init_reutiliza_bucket_existente():
    posts = []

    def handler(req):
        if req.method == "GET" and req.url.path == "/storage/v1/bucket":
            return httpx.Response(200, json=[{"name": "proposals"}])
        if req.method == "POST":
            posts.append(req.url.path)
            return httpx.Response(200, json={})
        return httpx.Response(404)

    supabase(handler)
    assert posts == []


def test_supabase_init_lista_bucket_falla():
    def handler(req):
        return httpx.Response(500, text="boom")

    with pytest.raises(HTTPException) as e:
        supabase(handler)
    assert e.value.status_code == 502
    assert err_code(e.value) == "STORAGE_UNAVAILABLE"


def test_supabase_init_crear_bucket_falla():
    def handler(req):
        if req.method == "GET" and req.url.path == "/storage/v1/bucket":
            return httpx.Response(200, json=[])
        return httpx.Response(500, text="boom")

    with pytest.raises(HTTPException) as e:
        supabase(handler)
    assert e.value.status_code == 502
    assert err_code(e.value) == "STORAGE_BUCKET_FAILED"


def test_supabase_upload_ok_con_mime():
    vistos = {}

    def handler(req):
        if req.method == "GET" and req.url.path == "/storage/v1/bucket":
            return httpx.Response(200, json=[{"name": "proposals"}])
        if req.method == "POST" and req.url.path.startswith("/storage/v1/object/"):
            vistos["content-type"] = req.headers.get("content-type")
            vistos["x-upsert"] = req.headers.get("x-upsert")
            return httpx.Response(200, json={"Key": "k"})
        return httpx.Response(404)

    a = supabase(handler)
    a.upload(bucket="proposals", object_key="ab.pdf", content=b"%PDF", content_type="application/pdf")
    assert vistos["content-type"] == "application/pdf"
    assert vistos["x-upsert"] == "true"


def test_supabase_upload_falla_502():
    def handler(req):
        if req.method == "GET" and req.url.path == "/storage/v1/bucket":
            return httpx.Response(200, json=[{"name": "proposals"}])
        return httpx.Response(400, json={"error": "nope"})

    a = supabase(handler)
    with pytest.raises(HTTPException) as e:
        a.upload(bucket="proposals", object_key="ab.pdf", content=b"%PDF")
    assert e.value.status_code == 502
    assert err_code(e.value) == "STORAGE_UPLOAD_FAILED"


def test_supabase_get_bytes_ok():
    def handler(req):
        if req.method == "GET" and req.url.path == "/storage/v1/bucket":
            return httpx.Response(200, json=[{"name": "proposals"}])
        if req.method == "GET" and req.url.path.startswith("/storage/v1/object/"):
            return httpx.Response(200, content=b"%PDF-1.4")
        return httpx.Response(404)

    a = supabase(handler)
    assert a.get_bytes(bucket="proposals", object_key="ab.pdf") == b"%PDF-1.4"


def test_supabase_get_bytes_404():
    def handler(req):
        if req.method == "GET" and req.url.path == "/storage/v1/bucket":
            return httpx.Response(200, json=[{"name": "proposals"}])
        return httpx.Response(404)

    a = supabase(handler)
    with pytest.raises(HTTPException) as e:
        a.get_bytes(bucket="proposals", object_key="ab.pdf")
    assert e.value.status_code == 404
    assert err_code(e.value) == "STORAGE_OBJECT_NOT_FOUND"


def test_supabase_get_bytes_falla_502():
    def handler(req):
        if req.method == "GET" and req.url.path == "/storage/v1/bucket":
            return httpx.Response(200, json=[{"name": "proposals"}])
        return httpx.Response(500)

    a = supabase(handler)
    with pytest.raises(HTTPException) as e:
        a.get_bytes(bucket="proposals", object_key="ab.pdf")
    assert e.value.status_code == 502
    assert err_code(e.value) == "STORAGE_DOWNLOAD_FAILED"


def test_supabase_url_firmada_prefijo_storage_v1():
    def handler(req):
        if req.method == "GET" and req.url.path == "/storage/v1/bucket":
            return httpx.Response(200, json=[{"name": "proposals"}])
        if req.method == "POST" and req.url.path == "/storage/v1/object/sign/proposals/ab.pdf":
            return httpx.Response(200, json={"signedURL": "/object/sign/proposals/ab.pdf?token=t"})
        return httpx.Response(404)

    a = supabase(handler)
    url = a.create_signed_url(bucket="proposals", object_key="ab.pdf", expires_in=900)
    assert url == f"{BASE}/storage/v1/object/sign/proposals/ab.pdf?token=t"


def test_supabase_url_firmada_sin_ruta():
    def handler(req):
        if req.method == "GET" and req.url.path == "/storage/v1/bucket":
            return httpx.Response(200, json=[{"name": "proposals"}])
        return httpx.Response(200, json={})

    a = supabase(handler)
    with pytest.raises(HTTPException) as e:
        a.create_signed_url(bucket="proposals", object_key="ab.pdf")
    assert e.value.status_code == 502
    assert err_code(e.value) == "STORAGE_SIGN_FAILED"


def test_supabase_url_firmada_falla_502():
    def handler(req):
        if req.method == "GET" and req.url.path == "/storage/v1/bucket":
            return httpx.Response(200, json=[{"name": "proposals"}])
        return httpx.Response(500)

    a = supabase(handler)
    with pytest.raises(HTTPException) as e:
        a.create_signed_url(bucket="proposals", object_key="ab.pdf")
    assert e.value.status_code == 502
    assert err_code(e.value) == "STORAGE_SIGN_FAILED"


# ---------- Selección del adaptador y helpers ----------


def test_get_storage_local_sin_credenciales(monkeypatch):
    monkeypatch.setattr(settings, "supabase_url", "")
    monkeypatch.setattr(settings, "supabase_service_key", "")
    get_storage.cache_clear()
    try:
        assert isinstance(get_storage(), LocalStorageAdapter)
    finally:
        get_storage.cache_clear()


def test_get_storage_supabase_con_credenciales(monkeypatch):
    recibidos = {}

    class Fake:
        provider = "supabase"

        def __init__(self, **kw):
            recibidos.update(kw)

    monkeypatch.setattr(settings, "supabase_url", "https://x.supabase.co")
    monkeypatch.setattr(settings, "supabase_service_key", "sb_x")
    monkeypatch.setattr(storage_mod, "SupabaseStorageAdapter", Fake)
    get_storage.cache_clear()
    try:
        got = get_storage()
        assert got.provider == "supabase"
        assert recibidos["base_url"] == "https://x.supabase.co"
        assert recibidos["service_key"] == "sb_x"
    finally:
        get_storage.cache_clear()


def test_validate_upload_extension_permitida():
    ext = validate_upload("propuesta.TXT", b"hola")
    assert ext == "txt"


def test_validate_upload_extension_prohibida():
    with pytest.raises(HTTPException) as e:
        validate_upload("virus.exe", b"x")
    assert e.value.status_code == 422
    assert err_code(e.value) == "INVALID_EXTENSION"


def test_validate_upload_sin_extension():
    with pytest.raises(HTTPException) as e:
        validate_upload("propuesta", b"x")
    assert err_code(e.value) == "INVALID_EXTENSION"


def test_validate_upload_demasiado_grande(monkeypatch):
    monkeypatch.setattr(settings, "max_proposal_size_mb", 1)
    with pytest.raises(HTTPException) as e:
        validate_upload("grande.pdf", b"x" * (1024 * 1024 + 1))
    assert e.value.status_code == 422
    assert err_code(e.value) == "FILE_TOO_LARGE"


def test_random_object_key_formato():
    key = random_object_key("pdf")
    assert key.endswith(".pdf")
    prefix = key[: -len(".pdf")]
    assert re.fullmatch(r"[0-9a-f]{32}", prefix)  # uuid4 hex


def test_safe_original_name_sanea():
    assert safe_original_name("../../etc/passwd") == "passwd"  # Path toma el basename
    assert safe_original_name("") == "propuesta"
    assert safe_original_name(".") == "propuesta"
    assert safe_original_name("Bomba & < >.pdf") == "Bomba _ _ _.pdf"


def test_sha256_checksum_determinista():
    a = sha256_checksum(b"contenido")
    assert a == sha256_checksum(b"contenido")
    assert len(a) == 64