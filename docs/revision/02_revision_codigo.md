# Revisión de código — hallazgos (2026-10-08)

Alcance: `backend/app` (models, services, schemas, api/v1, core, jobs) y
`frontend/src` (app/, lib/api.ts), más flujos E2E. Objetivo: bugs de
lógica y problemas de seguridad, no estilo. Veredicto resumido:
**0 críticos, 0 altos, 1 medio, 2 bajos** (uno ya corregido), varios
hallazgos informativos. Sin secretos expuestos, sin inyección, sin
rutas sin autenticar en `/api/v1`.

## Hallazgos

### MEDIO

**M1 — El guard de sesión del frontend solo comprueba presencia de cookie.**
`frontend/src/app/(app)/layout.tsx` redirige a /login si no existe la
cookie `access_token`, pero no valida la sesión (JWT podría estar caducado
o manipulado). Consecuencia: un usuario con sesión caducada entra a la
app y cada página muestra un banner 401 en lugar de volver al login.
No es una falla de seguridad (el backend valida en CADA endpoint; la UI no
oculta nada), es UX + robustez.
Sugerencia: en `src/lib/api.ts`, ante `401` en un endpoint de negocio,
navegar a `/login` (o validar `/api/auth/me` en el layout y redirigir).

### BAJOS

**B1 — Error 422 genérico en la UI.**
Cuando FastAPI devuelve `detail` como array (errores pydantic),
`api.ts` no extrae el mensaje y muestra "Error 422".
Sugerencia: si `detail` es array, usar `detail[0].msg`.
(Código: `frontend/src/lib/api.ts` → `request()`.)

**B2 — Warning de hidratación de React en /licitaciones (CORREGIDO).**
`useState(toLocalInput(new Date(Date.now() + 15d)))` calculaba una fecha
distinta en SSR y en el cliente → "A tree hydrated but some attributes...".
Corregido inicializando el campo vacío y rellenándolo en `useEffect`
(2026-10-08); verificado: el warning ya no aparece en consola y el
E2E feliz sigue 15/15.

### INFORMATIVOS (decisiones a tomar, no bugs)

- **I1 — `GET /users` accesible a cualquier usuario autenticado.** La guía
  restringe la creación a admin, no el listado. Exponer directorio del
  equipo a cualquier cuenta es una decisión: restringir a admin o
  justificar. (Ver auditoría §Ambigüedades.1)
- **I2 — Productos con nombre no único.** Modelo con `index=True` (no
  `unique`); la guía no pide unicidad. Válido por diseño.
- **I3 — Sin rate limiting en login.** No lo exige la guía; recomendable
  en producción (fail2ban o middleware) como defensa en profundidad.
- **I4 — Operativo:** `npm run build` con `next dev` activo corrompe
  `.next/` (500) — documentado en `frontend/README.md`. `pkill -f
  "uvicorn app.main"` se automata (patrón que matchea su propia línea) —
  usar `pgrep -af "[u]vicorn"`.
- **I5 — `_ensure_bucket` en cada construcción del adaptador.** Mitigado
  por `lru_cache` en `get_storage()`; se añadió `http`
  inyectable para tests (sin red real).
- **I6 — La URL firmada viaja en el `Location` de la respuesta 307.**
  Comportamiento esperado (descarga del documento en pestaña/browser);
  duración corta (15 min) y bucket privado.

## Verificaciones positivas (sin hallazgos)

- Sin secretos hardcodeados ni en logs (scan semilla + revisión).
- Sin inyección SQL: `session.exec/execute` con parámetros; sin `format`
  en consultas. Sin `eval`/`os.system`/`pickle` en el árbol de app.
- `password_hash` nunca en respuestas; Argon2id en `core/security.py`.
- Concurrencia: `FOR UPDATE` en partidas, pagos, transiciones y jobs;
  tests de carrera (pagos y vencimiento con 2 hilos) en verde.
- MIME/tamaño/extensión validados en upload; nombres de objeto aleatorios
  (uuid4 hex); nombre original saneado (sin traversal) — cubierto por los
  tests nuevos `test_storage_adapters.py` (24 casos, storage 94%).
- Frontend React escapa el contenido (sin XSS por interpolación);
  `credentials: same-origin` y cookie HttpOnly.
- Códigos de error estables (`core/errors.py`) y coherentes: envío sin
  propuesta → 409 `PROPOSAL_REQUIRED`; descarga de propuesta inexistente
  → 404 (semántica de "ausente" de la guía).

## Sugerencias de mejora (no bloqueantes)

1. Manejo global de 401 (ver M1) cuando se formalice la sesión en el
   layout; 2. formatear 422 (B1); 3. decidir el alcance de `GET /users`
   (I1); 4. rate limiting de login en despliegue (I3).