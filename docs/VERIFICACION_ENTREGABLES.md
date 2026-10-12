# Verificación de entregables - Prueba Técnica CSC

Este documento cruza cada requisito de la guía de la prueba técnica con la
evidencia concreta en el repositorio y en el entorno desplegado.

## Entregables obligatorios (según la guía)

| # | Requisito | Estado | Evidencia |
|---|---|---|---|
| 1 | Repositorio Git público con README de instalación | ✅ | [github.com/sinidiem/csc-licitaciones](https://github.com/sinidiem/csc-licitaciones); `README.md` en raíz con arranque de 5 min (`./scripts/bootstrap.sh --run`), credenciales demo y tabla de verificación |
| 2 | Despliegue en servicio gratuito (Vercel, Render o Netlify) con enlace funcional | ✅ | [https://csc-licitaciones.onrender.com](https://csc-licitaciones.onrender.com) - Render (plan free, un solo origen: API + frontend en un contenedor Docker desde el `Dockerfile` raíz); login, CRUD y job interno verificados en vivo |
| 3 | Correo real con adjunto (evidencia de recepción) | ✅ | Outbox con Resend (sandbox, buzón `sinidie@proton.me`); 7 correos `sent` con IDs del proveedor en desarrollo + 1 correo desde producción enviado durante el E2E desplegado; captura `06_tras_envio.png` en `docs/evidencias/dia10_desplegado/ui/` |
| 4 | Documento de propuesta accesible vía URL real | ✅ | Storage privado en Supabase (`proposals`); descarga por URL firmada de 15 min (`GET /tenders/{id}/proposal/download/signed` -> 307 a Supabase); smoke 11/11 con upload/descarga/URL firmada reales (evidencia en `docs/evidencias/dia9_supabase_ui.md`) |
| 5 | Swagger / OpenAPI | ✅ | `/docs` visible en desarrollo, oculto en producción por regla de seguridad (`docs_url=None` y `openapi_url=None` cuando `ENVIRONMENT=production`); verificado en vivo: `/docs` 404, `/openapi.json` 404 en el desplegado |
| 6 | Cron externo ejecutándose | ✅ | cron-job.org: job cada 30 min -> `POST /internal/jobs/tenders` con cabecera `X-Cron-Secret`; prueba de ejecución manual 200 OK con contadores; captura `cron-job-verificacion.png` en `docs/evidencias/dia10_desplegado/` |

## Funcionalidad (ciclo completo de licitación)

| Requisito | Estado | Evidencia |
|---|---|---|
| Borrador -> Activa (envío oficial con propuesta y correo) | ✅ | E2E Playwright 15/15 en local y en el desplegado; `POST /tenders/{id}/send` con validación de propuesta + outbox + transición atómica |
| Activa -> Finalizada (ganada y entregada) | ✅ | `POST /tenders/{id}/finish`; historial completo en la misma transacción |
| Activa -> Perdida (manual o por vencimiento automático) | ✅ | `POST /tenders/{id}/lose` + job del cron (`/internal/jobs/tenders`) con `SELECT ... FOR UPDATE`; test de concurrencia con 2 hilos |
| Finalizada -> Por cobrar (factura) | ✅ | `POST /tenders/{id}/invoice`; importe positivo; validación de que el importe puede ser distinto del total (decisión documentada) |
| Por cobrar -> Cobrada (saldo = 0 automático) | ✅ | `POST /tenders/{id}/payments`; validación de no sobrepago (422); transición a `collected` en la misma transacción del último pago |
| Partidas (productos + cantidad + precio) | ✅ | `POST /tenders/{id}/items`; `SUM(quantity × unit_price) ≤ budget_max` con `FOR UPDATE`; bloqueo de edición en estados terminales |
| Historial inmutable de cambios de estado | ✅ | `tender_status_history` (anterior, nuevo, actor, razón, `source` user|system); registrado en la misma transacción que el cambio |
| Soft delete de clientes | ✅ | `clients.deleted_at`: la fila permanece; no aparece en listas ni permite nuevas licitaciones; las licitaciones existentes se conservan; unicidad de correo en todas las filas |

## Reglas de negocio automáticas

| Regla | Estado | Evidencia |
|---|---|---|
| Vencimiento: deadline pasado + activa -> perdida | ✅ | Job del cron; test `test_vencimiento_automatico_y_idempotente`; idempotente (no duplica transiciones) |
| Recordatorio: ≤48h del deadline, una sola vez | ✅ | Job del cron; flag `reminder_sent_at`; test `test_recordatorio_dentro_de_48h_una_sola_vez`; sin tocar licitaciones ya vencidas |
| Envío solo con propuesta subida | ✅ | `send_tender` -> 409 `PROPOSAL_REQUIRED` si `proposal_file_id IS NULL` |
| Correo con resumen + adjunto al enviar | ✅ | `build_tender_summary_html` + attachment desde storage (Resend); solo avanza a `active` si el proveedor acepta (502 `EMAIL_PROVIDER_FAILED` si no) |
| Pagos solo en `to_collect`, 0 < amount ≤ saldo | ✅ | Validación en `register_payment`; 422 `OVERPAYMENT` si amount > saldo; test de pagos parciales y totales |

## Seguridad

| Requisito | Estado | Evidencia |
|---|---|---|
| Contraseñas con Argon2id | ✅ | `argon2-cffi`; `hash_password` / `verify_password` en `app/core/security.py` |
| Sesión JWT en cookie HttpOnly | ✅ | HS256, `access_token` en cookie; `Secure=True` en producción; `SameSite=lax`; tests de acceso 401 |
| Roles: solo admin crea/lista usuarios | ✅ | `AdminUser` dependency; `GET /users` -> 403 para rol `user`; menú de la UI oculta "Usuarios" a no-admins |
| Rate limit en login (20 intentos/min por IP) | ✅ | `login_rate_limit` en memoria (ventana deslizante); test 429 tras 20 intentos, limpieza entre tests; documentado como mono-worker (a Redis en multi-worker) |
| CSRF mitigado | ✅ | `SameSite=lax` + mismo-origen + JSON sin token adicional; decisión formalizada en `docs/ARQUITECTURA.md` |
| Endpoint interno del cron autenticado | ✅ | `POST /internal/jobs/tenders` con `X-Cron-Secret` comparado con `hmac.compare_digest`; 401 sin/incorrecto; nunca se loguea el secreto |
| Secretos nunca en el repo | ✅ | `.env` en `.gitignore`; `.env.example` documenta variables sin valores; secretos de producción en Render (variables de entorno); `.dockerignore` excluye `.env` |
| Swagger/OpenAPI solo en dev | ✅ | `docs_url` y `openapi_url` = `None` en producción; verificado en vivo (404 en el desplegado) |

## Calidad del código y pruebas

| Requisito | Estado | Evidencia |
|---|---|---|
| Backend: pytest contra PostgreSQL real aislado | ✅ | 77 tests (BD `licitaciones_test`), cobertura global ~86% (storage 94%, email 27%); `conftest.py` con migraciones Alembic automáticas |
| Frontend: E2E con Playwright | ✅ | `frontend/e2e/ui_flow.mjs`: 15/15 verificaciones (borrador -> cobrada, partidas, propuesta, historial, pagos) + `ui_flow_neg.mjs`: 9/9 casos negativos (401/403/409/422/404 con banners) |
| TypeScript sin errores | ✅ | `tsc --noEmit` limpio (`frontend/`) |
| Migraciones Alembic (nunca `create_all`) | ✅ | `alembic/versions/` versionado; `alembic upgrade head` en bootstrap y entrypoint de despliegue |
| Arranque idempotente en 5 minutos | ✅ | `./scripts/bootstrap.sh --run` probado de punta a punta; contenedor existente o compose; venv, migraciones, seed, frontend |
| Integraciones reales (no simuladas en los tests de integración) | ✅ | Smokes con Resend (correos `delivered` reales, IDs registrados); Supabase Storage (upload/descarga/URL firmada 11/11); cron-job.org (200 OK con contadores, captura) |
| Documentación completa | ✅ | `README.md` (producto), `docs/ARQUITECTURA.md` (10 min), `docs/DEPLOY.md` (runbook), `docs/MANUAL_USUARIO.md`, `docs/revision/` (3 informes de calidad), `docs/REGISTRO_DESARROLLO.md` (bitácora), `backend/README.md` y `frontend/README.md` |

## Resumen

Todos los requisitos obligatorios y funcionalidades descritas en la guía de la
prueba técnica tienen evidencia concreta en el repositorio y en el entorno
desplegado. La verificación en vivo del desplegado (login, CRUD, job interno
200/401, Swagger oculto, E2E completo 15/15 con correo real desde producción)
confirma que el sistema funciona de extremo a extremo en el entorno de
evaluación.