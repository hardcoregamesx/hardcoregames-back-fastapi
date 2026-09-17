from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_session
from app.models import ShoppingCar, User, GameDetail, Product, Consoles, Licenses
from app.util.util_auth import get_current_user

router = APIRouter(prefix="/shopping-car", tags=["shopping-car"])

MODOS_PAGO_VALIDOS = ("contado", "cuotas", "reserva")


class ShoppingCarCreate(BaseModel):
    product_id: int
    estado: bool | None = True
    # 'contado' | 'cuotas' | 'reserva' (docs/cuotas-y-reserva.md §5). Default
    # 'contado' para que los clientes viejos que no mandan este campo sigan
    # comprando de contado exactamente como antes.
    modo_pago: str | None = "contado"


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
    # IDs crudos de la combinacion (mismos nombres/valores que devuelve
    # /products/combination-price/{id}): el checkout los usa para armar la
    # descripcion que se envia a Bold. Sin esto el checkout desde el carrito
    # mandaba "Titulo | - | - | -" aunque desc_console/desc_licence si
    # llegaran bien.
    consola: int | None = None
    licencia: int | None = None
    duracion_dias_alquiler: int | None = None
    # Cuotas y reserva (docs/cuotas-y-reserva.md §5) -- campos aditivos,
    # ningun cliente viejo los lee.
    modo_pago: str = "contado"
    pago_hoy: int | None = None
    cuotas_activas: bool = False
    num_cuotas: int = 3
    valor_cuota: int = 0
    cuota_inicial: int | None = None
    reserva_activa: bool = False
    monto_reserva: int = 20000

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
            GameDetail.consola_id,
            GameDetail.licencia_id,
            GameDetail.duracion_dias_alquiler,
            GameDetail.cuotas_activas,
            GameDetail.num_cuotas,
            GameDetail.valor_cuota,
            GameDetail.cuota_inicial,
            GameDetail.reserva_activa,
            GameDetail.monto_reserva,
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


def _pago_hoy(
    modo_pago: str,
    precio_contado: int | None,
    cuota_inicial: int | None,
    valor_cuota: int | None,
    monto_reserva: int | None,
) -> int | None:
    """"Pago de hoy" por item, misma regla que Django _calculate_cart_amount
    (docs/cuotas-y-reserva.md §3.2): contado -> precio de contado; cuotas ->
    inicial (cuota_inicial si esta puesta, si no vale igual que valor_cuota);
    reserva -> monto_reserva."""
    if modo_pago == "cuotas":
        return cuota_inicial if cuota_inicial else (valor_cuota or 0)
    if modo_pago == "reserva":
        return monto_reserva
    return precio_contado


def _build_shopping_car_read(
    item,
    precio,
    precio_descuento,
    title,
    image,
    desc_console,
    desc_licence,
    base_game_id,
    consola_id,
    licencia_id,
    duracion_dias_alquiler,
    cuotas_activas,
    num_cuotas,
    valor_cuota,
    cuota_inicial,
    reserva_activa,
    monto_reserva,
) -> ShoppingCarRead:
    modo_pago = getattr(item, "modo_pago", None) or "contado"
    precio_contado = _effective_price(precio, precio_descuento)
    return ShoppingCarRead(
        id_shopping_car=item.id_shopping_car,
        user_id=item.user_id,
        product_id=item.product_id,
        estado=item.estado,
        product_price=precio_contado,
        title=title,
        image=image,
        desc_console=desc_console,
        desc_licence=desc_licence,
        base_game_id=base_game_id,
        consola=consola_id,
        licencia=licencia_id,
        duracion_dias_alquiler=duracion_dias_alquiler,
        modo_pago=modo_pago,
        pago_hoy=_pago_hoy(modo_pago, precio_contado, cuota_inicial, valor_cuota, monto_reserva),
        cuotas_activas=bool(cuotas_activas),
        num_cuotas=num_cuotas if num_cuotas is not None else 3,
        valor_cuota=valor_cuota if valor_cuota is not None else 0,
        cuota_inicial=cuota_inicial,
        reserva_activa=bool(reserva_activa),
        monto_reserva=monto_reserva if monto_reserva is not None else 20000,
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
        _build_shopping_car_read(
            item, precio, precio_descuento, title, image, desc_console, desc_licence,
            base_game_id, consola_id, licencia_id, duracion_dias_alquiler,
            cuotas_activas, num_cuotas, valor_cuota, cuota_inicial, reserva_activa, monto_reserva,
        )
        for item, precio, precio_descuento, title, image, desc_console, desc_licence,
        base_game_id, consola_id, licencia_id, duracion_dias_alquiler,
        cuotas_activas, num_cuotas, valor_cuota, cuota_inicial, reserva_activa, monto_reserva in rows
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

    (
        item, precio, precio_descuento, title, image, desc_console, desc_licence,
        base_game_id, consola_id, licencia_id, duracion_dias_alquiler,
        cuotas_activas, num_cuotas, valor_cuota, cuota_inicial, reserva_activa, monto_reserva,
    ) = row
    if item.user_id != current_user.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Item not found")

    return _build_shopping_car_read(
        item, precio, precio_descuento, title, image, desc_console, desc_licence,
        base_game_id, consola_id, licencia_id, duracion_dias_alquiler,
        cuotas_activas, num_cuotas, valor_cuota, cuota_inicial, reserva_activa, monto_reserva,
    )


@router.post("/", response_model=ShoppingCarRead, status_code=status.HTTP_201_CREATED)
async def create_shopping_car_item(
    payload: ShoppingCarCreate,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    modo_pago = (payload.modo_pago or "contado").strip().lower()
    if modo_pago not in MODOS_PAGO_VALIDOS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"modo_pago invalido. Debe ser uno de: {', '.join(MODOS_PAGO_VALIDOS)}.",
        )

    gd_result = await session.execute(
        select(GameDetail).where(GameDetail.id_game_detail == payload.product_id)
    )
    game_detail = gd_result.scalars().first()
    if game_detail is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Producto no encontrado.")

    if modo_pago == "cuotas" and not game_detail.cuotas_activas:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Esta variante no tiene cuotas activas.",
        )
    if modo_pago == "reserva" and not game_detail.reserva_activa:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Esta variante no tiene reserva activa.",
        )

    # Reject duplicate: same GameDetail already in this user's cart (con
    # cualquier modo de pago -- "una misma variante no puede estar dos veces
    # con modos distintos", docs/cuotas-y-reserva.md §1).
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
        modo_pago=modo_pago,
    )
    session.add(item)
    await session.commit()
    await session.refresh(item)

    result = await session.execute(
        _shopping_car_display_query().where(ShoppingCar.id_shopping_car == item.id_shopping_car)
    )
    (
        _, precio, precio_descuento, title, image, desc_console, desc_licence,
        base_game_id, consola_id, licencia_id, duracion_dias_alquiler,
        cuotas_activas, num_cuotas, valor_cuota, cuota_inicial, reserva_activa, monto_reserva,
    ) = result.first()

    return _build_shopping_car_read(
        item, precio, precio_descuento, title, image, desc_console, desc_licence,
        base_game_id, consola_id, licencia_id, duracion_dias_alquiler,
        cuotas_activas, num_cuotas, valor_cuota, cuota_inicial, reserva_activa, monto_reserva,
    )


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
    (
        _, precio, precio_descuento, title, image, desc_console, desc_licence,
        base_game_id, consola_id, licencia_id, duracion_dias_alquiler,
        cuotas_activas, num_cuotas, valor_cuota, cuota_inicial, reserva_activa, monto_reserva,
    ) = result.first()

    return _build_shopping_car_read(
        item, precio, precio_descuento, title, image, desc_console, desc_licence,
        base_game_id, consola_id, licencia_id, duracion_dias_alquiler,
        cuotas_activas, num_cuotas, valor_cuota, cuota_inicial, reserva_activa, monto_reserva,
    )


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
