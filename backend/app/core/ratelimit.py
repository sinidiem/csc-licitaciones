"""Limitador de intentos de login (defensa contra fuerza bruta).

Implementación en memoria con ventana deslizante por IP: suficiente para
una prueba técnica y para un despliegue de un solo worker (documentado en
ARQUITECTURA.md). Los tests limpian el estado entre casos vía conftest.

Configuración: `login_max_attempts` intentos por `login_window_seconds`s.
"""

import time
from collections import defaultdict, deque

from fastapi import HTTPException, Request

_login_attempts: dict[str, deque] = defaultdict(deque)


def login_rate_limit(
    request: Request,
    max_attempts: int = 20,
    window_seconds: int = 60,
) -> None:
    """Permite `max_attempts` llamadas por IP en la ventana; luego 429."""
    ip = request.client.host if request.client else "unknown"
    now = time.monotonic()
    queue = _login_attempts[ip]
    while queue and now - queue[0] > window_seconds:
        queue.popleft()
    if len(queue) >= max_attempts:
        raise HTTPException(
            status_code=429,
            detail="Demasiados intentos de acceso. Espera un minuto e inténtalo de nuevo.",
        )
    queue.append(now)


def clear_login_attempts() -> None:
    """Usado por los tests (estado limpio entre casos)."""
    _login_attempts.clear()