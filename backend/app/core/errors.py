"""Errores de negocio con códigos estables para la API.

CONTEXT.md plan §4: los errores de negocio llevan un código estable
(p. ej. INVALID_STATUS_TRANSITION) además del mensaje, para que el
frontend pueda actuar de forma determinista.
"""

from fastapi import HTTPException


def business_error(status_code: int, code: str, message: str) -> HTTPException:
    return HTTPException(
        status_code=status_code,
        detail={"code": code, "message": message},
    )