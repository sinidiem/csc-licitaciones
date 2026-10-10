#!/usr/bin/env bash
# CSC — Arranque de cero (desarrollo local).
#
#   ./scripts/bootstrap.sh         prepara BD, backend y frontend
#   ./scripts/bootstrap.sh --run   además deja uvicorn (:8000) y next dev (:3000) arriba
#
# Es idempotente: se puede re-ejecutar sin romper nada.
set -euo pipefail
cd "$(dirname "$0")/.."

echo "[1/5] PostgreSQL (Docker Compose)"
if docker ps -a --format '{{.Names}}' | grep -qx pg-licitaciones; then
  # Contenedor ya existente (dev actual): solo asegurar que esté en marcha.
  docker start pg-licitaciones >/dev/null
else
  docker compose up -d db
fi
for _ in $(seq 1 30); do
  docker exec pg-licitaciones pg_isready -U postgres -d licitaciones_db >/dev/null 2>&1 && break
  sleep 1
done

echo "[2/5] Backend: venv + dependencias"
cd backend
if [ ! -d venv ]; then python3 -m venv venv; fi
./venv/bin/pip install -q -r requirements.txt
if [ ! -f .env ]; then
  cp .env.example .env
  echo "      .env creado desde .env.example — revisa las credenciales antes de seguir"
fi

echo "[3/5] Migraciones + seed admin (idempotente)"
./venv/bin/alembic upgrade head
./venv/bin/python -m scripts.seed_admin
cd ..

echo "[4/5] Frontend: dependencias"
cd frontend
if [ ! -d node_modules ]; then npm install --no-audit --no-fund; fi
cd ..

if [ "${1:-}" = "--run" ]; then
  echo "[5/5] Servidores en marcha (Ctrl-C para detener)"
  trap 'kill 0' EXIT
  (cd backend && exec ./venv/bin/uvicorn app.main:app --port 8000) &
  (cd frontend && exec npm run dev) &
  wait
else
  echo "[5/5] Preparado. Para arrancar: ./scripts/bootstrap.sh --run"
fi