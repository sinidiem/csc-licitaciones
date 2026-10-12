# Frontend - Sistema de Gestión de Licitaciones (Next.js)

Interfaz web que consume la API REST del backend (FastAPI) en `/api/v1/*`.
Sesión por cookie JWT HttpOnly (misma-origen), login, guard de rutas y
gestión completa del flujo de licitaciones.

## Requisitos

- Node.js ≥ 18 (desarrollado con Node 26 / npm 12).

## Arranque (dev)

```bash
# 1) Backend corriendo en http://127.0.0.1:8000 (ver backend/README.md)
cd backend && ./venv/bin/uvicorn app.main:app --reload

# 2) Frontend
cd frontend
npm install
npm run dev  # http://localhost:3000
```

La cookie de sesión es `HttpOnly` y la comunicación es misma-origen: un
`rewrite` de Next enruta `/api/*` -> `http://127.0.0.1:8000/api/v1/*` (señal
`BACKEND_URL` si el backend vive en otro host).

## Producción / verificación

```bash
npm run build  # compila + valida tipos (next build)
npm run start  # sirve el build en :3000
```

## Páginas

| Ruta | Descripción |
|---|---|
| `/login` | Autenticación (cookie JWT). |
| `/licitaciones` | Listado + creación de borradores. |
| `/licitaciones/[id]` | Detalle: partidas, propuesta (subir/descargar vía URL firmada), acciones por estado (enviar, finalizar, perder, facturar, pagar), pagos e historial. |
| `/clientes`, `/productos` | Datos maestros. |
| `/usuarios` | Solo admin (el backend valida el rol y el menú oculta el enlace a no-admins). |

Sin sesión, las rutas protegidas redirigen a `/login` (guard server-side con
`cookies`).

## Solución de problemas

"NetworkError when attempting to fetch resource" al usar la UI: el fetch
del navegador no pudo contactar con la API. Causa raíz ya corregida (sesión
12): los endpoints de listado del backend redirigían con `Location` absoluto
hacia `127.0.0.1:8000` (cross-origin -> preflight CORS fallaba). Hoy las rutas
son sin barra final en backend y frontend y no hay redirects de por medio.
Aun así, si aparece:

1. Backend caído (la más común): el rewrite de Next no tiene destino y
  el fetch falla. Verifica que `http://127.0.0.1:8000/` responda 200 antes
  de abrir la UI.
2. Acceso desde otro equipo: `next dev`/`next start` solo escuchan en
  `127.0.0.1`. Para exponer en la LAN: `npm run dev -- -H 0.0.0.0` (o
  `next start -H 0.0.0.0`) y `BACKEND_URL` apuntando a un host accesible
  (si deja de ser misma-origen, revisa la política CORS del backend).
3. `next build` con `next dev` en marcha: ambos comparten `.next/` y el
  dev server se rompe con 500 tras el build. No los lances a la vez; si
  pasó, reinicia el dev server (`kill` al proceso y `npm run dev`).

## E2E con Playwright

```bash
# Requisitos: backend en :8000 y frontend en :3000 (ver arriba).
cd frontend && npm run e2e  # node e2e/ui_flow.mjs - flujo completo (15/15)
node e2e/ui_flow_neg.mjs  # casos negativos: guard, 401/403/409/422/404 (9/9)
```

El script recorre login -> cliente -> producto -> borrador -> partidas ->
propuesta -> envío (correo Resend real) -> finalizar -> facturar -> pagar ->
cobrada, y guarda capturas en `../docs/evidencias/dia10_ui/`. Necesita su
propio Chromium (`npx playwright install chromium` la primera vez) y al
usuario fixture `ui.demo@csc.dev` / `Uitest123!` (crearlo con el admin si no
existe). El cliente del sandbox de Resend se reutiliza si ya existe (su
`company_email` es único).

Checklist completa (backend + frontend, dos terminales):

```bash
# Terminal 1 - backend
cd backend && ./venv/bin/uvicorn app.main:app  # :8000, docs en /docs

# Terminal 2 - frontend (requisito: npm install una vez)
cd frontend && npm run dev  # http://localhost:3000
```

## Notas

- Importes: strings decimales del backend (`Decimal`), formateo con
  `toLocaleString("es-ES")`.
- Estados: `draft` borrador · `active` activa · `finished` finalizada ·
  `to_collect` por cobrar · `collected` cobrada · `lost` perdida.
- Descarga de propuesta: `/api/tenders/{id}/proposal/download` devuelve un
  307 a la URL firmada de Supabase (o bytes directos con el storage local).