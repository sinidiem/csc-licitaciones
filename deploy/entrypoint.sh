#!/usr/bin/env bash
# Entrada del contenedor de despliegue (un solo origen, decisión de despliegue
# §11.10): prepara la BD (migraciones + seed, idempotentes), arranca la API
# en :8000 y el frontend standalone en :3000.
#
# Si un proceso muere, el contenedor termina y el orquestador lo reinicia
# (en Fly la máquina se destruye/recrea; las migraciones vuelven a correr,
# pero son idempotentes y no tocan datos).
set -euo pipefail

cd /app/backend
echo "[entrypoint] migraciones Alembic (idempotentes)..."
python -m alembic upgrade head

echo "[entrypoint] seed del primer admin (idempotente)..."
python -m scripts.seed_admin

echo "[entrypoint] arrancando uvicorn en :8000..."
python -m uvicorn app.main:app --host 0.0.0.0 --port 8000 &
UVICORN_PID=$!

cleanup() {
  kill -TERM "$UVICORN_PID" 2>/dev/null || true
}
trap cleanup INT TERM

echo "[entrypoint] arrancando Next.js standalone en :3000..."
cd /app/frontend
node server.js &
NEXT_PID=$!

set +e
wait -n "$UVICORN_PID" "$NEXT_PID"
RC=$?
set -e
kill "$UVICORN_PID" "$NEXT_PID" 2>/dev/null || true
echo "[entrypoint] proceso terminado (rc=$RC)"
exit "$RC"