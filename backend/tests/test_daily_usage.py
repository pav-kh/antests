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
