import datetime as dt

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import service as auth_service
from app.db.models import Question, TestSession
from app.generation.planner import LEVEL_TOTALS, plan_adaptive, plan_exam

LEVEL_TIME_LIMITS = {"base": 120 * 60, "specialist": 180 * 60}


class DailyLimitExceeded(Exception):
    pass


async def _load_competency(db: AsyncSession, user_id, level) -> dict[str, float]:
    try:
        from app.db.models import TopicCompetency  # type: ignore
    except ImportError:
        return {}
    rows = (
        await db.execute(
            select(TopicCompetency).where(
                TopicCompetency.user_id == user_id,
                TopicCompetency.level == level,
            )
        )
    ).scalars().all()
    return {r.topic_id: float(r.accuracy) for r in rows}


async def create_session(
    db: AsyncSession, user_id, level: str, mode: str,
    daily_limit: int, adaptive_count: int, weak_threshold: float,
) -> tuple[TestSession, list]:
    today = dt.date.today()
    if not await auth_service.is_within_daily_limit(db, user_id, today, daily_limit):
        raise DailyLimitExceeded()

    if mode == "exam":
        plan = plan_exam(level)
        total = LEVEL_TOTALS[level]
    else:
        competency = await _load_competency(db, user_id, level)
        plan = plan_adaptive(competency, total=adaptive_count, threshold=weak_threshold)
        total = adaptive_count

    session = TestSession(
        user_id=user_id, level=level, mode=mode, status="generating",
        total_questions=total, generated_count=0,
        time_limit_sec=LEVEL_TIME_LIMITS[level],
    )
    db.add(session)
    await db.commit()
    await db.refresh(session)
    await auth_service.increment_usage(db, user_id, today)
    return session, plan


async def get_status(db: AsyncSession, session_id) -> TestSession | None:
    return await db.get(TestSession, session_id)


async def list_ready_questions(db: AsyncSession, session_id) -> list[Question]:
    rows = (
        await db.execute(
            select(Question)
            .where(Question.session_id == session_id)
            .order_by(Question.seq)
        )
    ).scalars().all()
    return rows
