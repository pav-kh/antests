import uuid

import pytest
from sqlalchemy import select

from app.assessment.competency import update_competency, load_competency
from app.db.models import TopicCompetency, User


async def _user(db):
    u = User(login=f"u{uuid.uuid4().hex[:8]}", password_hash="x")
    db.add(u)
    await db.commit()
    await db.refresh(u)
    return u


@pytest.mark.asyncio
async def test_update_creates_rows_and_computes_accuracy(db_session):
    u = await _user(db_session)
    await update_competency(
        db_session, u.id, level="base",
        per_topic={"data": (4, 2), "modeling": (2, 2)},
    )
    rows = (await db_session.execute(
        select(TopicCompetency).where(TopicCompetency.user_id == u.id))).scalars().all()
    by_topic = {r.topic_id: r for r in rows}
    assert float(by_topic["data"].accuracy) == 0.5
    assert by_topic["data"].total_answered == 4
    assert float(by_topic["modeling"].accuracy) == 1.0


@pytest.mark.asyncio
async def test_update_accumulates_across_tests(db_session):
    u = await _user(db_session)
    await update_competency(db_session, u.id, "base", {"data": (4, 2)})
    await update_competency(db_session, u.id, "base", {"data": (6, 6)})
    row = (await db_session.execute(
        select(TopicCompetency).where(
            TopicCompetency.user_id == u.id, TopicCompetency.topic_id == "data"
        ))).scalar_one()
    assert row.total_answered == 10
    assert row.total_correct == 8
    assert float(row.accuracy) == 0.8


@pytest.mark.asyncio
async def test_levels_are_separate(db_session):
    u = await _user(db_session)
    await update_competency(db_session, u.id, "base", {"data": (2, 2)})
    await update_competency(db_session, u.id, "specialist", {"data": (2, 0)})
    base = await load_competency(db_session, u.id, "base")
    spec = await load_competency(db_session, u.id, "specialist")
    assert base["data"] == 1.0
    assert spec["data"] == 0.0


@pytest.mark.asyncio
async def test_load_empty_returns_empty_dict(db_session):
    u = await _user(db_session)
    assert await load_competency(db_session, u.id, "base") == {}
