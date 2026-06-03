import uuid

import pytest

from app.assessment.competency import update_competency
from app.db.models import User
from app.generation import service as gen_service


async def _user(db):
    u = User(login=f"u{uuid.uuid4().hex[:8]}", password_hash="x")
    db.add(u)
    await db.commit()
    await db.refresh(u)
    return u


@pytest.mark.asyncio
async def test_adaptive_plan_targets_weak_topics_from_profile(db_session):
    u = await _user(db_session)
    await update_competency(db_session, u.id, "base", {"data": (10, 2)})
    await update_competency(db_session, u.id, "base", {"modeling": (10, 9)})
    session, plan = await gen_service.create_session(
        db_session, u.id, "base", "adaptive",
        daily_limit=99, adaptive_count=10, weak_threshold=0.6,
    )
    plan_d = dict(plan)
    assert "data" in plan_d
    assert "modeling" not in plan_d
    assert sum(plan_d.values()) == 10
