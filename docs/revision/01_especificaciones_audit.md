# Auditoría de cumplimiento de especificaciones — CSC

Fecha: 2026-10-08. Fuente de requisitos (autoridad máxima):
`CONTEXT.md` y `AGENTS.md`.

Método y evidencias: lectura sistemática del código (`backend/app`,
`frontend/src`), suite pytest (**62/62 en verde** contra
PostgreSQL real aislado + Alembic), E2E de la UI con Playwright (**15/15**
flujo feliz y **9/9** casos negativos), smokes reales con
proveedores (Resend 20/20 y 16/16; Supabase 11/11).
Nota de método: revisión directa del código y de las especificaciones,
verificando cada requisito contra la implementación y las pruebas.

Veredicto global: **✅ CUMPLE**. Sin incumplimientos (❌); 4 ambigüedades /
formalizaciones (⚠) documentadas al final, todas resueltas el mismo día (2026-10-08).

---

## 1. Convenciones de modelo de datos (AGENTS §2)

| Requisito | Veredicto | Evidencia |
|---|---|---|
| PK uuid.UUID con `UuidPkMixin` | ✅ | `backend/app/models/mixins.py` (UuidPkMixin); usado en todos los modelos |
| Fechas `AwareDatetime` → UTCDateTime (`timestamptz` UTC) | ✅ | `models/mixins.py`; `deadline_at`, `paid_at`, historia — migraciones Alembic |
| Importes `Decimal` con `Numeric(14,2)`, prohibido `float` | ✅ | `models/tender.py` (budget_max, invoiced_total), `tender_item.py`, `payment.py`; schemas validan string decimal |
| Auditoría en entidades mutables (`AuditMixin`) | ✅ | `mixins.py` (created_at/by, updated_at/by); clientes, productos, tenders, partidas, pagos |
| Sin `sa_column=Column(...)` dentro de mixins | ✅ | mixins usan solo anotaciones puras |
| Checks/unique/FKs en la BD además de validación de app | ✅ | `ck_tenders_*`, `ck_products_default_unit_price_non_neg`, `unique(company_email)` en clientes; FK partidas→producto, historial→tender |
| Migraciones Alembic, nunca `create_all` | ✅ | `alembic/versions/*`; arranque y conftest usan `alembic upgrade head` |

## 2. Estados de licitación y matriz de transiciones (AGENTS §3)

| Requisito | Veredicto | Evidencia |
|---|---|---|
| Códigos internos en inglés → etiquetas en español | ✅ | `frontend/src/lib/api.ts` (`STATUS_LABELS`); badges en la UI |
| Solo transiciones válidas; cualquier otra → 409 `INVALID_STATUS_TRANSITION` | ✅ | `services/transitions.py` + `tests/test_dia7_resolucion_factura_pagos.py` (20 transiciones inválidas parametrizadas) |
| `draft→active` exige propuesta adjunta + correo enviado | ✅ | `transitions.py:207` (409 `PROPOSAL_REQUIRED`); envío real vía outbox Resend verificado (smoke 20/20, correo `delivered`) |
| `finished/to_collect/collected/lost` terminales para partidas (no agregar/quitar) | ✅ | `tests/test_dia7_*` (regresión §11.1): 409 al añadir/quitar partidas en estados no-draft |
| Historial `tender_status_history` en la misma transacción | ✅ | `transitions.py`, `payments.py`, `jobs.py` (historial dentro de la tx con `FOR UPDATE`); verificado en detalle de la UI |

## 3. Reglas de negocio (AGENTS §4)

| Regla | Veredicto | Evidencia |
|---|---|---|
| 4.1 `SUM(quantity*unit_price) <= budget_max` con lock | ✅ | `services/tenders.py` (partidas con `FOR UPDATE`); 422 `BUDGET_EXCEEDED`; test de carrera concurrente + E2E negativo (banner "supera el presupuesto") |
| 4.2 Vencida `active` → `lost` automático (job, actor system) | ✅ | `services/jobs.py` + `tests/test_dia8_jobs.py` + smoke 16/16 (vencida −2h → lost con historial `source=system`) |
| 4.3 Enviar solo con propuesta en storage | ✅ | `transitions.py:207`; E2E negativo (envío sin propuesta rechazado) |
| 4.4 Correo real Resend vía outbox idempotente | ✅ | `services/email.py` (`dispatch_outbox`); tests de idempotencia/2 corridas, smoke con `delivered` real |
| 4.5 Recordatorio único ≤48h con `reminder_sent_at` | ✅ | `services/jobs.py`; smoke real `delivered` (id en LOG); no toca vencidas (test) |
| 4.6 Pagos solo en `to_collect`, `amount>0` y `≤ saldo`, sobrepago rechazado, saldo=0 → `collected` | ✅ | `services/payments.py`; 422 `OVERPAYMENT` con rollback, `collected` en la misma txn del último pago; tests + E2E feliz |
| 4.7 `invoiced_total` positivo, sin saldo negativo | ✅ | `services/transitions.py` (invoice) + tests 422 `INVOICE_AMOUNT_INVALID`/`INVOICE_BELOW_PAYMENTS` |

## 4. API y códigos de error (AGENTS §5)

| Requisito | Veredicto | Evidencia |
|---|---|---|
| Prefijo `/api/v1`; Swagger visible en dev, oculto en producción | ✅ | `main.py`/`router.py`; docs condicionados al entorno |
| 401 no autenticado · 403 sin rol · 404 ausente · 409 transición/duplicado · 422 validación | ✅ | Autenticación 401; 403 `Se requiere rol admin` (admin-only); 404 objeto ausente; 409 `INVALID_STATUS_TRANSITION`/duplicado de cliente; 422 validación/presupuesto |
| Solo admin crea usuarios; nunca exponer `password_hash` | ✅ | `endpoints/users.py` (`AdminUser` en create); `UserRead` excluye `password_hash`; E2E negativo 403 al crear como user |
| Endpoints de negocio exigen sesión; rol validado en backend | ✅ | dependencias `CurrentUser`/`AdminUser`; la UI no oculta nada por sí sola (comprobado: el 403 llega del backend) |
| Códigos estables en los errores de negocio | ✅ | `core/errors.py` `business_error(code, message)` |

## 5. Seguridad (AGENTS §6)

| Requisito | Veredicto | Evidencia |
|---|---|---|
| Argon2id para contraseñas | ✅ | `core/security.py` (hash_password Argon2id); seed admin y login con él |
| JWT HS256 en cookie HttpOnly; `Secure` en producción; `SameSite=lax` | ✅ | `endpoints/auth.py` (cookie HttpOnly, SameSite=lax); README documenta Secure en prod |
| `SECRET_KEY` ≥ 32 bytes (RFC 7518) | ✅ | `core/config.py` valida longitud mínima (verificar línea exacta al tocar) |
| Secretos solo en `.env`/despliegue; nunca versionados ni logueados | ✅ | `.env` en `.gitignore` (verificado con `git check-ignore`); sin secretos hardcodeados (scan de la revisión) |
| Storage privado + URL firmada corta con autorización | ✅ | `services/storage.py` (bucket privado, URL firmada 15 min en descarga); smoke 11/11 con Supabase real |
| Validar extensión, tamaño y MIME; nombres de objeto aleatorios | ✅ | `validate_upload`, `random_object_key`, `read_uploaded` (límite de memoria); `safe_original_name` saneado; tests nuevos `test_storage_adapters.py` |
| Cron interno con secreto rotable y comparación segura | ✅ | `endpoints/internal.py` (`hmac.compare_digest`, 401 sin/incorrecto; no se loguea) |
| Defensa CSRF evaluada y documentada | ⚠ | `SameSite=lax` activo y documentado en README; falta la formalización en CONTEXT.md (pendiente identificado) |

## 6. Automatización / jobs (AGENTS §7)

| Requisito | Veredicto | Evidencia |
|---|---|---|
| Vencimiento y recordatorio vía cron → endpoint interno autenticado | ✅ | `POST /internal/jobs/tenders` con `X-Cron-Secret`; ejemplo de crontab en `backend/README.md`; pendiente solo el cron DESPLEGADO (día 9: Render + cron externo) |
| Idempotencia por licitación (lock/update condicional) | ✅ | `SELECT ... FOR UPDATE` + outbox `pending` dentro del lock; test con 2 hilos |
| Reintentos de emails sin repetir acciones completadas | ✅ | `dispatch_outbox` reintenta `pending`; `reminder_sent_at` se marca solo tras aceptación del proveedor |
| El recordatorio no toca vencidas | ✅ | `tests/test_dia8_jobs.py` |

## 7. Frontend (guía: UI funcional en español)

| Requisito | Veredicto | Evidencia |
|---|---|---|
| Login y guard de sesión | ✅ | `/login`; layout protegido redirige a /login sin cookie (E2E negativo) |
| Licitaciones: listado, detalle y acciones por estado (enviar/finalizar/perder/facturar/pagar) | ✅ | E2E 15/15: borrador→activa→finalizada→por cobrar→cobrada con historial |
| Clientes y productos | ✅ | CRUD funcional; duplicado de cliente rechazado (409) en E2E |
| Usuarios solo admin | ✅ | formulario presente pero el backend rechaza con 403 (E2E negativo) |
| Estados mostrados en español | ✅ | `STATUS_LABELS` |

---

## Ambigüedades / acciones pendientes (⚠)

1. **Listado de usuarios visible a cualquier usuario autenticado.** La guía
   solo restringe la creación ("solo admin crea usuarios"); el listado
   (`GET /users`) expone nombre/correo/rol de todo el equipo a cualquier
   cuenta. **RESUELTA (2026-10-08):** `GET /users` pasó a requerir admin
   (403 para rol user) y el menú oculta el enlace al resto.
2. **Productos sin unicidad por nombre.** El modelo indexa el nombre pero
   no lo declara `unique`; la guía no exige unicidad (el único unique
   requerido por la guía es el correo del cliente). Comportamiento por
   diseño, documentado; repetir nombres es válido.
3. **Decisión CSRF** — **RESUELTA (2026-10-08):** formalizada en
   CONTEXT.md §11.9 (`SameSite=lax` + mismo-origen + JSON; sin token
   adicional) y complementada con rate limit por IP en `/auth/login`.
4. **Detalle de validación 422 en la UI** — **RESUELTO (2026-10-08):**
   `api.ts` formatea los `detail` tipo array de pydantic (B1 de la
   revisión de código).