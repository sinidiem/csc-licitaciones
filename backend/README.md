# Backend — Sistema de Gestión de Licitaciones (CSC)

FastAPI + SQLModel + Alembic + PostgreSQL (stack definido en los requisitos del proyecto,
sección "Decisiones Tecnológicas").

## Estructura

```
backend/
├── alembic.ini            # Configuración de Alembic (URL la inyecta env.py)
├── alembic/
│   ├── env.py             # Conecta settings (.env) + SQLModel.metadata
│   ├── script.py.mako     # Plantilla de migraciones (importa sqlmodel)
│   └── versions/          # Migraciones versionadas
├── app/
│   ├── main.py            # FastAPI app + router /api/v1
│   ├── core/config.py     # Settings vía pydantic-settings (.env)
│   ├── db/                # engine, sesión y hub de metadata
│   ├── models/            # SQLModel: users, clients, products, tenders,
│   │                      #   tender_items, proposal_files, payments,
│   │                      #   tender_status_history, email_outbox
│   ├── api/v1/            # Routers (endpoints en días 2-8 del plan)
│   ├── schemas/           # Pydantic request/response
│   ├── services/          # Reglas de negocio (transiciones, pagos, outbox)
│   └── jobs/              # Vencimiento y recordatorios (cron)
└── tests/                 # Pytest (suite de pruebas automáticas)
```

## Arranque

```bash
cp .env.example .env        # ajustar DATABASE_URL y secretos
docker compose up -d db     # PostgreSQL (repositorio raíz)
./venv/bin/pip install -r requirements.txt
./venv/bin/alembic upgrade head                  # aplicar migraciones
./venv/bin/python -m scripts.seed_admin         # primer admin (idempotente)
./venv/bin/uvicorn app.main:app --reload   # http://localhost:8000/docs
```

## API disponible (prefijo /api/v1)

| Endpoint | Uso |
|---|---|
| `POST /auth/login` | Email/password → JWT en cookie HttpOnly + devuelve usuario |
| `POST /auth/logout` | Borra la cookie de sesión |
| `GET /auth/me` | Usuario autenticado actual |
| `GET /users` | Listado de usuarios (autenticado) |
| `POST /users` | Alta de usuario (solo admin); el admin crea admins o users |
| `GET /clients` | Listado de clientes activos (autenticado; excluye borrados) |
| `POST /clients` | Alta de cliente: `company_email` válido y único (409 si existe) |
| `PATCH /clients/{id}` | Edición parcial (nombre, correo, contactos); 409 si el correo ya lo usa otro cliente; 422 sin campos |
| `DELETE /clients/{id}` | Borrado LÓGICO (`deleted_at`): sale de listas y web; sus licitaciones se conservan; no admite nuevas licitaciones |
| `GET /products` | Listado de productos (autenticado) |
| `POST /products` | Alta de producto con `default_unit_price` (Decimal ≥ 0) |
| `POST /tenders` | Crear licitación en `draft` (cliente, título, deadline, presupuesto) |
| `GET /tenders` | Listado paginado (`status`, `client_id`, `limit`, `offset`) |
| `GET /tenders/{id}` | Detalle: cliente, partidas, totales, historial |
| `POST /tenders/{id}/items` | Añadir partida (solo `draft`; valida presupuesto en transacción) |
| `DELETE /tenders/{id}/items/{item_id}` | Quitar partida (solo `draft`; 409 en otros estados) |
| `POST /tenders/{id}/proposal` | Cargar propuesta (multipart; valida extensión/MIME/tamaño; solo `draft`) |
| `GET /tenders/{id}/proposal/download` | Descarga autorizada de la propuesta actual |
| `POST /tenders/{id}/send` | Envío oficial: correo real con adjunto + `draft → active` + historial |
| `POST /tenders/{id}/transitions/finish` | `active → finished` (ganada y entregada) + historial |
| `POST /tenders/{id}/transitions/lose` | `active → lost` (resolución manual) + historial |
| `POST /tenders/{id}/invoice` | `finished → to_collect`: registra `invoiced_total` (positivo; puede diferir del total de partidas, decisión §11.3) |
| `POST /tenders/{id}/payments` | Abono en `por_cobrar`; saldo = 0 → `collected` automático en la misma transacción |
| `POST /internal/jobs/tenders` | Cron (fuera de `/api/v1`, oculto del OpenAPI): vencimientos → `lost` y recordatorio 48h. Header `X-Cron-Secret` obligatorio (401 si falta/falla) |

Reglas de negocio de partidas: el total
`SUM(quantity × unit_price)` no puede superar `budget_max` (422
`BUDGET_EXCEEDED`, validado con `FOR UPDATE` contra carreras); partidas solo
editables en `draft` (409 `INVALID_STATUS_TRANSITION` en `active` y estados
terminales); producto repetido → 409 `DUPLICATE_ITEM`; la creación registra
`tender_status_history` en la misma transacción. Los errores de negocio
devuelven `{"detail": {"code": ..., "message": ...}}` con códigos estables.

Reglas del envío (día 6): sin propuesta → 409 `PROPOSAL_REQUIRED`; sin
correo de empresa en el cliente → 409 `CLIENT_EMAIL_REQUIRED`; el correo real
se envía con patrón outbox (Resend) FUERA de la transacción y la licitación
pasa a `active` solo cuando el proveedor acepta (502 `EMAIL_PROVIDER_FAILED`
si no); reenvío → 409. La propuesta se guarda en **Supabase Storage**
(bucket privado `proposals`, storage en Supabase) cuando hay
`SUPABASE_URL` + `SUPABASE_SERVICE_KEY` en el entorno; sin ellas, el
adaptador local `.storage/` (gitignored) hace de placeholder de desarrollo.
`GET /tenders/{id}/proposal/download` devuelve un `307` a la **URL firmada**
de corta duración (15 min, `SIGNED_URL_EXPIRES_SECONDS`) con adaptador
supabase, y los bytes directos con el adaptador local. Las keys nuevas de
Supabase (`sb_secret_…`) se envían como `apikey` + `Authorization: Bearer`
(se verifica el bucket privado al arrancar el adaptador).

Toda creación registra auditoría (`created_by` / `created_at`); los importes
viajan como string decimal (`"22.50"`), nunca como `float` (regla del modelo de datos).

Autenticación: JWT (HS256, Argon2id para contraseñas) en cookie HttpOnly,
`Secure` en producción y `SameSite=lax`. Los endpoints protegidos devuelven
401 sin sesión y 403 sin rol suficiente.

## Job programado (cron externo, día 8)

El cron invoca `POST /internal/jobs/tenders` (ruta plana, sin /api/v1,
oculta del OpenAPI) con el header `X-Cron-Secret` (valor de `CRON_SECRET`,
comparación segura con `hmac.compare_digest`). Ejecución idempotente por
licitación (`SELECT ... FOR UPDATE` + outbox `pending` dentro del lock):

- **Vencimiento:** `active` con `deadline_at <= now()` → `lost`, historial
  con `source=system` y actor NULL, en la misma transacción.
- **Recordatorio:** `active` con `now < deadline_at <= now+48h` y
  `reminder_sent_at IS NULL` → un solo correo real (outbox
  `tender_reminder`, sin adjunto); `reminder_sent_at` se marca solo cuando
  el proveedor acepta. Si el correo falla, se reintenta en la próxima
  corrida sin duplicar acciones completadas.

Ejemplo de crontab (cada 30 minutos; cambiar el secreto y la URL por los
del despliegue):

```cron
*/30 * * * * curl -s -o /dev/null -X POST -H "X-Cron-Secret: CAMBIA-ESTE-SECRETO" http://127.0.0.1:8000/internal/jobs/tenders
```

El endpoint está diseñado para que el cron pueda vivir FUERA del servidor de
la app: alternativas igualmente válidas — **GitHub
Actions** `schedule:` (ejemplo en `docs/REGISTRO_DESARROLLO.md`) o **cron-job.org**
(job HTTP con cabecera `X-Cron-Secret` personalizada), cada 30-60 minutos.

El secreto se rota desde el entorno (`.env`/secretos del despliegue); nunca
se loguea ni se versiona.

## Migraciones (Alembic)

```bash
./venv/bin/alembic revision --autogenerate -m "descripcion"  # nueva migración
./venv/bin/alembic upgrade head                              # aplicar
./venv/bin/alembic downgrade base                            # revertir todo
./venv/bin/alembic current                                   # estado actual
```

La URL de la base la inyecta `alembic/env.py` desde `DATABASE_URL` del `.env`
(nunca se fija en `alembic.ini`). El metadata viene de `app.db.base` (todos los
modelos registrados en `SQLModel.metadata`).

## Estado actual y pendientes

Hecho y verificado con ejecución real (uvicorn + curl contra PostgreSQL y
Resend; pytest contra `licitaciones_test`): autenticación y roles, seed
admin, clientes/productos, borradores y partidas con presupuesto en
transacción (`FOR UPDATE`, 422 `BUDGET_EXCEEDED`), propuesta en storage local
validada (extensión/MIME/tamaño), envío oficial `draft → active` con correo
real de Resend (outbox, adjunto, historial; 409 `PROPOSAL_REQUIRED` sin
propuesta, 502 si el proveedor rechaza), y **día 7 completo**: `finish`/`lose`
(409 fuera de `active`), `invoice` (`finished → to_collect`, importe positivo
y ≥ pagos registrados, 422 `INVOICE_AMOUNT_INVALID`/`INVOICE_BELOW_PAYMENTS`,
409 factura doble), pagos parciales con `FOR UPDATE` (409 fuera de
`por_cobrar`, 422 `OVERPAYMENT` si supera el saldo, 422 importe ≤ 0) y
transición automática a `collected` al saldar, siempre con historial en la
misma transacción.

**Día 8 (cron):** `POST /internal/jobs/tenders` protegido por
`X-Cron-Secret` (401 sin/incorrecto), vencimientos automáticos
(`active` vencida → `lost`, source=system, actor NULL) y recordatorio único
48h (`reminder_sent_at` solo tras aceptación del proveedor; reintento si
falla), idempotente bajo corridas concurrentes. Verificado con pytest (8
casos, incluida concurrencia) y smoke real con Resend (`scripts/smoke_dia8.py`,
16/16; recordatorio `delivered` con id de proveedor en LOG.md).

Pruebas: `tests/` con pytest + TestClient contra una BD PostgreSQL real
aislada (`licitaciones_test`, migraciones vía Alembic, limpieza entre tests,
email simulado). **77/77 casos en verde** (días 7-14: reglas de negocio,
jobs, storage mockeado, soft delete de clientes, seguridad/acceso). El smoke
end-to-end con email real está en `scripts/smoke_dia7.py` y
`scripts/smoke_dia8.py` (evidencia de proveedor `delivered` en
`docs/REGISTRO_DESARROLLO.md`);
verificación en vivo del job con contadores `reminders_sent/duplicated`
(2026-10-08).

Pendiente: DESPLIEGUE (decisión RESUELTA: Render, un
solo origen, + Supabase + cron externo; runbook en `../docs/DEPLOY.md`),
cron real desplegado, recorrido integral en el entorno desplegado y
evidencias finales (día 10). El frontend (Next.js) está en `../frontend` y
se conecta a esta API vía rewrite de `/api/*` (ver `../frontend/README.md`).
Detalle, reglas y roadmap en `../README.md` (raíz).

## Convenciones de modelo de datos

- PK: `uuid.UUID` (`UuidPkMixin`) → `UUID` en PostgreSQL.
- Fechas: `AwareDatetime` → `UTCDateTime` (`TIMESTAMP WITH TIME ZONE`).
- Importes: `Decimal` con `Numeric(14,2)` — nunca `float`.
- Auditoría: `AuditMixin` (`created_at/by`, `updated_at/by`).
- Restricciones e índices en BD además de validación en app.