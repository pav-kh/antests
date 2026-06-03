from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import service
from app.auth.schemas import LoginRequest, RegisterRequest, UserOut
from app.core.config import get_settings
from app.core.security import sign_session
from app.db.base import get_session
from app.deps import SESSION_COOKIE, current_user
from app.db.models import User

router = APIRouter(prefix="/auth", tags=["auth"])


def _set_session_cookie(response: Response, user_id: str) -> None:
    settings = get_settings()
    token = sign_session(user_id, settings.session_secret)
    response.set_cookie(
        SESSION_COOKIE,
        token,
        httponly=True,
        samesite="lax",
        secure=settings.cookie_secure,
        max_age=60 * 60 * 24 * 14,
    )


@router.post("/register", response_model=UserOut, status_code=status.HTTP_201_CREATED)
async def register(
    req: RegisterRequest, response: Response, db: AsyncSession = Depends(get_session)
):
    settings = get_settings()
    try:
        user = await service.register_user(db, req, expected_code=settings.access_code)
    except service.InvalidAccessCode:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Invalid access code")
    except service.LoginTaken:
        raise HTTPException(status.HTTP_409_CONFLICT, "Login already taken")
    _set_session_cookie(response, str(user.id))
    return UserOut(id=str(user.id), login=user.login)


@router.post("/login", response_model=UserOut)
async def login(
    req: LoginRequest, response: Response, db: AsyncSession = Depends(get_session)
):
    try:
        user = await service.authenticate_user(db, req)
    except service.InvalidCredentials:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid login or password")
    _set_session_cookie(response, str(user.id))
    return UserOut(id=str(user.id), login=user.login)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(response: Response):
    settings = get_settings()
    response.delete_cookie(
        SESSION_COOKIE,
        path="/",
        samesite="lax",
        httponly=True,
        secure=settings.cookie_secure,
    )


@router.get("/me", response_model=UserOut)
async def me(user: User = Depends(current_user)):
    return UserOut(id=str(user.id), login=user.login)
