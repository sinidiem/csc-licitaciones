# Evidencia — Supabase Storage real y frontend (2026-10-07)

Sin secretos: las keys y los tokens de URL firmada NO se reproducen aquí.

## Supabase Storage (decisión de arquitectura sobre storage)

Proveedor real verificado con `scripts/smoke_storage_supabase.py` contra
uvicorn + PostgreSQL + Resend reales (salida: **11/11 verificaciones ok**):

```
[ok  ] login admin (200)
[ok  ] cliente del sandbox listo
[ok  ] partida añadida (201)
[ok  ] subir propuesta -> Supabase (201)
[ok  ] provider == supabase en BD provider=supabase bucket=proposals
[ok  ] endpoint firmado -> 307 (307)
[ok  ] Location apunta a Supabase https://<proyecto>.supabase.co/storage/v1/object/sign/proposals/<objeto>.pdf
[ok  ] objeto firmado accesible (200)
[ok  ] bytes idénticos al original
[ok  ] envío oficial (adjunto desde Supabase) (200)
[ok  ] status active + submitted_at
```

- Bucket privado `proposals` (no público), creado por el adaptador.
- `GET /tenders/{id}/proposal/download` → `307` con `Location` a la URL
  firmada (`/storage/v1/object/sign/...?token=…`); el token se omite aquí.
- El adjunto del email oficial se descarga de Supabase vía `get_bytes`
  (misma lógica de envío con Resend verificada en los smokes).
- Detalle técnico: las keys nuevas de Supabase (`sb_secret_…`) requieren los
  headers `apikey` + `Authorization`; la URL firmada que devuelve la
  API es relativa al API de storage (`/storage/v1` + ruta).

## Frontend Next.js (nuevo)

Verificado por HTTP end-to-end con el build de producción (Next :3000 +
backend :8000, `next build` sin errores de tipos, 9 rutas):

| Comprobación | Resultado |
|---|---|
| `GET /login` (UI renderizada) | 200 |
| `GET /licitaciones` sin sesión | 307 → `/login` (guard server-side) |
| `POST /api/auth/login` vía el proxy de Next (usuario ficticio `ui.demo@csc.dev` creado por el admin) | 200, cookie `access_token` |
| `GET /licitaciones` con sesión | 200 |
| `GET /api/auth/me` y listados vía el proxy | 200 |

Comprobación visual: cubierta por el E2E con Playwright (15/15) y capturas
en `docs/evidencias/dia10_ui/` y `docs/revision/capturas/`.