"""Configuración de la aplicación vía variables de entorno (.env).

Regla CONTEXT.md: los secretos (DB, correo, storage, cron) viven en el
ambiente/despliegue, nunca en el repositorio. Aquí solo se definen defaults
de desarrollo y los nombres de variables.
"""

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # --- Aplicación -----------------------------------------------------
    app_name: str = "CSC - Sistema de Gestión de Licitaciones"
    environment: str = "development"  # development | production
    api_v1_prefix: str = "/api/v1"

    # --- Base de datos (PostgreSQL, stack definido en CONTEXT.md) -------
    database_url: str = "postgresql://postgres:password@localhost:5432/licitaciones_db"

    # --- Seguridad / sesión (JWT en cookie HttpOnly) --------------------
    # Mínimo 32 bytes para HS256 (RFC 7518). Dev usa este default; prod via env.
    secret_key: str = "dev-only-secret-key-32-bytes-min-0123456789abcdef"
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 60 * 24 * 7  # 7 días en dev
    cookie_name: str = "access_token"
    # False en local (http); True solo en producción (https).
    cookie_secure: bool = False
    cookie_samesite: str = "lax"
    # Fuerza bruta en /auth/login: N intentos por IP en la ventana (en memoria).
    login_max_attempts: int = 20
    login_window_seconds: int = 60

    # --- Seed del primer admin (día 2 del plan, seed controlado) --------
    admin_email: str = "admin@example.com"
    admin_password: str = "CambiaEstaClave1!"  # solo para dev; en prod via env
    admin_name: str = "Administrador"

    # --- Cron interno: secreto compartido para proteger el endpoint -----
    cron_secret: str = "dev-only-cron-secret"

    # --- Integraciones reales (se llenan en .env del despliegue) --------
    # Email (Resend). Dev usa el dominio sandbox onboarding@resend.dev, que
    # solo permite enviar al email verificado de la cuenta (RESEND_TEST_TO).
    resend_api_key: str = ""
    resend_from: str = "onboarding@resend.dev"
    # Destinatario de pruebas; en sandbox debe ser el email de la cuenta.
    resend_test_to: str = ""
    supabase_url: str = ""
    supabase_service_key: str = ""

    # --- Storage de propuestas (decisión CONTEXT.md §11.2) --------------
    # Dev: adaptador "local" (disco, gitignored, misma interfaz). Cuando
    # existan SUPABASE_URL+SERVICE_KEY se usa el adaptador supabase
    # (bucket privado + URL firmada de corta duración).
    storage_bucket: str = "proposals"
    storage_local_dir: str = ".storage"
    max_proposal_size_mb: int = 10
    # Duración de la URL firmada para descarga de propuestas (segundos).
    signed_url_expires_seconds: int = 900
    # Extensiones admitidas (validación CONTEXT.md §7: tipo/tamaño).
    allowed_extensions: str = "pdf,doc,docx,xls,xlsx,odt,txt"


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()