# Evidencia del desplegado - Render + Supabase (2026-10-08)

Entorno real de producción, separado de las evidencias locales
(`docs/evidencias/dia10_ui/`, `dia9_supabase_ui.md`).

| Dato | Valor |
|---|---|
| URL desplegada | https://csc-licitaciones.onrender.com |
| Commit evaluado | `c354c00` (rama `main`, tag `v1.0.0`) |
| Proveedores | Render (free, un solo origen) + Supabase (Postgres y Storage) + Resend |
| BD | Postgres gestionado de Supabase vía pooler (IPv4) |

## Comprobaciones en vivo (2026-10-08, contra la URL pública)

| Comprobación | Resultado |
|---|---|
| `GET /login` (UI) | 200 |
| `POST /api/auth/login` (admin, ruta real del frontend) | 200 + cookie HttpOnly |
| `GET /api/tenders`, `/api/clients`, `/api/products`, `/api/users` | 200 (autenticado) |
| `GET /docs`, `GET /openapi.json` | 404 - Swagger/OpenAPI solo visible en dev (regla de seguridad) |
| `POST /internal/jobs/tenders` con `X-Cron-Secret` | 200 + contadores (`expired`/`reminders_*`) |
| `POST /internal/jobs/tenders` sin secreto | 401 |
| Migraciones + seed al primer arranque | OK (Alembic contra el Postgres de Supabase, idempotente) |

## Cron externo (cron-job.org)

Job activo: `POST https://csc-licitaciones.onrender.com/internal/jobs/tenders`
con cabecera `X-Cron-Secret`, cada 30 minutos. Ejecución de prueba: HTTP
200 con respuesta `{"expired":0,"reminders_sent":0,"reminders_failed":0,
"reminders_duplicated":0,"reminders_skipped_no_client":0}` (el endpoint
devuelve ~110 bytes, muy por debajo del límite del proveedor). Captura del
panel: `cron-job-verificacion.png`. La respuesta de contadores se verifica
además en cada ejecución programada desde el historial del proveedor.

## Recorrido borrador -> cobrada en el entorno desplegado

E2E de Playwright ejecutado contra la URL de producción (mismo script que
el local, con `UI_URL` apuntando al desplegado): 15/15 verificaciones,
8 capturas en `ui/`, y se disparó un correo REAL de Resend desde
producción al buzón sandbox con la propuesta adjunta. Detalle del flujo:
cliente nuevo (buzón sandbox) -> producto -> borrador -> partida (total
625,00) -> propuesta subida al bucket (URL firmada) -> enviada (correo) ->
finalizada -> facturada -> pago total -> cobrada; historial completo
(Borrador -> Activa -> Finalizada -> Por cobrar -> Cobrada) y listado final.