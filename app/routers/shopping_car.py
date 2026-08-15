from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_session
from app.models import ShoppingCar, User, GameDetail, Product, Consoles, Licenses
from app.util.util_auth import get_current_user

router = APIRouter(prefix="/shopping-car", tags=["shopping-car"])


class ShoppingCarCreate(BaseModel):
    product_id: int
    estado: bool | None = True


class ShoppingCarUpdate(BaseModel):
    estado: bool


class ShoppingCarRead(BaseModel):
    id_shopping_car: int
    user_id: int
    product_id: int
    estado: bool
    product_price: int | None = None
    # Display data resuelta en el servidor para que el carrito se vea igual
    # en cualquier dispositivo, sin depender del cache local
    # "cart_combinations" que solo existe en el navegador donde se agrego
    # el producto.
    title: str | None = None
    image: str | None = None
    desc_console: str | None = None
    desc_licence: str | None = None
    base_game_id: int | None = None

    class Config:
        orm_mode = True


def _shopping_car_display_query():
    return (
        select(
            ShoppingCar,
            GameDetail.precio,
            GameDetail.precio_descuento,
            Product.title,
            Product.image,
            Consoles.descripcion.label("desc_console"),
            Licenses.descripcion.label("desc_licence"),
            GameDetail.producto_id,
        )
        .select_from(ShoppingCar)
        .join(GameDetail, ShoppingCar.product_id == GameDetail.id_game_detail)
        .join(Product, GameDetail.producto_id == Product.id_product, isouter=True)
        .join(Consoles, GameDetail.consola_id == Consoles.id_console, isouter=True)
        .join(Licenses, GameDetail.licencia_id == Licenses.id_license, isouter=True)
    )


def _effective_price(precio: int | None, precio_descuento: int | None) -> int | None:
    # Misma regla que ya usa la pagina de producto al agregar al carrito
    # (variable "M" en el bundle): la oferta solo cuenta si es mayor que 0
    # y menor que el precio de lista.
    if precio_descuento and precio and 0 < precio_descuento < precio:
        return precio_descuento
    return precio


def _build_shopping_car_read(item, precio, precio_descuento, title, image, desc_console, desc_licence, base_game_id) -> ShoppingCarRead:
    return ShoppingCarRead(
        id_shopping_car=item.id_shopping_car,
        user_id=item.user_id,
        product_id=item.product_id,
        estado=item.estado,
        product_price=_effective_price(precio, precio_descuento),
        title=title,
        image=image,
        desc_console=desc_console,
        desc_licence=desc_licence,
        base_game_id=base_game_id,
    )


@router.get("/", response_model=list[ShoppingCarRead])
async def list_shopping_car(
    state: bool | None = None,
    user_id: int | None = None,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    query = _shopping_car_display_query()

    # if user_id is not provided, default to current user
    effective_user_id = user_id if user_id is not None else current_user.id
    query = query.where(ShoppingCar.user_id == effective_user_id)

    if state is not None:
        query = query.where(ShoppingCar.estado == state)

    result = await session.execute(query)
    rows = result.all()

    return [
        _build_shopping_car_read(item, precio, precio_descuento, title, image, desc_console, desc_licence, base_game_id)
        for item, precio, precio_descuento, title, image, desc_console, desc_licence, base_game_id in rows
    ]


@router.get("/{shopping_car_id}", response_model=ShoppingCarRead)
async def get_shopping_car_item(
    shopping_car_id: int,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    result = await session.execute(
        _shopping_car_display_query().where(ShoppingCar.id_shopping_car == shopping_car_id)
    )
    row = result.first()
    if not row:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Item not found")

    item, precio, precio_descuento, title, image, desc_console, desc_licence, base_game_id = row
    if item.user_id != current_user.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Item not found")

    return _build_shopping_car_read(item, precio, precio_descuento, title, image, desc_console, desc_licence, base_game_id)


@router.post("/", response_model=ShoppingCarRead, status_code=status.HTTP_201_CREATED)
async def create_shopping_car_item(
    payload: ShoppingCarCreate,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    # Reject duplicate: same GameDetail already in this user's cart.
    existing = await session.execute(
        select(ShoppingCar).where(
            ShoppingCar.user_id == current_user.id,
            ShoppingCar.product_id == payload.product_id,
        )
    )
    if existing.scalars().first() is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="El producto ya está en el carrito.",
        )

    item = ShoppingCar(
        user_id=current_user.id,
        product_id=payload.product_id,
        estado=payload.estado if payload.estado is not None else True,
    )
    session.add(item)
    await session.commit()
    await session.refresh(item)

    result = await session.execute(
        _shopping_car_display_query().where(ShoppingCar.id_shopping_car == item.id_shopping_car)
    )
    _, precio, precio_descuento, title, image, desc_console, desc_licence, base_game_id = result.first()

    return _build_shopping_car_read(item, precio, precio_descuento, title, image, desc_console, desc_licence, base_game_id)


@router.put("/{product_id}", response_model=ShoppingCarRead)
async def update_shopping_car_item(
    product_id: int,
    payload: ShoppingCarUpdate,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    result = await session.execute(
        select(ShoppingCar).where(
            ShoppingCar.user_id == current_user.id,
            ShoppingCar.product_id == product_id,
        )
    )
    item = result.scalars().first()
    if not item:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Item not found")

    item.estado = payload.estado
    await session.commit()
    await session.refresh(item)

    result = await session.execute(
        _shopping_car_display_query().where(ShoppingCar.id_shopping_car == item.id_shopping_car)
    )
    _, precio, precio_descuento, title, image, desc_console, desc_licence, base_game_id = result.first()

    return _build_shopping_car_read(item, precio, precio_descuento, title, image, desc_console, desc_licence, base_game_id)


@router.delete("/{shopping_car_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_shopping_car_item(
    shopping_car_id: int,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    item = await session.get(ShoppingCar, shopping_car_id)
    if not item or item.user_id != current_user.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Item not found")

    await session.delete(item)
    await session.commit()
    return None
