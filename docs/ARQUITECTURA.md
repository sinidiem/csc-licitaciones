# Arquitectura — CSC (resumen de 10 minutos)

## Qué es

Plataforma web para gestionar el ciclo de vida completo de una licitación:
borrador → envío oficial → ganada/perdida → factura → cobro. Un usuario
(comercial) arma la oferta con productos, sube el documento de propuesta y
la envía; el sistema manda el correo real, recuerda vencimientos y cobranzas,
y aplica todas las reglas de negocio.

## Piezas y cómo hablan entre sí

```
Navegador (Next.js :3000)
   │  /api/* (rewrite same-origin; cookie HttpOnly access_token)
   ▼
FastAPI (:8000, /api/v1) ── alembic ──► PostgreSQL (Docker)
   │  services/ (reglas de negocio + transacciones, FOR UPDATE)
   ├─ Resend (API)         → correos reales vía patrón outbox
   └─ Supabase Storage     → propuestas en bucket privado + URL firmada
```

- **Backend**: FastAPI + SQLModel + Alembic. Los routers (`api/v1/endpoints`)
  son delgados; la lógica de negocio vive en `services/` (transiciones,
  pagos, jobs, email, storage) para poder probarla y reutilizarla.
- **Frontend**: Next.js App Router, `src/lib/api.ts` como único cliente HTTP
  (rutas sin barra final; ver LOG del desarrollo en
  `docs/REGISTRO_DESARROLLO.md`), UI en español.
- **BD**: PostgreSQL en Docker para dev; migraciones Alembic (nunca
  `create_all`); testeado con una BD aislada `licitaciones_test`.

## Decisiones que conviene poder defender

1. **Matriz de estados con historial en la misma transacción.**
   `draft → active → finished → to_collect → collected` (+ `lost`). Cualquier
   salto inválido → 409 `INVALID_STATUS_TRANSITION`. Cada cambio registra
   `tender_status_history` (anterior, nuevo, actor, razón, source user|system)
   dentro del mismo `commit` — nunca hay un cambio de estado sin su rastro.

2. **`SELECT ... FOR UPDATE` contra carreras de negocio.**
   Presupuesto (suma de partidas ≤ budget_max), vencimiento automático y
   último pago (saldo 0 → `collected`) se resuelven bajo lock de fila; hay
   tests de concurrencia con 2 hilos. Es la diferencia entre "funciona en
   un navegador" y "no se puede romper con dos pestañas".

3. **Patrón outbox para el email real (Resend).** El envío de correo se
   encola en `email_outbox` en la MISMA transacción que la transición de
   estado; un worker dispensa `pending` con reintentos e idempotencia. Así
   un timeout ambiguo del proveedor no duplica correos ni estados.

4. **URL firmada para propuestas.** Bucket privado en Supabase; el backend
   devuelve un `307` a una URL firmada de corta duración (nunca se expone el
   objeto). Validación de extensión/MIME/tamaño + nombres de objeto
   aleatorios; adaptador local para dev (`.storage/`) y adapter `supabase`
   con httpx (el SDK oficial rechaza las keys nuevas `sb_secret_…`).

5. **Seguridad por capas, sin secretos en el repo:**
   Argon2id para contraseñas; JWT HS256 en cookie `HttpOnly` + `SameSite=lax`
   (mismo-origen, sin CORS abierto — decisión CSRF formalizada en
   documentación de seguridad); `GET /users` y alta de usuarios solo admin; endpoint
   interno `/internal/jobs/tenders` con `X-Cron-Secret` comparado con
   `hmac.compare_digest`; limitador por IP en `/auth/login` (429).

6. **Soft delete de clientes.** `clients.deleted_at`: fuera de listas y web,
   fila, licitaciones e historial intactos; sin nuevas licitaciones para él.

## Cómo está verificado (evidencia, no "compila = listo")

- Backend: pytest contra PostgreSQL real aislado (77 casos: matriz 20
  transiciones inválidas, presupuesto, pagos/sobrepago, jobs/cron, storage
  mockeado, seguridad/rate-limit, soft delete de clientes); cobertura global
  ≈ 86 %.
- UI: Playwright `frontend/e2e/` — flujo feliz completo 15/15 (borrador →
  cobrada con partidas, propuesta, historial y pagos) + casos negativos 9/9
  (guard, 401/403/409/422/404 con banners correctos).
- Integraciones reales: smokes con Resend (correos `delivered` reales, IDs
  en LOG.md) y Supabase Storage (upload/descarga/URL firmada 11/11).
- `tsc --noEmit` limpio. `./scripts/bootstrap.sh --run` arranca todo.

## Despliegue (estado y opciones)

DECIDIDO (2026-10-08): **Render (plan free), un solo
origen**. API + frontend viven en UN web service a partir del `Dockerfile`
de la raíz (uvicorn :8000 + Next standalone :3000 detrás del mismo dominio
`*.onrender.com`): la cookie JWT `SameSite=lax` se mantiene misma-origen y
el cron entra por el rewrite de `POST /internal/jobs/tenders`.

- Postgres y Storage: **Supabase** (proyecto ya contratado); Alembic corre
  al primer arranque (entrypoint idempotente). (El Postgres free de Render
  se borra a los 30 días; por eso no se usa.)
- Cron: **externo** — cron-job.org (o GitHub Actions al subir el repo) con
  `X-Cron-Secret`; Healthchecks.io opcional.
- Free tier: el servicio duerme tras ~15 min sin tráfico (cold start
  30-60 s; el ping del cron lo despierta).
- Render necesita el código: repo git (GitHub) o imagen pública (Docker
  Hub). Runbook completo: `docs/DEPLOY.md`.

Secretos del despliegue: `SECRET_KEY`, `ADMIN_PASSWORD`, `RESEND_API_KEY`,
`SUPABASE_URL`, `SUPABASE_SERVICE_KEY`, `CRON_SECRET` (`backend/.env.example`).

## Límites conscientes (fuera de alcance de la prueba técnica)

- Multiusuario sin multi-tenant ni ownership por comercial (roles
  admin/user + permisos puntuales).
- Sin paginación en la UI del listado (la API ya tiene `limit/offset`).
- Rate limiting por IP en memoria (mono-worker): para producción
  multi-worker se movería a Redis. El cron ya es externo por diseño
  (endpoint + secreto): puede vivir en otro servicio aunque la app caiga.
- Sin CI ni remoto git aún: el usuario quiere GitHub "casi al final"; el
  repo ya está listo (tag v1.0.0, docs completas) para empujar y colgar CI.
  Despliegue decidido: Render (sección anterior); ejecución pendiente.