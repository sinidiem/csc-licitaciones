"""Router agregador de la API v1.

Cada recurso vive en su propio módulo bajo app/api/v1/endpoints/ y se
incluye aquí. Prefijo base /api/v1 lo aplica app/main.py.
"""

from fastapi import APIRouter

from app.api.v1.endpoints import auth, clients, products, tenders, users

api_router = APIRouter()

api_router.include_router(auth.router)
api_router.include_router(users.router)
api_router.include_router(clients.router)
api_router.include_router(products.router)
api_router.include_router(tenders.router)

# Días 5-8: proposal (storage), send, invoice, payments, internal/jobs.