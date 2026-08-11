from datetime import datetime, timedelta, timezone

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.models import User, UserCustomized, Coupon
from app.util.util_auth import get_password_hash

WELCOME_COUPON_AMOUNT = 3000
WELCOME_COUPON_VALIDITY_MINUTES = 60

async def get_user_by_username(session: AsyncSession, username: str):
    result = await session.execute(select(User).filter(User.username == username))
    return result.scalars().first()

async def get_user_by_email(session: AsyncSession, email: str):
    result = await session.execute(select(User).filter(User.email == email))
    return result.scalars().first()

async def create_user(
    session: AsyncSession,
    username: str,
    email: str,
    password: str,
    phone_number: str = "",
    avatar: str = "",
):
    """Create base auth user plus associated UserCustomized profile."""

    hashed_password = get_password_hash(password)
    db_user = User(username=username, email=email, password=hashed_password)
    session.add(db_user)

    # flush to assign primary key without committing yet
    await session.flush()

    profile = UserCustomized(
        user_id=db_user.id,
        phone_number=phone_number or "",
        avatar=avatar or "",
        puntos=0,
    )
    session.add(profile)

    expiration = datetime.now(timezone.utc) + timedelta(minutes=WELCOME_COUPON_VALIDITY_MINUTES)
    welcome_coupon = Coupon(
        name_coupon=f"WELCOME-{db_user.id}-{int(datetime.now(timezone.utc).timestamp())}",
        expiration_date=expiration,
        is_valid=True,
        user_id=db_user.id,
        discount_type="FIXED_AMOUNT",
        fixed_amount=WELCOME_COUPON_AMOUNT,
        source="WELCOME",
    )
    session.add(welcome_coupon)

    await session.commit()
    await session.refresh(db_user)
    return db_user


async def update_user_password(session: AsyncSession, user: User, new_password: str) -> User:
    hashed_password = get_password_hash(new_password)
    user.password = hashed_password
    session.add(user)
    await session.commit()
    await session.refresh(user)
    return user
