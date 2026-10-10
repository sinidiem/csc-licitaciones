"""Endpoints de productos: creación y listado (API mínima ).

El precio en el catálogo es de referencia; la licitación conserva el precio
acordado en la partida (tender_items.unit_price).
"""

from fastapi import APIRouter, status
from sqlmodel import select

from app.api.v1.deps import CurrentUser, SessionDep
from app.models.product import Product
from app.schemas.product import ProductCreate, ProductRead

router = APIRouter(prefix="/products", tags=["products"])


@router.get("", response_model=list[ProductRead])
def list_products(user: CurrentUser, session: SessionDep) -> list[Product]:
    return list(session.exec(select(Product).order_by(Product.created_at)))


@router.post("", response_model=ProductRead, status_code=status.HTTP_201_CREATED)
def create_product(
    payload: ProductCreate,
    user: CurrentUser,
    session: SessionDep,
) -> Product:
    product = Product(
        **payload.model_dump(),
        created_by=user.id,
    )
    session.add(product)
    session.commit()
    session.refresh(product)
    return product