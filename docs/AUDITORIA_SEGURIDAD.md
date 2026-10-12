# Auditoría de seguridad - Sistema de Gestión de Licitaciones (CSC)

Revisión de las capas de seguridad del proyecto, desde la autenticación
hasta el despliegue. Cada sección describe lo implementado, lo que falta y
el riesgo residual.

## 1. Autenticación y sesión

| Aspecto | Estado | Detalle |
|---|---|---|
| Hash de contraseñas | Argon2id | `argon2-cffi` con `PasswordHasher` por defecto (parámetros OWASP). Salt aleatorio embebido en el digest. |
| Sesión | JWT HS256 en cookie HttpOnly | `create_access_token` con `sub` (UUID), `role`, `iat`, `exp`. El token nunca llega a JavaScript (`httponly=True`). |
| Cookie en producción | `Secure=True`, `SameSite=lax` | Configurado vía `cookie_secure` y `cookie_samesite` en Settings; en prod (`ENVIRONMENT=production`) el deploy de Render fuerza HTTPS. |
| Cierre de sesión | `delete_cookie` | `POST /auth/logout` elimina la cookie con `path=/`. Sin invalidación de token en servidor (el token sigue siendo válido hasta que expira; riesgo bajo para una prueba técnica). |
| Bloqueo de cuenta | No implementado | Sin bloqueo tras N intentos fallidos por usuario; el rate limit por IP mitiga parcialmente la fuerza bruta (ver §8). |

## 2. Autorización y control de acceso

| Aspecto | Estado | Detalle |
|---|---|---|
| Roles | `admin` y `user` | `require_admin` eleva 403 si `user.role != "admin"`. Aplicado en `GET /users` (listado) y `POST /users` (creación). |
| Endpoints protegidos | `CurrentUser` dependency | Todos los endpoints de negocio requieren sesión válida (`get_current_user` -> cookie -> JWT -> BD). |
| Endpoint interno | `X-Cron-Secret` + `hmac.compare_digest` | `POST /internal/jobs/tenders` usa comparación en tiempo constante. Sin secreto -> 401; el secreto nunca se loguea. `include_in_schema=False` lo oculta del OpenAPI incluso en dev. |
| Soft delete de clientes | `deleted_at` + filtro en queries | Las licitaciones existentes se conservan; el cliente borrado no acepta nuevas ni aparece en listas. La unicidad de correo se mantiene en TODAS las filas (incluidas las borradas). |
| UI oculta menú admin | `Nav.tsx` + verificación backend | El menú solo muestra "Usuarios" si `/api/users` (admin requerido) responde 200; si no, se oculta. El backend pone el 403. |

## 3. Validación de entrada y prevención de inyección

| Aspecto | Estado | Detalle |
|---|---|---|
| ORM parametrizado | SQLModel (SQLAlchemy) | Todas las consultas usan el ORM o `select` con parámetros; no hay SQL crudo interpolado. |
| Validación de esquemas | Pydantic v2 | `BaseModel` con tipos estrictos en todos los endpoints de entrada (LoginRequest, UserCreate, TenderCreate, PaymentCreate...). |
| Importes | `Decimal` con `Numeric(14,2)` | Nunca `float` para dinero; evita errores de redondeo y desbordamiento. |
| IDs | `uuid.UUID` | Validación automática por Pydantic en parámetros de ruta. |
| Archivos (propuesta) | `validate_upload` | Extensión en lista blanca (pdf, doc, docx, xls, xlsx, odt, txt), tamaño máximo configurable (10 MB), MIME inspeccionado en el llamador; nombre de objeto aleatorio (`uuid4` hex + extensión saneada). |

## 4. Gestión de secretos

| Aspecto | Estado | Detalle |
|---|---|---|
| `.env` local | Gitignored | `.gitignore` excluye `.env` y `*.env` excepto `.env.example`. |
| `.env.example` | Sin valores reales | Documenta todas las variables necesarias, con defaults de desarrollo explícitamente débiles (`dev-only-...`). |
| Despliegue (Render) | Variables de entorno | `SECRET_KEY`, `ADMIN_PASSWORD`, `RESEND_API_KEY`, `CRON_SECRET`, `SUPABASE_URL`, `SUPABASE_SERVICE_KEY`, `DATABASE_URL` inyectados como env vars del servicio; nunca en la imagen. |
| `.dockerignore` | Excluye `.env*` y `.git` | Refuerza que los secretos no lleguen a la imagen. |
| Logs | Sin secretos | `email.py`, `internal.py` y `storage.py` tienen directrices explícitas de no loguear keys, tokens ni contenido de propuestas. |
| Defaults de desarrollo | Débiles por diseño | `SECRET_KEY`, `ADMIN_PASSWORD` y `CRON_SECRET` tienen valores `dev-only-*` en `config.py`; en producción DEBEN ser sobrescritos por variables de entorno. El entrypoint de despliegue no verifica que se hayan cambiado (ver §10 Hallazgos). |

## 5. Red y despliegue

| Aspecto | Estado | Detalle |
|---|---|---|
| HTTPS | Render impone TLS | El free tier de Render termina TLS en el borde; el tráfico interno es HTTP (puerto 3000). La cookie viaja con `Secure=True` (el navegador solo la envía por HTTPS). |
| Exposición de puertos | Solo 3000 | El `EXPOSE 3000` del Dockerfile y el `PORT=3000` limitan la superficie. uvicorn en :8000 solo es accesible desde dentro del contenedor (el rewrite de Next). |
| Mismo origen | Backend + frontend en un solo contenedor | Sin CORS abierto: el navegador solo habla con el dominio de Render; Next reescribe `/api/*` y `/internal/*` al backend local. |
| Swagger/OpenAPI | Oculto en producción | `docs_url=None` y `openapi_url=None` cuando `ENVIRONMENT=production`. |
| Healthcheck | `HEALTHCHECK` en Dockerfile | Verifica conectividad a los puertos 3000 (`/login`) y 8000 (`/auth/me`). Ver §10 Hallazgos por posible falso negativo en el chequeo del backend. |

## 6. Storage (Supabase)

| Aspecto | Estado | Detalle |
|---|---|---|
| Bucket | Privado (`proposals`) | No es público; solo accesible con la `service_key` desde el backend. |
| URL de descarga | Firmada, 15 min | `GET /tenders/{id}/proposal/download/signed` -> 307 al objeto con token efímero. Sin la URL firmada, el objeto es inaccesible. |
| Nombres de objeto | Aleatorios | `random_object_key` genera `uuid4.hex + ext`; no revelan el nombre original del archivo. |
| Adaptador local | Solo desarrollo | En producción, el backend exige credenciales de Supabase (`storage.provider != "supabase"` -> 409 en descarga firmada). |
| RLS de Supabase | DESACTIVADO | Las políticas de Row Level Security en el proyecto de Supabase no están habilitadas. El backend usa la `service_key` (rol `service_role`, bypass de RLS) para todas las operaciones, así que el acceso está mediado exclusivamente por la lógica de la aplicación, no por la base de datos. Riesgo: si la `service_key` se filtrara, un atacante tendría acceso completo a los buckets y a las filas de Postgres sin restricción adicional. Recomendación: activar RLS con políticas que restrinjan el acceso incluso al rol `service_role` (o usar una key con menos privilegios para el backend). |

## 7. Correo electrónico (Resend)

| Aspecto | Estado | Detalle |
|---|---|---|
| API key | En variable de entorno | `RESEND_API_KEY` viaja en el header `Authorization` del SDK de Resend; nunca se loguea. |
| Sandbox | Solo entrega al buzón verificado | `onboarding@resend.dev` como remitente; el destino debe ser el email dueño de la cuenta. |
| Outbox | Idempotente, sin duplicados | `email_outbox` con clave única `(tender_id, email_type)`; `dispatch_outbox` no reenvía filas ya `sent`. |
| Adjuntos | Desde storage (no expuestos) | El adjunto se obtiene con `get_bytes` del adaptador de storage y se pasa como `list[int]` a Resend; no se escribe en disco ni se expone en logs. |

## 8. Rate limiting y fuerza bruta

| Aspecto | Estado | Detalle |
|---|---|---|
| Login | Ventana deslizante por IP, 20 intentos/min | `login_rate_limit` en `app/core/ratelimit.py`; implementación en memoria con `deque` por IP. Tras superar el límite -> 429. |
| Limpieza entre tests | `clear_login_attempts` | `conftest.py` resetea el estado al inicio de la sesión. |
| Límite del enfoque | Mono-worker | En un despliegue multi-worker (varios procesos uvicorn), cada worker tiene su propio diccionario en memoria -> un atacante podría distribuir intentos entre workers. Documentado como límite consciente; a producción se movería a Redis. |
| Sin rate limit en otros endpoints | Solo login | `POST /users` (creación), `POST /tenders/{id}/payments` y otros endpoints de escritura no tienen rate limit. Riesgo bajo en una prueba técnica con pocos usuarios. |

## 9. Modelo de datos y consistencia

| Aspecto | Estado | Detalle |
|---|---|---|
| Bloqueo contra carreras | `SELECT ... FOR UPDATE` | Aplicado en presupuesto (partidas), pagos (último pago -> `collected`), vencimiento automático (job del cron). |
| Transiciones atómicas | `tender_status_history` en la misma transacción | Cada cambio de estado registra actor, razón y fuente (`user` o `system`) sin posibilidad de estados huérfanos. |
| Soft delete | `deleted_at` con índice | Las filas no se eliminan físicamente; los listados y la lógica de negocio las excluyen. Restricción `UNIQUE` en `company_email` aplica a TODAS las filas. |

## 10. Hallazgos y recomendaciones

### H1 - Healthcheck del backend siempre falla (Bajo)

El `HEALTHCHECK` del Dockerfile verifica el puerto 8000 con una petición a
`/api/v1/auth/me`, que requiere cookie de sesión. Sin cookie -> 401 ->
`HTTPError` -> `exit 1`. Como resultado, el healthcheck del backend nunca
reporta `healthy`. El chequeo del frontend (`/login` en :3000) sí funciona.

Recomendación: añadir un endpoint público de salud (ej. `GET /health`
que responda `{"status":"ok"}` sin autenticación) o cambiar la verificación
del backend por una ruta que no exija sesión (ej. `POST /api/auth/login`
con credenciales inválidas esperando un 401, o simplemente verificar que el
puerto acepte conexiones).

### H2 - RLS de Supabase desactivado (Medio)

El Row Level Security del proyecto de Supabase está desactivado. El backend
usa la `service_key` (`service_role`) que omite cualquier política RLS. Si
esta key se filtrara (ej. por un error de configuración, un log accidental,
o una vulnerabilidad en el backend), un atacante tendría acceso completo a
todas las tablas y buckets.

Recomendación: habilitar RLS en las tablas de Postgres y en el bucket de
Storage, y crear políticas que restrinjan las operaciones incluso al rol
autenticado. Si se necesita el bypass para el backend, usar una key con rol
`authenticated` y políticas que permitan las operaciones necesarias, en vez
de `service_role`.

### H3 - Sin verificación de que los defaults de desarrollo se hayan cambiado en producción (Medio)

`SECRET_KEY`, `ADMIN_PASSWORD` y `CRON_SECRET` tienen valores débiles
(`dev-only-*`) en `config.py`. Si se despliega sin sobrescribir las
variables de entorno, la aplicación arranca con secretos conocidos
públicamente.

Recomendación: en el entrypoint de despliegue (`deploy/entrypoint.sh`),
verificar que `SECRET_KEY` no coincida con el default de desarrollo y
abortar el arranque si es el caso. Ídem para `CRON_SECRET` y
`ADMIN_PASSWORD`.

### H4 - Sin invalidación de tokens al cerrar sesión (Bajo)

`POST /auth/logout` solo borra la cookie del navegador; el token JWT sigue
siendo válido hasta que expire (7 días en dev). Si un atacante captura el
token antes del logout, puede usarlo hasta su expiración natural.

Recomendación: para producción, mantener una lista negra de tokens
revocados (en Redis o BD) con TTL igual al `exp` restante, o reducir la
vida del token y usar refresh tokens.

### H5 - Rate limit no distribuido (Bajo)

El limitador de login es un diccionario en memoria del proceso Python. En
un despliegue con múltiples workers, cada uno tiene su propia ventana.

Recomendación: documentado como límite consciente. A producción
multi-worker, mover a Redis (`INCR` + `EXPIRE`).

### H6 - Sin registro de auditoría de accesos (Bajo)

No hay log de inicios de sesión (exitosos o fallidos) más allá del rate
limit en memoria.

Recomendación: para un sistema en producción, registrar intentos de
login en una tabla `login_audit` (éxito, fallo, IP, timestamp) para
detección de anomalías.

---

Conclusión: el proyecto implementa las capas de seguridad esperadas para
una prueba técnica (autenticación, autorización, validación, secretos,
transporte). Los hallazgos son limitaciones conscientes documentadas, salvo
el healthcheck del backend (H1, corregible en minutos) y el RLS de Supabase
(H2, que requiere acción en el panel de Supabase).