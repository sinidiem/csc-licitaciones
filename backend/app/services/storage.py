"""Adaptador de storage para documentos de propuesta ( §11.2).

Interfaz única para la lógica de negocio: upload/get_bytes (+ URL firmada
para descarga autorizada). En desarrollo sin credenciales es el adaptador
local (disco gitignored); con `SUPABASE_URL` + `SUPABASE_SERVICE_KEY` el
adaptador supabase usa Supabase Storage (bucket PRIVADO, nombre de objeto
aleatorio y URL firmada de corta duración).

Nota de implementación: la API REST de Supabase Storage se usa con httpx (no
el SDK `supabase-py`): las keys nuevas (formato `sb_secret_...`, 2025) son
rechazadas por el SDK antiguo en `create_client()` ("Invalid API key") y por
el gateway si solo se envía `Authorization`; con los headers `apikey` +
`Authorization: Bearer <key>` todo funciona. Los endpoints usados:
/storage/v1/bucket (list/create), /storage/v1/object (upload/download/delete)
y /storage/v1/object/sign (URL firmada).

Seguridad ( §7):
- Validación de extensión y tamaño ANTES de persistir (aquí solo se guarda;
  la validación de MIME la hace el llamador con el contenido real).
- Nombres de objeto aleatorios (uuid hex + extensión saneada).
- No se loguea contenido de propuestas ni la key.
"""

import dataclasses
import hashlib
import re
import uuid
from functools import lru_cache
from pathlib import Path

import httpx
from fastapi import UploadFile

from app.core.config import settings
from app.core.errors import business_error


@dataclasses.dataclass(frozen=True)
class StorageRef:
    """Referencia persistible a un objeto: proveedor/bucket/object_key."""

    provider: str
    bucket: str
    object_key: str


class LocalStorageAdapter:
    """Adaptador de desarrollo: objetos en disco bajo settings.storage_local_dir."""

    provider = "local"

    def __init__(self, base_dir: Path) -> None:
        self.base_dir = base_dir

    def _path(self, bucket: str, object_key: str) -> Path:
        # object_key es uuid hex (+ext), generado por nosotros: sin traversal.
        p = self.base_dir / bucket / object_key
        p.parent.mkdir(parents=True, exist_ok=True)
        return p

    def upload(
        self, *, bucket: str, object_key: str, content: bytes, content_type: str | None = None
    ) -> None:
        self._path(bucket, object_key).write_bytes(content)

    def get_bytes(self, *, bucket: str, object_key: str) -> bytes:
        path = self._path(bucket, object_key)
        if not path.is_file():
            raise business_error(404, "STORAGE_OBJECT_NOT_FOUND", "Objeto no encontrado en storage")
        return path.read_bytes()

    def create_signed_url(self, *, bucket: str, object_key: str, expires_in: int = 900) -> str:
        raise business_error(
            409, "SIGNED_URL_UNAVAILABLE",
            "El adaptador local no genera URLs firmadas; use el endpoint de bytes",
        )


class SupabaseStorageAdapter:
    """Supabase Storage: bucket PRIVADO + URL firmada de corta duración.

    La key (`sb_secret_...` o `eyJ...`) se envía siempre como `apikey` +
    `Authorization: Bearer`. El bucket se crea privado si no existe.
    """

    provider = "supabase"

    def __init__(
        self, *, base_url: str, service_key: str, http: httpx.Client | None = None
    ) -> None:
        self.base_url = base_url.rstrip("/")
        # `http` inyectable para tests (httpx.MockTransport); en producción
        # se construye el cliente real con la key del entorno.
        self._http = http or httpx.Client(
            base_url=self.base_url,
            headers={"Authorization": f"Bearer {service_key}", "apikey": service_key},
            timeout=30,
        )
        self._ensure_bucket(settings.storage_bucket)

    def _ensure_bucket(self, bucket: str) -> None:
        r = self._http.get("/storage/v1/bucket")
        if r.status_code != 200:
            raise business_error(502, "STORAGE_UNAVAILABLE", "No se pudo listar el bucket de storage")
        names = {b.get("name") for b in r.json() if isinstance(b, dict)}
        if bucket not in names:
            r = self._http.post("/storage/v1/bucket", json={"name": bucket, "public": False})
            if r.status_code not in (200, 201):
                raise business_error(
                    502, "STORAGE_BUCKET_FAILED",
                    f"No se pudo crear el bucket privado '{bucket}' en Supabase",
                )

    def upload(
        self, *, bucket: str, object_key: str, content: bytes, content_type: str | None = None
    ) -> None:
        headers = {"x-upsert": "true"}
        if content_type:
            headers["content-type"] = content_type  # el objeto queda con el MIME real
        r = self._http.post(
            f"/storage/v1/object/{bucket}/{object_key}", content=content, headers=headers
        )
        if r.status_code != 200:
            raise business_error(
                502, "STORAGE_UPLOAD_FAILED",
                f"Supabase rechazó el objeto {object_key} ({r.status_code})",
            )

    def get_bytes(self, *, bucket: str, object_key: str) -> bytes:
        r = self._http.get(f"/storage/v1/object/{bucket}/{object_key}")
        if r.status_code == 404:
            raise business_error(404, "STORAGE_OBJECT_NOT_FOUND", "Objeto no encontrado en storage")
        if r.status_code != 200:
            raise business_error(
                502, "STORAGE_DOWNLOAD_FAILED",
                f"Supabase no devolvió el objeto ({r.status_code})",
            )
        return r.content

    def create_signed_url(self, *, bucket: str, object_key: str, expires_in: int = 900) -> str:
        """URL firmada de corta duración para descarga autorizada ( §7)."""
        r = self._http.post(
            f"/storage/v1/object/sign/{bucket}/{object_key}", json={"expiresIn": expires_in}
        )
        if r.status_code != 200:
            raise business_error(
                502, "STORAGE_SIGN_FAILED",
                f"Supabase no firmó el objeto {object_key} ({r.status_code})",
            )
        signed_path = r.json().get("signedURL")
        if not signed_path:
            raise business_error(502, "STORAGE_SIGN_FAILED", "Respuesta de firma sin URL")
        # La API devuelve una ruta relativa al API de storage (verificado
        # empíricamente): la URL completa es base + /storage/v1 + ruta.
        return f"{self.base_url}/storage/v1{signed_path}"


@lru_cache
def get_storage() -> LocalStorageAdapter | SupabaseStorageAdapter:
    """Adaptador activo: Supabase si hay credenciales, si no, local (dev/tests)."""
    if settings.supabase_url and settings.supabase_service_key:
        return SupabaseStorageAdapter(
            base_url=settings.supabase_url,
            service_key=settings.supabase_service_key,
        )
    return LocalStorageAdapter(Path(settings.storage_local_dir).resolve())


_EXT_RE = re.compile(r"\.([a-z0-9]{1,10})$", re.IGNORECASE)


def _sane_extension(filename: str) -> str:
    m = _EXT_RE.search(filename)
    if not m:
        raise business_error(422, "INVALID_EXTENSION", "El archivo no tiene extensión")
    return m.group(1).lower()


def validate_upload(filename: str, content: bytes) -> str:
    """Valida extensión y tamaño; devuelve la extensión saneada.

    El MIME real se comprueba en el endpoint contra `content_type` declarado
    por el cliente; el límite de tamaño viene de settings.
    """
    ext = _sane_extension(filename)
    allowed = {e.strip().lower() for e in settings.allowed_extensions.split(",") if e.strip()}
    if ext not in allowed:
        raise business_error(
            422, "INVALID_EXTENSION",
            f"Extensión '.{ext}' no permitida. Permitidas: {', '.join(sorted(allowed))}",
        )
    max_bytes = settings.max_proposal_size_mb * 1024 * 1024
    if len(content) > max_bytes:
        raise business_error(
            422, "FILE_TOO_LARGE",
            f"El archivo supera el máximo de {settings.max_proposal_size_mb} MB",
        )
    return ext


def random_object_key(ext: str) -> str:
    """Nombre de objeto aleatorio (uuid hex) + extensión saneada."""
    return f"{uuid.uuid4().hex}.{ext}"


def safe_original_name(filename: str) -> str:
    """Nombre original saneado para guardar como metadato (sin rutas)."""
    name = Path(filename or "propuesta").name.strip()
    if not name or name in (".", ".."):
        return "propuesta"
    # Elimina caracteres problemáticos y limita longitud (columna 255).
    name = re.sub(r"[^A-Za-z0-9._\- ]+", "_", name).strip()
    return name[:255] or "propuesta"


def sha256_checksum(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


async def read_uploaded(upload: UploadFile) -> bytes:
    """Lee el contenido del upload con límite de tamaño (evita DoS por memoria)."""
    max_bytes = settings.max_proposal_size_mb * 1024 * 1024 + 1024
    content = await upload.read(max_bytes + 1)
    if len(content) > max_bytes:
        raise business_error(
            422, "FILE_TOO_LARGE",
            f"El archivo supera el máximo de {settings.max_proposal_size_mb} MB",
        )
    return content