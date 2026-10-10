# DESPLIEGUE — runbook (Render + Supabase, un solo origen)

Decisión de despliegue (2026-10-08): la app completa
(API + frontend) en RENDER como UN web service de un solo origen (uvicorn
:8000 + Next.js standalone :3000 en el mismo contenedor), Postgres y
Storage en SUPABASE (proyecto ya contratado), cron EXTERNO (cron-job.org;
GitHub Actions opcional al subir el repo).

## 0. Requisitos (cuentas del usuario)

1. **Render**: crear cuenta en https://render.com (plan gratuito).
2. **Supabase**: el proyecto ya existe (storage). Recuperar la cadena del
   Postgres gestionado en Dashboard → Project Settings → Database →
   **Connection string (Direct)** ≈
   `postgresql://postgres.<ref>:<PASSWORD>@aws-…pooler.supabase.com:5432/postgres`
   (elegir "Direct"; el contenedor siempre activo no necesita pooler). Si
   no se recuerda la contraseña del rol, "Reset database password".
3. **Código accesible para Render** (elige UNA):
   - **(A, recomendada si GitHub sigue "casi al final")** Docker Hub:
     cuenta en hub.docker.com; empujar la imagen construida localmente.
   - **(B, con GitHub)** subir el repo a GitHub, conectar la cuenta y usar
     `render.yaml` (blueprint) o crear el web service desde el repo.

## 1. Verificar la imagen ANTES de tocar Render (local)

```bash
docker build -t csc:latest .                      # multi-etapa (~5-8 min la 1ª vez)
docker run --rm -p 3000:3000 --env-file backend/.env csc:latest
#   UI:      http://localhost:3000/login
#   API:     POST http://localhost:3000/api/v1/auth/login
#   Swagger: http://localhost:3000/docs
#   Cron:    POST http://localhost:3000/internal/jobs/tenders -H "X-Cron-Secret: …"
# (los endpoints de la :3000 prueban el rewrite un solo-origen; el
#  entrypoint corre migraciones + seed contra el Postgres local)
docker stop $(docker ps -q --filter ancestor=csc:latest)
```

## 2a. Opción A — desplegar por imagen (sin GitHub)

```bash
docker build -t <usuario>/csc-licitaciones:latest .
docker login                                  # Docker Hub
docker push <usuario>/csc-licitaciones:latest
```
En Render: **New → Web Service → Deploy from image** →
`<usuario>/csc-licitaciones:latest`. Luego en **Environment** fijar (igual
que el blueprint):

```
ENVIRONMENT=production        COOKIE_SECURE=true
HOSTNAME=0.0.0.0              PORT=3000
SECRET_KEY=<min 32 bytes>     ADMIN_PASSWORD=<clave admin prod>
RESEND_API_KEY=<de backend/.env>   RESEND_TEST_TO=sinidie@proton.me
SUPABASE_URL=<de backend/.env>     SUPABASE_SERVICE_KEY=<de backend/.env>
CRON_SECRET=<valor nuevo>     DATABASE_URL=postgresql://postgres.<ref>:…@…supabase.com:5432/postgres
```

Guardar y **Deploy**. Para actualizar tras un cambio: rebuild + push +
"Manual Deploy → Clear build cache & deploy" (o re-pull de la imagen).

## 2b. Opción B — blueprint desde GitHub

1. `git push` del repo (ver README/LOG: el usuario lo quiere "casi al
   final"; aquí ya no es evitable si se quiere auto-deploy).
2. Render → **New → Blueprint** → conectar el repo → Render genera los
   recursos desde `render.yaml`; los `sync: false` se rellenan en el
   dashboard del servicio (Environment → New secret).

## 3. Comprobación del desplegado

```bash
curl -fsS -o /dev/null -w "%{http_code}\n" https://csc-licitaciones.onrender.com/login
curl -fsS -X POST https://csc-licitaciones.onrender.com/api/v1/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email":"admin@example.com","password":"<ADMIN_PASSWORD>"}' | head -c 300
curl -fsS -X POST https://csc-licitaciones.onrender.com/internal/jobs/tenders \
  -H "X-Cron-Secret: <CRON_SECRET>" -H "Content-Type: application/json" -d '{}'
```
Primer arranque: el entrypoint corre `alembic upgrade head` + seed del
admin contra el Postgres de Supabase (idempotente). Logs en el dashboard.

## 4. Cron externo (cron-job.org)

1. Crear cuenta; crear job:
   - URL: `https://csc-licitaciones.onrender.com/internal/jobs/tenders`
   - Método: `POST`; cabecera personalizada `X-Cron-Secret: <CRON_SECRET>`.
   - Frecuencia: cada 30 minutos (el free tier de Render duerme a los
     ~15 min; el ping lo despierta, cold start 30-60 s → el job con
     timeout amplio lo cubre).
2. Probar el job manualmente una vez y guardar captura del registro.
3. (Opcional, con GitHub) el YAML de Actions está en
   `docs/REGISTRO_DESARROLLO.md` (sección de automatización).

## 5. Evidencias del desplegado (día 10, separadas de las locales)

- Recorrido borrador → cobrada en el entorno real (capturas en
  `docs/evidencias/dia10_desplegado/`).
- Registro del cron ejecutado (cron-job.org) y respuesta con contadores
  (`reminders_sent`/`duplicated`).
- Un vencimiento automático y un recordatorio reales (correo `delivered`
  de Resend en el desplegado).
- URL desplegada + hash/commit de la versión evaluada (README/LOG).

## Notas / reglas

- `ENVIRONMENT=production` y `COOKIE_SECURE=true` (cookie `Secure`
  obligatoria sobre https). Todo lo demás por variables/secretos de Render
  (pydantic-settings los lee del entorno; no hay `.env` en producción).
- Sandbox de Resend: solo entrega a `sinidie@proton.me` (`RESEND_TEST_TO`);
  `RESEND_FROM` queda `onboarding@resend.dev` salvo cuenta pagada.
- El Postgres de Supabase arranca VACÍO: los datos demo (cliente,
  productos, licitaciones de prueba) se recrean en el desplegado por
  API/UI para la evidencia (como se hizo localmente), o se restaura un
  dump de `licitaciones_db` si se prefiere.
- El Postgres free de Render expira a los 30 días → por eso la BD vive en
  Supabase (no expira).
- El job es idempotente (locks + outbox): solapamientos de pings del cron
  no duplican vencimientos ni recordatorios.