"""Endpoints de clientes: listado, creación, edición y borrado lógico.

Cualquier usuario autenticado puede gestionar clientes; la auditoría
(created_by/updated_by) registra quién. El borrado es SOFT DELETE
(`deleted_at`): la fila permanece en BD (licitaciones, historial y
auditoría intactos) pero no aparece en listas ni en la web, y no pueden
crearse licitaciones nuevas para él. Decisión CONTEXT.md (2026-10-08).

El correo de empresa sigue siendo único en BD (incluidos los borrados):
no se puede re-crear un cliente con el correo de uno eliminado.
"""

import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, HTTPException, status
from sqlmodel import select

from app.api.v1.deps import CurrentUser, SessionDep
from app.models.client import Client
from app.schemas.client import ClientCreate, ClientRead, ClientUpdate

router = APIRouter(prefix="/clients", tags=["clients"])


def _get_live(client_id: uuid.UUID, session) -> Client:
    """Cliente activo (no borrado) o 404."""
    client = session.get(Client, client_id)
    if client is None or client.deleted_at is not None:
        raise HTTPException(status_code=404, detail="Cliente no encontrado")
    return client


@router.get("", response_model=list[ClientRead])
def list_clients(user: CurrentUser, session: SessionDep) -> list[Client]:
    return list(
        session.exec(
            select(Client)
            .where(Client.deleted_at.is_(None))
            .order_by(Client.created_at)
        )
    )


@router.post("", response_model=ClientRead, status_code=status.HTTP_201_CREATED)
def create_client(
    payload: ClientCreate,
    user: CurrentUser,
    session: SessionDep,
) -> Client:
    existing = session.exec(
        select(Client).where(Client.company_email == payload.company_email)
    ).first()
    if existing is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Ya existe un cliente con ese correo de empresa",
        )
    client = Client(
        **payload.model_dump(),
        created_by=user.id,
    )
    session.add(client)
    session.commit()
    session.refresh(client)
    return client


@router.patch("/{client_id}", response_model=ClientRead)
def update_client(
    client_id: uuid.UUID,
    payload: ClientUpdate,
    user: CurrentUser,
    session: SessionDep,
) -> Client:
    client = _get_live(client_id, session)
    data = payload.model_dump(exclude_unset=True)
    if not data:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="No se enviaron campos para actualizar",
        )
    if "company_email" in data:
        other = session.exec(
            select(Client).where(
                Client.company_email == data["company_email"],
                Client.id != client_id,
            )
        ).first()
        if other is not None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Ya existe un cliente con ese correo de empresa",
            )
    for key, value in data.items():
        setattr(client, key, value)
    client.updated_by = user.id
    session.add(client)
    session.commit()
    session.refresh(client)
    return client


@router.delete("/{client_id}", response_model=ClientRead)
def delete_client(
    client_id: uuid.UUID,
    user: CurrentUser,
    session: SessionDep,
) -> Client:
    client = _get_live(client_id, session)
    client.deleted_at = datetime.now(UTC)
    client.updated_by = user.id
    session.add(client)
    session.commit()
    session.refresh(client)
    return client