import asyncio
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


@pytest.mark.asyncio
async def test_increment_usage_first_of_day_does_not_raise(db_session):
    # First increment of the day (no existing row) must not raise IntegrityError.
    user = await _make_user(db_session)
    today = dt.date(2026, 6, 3)
    await service.increment_usage(db_session, user.id, today)
    assert await service.get_usage_count(db_session, user.id, today) == 1


@pytest.mark.asyncio
async def test_increment_usage_concurrent_does_not_undercount(db_session):
    # Concurrent same-user/same-day increments from independent connections
    # must each count exactly once and must not 500 on the racing first insert.
    from tests.conftest import _Session

    user = await _make_user(db_session)
    await db_session.commit()  # make the user visible to other connections
    today = dt.date(2026, 6, 3)

    async def one_increment():
        async with _Session() as s:
            await service.increment_usage(s, user.id, today)

    await asyncio.gather(*(one_increment() for _ in range(10)))

    assert await service.get_usage_count(db_session, user.id, today) == 10
