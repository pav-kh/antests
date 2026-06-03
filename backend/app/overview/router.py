from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.base import get_session
from app.db.models import TestSession, TopicCompetency, User
from app.deps import current_user

router = APIRouter(tags=["overview"])


@router.get("/me/overview")
async def overview(
    user: User = Depends(current_user),
    db: AsyncSession = Depends(get_session),
):
    sessions = (
        await db.execute(
            select(TestSession)
            .where(TestSession.user_id == user.id)
            .order_by(TestSession.created_at.desc())
        )
    ).scalars().all()
    competency = (
        await db.execute(
            select(TopicCompetency).where(TopicCompetency.user_id == user.id)
        )
    ).scalars().all()
    return {
        "sessions": [
            {
                "id": str(s.id), "level": s.level, "mode": s.mode, "status": s.status,
                "score_percent": float(s.score_percent) if s.score_percent is not None else None,
                "passed": s.passed,
                "created_at": s.created_at.isoformat(),
            }
            for s in sessions
        ],
        "competency": [
            {"topic_id": c.topic_id, "level": c.level, "accuracy": float(c.accuracy)}
            for c in competency
        ],
    }
