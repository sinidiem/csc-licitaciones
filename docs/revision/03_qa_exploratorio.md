# QA exploratorio — informe (2026-10-08)

Ámbito: plataforma completa (backend + frontend) probada en vivo contra
PostgreSQL real en Docker, Resend real y storage Supabase real (local).

Ejecuciones: E2E feliz **15/15** (borrador → activa → finalizada → por
cobrar → cobrada, con partidas, propuesta, historial y correos),
E2E negativo **9/9**, suite pytest **62/62** (incluye 24 tests
nuevos de storage), smokes reales 20/20 + 16/16 + 11/11.
Capturas: `docs/evidencias/dia10_ui/*.png` (feliz) y
`docs/revision/capturas/*.png` (negativos).

## Severidad

| Severidad | Cantidad |
|---|---|
| Crítico | 0 |
| Alto | 0 |
| Medio | 1 |
| Bajo | 2 (1 corregido) |
| Informativo | 6 |

## Detalle

### M1 — Sesión caducada no redirige a /login (medio, UX)
El guard verifica presencia de cookie, no validez; con JWT vencido cada
página muestra banner 401. Backend seguro (valida en cada llamada).
Mitigación sugerida: manejo de 401 en `api.ts`. → Ver
`02_revision_codigo.md` M1.

### B1 — 422 genérico (bajo)
Errores de validación pydantic (detail array) muestran "Error 422" en
lugar del mensaje concreto. → `02_revision_codigo.md` B1.

### B2 — Warning de hidratación React (bajo, CORREGIDO)
`/licitaciones` fecha límite por defecto calculada con `Date.now()` en
render → SSR vs hidratación divergentes. Corregido (inicial vacío +
relleno en `useEffect`); consola limpia tras el fix y E2E 15/15.

## Resultados por caso negativo (con mensaje exacto del backend)

1. Sin sesión → `/licitaciones` redirige a `/login`. ✓
2. Login con contraseña incorrecta → banner "Credenciales inválidas",
   permanece en /login. ✓
3. Crear usuario con rol `user` → 403 "Se requiere rol admin" (el backend
   corta; la UI no "esconde"). ✓
4. Cliente duplicado por correo → 409 "Ya existe un cliente con ese correo
   de empresa". ✓
5. Partida que excede el presupuesto → 422 "El total de partidas (625.00)
   supera el presupuesto máximo" y las partidas quedan intactas. ✓
6. Enviar sin propuesta → 409 "No se puede enviar sin el documento de
   propuesta subido"; estado sigue Borrador. ✓
7. Detalle de id inexistente → "Licitación no encontrada". ✓
8. Cero excepciones JavaScript sin capturar en TODA la sesión. ✓

## Consola del navegador

- Los recursos 4xx/5xx esperados ("Failed to load resource") aparecen solo
  en los flujos negativos (401/403/409/422/404), con su banner correcto.
- El warning de hidratación apareció en la primera corrida y desapareció
  tras el arreglo B2.
- Sin errores residuales en el flujo feliz.

## Pruebas manuales / bordes adicionales

- Presupuesto 0 → π, fecha límite en el pasado: el backend valida y
  responde 422 (validación de esquema; no crash — cubierto en tests).
- Descarga de propuesta: 307 a URL firmada (nube) / bytes (local),
  contenido idéntico al subido (verificado en smoke 11/11).

## Acciones

1. Aplicar M1 (manejo global de 401) cuando se formalice el guard.
2. Aplicar B1 (formatear detail array).
3. Decidir I1 (listado de usuarios) — ver auditoría.
4. Re-ejecutar negativos tras cualquier cambio de frontend (comando:
   `cd frontend && node e2e/ui_flow_neg.mjs`).