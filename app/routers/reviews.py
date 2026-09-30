"""Reseñas de producto: calificación (1-5) y comentario corto sobre el JUEGO.

- Lectura pública: promedio, cantidad y los comentarios que se pueden mostrar.
- Escritura: solo quien tiene una venta entregada de ese producto
  (products_saledetail, la misma tabla que alimenta /purchases en el front).
- Los comentarios que hablan del servicio de la tienda no se muestran (ver
  app/services/reviews.py); la calificación cuenta igual.
"""
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_session
from app.models import Product, ProductReview, SaleDetail, User
from app.services.reviews import MAX_COMMENT_LENGTH, classify_comment, clean_comment, display_name
from app.util.util_auth import get_current_user

router = APIRouter(prefix="/reviews", tags=["reviews"])


class ReviewIn(BaseModel):
    rating: int = Field(..., ge=1, le=5, description="Estrellas de 1 a 5")
    comment: str | None = Field(None, max_length=MAX_COMMENT_LENGTH * 2)


def _mine_payload(review: ProductReview) -> dict:
    return {
        "product_id": review.product_id,
        "rating": review.rating,
        "comment": review.comment,
        "comment_hidden": review.comment_hidden,
        # Para decirle al comprador por qué su comentario no aparece.
        "hidden_reason": review.hidden_reason,
        "updated_at": review.updated_at,
    }


@router.get("/mine")
async def my_reviews(
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    """Reseñas del usuario logueado (para precargar el formulario en /purchases)."""
    result = await session.execute(select(ProductReview).where(ProductReview.user_id == current_user.id))
    return {"data": [_mine_payload(r) for r in result.scalars().all()]}


@router.get("/product/{product_id}")
async def product_reviews(
    product_id: int,
    limit: int = Query(10, ge=1, le=50),
    session: AsyncSession = Depends(get_session),
):
    """Promedio, cantidad y comentarios visibles de un producto.

    `count` y `average` cuentan toda reseña no oculta (con o sin comentario
    visible). `reviews` trae solo las que tienen un comentario publicable.
    """
    agg = await session.execute(
        select(func.count(ProductReview.id), func.avg(ProductReview.rating)).where(
            ProductReview.product_id == product_id,
            ProductReview.is_hidden.is_(False),
        )
    )
    count, average = agg.one()
    count = int(count or 0)

    rows = await session.execute(
        select(ProductReview)
        .where(
            ProductReview.product_id == product_id,
            ProductReview.is_hidden.is_(False),
            ProductReview.comment_hidden.is_(False),
            ProductReview.comment.is_not(None),
        )
        .order_by(ProductReview.created_at.desc())
        .limit(limit)
    )
    reviews = [
        {
            "id": r.id,
            "rating": r.rating,
            "comment": r.comment,
            "author": display_name(r.user.first_name if r.user else None),
            "created_at": r.created_at,
        }
        for r in rows.scalars().all()
    ]
    return {
        "product_id": product_id,
        "count": count,
        "average": round(float(average), 1) if count else None,
        "reviews": reviews,
    }


@router.put("/product/{product_id}")
async def upsert_review(
    product_id: int,
    body: ReviewIn,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    """Crea o edita la reseña del usuario logueado para este producto."""
    product = await session.get(Product, product_id)
    if product is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Producto no encontrado")

    bought = await session.execute(
        select(SaleDetail.id_sale_detail)
        .where(SaleDetail.usuario_id == current_user.id, SaleDetail.producto_id == product_id)
        .limit(1)
    )
    if bought.first() is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Solo pueden calificar quienes compraron este producto.",
        )

    comment = clean_comment(body.comment)
    if comment and len(comment) > MAX_COMMENT_LENGTH:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"El comentario admite hasta {MAX_COMMENT_LENGTH} caracteres.",
        )
    hidden, reason = classify_comment(comment)

    existing = await session.execute(
        select(ProductReview).where(
            ProductReview.product_id == product_id,
            ProductReview.user_id == current_user.id,
        )
    )
    review = existing.scalars().first()
    now = datetime.utcnow()
    if review is None:
        review = ProductReview(product_id=product_id, user_id=current_user.id, created_at=now)
        session.add(review)
    previous_comment, previous_reason = review.comment, review.hidden_reason
    review.rating = body.rating
    review.comment = comment
    # Un ocultamiento manual ('manual') se respeta mientras el comentario no
    # cambie; si el comprador lo reescribe, se vuelve a evaluar desde cero.
    keeps_manual_hide = previous_reason == "manual" and previous_comment == comment
    if not keeps_manual_hide:
        review.comment_hidden = hidden
        review.hidden_reason = reason
    review.updated_at = now
    await session.commit()
    await session.refresh(review)
    return _mine_payload(review)
