# ============================================================================
# CSC — imagen de despliegue (un solo origen: API + frontend).
#   docker build -t csc:latest .
# Runtime: uvicorn :8000 (API) y Next.js standalone :3000 (UI), ambos tras un
# mismo dominio https (cookie JWT misma-origen; decisión de despliegue).
# Los secretos entran por variables de entorno del despliegue, nunca en la
# imagen (.dockerignore excluye .env).
# ============================================================================

# --- Etapa 1: frontend (build) ---------------------------------------------
FROM node:22-bookworm-slim AS frontend-build
# Playwright (devDep) no debe descargar browsers dentro de la imagen.
ENV PLAYWRIGHT_SKIP_BROWSER_DOWNLOAD=1
WORKDIR /build/frontend
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY frontend/ ./
RUN npm run build

# --- Etapa 2: backend (dependencias, cacheable) ----------------------------
FROM python:3.14-slim AS backend-deps
WORKDIR /build
COPY backend/requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

# --- Etapa 3: runtime (API + UI) -------------------------------------------
FROM python:3.14-slim
ENV PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    HOSTNAME=0.0.0.0 \
    PORT=3000

# Node para el servidor standalone de Next (mismo binario de la etapa 1).
COPY --from=frontend-build /usr/local/bin/node /usr/local/bin/node

# Backend: dependencias + código (uvicorn/alembic vía `python -m`).
WORKDIR /app/backend
COPY --from=backend-deps /usr/local/lib/python3.14/site-packages /usr/local/lib/python3.14/site-packages
COPY backend/ ./

# Frontend: salida standalone (server.js + node_modules pruned + estáticos).
WORKDIR /app/frontend
COPY --from=frontend-build /build/frontend/.next/standalone ./
COPY --from=frontend-build /build/frontend/.next/static ./.next/static

# Entrypoint: migraciones + seed (idempotentes) + uvicorn + next.
COPY deploy/entrypoint.sh /app/entrypoint.sh
RUN chmod +x /app/entrypoint.sh

WORKDIR /app
EXPOSE 3000
HEALTHCHECK --interval=30s --timeout=5s --start-period=90s \
  CMD python -c "import urllib.request, urllib.error; req=urllib.request.Request('http://127.0.0.1:8000/api/auth/login',data=b'{}',headers={'Content-Type':'application/json'},method='POST'); urllib.request.urlopen(req,timeout=4)" >/dev/null 2>&1 || \
  python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:3000/login',timeout=4)" >/dev/null 2>&1 || exit 1

CMD ["/app/entrypoint.sh"]