import datetime as dt
import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import TopicCompetency


async def update_competency(
    session: AsyncSession,
    user_id: uuid.UUID,
    level: str,
    per_topic: dict[str, tuple[int, int]],
) -> None:
    """Accumulate per-topic (answered, correct) tallies into the user's
    competency profile for a level, recomputing accuracy. Upsert per topic."""
    now = dt.datetime.now(dt.timezone.utc)
    for topic_id, (answered, correct) in per_topic.items():
        row = (
            await session.execute(
                select(TopicCompetency).where(
                    TopicCompetency.user_id == user_id,
                    TopicCompetency.topic_id == topic_id,
                    TopicCompetency.level == level,
                )
            )
        ).scalar_one_or_none()
        if row is None:
            row = TopicCompetency(
                user_id=user_id, topic_id=topic_id, level=level,
                total_answered=0, total_correct=0, accuracy=0,
            )
            session.add(row)
        row.total_answered += answered
        row.total_correct += correct
        row.accuracy = (
            row.total_correct / row.total_answered if row.total_answered > 0 else 0
        )
        row.updated_at = now
    await session.commit()


async def load_competency(
    session: AsyncSession, user_id: uuid.UUID, level: str
) -> dict[str, float]:
    rows = (
        await session.execute(
            select(TopicCompetency).where(
                TopicCompetency.user_id == user_id,
                TopicCompetency.level == level,
            )
        )
    ).scalars().all()
    return {r.topic_id: float(r.accuracy) for r in rows}
