import datetime as dt
import uuid

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.exc import IntegrityError
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


# Precomputed argon2 hash used to keep the missing-user login path roughly as
# expensive as the wrong-password path, so request timing does not leak whether
# a given login exists. Computed once at import time.
_DUMMY_PASSWORD_HASH = hash_password("dummy-password-for-constant-time-login")


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
    try:
        await session.commit()
    except IntegrityError:
        # A concurrent identical registration won the race after our pre-check;
        # the unique-login constraint rejected this insert. Roll back and map
        # to the same LoginTaken -> 409 path instead of surfacing a 500.
        await session.rollback()
        raise LoginTaken()
    await session.refresh(user)
    return user


async def authenticate_user(session: AsyncSession, req: LoginRequest) -> User:
    user = (
        await session.execute(select(User).where(User.login == req.login))
    ).scalar_one_or_none()
    # Always run an argon2 verification, even when the user is absent, so both
    # branches take similar time and request timing does not reveal whether a
    # login exists. The dummy hash never matches, so a missing user still fails.
    password_hash = user.password_hash if user is not None else _DUMMY_PASSWORD_HASH
    password_ok = verify_password(req.password, password_hash)
    if user is None or not password_ok:
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
    # Atomic upsert: a concurrent first-of-day insert from another connection
    # hits ON CONFLICT and increments instead of raising IntegrityError, so
    # there is no undercount and no racing 500.
    stmt = (
        pg_insert(DailyUsage)
        .values(user_id=user_id, date=day, sessions_started=1)
        .on_conflict_do_update(
            index_elements=[DailyUsage.user_id, DailyUsage.date],
            set_={"sessions_started": DailyUsage.sessions_started + 1},
        )
    )
    await session.execute(stmt)
    await session.commit()


async def decrement_usage(
    session: AsyncSession, user_id: uuid.UUID, day: dt.date
) -> None:
    row = (
        await session.execute(
            select(DailyUsage).where(
                DailyUsage.user_id == user_id, DailyUsage.date == day
            )
        )
    ).scalar_one_or_none()
    if row is not None and row.sessions_started > 0:
        row.sessions_started -= 1
        await session.commit()


async def is_within_daily_limit(
    session: AsyncSession, user_id: uuid.UUID, day: dt.date, limit: int
) -> bool:
    return await get_usage_count(session, user_id, day) < limit
