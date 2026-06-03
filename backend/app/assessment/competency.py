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
    competency profile for a level, recomputing accuracy. Atomic upsert per topic."""
    from sqlalchemy.dialects.postgresql import insert as pg_insert
    now = dt.datetime.now(dt.timezone.utc)
    for topic_id, (answered, correct) in per_topic.items():
        new_answered = TopicCompetency.total_answered + answered
        # Use float division (* 1.0) so Postgres does not integer-truncate the
        # accuracy on integer columns (e.g. 8/10 must be 0.8, not 0).
        new_accuracy = (
            (TopicCompetency.total_correct + correct)
            * 1.0
            / (TopicCompetency.total_answered + answered)
        )
        stmt = (
            pg_insert(TopicCompetency)
            .values(
                user_id=user_id, topic_id=topic_id, level=level,
                total_answered=answered, total_correct=correct,
                accuracy=(correct / answered if answered > 0 else 0),
                updated_at=now,
            )
            .on_conflict_do_update(
                index_elements=[
                    TopicCompetency.user_id,
                    TopicCompetency.topic_id,
                    TopicCompetency.level,
                ],
                set_={
                    "total_answered": new_answered,
                    "total_correct": TopicCompetency.total_correct + correct,
                    "accuracy": new_accuracy,
                    "updated_at": now,
                },
            )
        )
        await session.execute(stmt)
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
