# Subsystem 1: Foundation + Auth — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Stand up the FastAPI backend skeleton, PostgreSQL schema (via SQLAlchemy + Alembic), and a working auth subsystem — registration (login + password + access code), login (session cookie), and a daily rate-limit primitive — all under test.

**Architecture:** FastAPI app with a layered structure: `db` (engine/session/models), `core` (config, security, password hashing), `auth` (router + service), and `main` (app wiring). Auth uses signed session cookies backed by a `users` table. Registration is gated by a shared access code from config. A `daily_usage` table + helper enforces a per-user daily session-start limit (the limit itself is consumed by Subsystem 2, but the table and the check function live here). Tests use pytest against a disposable Postgres database.

**Tech Stack:** Python 3.12, FastAPI, Uvicorn, SQLAlchemy 2.x (async), asyncpg, Alembic, Pydantic v2 + pydantic-settings, argon2-cffi (password hashing), itsdangerous (signed cookies), pytest + pytest-asyncio + httpx (async test client).

---

## File Structure

```
backend/
  pyproject.toml              # deps + tool config (pytest, ruff)
  alembic.ini                 # alembic config
  .env.example                # documented env vars
  app/
    __init__.py
    main.py                   # FastAPI app factory + router wiring
    core/
      __init__.py
      config.py               # Settings (pydantic-settings): DB url, access code, limits, secret
      security.py             # password hash/verify, session cookie sign/read
    db/
      __init__.py
      base.py                 # DeclarativeBase + async engine + session factory + get_session dep
      models.py               # SQLAlchemy models: User, DailyUsage (others added in later subsystems)
    auth/
      __init__.py
      schemas.py              # Pydantic request/response models
      service.py              # register_user, authenticate_user, daily-usage helpers (pure logic)
      router.py               # POST /auth/register, POST /auth/login, POST /auth/logout, GET /auth/me
    deps.py                   # current_user dependency (reads session cookie)
  alembic/
    env.py                    # async-aware alembic env
    script.py.mako
    versions/                 # migration files
  tests/
    __init__.py
    conftest.py               # db fixture (create/drop schema), app client fixture
    test_security.py          # hashing + cookie unit tests
    test_auth_register.py     # registration endpoint tests
    test_auth_login.py        # login/logout/me endpoint tests
    test_daily_usage.py       # rate-limit helper tests
```

Each file has one responsibility. `service.py` holds pure logic (testable without HTTP); `router.py` is thin HTTP glue. Models for later subsystems (`TestSession`, `Question`, `Answer`, `TopicCompetency`) are intentionally NOT created here — they belong to Subsystems 2 and 3.

---

## Prerequisites

This plan assumes a local PostgreSQL is reachable. Tasks use two databases:
- `antests` — dev database
- `antests_test` — test database (created in Task 1)

If Postgres runs via Docker, the engineer can start one with:
`docker run -d --name antests-pg -e POSTGRES_PASSWORD=postgres -p 5432:5432 postgres:16`

---

### Task 1: Project scaffold + dependencies

**Files:**
- Create: `backend/pyproject.toml`
- Create: `backend/.env.example`
- Create: `backend/app/__init__.py` (empty)
- Create: `backend/tests/__init__.py` (empty)

- [ ] **Step 1: Create `backend/pyproject.toml`**

```toml
[project]
name = "antests-backend"
version = "0.1.0"
description = "IBS certification trainer backend"
requires-python = ">=3.12"
dependencies = [
    "fastapi>=0.115",
    "uvicorn[standard]>=0.32",
    "sqlalchemy[asyncio]>=2.0.36",
    "asyncpg>=0.30",
    "alembic>=1.14",
    "pydantic>=2.10",
    "pydantic-settings>=2.6",
    "argon2-cffi>=23.1",
    "itsdangerous>=2.2",
]

[project.optional-dependencies]
dev = [
    "pytest>=8.3",
    "pytest-asyncio>=0.24",
    "httpx>=0.28",
    "ruff>=0.8",
]

[tool.pytest.ini_options]
asyncio_mode = "auto"
testpaths = ["tests"]

[tool.ruff]
line-length = 100
target-version = "py312"

[build-system]
requires = ["setuptools>=68"]
build-backend = "setuptools.build_meta"

[tool.setuptools.packages.find]
where = ["."]
include = ["app*"]
```

- [ ] **Step 2: Create `backend/.env.example`**

```bash
# Database (async driver)
DATABASE_URL=postgresql+asyncpg://postgres:postgres@localhost:5432/antests
TEST_DATABASE_URL=postgresql+asyncpg://postgres:postgres@localhost:5432/antests_test

# Secret for signing session cookies (generate a long random string in prod)
SESSION_SECRET=dev-only-change-me-to-a-long-random-string

# Shared registration access code (told to your ~15 users)
ACCESS_CODE=CHANGE_ME

# Daily limit: max test sessions a user may START per day
DAILY_SESSION_LIMIT=10
```

- [ ] **Step 3: Create empty `backend/app/__init__.py` and `backend/tests/__init__.py`**

Both files are empty.

- [ ] **Step 4: Create virtualenv and install**

Run:
```bash
cd backend && python3.12 -m venv .venv && . .venv/bin/activate && pip install -e ".[dev]"
```
Expected: installs without error; `pip show fastapi` prints a version.

- [ ] **Step 5: Commit**

```bash
git add backend/pyproject.toml backend/.env.example backend/app/__init__.py backend/tests/__init__.py
git commit -m "chore: scaffold backend project and dependencies"
```

---

### Task 2: Settings (config)

**Files:**
- Create: `backend/app/core/__init__.py` (empty)
- Create: `backend/app/core/config.py`
- Test: `backend/tests/test_config.py`

- [ ] **Step 1: Write the failing test** — `backend/tests/test_config.py`

```python
import os
from app.core.config import Settings


def test_settings_reads_env(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "postgresql+asyncpg://u:p@h:5432/d")
    monkeypatch.setenv("SESSION_SECRET", "secret")
    monkeypatch.setenv("ACCESS_CODE", "LET-ME-IN")
    monkeypatch.setenv("DAILY_SESSION_LIMIT", "7")
    s = Settings()
    assert s.database_url == "postgresql+asyncpg://u:p@h:5432/d"
    assert s.access_code == "LET-ME-IN"
    assert s.daily_session_limit == 7


def test_daily_limit_has_default(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "postgresql+asyncpg://u:p@h:5432/d")
    monkeypatch.setenv("SESSION_SECRET", "secret")
    monkeypatch.setenv("ACCESS_CODE", "X")
    monkeypatch.delenv("DAILY_SESSION_LIMIT", raising=False)
    s = Settings()
    assert s.daily_session_limit == 10
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && . .venv/bin/activate && pytest tests/test_config.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.core.config'`

- [ ] **Step 3: Create empty `backend/app/core/__init__.py`, then write `backend/app/core/config.py`**

```python
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str
    test_database_url: str = ""
    session_secret: str
    access_code: str
    daily_session_limit: int = 10


def get_settings() -> Settings:
    return Settings()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_config.py -v`
Expected: PASS (2 passed)

- [ ] **Step 5: Commit**

```bash
git add backend/app/core/__init__.py backend/app/core/config.py backend/tests/test_config.py
git commit -m "feat: add settings config from environment"
```

---

### Task 3: Security — password hashing + session cookies

**Files:**
- Create: `backend/app/core/security.py`
- Test: `backend/tests/test_security.py`

- [ ] **Step 1: Write the failing test** — `backend/tests/test_security.py`

```python
import pytest
from app.core.security import (
    hash_password,
    verify_password,
    sign_session,
    read_session,
)

SECRET = "test-secret"


def test_hash_and_verify_roundtrip():
    h = hash_password("hunter2")
    assert h != "hunter2"
    assert verify_password("hunter2", h) is True
    assert verify_password("wrong", h) is False


def test_session_sign_and_read_roundtrip():
    token = sign_session("user-id-123", SECRET)
    assert read_session(token, SECRET) == "user-id-123"


def test_read_session_rejects_tampered_token():
    token = sign_session("user-id-123", SECRET)
    tampered = token[:-1] + ("A" if token[-1] != "A" else "B")
    assert read_session(tampered, SECRET) is None


def test_read_session_rejects_wrong_secret():
    token = sign_session("user-id-123", SECRET)
    assert read_session(token, "other-secret") is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_security.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.core.security'`

- [ ] **Step 3: Write `backend/app/core/security.py`**

```python
from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError, VerificationError
from itsdangerous import URLSafeSerializer, BadSignature

_ph = PasswordHasher()
_SALT = "session"


def hash_password(plain: str) -> str:
    return _ph.hash(plain)


def verify_password(plain: str, hashed: str) -> bool:
    try:
        return _ph.verify(hashed, plain)
    except (VerifyMismatchError, VerificationError):
        return False


def sign_session(user_id: str, secret: str) -> str:
    return URLSafeSerializer(secret, salt=_SALT).dumps(user_id)


def read_session(token: str, secret: str) -> str | None:
    try:
        return URLSafeSerializer(secret, salt=_SALT).loads(token)
    except BadSignature:
        return None
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_security.py -v`
Expected: PASS (4 passed)

- [ ] **Step 5: Commit**

```bash
git add backend/app/core/security.py backend/tests/test_security.py
git commit -m "feat: add password hashing and signed session cookies"
```

---

### Task 4: Database base (engine, session, declarative base)

**Files:**
- Create: `backend/app/db/__init__.py` (empty)
- Create: `backend/app/db/base.py`

(No dedicated test file — this is exercised by every later DB test via the conftest fixture in Task 6.)

- [ ] **Step 1: Create empty `backend/app/db/__init__.py`, then write `backend/app/db/base.py`**

```python
from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase

from app.core.config import get_settings


class Base(DeclarativeBase):
    pass


_settings = get_settings()
engine = create_async_engine(_settings.database_url, future=True)
SessionLocal = async_sessionmaker(engine, expire_on_commit=False)


async def get_session() -> AsyncGenerator[AsyncSession, None]:
    async with SessionLocal() as session:
        yield session
```

- [ ] **Step 2: Sanity import check**

Run: `pytest --collect-only -q 2>&1 | head -5` (collection imports the package)
Expected: no import error referencing `app.db.base`. (Collection may show existing tests; that's fine.)

- [ ] **Step 3: Commit**

```bash
git add backend/app/db/__init__.py backend/app/db/base.py
git commit -m "feat: add async db engine, session factory, declarative base"
```

---

### Task 5: Models — User and DailyUsage

**Files:**
- Create: `backend/app/db/models.py`

- [ ] **Step 1: Write `backend/app/db/models.py`**

```python
import uuid
from datetime import date, datetime

from sqlalchemy import Date, DateTime, ForeignKey, Integer, String, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class User(Base):
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    login: Mapped[str] = mapped_column(String, unique=True, nullable=False, index=True)
    password_hash: Mapped[str] = mapped_column(String, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class DailyUsage(Base):
    __tablename__ = "daily_usage"
    __table_args__ = (UniqueConstraint("user_id", "date", name="uq_daily_usage_user_date"),)

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), primary_key=True
    )
    date: Mapped[date] = mapped_column(Date, primary_key=True)
    sessions_started: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
```

- [ ] **Step 2: Sanity import check**

Run: `python -c "from app.db.models import User, DailyUsage; print('ok')"`
Expected: prints `ok`

- [ ] **Step 3: Commit**

```bash
git add backend/app/db/models.py
git commit -m "feat: add User and DailyUsage models"
```

---

### Task 6: Test harness — conftest with disposable test DB

**Files:**
- Create: `backend/tests/conftest.py`

This fixture creates all tables in `antests_test` before each test and drops them after, and provides an `AsyncSession` and an `httpx` client wired to the app with the test DB.

- [ ] **Step 1: Write `backend/tests/conftest.py`**

```python
import os

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

# Ensure required env exists before app modules import settings.
os.environ.setdefault("SESSION_SECRET", "test-secret")
os.environ.setdefault("ACCESS_CODE", "TEST-CODE")
os.environ.setdefault("DAILY_SESSION_LIMIT", "3")

TEST_DB_URL = os.environ.get(
    "TEST_DATABASE_URL",
    "postgresql+asyncpg://postgres:postgres@localhost:5432/antests_test",
)
# Point the app at the test DB for the whole test run.
os.environ["DATABASE_URL"] = TEST_DB_URL

from app.db.base import Base  # noqa: E402  (import after env is set)
from app.db import models  # noqa: E402,F401  (registers tables on Base.metadata)

_engine = create_async_engine(TEST_DB_URL, future=True)
_Session = async_sessionmaker(_engine, expire_on_commit=False)


@pytest_asyncio.fixture()
async def db_session():
    async with _engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    async with _Session() as session:
        yield session
    async with _engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)


@pytest_asyncio.fixture()
async def client(db_session):
    from app.db.base import get_session
    from app.main import create_app

    app = create_app()

    async def _override_get_session():
        yield db_session

    app.dependency_overrides[get_session] = _override_get_session
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c
    app.dependency_overrides.clear()
```

- [ ] **Step 2: Create the test database**

Run:
```bash
createdb antests_test 2>/dev/null || psql -h localhost -U postgres -c "CREATE DATABASE antests_test;" 2>/dev/null || echo "ensure antests_test exists"
```
Expected: database exists (command succeeds or already-exists message).

- [ ] **Step 3: Commit**

```bash
git add backend/tests/conftest.py
git commit -m "test: add conftest with disposable test database and client fixtures"
```

---

### Task 7: Auth schemas + service (pure logic) — registration

**Files:**
- Create: `backend/app/auth/__init__.py` (empty)
- Create: `backend/app/auth/schemas.py`
- Create: `backend/app/auth/service.py`
- Test: `backend/tests/test_auth_register.py` (service-level tests in this task)

- [ ] **Step 1: Write the failing test** — `backend/tests/test_auth_register.py`

```python
import pytest
from app.auth import service
from app.auth.schemas import RegisterRequest
from app.db.models import User
from sqlalchemy import select


@pytest.mark.asyncio
async def test_register_creates_user_with_correct_code(db_session):
    req = RegisterRequest(login="alice", password="pw12345", access_code="TEST-CODE")
    user = await service.register_user(db_session, req, expected_code="TEST-CODE")
    assert user.login == "alice"
    rows = (await db_session.execute(select(User))).scalars().all()
    assert len(rows) == 1
    assert rows[0].password_hash != "pw12345"


@pytest.mark.asyncio
async def test_register_rejects_wrong_access_code(db_session):
    req = RegisterRequest(login="bob", password="pw12345", access_code="WRONG")
    with pytest.raises(service.InvalidAccessCode):
        await service.register_user(db_session, req, expected_code="TEST-CODE")


@pytest.mark.asyncio
async def test_register_rejects_duplicate_login(db_session):
    req = RegisterRequest(login="carol", password="pw12345", access_code="TEST-CODE")
    await service.register_user(db_session, req, expected_code="TEST-CODE")
    with pytest.raises(service.LoginTaken):
        await service.register_user(db_session, req, expected_code="TEST-CODE")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_auth_register.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.auth'`

- [ ] **Step 3: Create empty `backend/app/auth/__init__.py`, then write `backend/app/auth/schemas.py`**

```python
from pydantic import BaseModel, Field


class RegisterRequest(BaseModel):
    login: str = Field(min_length=3, max_length=50)
    password: str = Field(min_length=6, max_length=128)
    access_code: str


class LoginRequest(BaseModel):
    login: str
    password: str


class UserOut(BaseModel):
    id: str
    login: str
```

- [ ] **Step 4: Write `backend/app/auth/service.py`**

```python
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
```

- [ ] **Step 5: Run test to verify it passes**

Run: `pytest tests/test_auth_register.py -v`
Expected: PASS (3 passed)

- [ ] **Step 6: Commit**

```bash
git add backend/app/auth/__init__.py backend/app/auth/schemas.py backend/app/auth/service.py backend/tests/test_auth_register.py
git commit -m "feat: add auth schemas and registration service logic"
```

---

### Task 8: Daily-usage helper (rate-limit primitive)

**Files:**
- Modify: `backend/app/auth/service.py` (append helpers)
- Test: `backend/tests/test_daily_usage.py`

- [ ] **Step 1: Write the failing test** — `backend/tests/test_daily_usage.py`

```python
import datetime as dt

import pytest
from app.auth import service
from app.auth.schemas import RegisterRequest


async def _make_user(db_session):
    req = RegisterRequest(login="dave", password="pw12345", access_code="TEST-CODE")
    return await service.register_user(db_session, req, expected_code="TEST-CODE")


@pytest.mark.asyncio
async def test_usage_starts_at_zero(db_session):
    user = await _make_user(db_session)
    today = dt.date(2026, 6, 3)
    assert await service.get_usage_count(db_session, user.id, today) == 0


@pytest.mark.asyncio
async def test_increment_usage_accumulates(db_session):
    user = await _make_user(db_session)
    today = dt.date(2026, 6, 3)
    await service.increment_usage(db_session, user.id, today)
    await service.increment_usage(db_session, user.id, today)
    assert await service.get_usage_count(db_session, user.id, today) == 2


@pytest.mark.asyncio
async def test_limit_check(db_session):
    user = await _make_user(db_session)
    today = dt.date(2026, 6, 3)
    assert await service.is_within_daily_limit(db_session, user.id, today, limit=2) is True
    await service.increment_usage(db_session, user.id, today)
    await service.increment_usage(db_session, user.id, today)
    assert await service.is_within_daily_limit(db_session, user.id, today, limit=2) is False
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_daily_usage.py -v`
Expected: FAIL with `AttributeError: module 'app.auth.service' has no attribute 'get_usage_count'`

- [ ] **Step 3: Append helpers to `backend/app/auth/service.py`**

Add these imports at the top (merge with existing imports):

```python
import datetime as dt
import uuid

from app.db.models import DailyUsage
```

Append these functions to the end of the file:

```python
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
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_daily_usage.py -v`
Expected: PASS (3 passed)

- [ ] **Step 5: Commit**

```bash
git add backend/app/auth/service.py backend/tests/test_daily_usage.py
git commit -m "feat: add daily usage rate-limit helpers"
```

---

### Task 9: current_user dependency

**Files:**
- Create: `backend/app/deps.py`

(Tested indirectly via `GET /auth/me` in Task 11. No standalone test — it's a thin FastAPI dependency that needs the request/cookie context.)

- [ ] **Step 1: Write `backend/app/deps.py`**

```python
import uuid

from fastapi import Cookie, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.security import read_session
from app.db.base import get_session
from app.db.models import User

SESSION_COOKIE = "session"


async def current_user(
    session: str | None = Cookie(default=None),
    db: AsyncSession = Depends(get_session),
) -> User:
    settings = get_settings()
    if session is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Not authenticated")
    user_id = read_session(session, settings.session_secret)
    if user_id is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid session")
    user = await db.get(User, uuid.UUID(user_id))
    if user is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "User not found")
    return user
```

- [ ] **Step 2: Sanity import check**

Run: `python -c "from app.deps import current_user, SESSION_COOKIE; print('ok')"`
Expected: prints `ok`

- [ ] **Step 3: Commit**

```bash
git add backend/app/deps.py
git commit -m "feat: add current_user cookie dependency"
```

---

### Task 10: Auth router + app factory

**Files:**
- Create: `backend/app/auth/router.py`
- Create: `backend/app/main.py`

- [ ] **Step 1: Write `backend/app/auth/router.py`**

```python
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
    response.delete_cookie(SESSION_COOKIE)


@router.get("/me", response_model=UserOut)
async def me(user: User = Depends(current_user)):
    return UserOut(id=str(user.id), login=user.login)
```

- [ ] **Step 2: Write `backend/app/main.py`**

```python
from fastapi import FastAPI

from app.auth.router import router as auth_router


def create_app() -> FastAPI:
    app = FastAPI(title="IBS Certification Trainer")
    app.include_router(auth_router)

    @app.get("/health")
    async def health():
        return {"status": "ok"}

    return app


app = create_app()
```

- [ ] **Step 3: Sanity import check**

Run: `python -c "from app.main import create_app; create_app(); print('ok')"`
Expected: prints `ok`

- [ ] **Step 4: Commit**

```bash
git add backend/app/auth/router.py backend/app/main.py
git commit -m "feat: add auth router and FastAPI app factory"
```

---

### Task 11: Auth endpoint integration tests

**Files:**
- Create: `backend/tests/test_auth_login.py`
- Modify: `backend/tests/test_auth_register.py` (add endpoint-level tests)

- [ ] **Step 1: Append endpoint tests to `backend/tests/test_auth_register.py`**

```python
@pytest.mark.asyncio
async def test_register_endpoint_success(client):
    resp = await client.post(
        "/auth/register",
        json={"login": "erin", "password": "pw12345", "access_code": "TEST-CODE"},
    )
    assert resp.status_code == 201
    assert resp.json()["login"] == "erin"
    assert "session" in resp.cookies


@pytest.mark.asyncio
async def test_register_endpoint_wrong_code(client):
    resp = await client.post(
        "/auth/register",
        json={"login": "frank", "password": "pw12345", "access_code": "NOPE"},
    )
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_register_endpoint_duplicate(client):
    body = {"login": "grace", "password": "pw12345", "access_code": "TEST-CODE"}
    await client.post("/auth/register", json=body)
    resp = await client.post("/auth/register", json=body)
    assert resp.status_code == 409
```

- [ ] **Step 2: Write `backend/tests/test_auth_login.py`**

```python
import pytest


async def _register(client, login="heidi"):
    return await client.post(
        "/auth/register",
        json={"login": login, "password": "pw12345", "access_code": "TEST-CODE"},
    )


@pytest.mark.asyncio
async def test_login_success_and_me(client):
    await _register(client, "ivan")
    # logout first to clear the registration cookie
    await client.post("/auth/logout")
    resp = await client.post("/auth/login", json={"login": "ivan", "password": "pw12345"})
    assert resp.status_code == 200
    me = await client.get("/auth/me")
    assert me.status_code == 200
    assert me.json()["login"] == "ivan"


@pytest.mark.asyncio
async def test_login_wrong_password(client):
    await _register(client, "judy")
    await client.post("/auth/logout")
    resp = await client.post("/auth/login", json={"login": "judy", "password": "WRONG"})
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_me_requires_auth(client):
    await client.post("/auth/logout")
    resp = await client.get("/auth/me")
    assert resp.status_code == 401
```

- [ ] **Step 3: Run the full auth suite**

Run: `pytest tests/test_auth_register.py tests/test_auth_login.py -v`
Expected: PASS (all register + login tests green)

- [ ] **Step 4: Commit**

```bash
git add backend/tests/test_auth_register.py backend/tests/test_auth_login.py
git commit -m "test: add auth endpoint integration tests"
```

---

### Task 12: Alembic migrations

**Files:**
- Create: `backend/alembic.ini`
- Create: `backend/alembic/env.py`
- Create: `backend/alembic/script.py.mako`
- Create: `backend/alembic/versions/` (directory; first migration generated)

- [ ] **Step 1: Initialize alembic scaffolding**

Run: `cd backend && . .venv/bin/activate && alembic init -t async alembic`
Expected: creates `alembic.ini`, `alembic/env.py`, `alembic/script.py.mako`, `alembic/versions/`.

- [ ] **Step 2: Edit `backend/alembic/env.py` to use app metadata and settings**

Replace the `target_metadata = None` line and the URL handling. Ensure these elements exist in the file:

```python
import os
from logging.config import fileConfig

from alembic import context
from sqlalchemy import pool
from sqlalchemy.ext.asyncio import async_engine_from_config

from app.core.config import get_settings
from app.db.base import Base
from app.db import models  # noqa: F401  (register tables)

config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

config.set_main_option("sqlalchemy.url", get_settings().database_url)
target_metadata = Base.metadata
```

Keep the rest of the async `run_migrations_online` / `do_run_migrations` machinery that `alembic init -t async` generated.

- [ ] **Step 3: Generate the initial migration**

Run: `alembic revision --autogenerate -m "users and daily_usage"`
Expected: creates a file under `alembic/versions/` containing `create_table("users")` and `create_table("daily_usage")`.

- [ ] **Step 4: Apply the migration to the dev database**

Run: `createdb antests 2>/dev/null; alembic upgrade head`
Expected: `Running upgrade -> <hash>, users and daily_usage` with no error.

- [ ] **Step 5: Verify tables exist**

Run: `psql -h localhost -U postgres -d antests -c "\dt"`
Expected: lists `users`, `daily_usage`, `alembic_version`.

- [ ] **Step 6: Commit**

```bash
git add backend/alembic.ini backend/alembic/
git commit -m "feat: add alembic migrations for users and daily_usage"
```

---

### Task 13: Run the server end-to-end (smoke check)

**Files:** none (manual verification)

- [ ] **Step 1: Start the server**

Run: `cd backend && . .venv/bin/activate && uvicorn app.main:app --reload --port 8000`
Expected: `Uvicorn running on http://127.0.0.1:8000`

- [ ] **Step 2: Smoke-test health + register + me in a second shell**

Run:
```bash
curl -s localhost:8000/health
curl -s -c /tmp/cj.txt -X POST localhost:8000/auth/register \
  -H 'Content-Type: application/json' \
  -d '{"login":"smoke","password":"pw12345","access_code":"'"$ACCESS_CODE"'"}'
curl -s -b /tmp/cj.txt localhost:8000/auth/me
```
Expected: health returns `{"status":"ok"}`; register returns a user JSON with `id` and `login`; `/auth/me` returns the same user. (Set `ACCESS_CODE` in env to match `.env`.)

- [ ] **Step 3: Stop the server** (Ctrl-C). No commit.

---

### Task 14: Final verification of Subsystem 1

**Files:** none

- [ ] **Step 1: Run the entire test suite**

Run: `cd backend && . .venv/bin/activate && pytest -v`
Expected: ALL tests pass (config, security, register, login, daily_usage). Report the exact count.

- [ ] **Step 2: Lint**

Run: `ruff check app tests`
Expected: no errors (fix any reported).

- [ ] **Step 3: Confirm the success criteria** (do not claim done until all are true):
  - `pytest` is fully green.
  - `alembic upgrade head` applied cleanly to `antests`.
  - Manual smoke test (Task 13) returned the expected responses.

---

## Self-Review Notes

Checked against spec sections 3 (stack: FastAPI/Postgres/SQLAlchemy/Alembic ✓), 5 (`users`, `daily_usage` models match column-for-column ✓; other tables intentionally deferred to later subsystems), and product decision 10 (access code at registration ✓, daily rate-limit primitive ✓). Config exposes access code + daily limit + secret per spec section 10. No placeholders — every code/test step contains complete content. Type consistency verified: `register_user`, `authenticate_user`, `get_usage_count`, `increment_usage`, `is_within_daily_limit`, `current_user`, `SESSION_COOKIE`, `sign_session`/`read_session` names are identical across all tasks that reference them. The rate-limit is enforced (consumed) in Subsystem 2 at session-start; here it is built and unit-tested in isolation.
```
