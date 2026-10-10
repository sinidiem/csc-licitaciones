"""Endpoints de licitaciones: creación (borrador), listado, detalle y partidas.

Reglas clave (servicios en app/services/tenders.py):
- Crear licitación siempre en `draft` con historial.
- Partidas solo en `draft`; presupuesto validado en transacción (422).
- Estados terminales bloquear partidas (409).
"""

import uuid
from decimal import Decimal

from fastapi import APIRouter, File, Query, Response, UploadFile, status
from sqlmodel import select

from app.api.v1.deps import CurrentUser, SessionDep
from app.core.config import settings
from app.core.errors import business_error
from app.models.client import Client
from app.models.payment import Payment
from app.models.product import Product
from app.models.proposal_file import ProposalFile
from app.models.status_history import TenderStatusHistory
from app.models.tender import STATUS_ALLOWED, Tender, TenderStatus
from app.models.tender_item import TenderItem
from app.schemas.tender import (
    TenderCreate,
    TenderDetail,
    TenderHistoryRead,
    TenderInvoiceRequest,
    TenderItemCreate,
    TenderItemDetail,
    TenderListItem,
    TenderPaymentCreate,
    TenderPaymentItem,
    TransitionRequest,
)
from app.services import payments as payments_service
from app.services import storage as storage_service
from app.services import tenders as tenders_service
from app.services import transitions as transitions_service

router = APIRouter(prefix="/tenders", tags=["tenders"])


def _require_tender(session: SessionDep, tender_id: uuid.UUID) -> Tender:
    tender = tenders_service.get_tender(session, tender_id)
    if tender is None:
        raise business_error(404, "TENDER_NOT_FOUND", "Licitación no encontrada")
    return tender


def _item_detail(item: TenderItem, product: Product) -> TenderItemDetail:
    return TenderItemDetail(
        id=item.id,
        product_id=item.product_id,
        product_name=product.name,
        quantity=item.quantity,
        unit_price=item.unit_price,
        subtotal=item.subtotal(),
    )


@router.post("", response_model=TenderDetail, status_code=status.HTTP_201_CREATED)
def create_tender(payload: TenderCreate, user: CurrentUser, session: SessionDep) -> TenderDetail:
    tender = tenders_service.create_tender(
        session,
        client_id=payload.client_id,
        title=payload.title,
        reference=payload.reference,
        description=payload.description,
        deadline_at=payload.deadline_at,
        budget_max=payload.budget_max,
        actor_user_id=user.id,
    )
    return get_tender_detail(session, tender.id)


@router.get("", response_model=list[TenderListItem])
def list_tenders(
    user: CurrentUser,
    session: SessionDep,
    status_filter: str | None = Query(default=None, alias="status"),
    client_id: uuid.UUID | None = None,
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
) -> list[TenderListItem]:
    if status_filter is not None and status_filter not in STATUS_ALLOWED:
        raise business_error(422, "INVALID_STATUS", f"Estado inválido: {status_filter}")
    tenders = tenders_service.list_tenders(
        session,
        status=status_filter,
        client_id=client_id,
        limit=limit,
        offset=offset,
    )
    return [_list_item(session, t) for t in tenders]


def _list_item(session: SessionDep, tender: Tender) -> TenderListItem:
    client = session.get(Client, tender.client_id)
    total = tenders_service.current_total(session, tender.id)
    return TenderListItem(
        id=tender.id,
        client_id=tender.client_id,
        client_name=client.name if client else "?",
        title=tender.title,
        reference=tender.reference,
        status=tender.status,
        budget_max=tender.budget_max,
        total=total,
        deadline_at=tender.deadline_at,
        created_at=tender.created_at,
    )


@router.get("/{tender_id}", response_model=TenderDetail)
def get_tender(tender_id: uuid.UUID, user: CurrentUser, session: SessionDep) -> TenderDetail:
    return get_tender_detail(session, tender_id)


def get_tender_detail(session: SessionDep, tender_id: uuid.UUID) -> TenderDetail:
    tender = session.get(Tender, tender_id)
    if tender is None:
        raise business_error(404, "TENDER_NOT_FOUND", "Licitación no encontrada")

    client = session.get(Client, tender.client_id)
    items = list(
        session.exec(select(TenderItem).where(TenderItem.tender_id == tender_id))
    )
    products = {
        p.id: p
        for p in session.exec(
            select(Product).where(Product.id.in_([i.product_id for i in items]))
        )
    }
    history_rows = list(
        session.exec(
            select(TenderStatusHistory)
            .where(TenderStatusHistory.tender_id == tender_id)
            .order_by(TenderStatusHistory.created_at)
        )
    )
    payments = list(
        session.exec(select(Payment).where(Payment.tender_id == tender_id))
    )
    proposal = (
        session.get(ProposalFile, tender.proposal_file_id)
        if tender.proposal_file_id
        else None
    )
    total = tenders_service.current_total(session, tender_id)

    paid = sum((p.amount for p in payments), Decimal("0"))
    saldo = (
        (tender.invoiced_total - paid) if tender.invoiced_total is not None else None
    )

    return TenderDetail(
        id=tender.id,
        client_id=tender.client_id,
        client_name=client.name if client else "?",
        company_email=client.company_email if client else "",
        title=tender.title,
        reference=tender.reference,
        description=tender.description,
        status=tender.status,
        budget_max=tender.budget_max,
        total=total,
        deadline_at=tender.deadline_at,
        invoiced_total=tender.invoiced_total,
        saldo_pendiente=saldo,
        reminder_sent_at=tender.reminder_sent_at,
        submitted_at=tender.submitted_at,
        proposal_file_id=tender.proposal_file_id,
        proposal_name=proposal.original_name if proposal else None,
        created_at=tender.created_at,
        created_by=tender.created_by,
        items=[_item_detail(i, products[i.product_id]) for i in items],
        payments=[
            TenderPaymentItem(
                id=p.id,
                amount=p.amount,
                paid_at=p.paid_at,
                reference=p.reference,
                notes=p.notes,
            )
            for p in sorted(payments, key=lambda x: x.paid_at)
        ],
        history=[
            TenderHistoryRead(
                from_status=h.from_status,
                to_status=h.to_status,
                reason=h.reason,
                source=h.source,
                actor_user_id=h.actor_user_id,
                created_at=h.created_at,
            )
            for h in history_rows
        ],
    )


@router.post("/{tender_id}/items", response_model=TenderItemDetail, status_code=status.HTTP_201_CREATED)
def add_item(
    tender_id: uuid.UUID,
    payload: TenderItemCreate,
    user: CurrentUser,
    session: SessionDep,
) -> TenderItemDetail:
    tender = tenders_service.get_tender(session, tender_id)
    if tender is None:
        raise business_error(404, "TENDER_NOT_FOUND", "Licitación no encontrada")
    item = tenders_service.add_item(
        session,
        tender,
        product_id=payload.product_id,
        quantity=payload.quantity,
        unit_price=payload.unit_price,
        actor_user_id=user.id,
    )
    product = session.get(Product, item.product_id)
    return _item_detail(item, product)


@router.delete("/{tender_id}/items/{item_id}", status_code=status.HTTP_204_NO_CONTENT)
def remove_item(
    tender_id: uuid.UUID,
    item_id: uuid.UUID,
    user: CurrentUser,
    session: SessionDep,
) -> None:
    tender = tenders_service.get_tender(session, tender_id)
    if tender is None:
        raise business_error(404, "TENDER_NOT_FOUND", "Licitación no encontrada")
    tenders_service.remove_item(session, tender, item_id)


@router.post("/{tender_id}/proposal", response_model=TenderDetail, status_code=status.HTTP_201_CREATED)
async def upload_proposal(
    tender_id: uuid.UUID,
    user: CurrentUser,
    session: SessionDep,
    file: UploadFile = File(...),
) -> TenderDetail:
    """Carga multipart de la propuesta: validación + storage + metadata.

    §7: valida extensión/tamaño/MIME, nombre de objeto aleatorio,
    bucket privado. Permite reemplazar la propuesta actual SOLO en `draft`
    (decisión §11.1: estados posteriores congelan las partidas y la propuesta).
    En `active`/terminales se rechaza (409).
    """
    tender = tenders_service.get_tender(session, tender_id)
    if tender is None:
        raise business_error(404, "TENDER_NOT_FOUND", "Licitación no encontrada")
    if tender.status != TenderStatus.DRAFT.value:
        raise business_error(
            409, "INVALID_STATUS_TRANSITION",
            f"No se puede cambiar la propuesta en estado '{tender.status}'",
        )

    content = await storage_service.read_uploaded(file)
    ext = storage_service.validate_upload(file.filename or "", content)

 # MIME: debe corresponder exactamente a la extensión ().
    mimes: dict[str, str] = {
        "pdf": "application/pdf",
        "doc": "application/msword",
        "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        "xls": "application/vnd.ms-excel",
        "xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        "odt": "application/vnd.oasis.opendocument.text",
        "txt": "text/plain",
    }
    expected_mime = mimes[ext]
    if (file.content_type or "").lower() != expected_mime:
        raise business_error(
            422, "INVALID_MIME",
            f"Tipo MIME '{file.content_type}' no corresponde a un archivo .{ext}",
        )

    ref = storage_service.get_storage()
    object_key = storage_service.random_object_key(ext)
    ref.upload(
        bucket=settings.storage_bucket,
        object_key=object_key,
        content=content,
        content_type=file.content_type or mimes[ext],
    )

    proposal = ProposalFile(
        tender_id=tender.id,
        storage_provider=ref.provider,
        bucket=settings.storage_bucket,
        object_key=object_key,
        original_name=storage_service.safe_original_name(file.filename or "propuesta"),
        content_type=file.content_type or mimes[ext],
        size_bytes=len(content),
        checksum=storage_service.sha256_checksum(content),
        uploaded_by=user.id,
    )
    # El upload reemplaza la propuesta actual del borrador (se conservan las
    # filas históricas de proposal_files por su FK a la licitación).
    session.add(proposal)
    session.flush()
    tender.proposal_file_id = proposal.id
    session.commit()
    session.refresh(tender)
    return get_tender_detail(session, tender.id)


@router.get("/{tender_id}/proposal/download", status_code=status.HTTP_200_OK)
def download_proposal(tender_id: uuid.UUID, user: CurrentUser, session: SessionDep):
    """Descarga autorizada de la propuesta actual (URL firmada en Supabase).

    En dev (adaptador local) devuelve los bytes del objeto; cuando se active
    el adaptador supabase, aquí se generará la URL firmada de corta duración.
    Nunca se expone object_key ni URL en la respuesta.
    """
    tender = tenders_service.get_tender(session, tender_id)
    if tender is None:
        raise business_error(404, "TENDER_NOT_FOUND", "Licitación no encontrada")
    if tender.proposal_file_id is None:
        raise business_error(404, "PROPOSAL_REQUIRED", "La licitación no tiene propuesta")

    proposal = session.get(ProposalFile, tender.proposal_file_id)
    if proposal is None:
        raise business_error(404, "PROPOSAL_REQUIRED", "La propuesta referenciada no existe")

    content = storage_service.get_storage().get_bytes(
        bucket=proposal.bucket, object_key=proposal.object_key
    )
    return Response(
        content=content,
        media_type=proposal.content_type,
        headers={
            "Content-Disposition": f'attachment; filename="{proposal.original_name}"'
        },
    )


@router.get("/{tender_id}/proposal/download/signed", status_code=status.HTTP_307_TEMPORARY_REDIRECT)
def download_proposal_signed(tender_id: uuid.UUID, user: CurrentUser, session: SessionDep):
    """URL firmada de corta duración cuando el storage es Supabase ( §7).

    Redirige al objeto firmado para que el navegador lo abra/descargue
    directamente desde Supabase; el enlace expira (default 900 s). Solo
    disponible con el adaptador supabase; con el local, usar el endpoint
    de bytes (dev).
    """
    from fastapi.responses import RedirectResponse

    tender = tenders_service.get_tender(session, tender_id)
    if tender is None:
        raise business_error(404, "TENDER_NOT_FOUND", "Licitación no encontrada")
    if tender.proposal_file_id is None:
        raise business_error(404, "PROPOSAL_REQUIRED", "La licitación no tiene propuesta")

    proposal = session.get(ProposalFile, tender.proposal_file_id)
    if proposal is None:
        raise business_error(404, "PROPOSAL_REQUIRED", "La propuesta referenciada no existe")

    storage = storage_service.get_storage()
    if storage.provider != "supabase":
        raise business_error(
            409, "SIGNED_URL_UNAVAILABLE",
            "El storage activo no genera URLs firmadas (adaptador local)",
        )
    url = storage.create_signed_url(
        bucket=proposal.bucket,
        object_key=proposal.object_key,
        expires_in=settings.signed_url_expires_seconds,
    )
    return RedirectResponse(url=url, status_code=status.HTTP_307_TEMPORARY_REDIRECT)


@router.post("/{tender_id}/send", response_model=TenderDetail)
def send(tender_id: uuid.UUID, user: CurrentUser, session: SessionDep) -> TenderDetail:
    """Envío oficial: valida borrador/propuesta/destinatario, correo real con
    adjunto (outbox) y transición draft → active SOLO si el proveedor acepta."""
    tender = _require_tender(session, tender_id)
    transitions_service.send_tender(session, tender, actor_user_id=user.id)
    return get_tender_detail(session, tender.id)


@router.post("/{tender_id}/transitions/finish", response_model=TenderDetail)
def finish_tender(
    tender_id: uuid.UUID,
    payload: TransitionRequest,
    user: CurrentUser,
    session: SessionDep,
) -> TenderDetail:
    """active → finished: la empresa ganó y completó la entrega."""
    tender = _require_tender(session, tender_id)
    transitions_service.finish_tender(
        session, tender, actor_user_id=user.id, reason=payload.reason
    )
    return get_tender_detail(session, tender.id)


@router.post("/{tender_id}/transitions/lose", response_model=TenderDetail)
def lose_tender(
    tender_id: uuid.UUID,
    payload: TransitionRequest,
    user: CurrentUser,
    session: SessionDep,
) -> TenderDetail:
    """active → lost: resolución manual (no se ganó la licitación)."""
    tender = _require_tender(session, tender_id)
    transitions_service.lose_tender(
        session, tender, actor_user_id=user.id, reason=payload.reason
    )
    return get_tender_detail(session, tender.id)


@router.post("/{tender_id}/invoice", response_model=TenderDetail)
def invoice_tender(
    tender_id: uuid.UUID,
    payload: TenderInvoiceRequest,
    user: CurrentUser,
    session: SessionDep,
) -> TenderDetail:
    """finished → to_collect: registra el importe facturado (decisión §11.3)."""
    tender = _require_tender(session, tender_id)
    transitions_service.invoice_tender(
        session,
        tender,
        amount=payload.invoiced_total,
        actor_user_id=user.id,
        reason=payload.reason,
    )
    return get_tender_detail(session, tender.id)


@router.post(
    "/{tender_id}/payments",
    response_model=TenderDetail,
    status_code=status.HTTP_201_CREATED,
)
def create_payment(
    tender_id: uuid.UUID,
    payload: TenderPaymentCreate,
    user: CurrentUser,
    session: SessionDep,
) -> TenderDetail:
    """Registra un abono en `por_cobrar`; saldo = 0 → `collected` automático."""
    tender = _require_tender(session, tender_id)
    payments_service.register_payment(
        session,
        tender,
        amount=payload.amount,
        paid_at=payload.paid_at,
        reference=payload.reference,
        notes=payload.notes,
        actor_user_id=user.id,
    )
    return get_tender_detail(session, tender.id)