# Evidencia del desplegado — Render + Supabase (2026-10-08)

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
| `GET /docs`, `GET /openapi.json` | 404 — Swagger/OpenAPI solo visible en dev (regla de seguridad) |
| `POST /internal/jobs/tenders` con `X-Cron-Secret` | 200 + contadores (`expired`/`reminders_*`) |
| `POST /internal/jobs/tenders` sin secreto | 401 |
| Migraciones + seed al primer arranque | OK (Alembic contra el Postgres de Supabase, idempotente) |

## Pendiente de esta fase

- **Cron real disparando el job** (cada 30-60 min): GitHub Actions
  `schedule:` o cron-job.org → `POST {URL}/internal/jobs/tenders` con
  `X-Cron-Secret`; guardar registro de ejecución y un resultado real
  (vencido/recordatorio con correo `delivered`).
- **Recorrido borrador → cobrada** en la UI desplegada (capturas) y
  verificación de descarga de propuesta vía URL firmada en este entorno.