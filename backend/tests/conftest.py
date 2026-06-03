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
