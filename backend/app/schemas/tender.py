"""Esquemas Pydantic de licitaciones y partidas."""

import uuid
from datetime import datetime
from decimal import Decimal

from pydantic import AwareDatetime, BaseModel, Field


class TenderCreate(BaseModel):
    client_id: uuid.UUID
    title: str = Field(min_length=1, max_length=200)
    reference: str | None = Field(default=None, max_length=50)
    description: str | None = Field(default=None, max_length=2000)
    deadline_at: AwareDatetime
    budget_max: Decimal = Field(gt=0, max_digits=14, decimal_places=2)


class TenderItemCreate(BaseModel):
    product_id: uuid.UUID
    quantity: int = Field(gt=0)
    unit_price: Decimal = Field(ge=0, max_digits=14, decimal_places=2)


class TenderItemDetail(BaseModel):
    id: uuid.UUID
    product_id: uuid.UUID
    product_name: str
    quantity: int
    unit_price: Decimal
    subtotal: Decimal


class TenderHistoryRead(BaseModel):
    from_status: str | None
    to_status: str
    reason: str | None
    source: str
    actor_user_id: uuid.UUID | None
    created_at: datetime


class TenderListItem(BaseModel):
    id: uuid.UUID
    client_id: uuid.UUID
    client_name: str
    title: str
    reference: str | None
    status: str
    budget_max: Decimal
    total: Decimal
    deadline_at: datetime
    created_at: datetime


class TenderPaymentItem(BaseModel):
    id: uuid.UUID
    amount: Decimal
    paid_at: datetime
    reference: str | None = None
    notes: str | None = None


class TransitionRequest(BaseModel):
    """Razón opcional para transiciones manuales (finish/lose)."""

    reason: str | None = Field(default=None, max_length=500)


class TenderInvoiceRequest(BaseModel):
    """Registro de factura (decisión CONTEXT.md §11.3, día 7).

    Importe estrictamente positivo; puede diferir del total de partidas
    (negociación/descuentos). El servicio valida que no sea inferior a los
    pagos ya registrados (422 INVOICE_BELOW_PAYMENTS).
    """

    invoiced_total: Decimal = Field(gt=0, max_digits=14, decimal_places=2)
    reason: str | None = Field(default=None, max_length=500)


class TenderPaymentCreate(BaseModel):
    amount: Decimal = Field(gt=0, max_digits=14, decimal_places=2)
    paid_at: AwareDatetime | None = Field(default=None)
    reference: str | None = Field(default=None, max_length=100)
    notes: str | None = Field(default=None, max_length=500)


class TenderDetail(BaseModel):
    id: uuid.UUID
    client_id: uuid.UUID
    client_name: str
    company_email: str
    title: str
    reference: str | None
    description: str | None
    status: str
    budget_max: Decimal
    total: Decimal
    deadline_at: datetime
    invoiced_total: Decimal | None = None
    saldo_pendiente: Decimal | None = None
    reminder_sent_at: datetime | None = None
    submitted_at: datetime | None = None
    proposal_file_id: uuid.UUID | None = None
    proposal_name: str | None = None
    created_at: datetime
    created_by: uuid.UUID | None = None
    items: list[TenderItemDetail]
    payments: list[TenderPaymentItem] = []
    history: list[TenderHistoryRead]