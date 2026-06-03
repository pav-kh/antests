from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.schemas import LoginRequest, RegisterRequest
from app.core.security import hash_password, verify_password
from app.db.models import User


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
