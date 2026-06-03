import datetime as dt
import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.schemas import LoginRequest, RegisterRequest
from app.core.security import hash_password, verify_password
from app.db.models import DailyUsage, User


class InvalidAccessCode(Exception):
    pass


class LoginTaken(Exception):
    pass


class InvalidCredentials(Exception):
    pass


async def register_user(
    session: AsyncSession, req: RegisterRequest, expected_code: str
) -> User:
    if req.access_code != expected_code:
        raise InvalidAccessCode()
    existing = (
        await session.execute(select(User).where(User.login == req.login))
    ).scalar_one_or_none()
    if existing is not None:
        raise LoginTaken()
    user = User(login=req.login, password_hash=hash_password(req.password))
    session.add(user)
    await session.commit()
    await session.refresh(user)
    return user


async def authenticate_user(session: AsyncSession, req: LoginRequest) -> User:
    user = (
        await session.execute(select(User).where(User.login == req.login))
    ).scalar_one_or_none()
    if user is None or not verify_password(req.password, user.password_hash):
        raise InvalidCredentials()
    return user


async def get_usage_count(
    session: AsyncSession, user_id: uuid.UUID, day: dt.date
) -> int:
    row = (
        await session.execute(
            select(DailyUsage).where(
                DailyUsage.user_id == user_id, DailyUsage.date == day
            )
        )
    ).scalar_one_or_none()
    return row.sessions_started if row else 0


async def increment_usage(
    session: AsyncSession, user_id: uuid.UUID, day: dt.date
) -> None:
    row = (
        await session.execute(
            select(DailyUsage).where(
                DailyUsage.user_id == user_id, DailyUsage.date == day
            )
        )
    ).scalar_one_or_none()
    if row is None:
        row = DailyUsage(user_id=user_id, date=day, sessions_started=1)
        session.add(row)
    else:
        row.sessions_started += 1
    await session.commit()


async def is_within_daily_limit(
    session: AsyncSession, user_id: uuid.UUID, day: dt.date, limit: int
) -> bool:
    return await get_usage_count(session, user_id, day) < limit
