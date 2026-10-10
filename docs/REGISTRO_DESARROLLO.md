# Registro de desarrollo — Sistema de Gestión de Licitaciones (CSC)

Bitácora de progreso y registro de decisiones del proyecto. Complementa a
`README.md` (qué es y cómo arranca), `CONTEXT.md` (requisitos, modelo y
reglas de negocio) y `docs/ARQUITECTURA.md` (diseño y decisiones).

## Cronología

### Días 1-2 (2026-10-07) — Fundaciones: modelo de datos y autenticación

- **Modelo de datos**: PostgreSQL + SQLModel + Alembic. PK `uuid.UUID`,
  fechas UTC (`TIMESTAMP WITH TIME ZONE`), `Decimal(14,2)` para dinero
  (nunca float), auditoría (`created_at/by`, `updated_at/by`) en entidades
  mutables, y restricciones/índices en la BD además de la validación de
  aplicación.
- **Autenticación**: Argon2id para contraseñas, sesión JWT HS256 en cookie
  `HttpOnly` (`SameSite=lax`, `Secure` en producción), roles `admin`/`user`,
  seed del primer admin idempotente. Solo `admin` crea usuarios; los
  hashes nunca se devuelven en respuestas.

### Días 3-4 (2026-10-07) — Núcleo del negocio: la licitación

- Clientes y productos; borradores con **partidas** (producto, cantidad,
  precio unitario).
- Presupuesto: `SUM(quantity * unit_price) <= budget_max`, validado bajo
  `SELECT … FOR UPDATE` dentro de una transacción (insensible a carreras:
  dos pestañas no rompen la regla).
- **Envío oficial** `draft → active`: exige documento de propuesta subido
  (extensión, MIME y tamaño validados) y dispara el correo real con resumen
  y adjunto mediante **patrón outbox idempotente** (sin duplicados ante
  timeouts ambiguos).
- **Matriz estricta de estados y transiciones**; cualquier salto inválido
  → 409 `INVALID_STATUS_TRANSITION`. Toda transición registra
  `tender_status_history` (anterior, nuevo, actor, razón, fuente) en la
  misma transacción.

### Día 5 (2026-10-07) — Resolución, facturación y pagos

- Ganada (`finished`) / perdida (`lost`).
- Factura: importe positivo y coherente (422 `INVOICE_AMOUNT_INVALID` /
  `INVOICE_BELOW_PAYMENTS`); una sola factura por licitación.
- Pagos parciales en `to_collect`, importe > 0 y ≤ saldo pendiente
  (422 `OVERPAYMENT` si se excede); al saldar el saldo, transición
  automática a `collected` en la misma transacción.

### Días 6-8 (2026-10-07/08) — Automatización e integraciones reales

- **Vencimiento automático** (activa y plazo pasado → `lost`, actor
  `system`) y **recordatorio único a 48 h** (`reminder_sent_at`): endpoint
  interno protegido con `X-Cron-Secret` (comparación segura), ejecución
  idempotente bajo corridas concurrentes y reintentos sin duplicar
  acciones. El disparador (cron) vive **fuera** de la aplicación: el
  diseño con endpoint + secreto permite cron externo, GitHub Actions o
  crontab indistintamente.
- **Email real con Resend** (patrón outbox, adjunto; sandbox →
  `sinidie@proton.me`).
- **Storage real**: Supabase Storage privado + **URL firmada** de corta
  duración para descargar propuestas (adaptador inyectable con httpx;
  local solo en dev).

### Días 9-10 (2026-10-08) — Frontend y revisión de calidad

- Frontend **Next.js + TypeScript** completo: login con guard de rutas,
  listado y detalle de licitaciones, partidas, subida/descarga de
  propuesta, historial, pagos, clientes, productos y usuarios. El front
  habla con el backend por el mismo origen (rewrite `/api/*`), sin CORS.
- **Verificación automatizada**: E2E Playwright con flujo completo
  borrador → cobrada (**15/15**) y casos negativos (**9/9**:
  401/403/409/422/404); suite backend **77/77** sobre PostgreSQL real
  aislado con migraciones, cobertura ≈ **86 %**.
- **Revisión de calidad**: auditoría de especificaciones sin
  incumplimientos (4 ambigüedades documentadas), revisión de código y QA
  exploratorio en `docs/revision/`; manual de usuario en
  `docs/MANUAL_USUARIO.md`.
- Cierre de hallazgos: guard de sesión (401 → /login), errores 422
  legibles, patrón anti-hidratación en el listado, **rate limit por IP en
  /auth/login** (429) y acceso a `/users` restringido a admin (menú
  oculto para el resto), soft delete de clientes (las licitaciones se
  conservan).

## Decisiones registradas (detalle y motivo en CONTEXT.md §11)

1. **Storage**: Supabase bucket privado + URL firmada (2026-10-08).
2. **Email**: outbox idempotente con Resend; el estado solo avanza cuando
   el proveedor acepta.
3. **Factura** puede diferir del presupuesto total (2026-10-08).
4. **Borrado lógico de clientes** (`deleted_at`): fuera de listas y web,
   con licitaciones e historial intactos (2026-10-08).
5. **CSRF**: cookie `SameSite=lax` + frontend mismo-origen + JSON, sin
   token adicional (2026-10-08).
6. **Despliegue**: Render (un solo origen: API + frontend en un
   contenedor) + Postgres/Storage en Supabase + cron externo
   (2026-10-08, ver `docs/DEPLOY.md`).

## Evidencias (sin secretos)

| Prueba | Resultado | Referencia |
|---|---|---|
| Suite backend (pytest, BD real aislada) | 77/77, cobertura ≈ 86 % | `backend/tests/` |
| E2E Playwright — flujo feliz | 15/15 (borrador → cobrada) | `frontend/e2e/ui_flow.mjs` |
| E2E Playwright — negativos | 9/9 (guard, 401/403/409/422/404) | `frontend/e2e/ui_flow_neg.mjs` |
| Email Resend (smokes días 7-8) | 20/20 y 16/16 `delivered` (IDs de proveedor: `01a118c4-c50d-7774-89ca-e81084327e21`, `01a118d8-1605-7185-a6cc-44b3b980c654`, `ff32685a-f0a3-4057-92bb-ccdb9d1cdd96`) | `backend/scripts/smoke_dia7.py`, `smoke_dia8.py` |
| Storage Supabase (URL firmada) | 11/11 (upload + descarga + firma) | `backend/scripts/smoke_storage_supabase.py` |
| Job interno (vencimiento + recordatorio) | responde con contadores `reminders_sent`/`duplicated` sin duplicados | `POST /internal/jobs/tenders` |
| Capturas de la UI (datos ficticios) | flujo feliz y negativos | `docs/evidencias/dia10_ui/`, `docs/revision/capturas/` |

## Estado actual y próximos pasos

- **Listo y verificado en local**: funcionalidad completa (ciclo
  borrador → cobrada), reglas de negocio en BD + app + pruebas,
  automatismos, email y storage reales, seguridad por capas, documentación.
- **Desplegado en producción (2026-10-08)**: Render (un solo origen,
  https://csc-licitaciones.onrender.com) con Postgres y Storage en
  Supabase — verificado en vivo (login, CRUD, job interno, Swagger oculto
  en prod). Evidencias en `docs/evidencias/dia10_desplegado.md`.
- **Cron externo en marcha (cron-job.org, cada 30 min)**: 200 OK con
  contadores; captura en `docs/evidencias/dia10_desplegado/`.
- **Recorrido completo en el entorno desplegado**: E2E 15/15 con 8
  capturas (`docs/evidencias/dia10_desplegado/ui/`) y correo real de
  Resend disparado desde producción.
- **Cierre limpio**: nada pendiente salvo mantener la ejecución del cron
  (y opcionalmente desactivar Auto-Deploy de Render para pushes de docs).