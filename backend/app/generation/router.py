import asyncio
import logging
import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.db.base import SessionLocal, get_session
from app.db.models import User
from app.deps import current_user
from app.generation import service
from app.generation.generator import Generator
from app.generation.openai_client import OpenAIClient

router = APIRouter(tags=["sessions"])

logger = logging.getLogger(__name__)

# Strong references to in-flight background generation tasks. Without this the
# event loop keeps only a weak ref and the task may be GC'd mid-flight.
_background_tasks: set[asyncio.Task] = set()


class CreateSessionRequest(BaseModel):
    level: str
    mode: str


def build_openai_client():
    s = get_settings()
    return OpenAIClient(
        api_key=s.openai_api_key,
        gen_model=s.openai_gen_model,
        validate_model=s.openai_validate_model,
    )


async def _mark_session_failed(session_id) -> None:
    from app.db.models import TestSession
    try:
        async with SessionLocal() as db:
            session = await db.get(TestSession, session_id)
            if session is not None and session.status not in ("ready", "finished"):
                session.status = "failed"
                await db.commit()
    except Exception:
        logger.exception("Failed to mark session %s as failed", session_id)


async def _run_generation(session_id, plan):
    try:
        settings = get_settings()
        client = build_openai_client()
        async with SessionLocal() as db:
            gen = Generator(
                db, client, batch_size=settings.generation_batch_size
            )
            await gen.run(session_id, plan)
    except Exception:
        logger.exception("Background generation failed for session %s", session_id)
        await _mark_session_failed(session_id)


@router.post("/sessions", status_code=status.HTTP_201_CREATED)
async def create_session(
    req: CreateSessionRequest,
    user: User = Depends(current_user),
    db: AsyncSession = Depends(get_session),
):
    if req.level not in ("base", "specialist") or req.mode not in ("exam", "adaptive"):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Invalid level or mode")
    settings = get_settings()
    try:
        session, plan = await service.create_session(
            db, user.id, req.level, req.mode,
            daily_limit=settings.daily_session_limit,
            adaptive_count=settings.adaptive_question_count,
            weak_threshold=settings.weak_topic_threshold,
        )
    except service.DailyLimitExceeded:
        raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS, "Daily session limit reached")

    task = asyncio.create_task(_run_generation(session.id, plan))
    _background_tasks.add(task)
    task.add_done_callback(_background_tasks.discard)
    return {"id": str(session.id), "status": session.status,
            "total_questions": session.total_questions}


@router.get("/sessions/{session_id}/status")
async def session_status(
    session_id: uuid.UUID,
    user: User = Depends(current_user),
    db: AsyncSession = Depends(get_session),
):
    s = await service.get_status(db, session_id)
    if s is None or s.user_id != user.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Session not found")
    return {
        "id": str(s.id), "status": s.status, "level": s.level, "mode": s.mode,
        "total_questions": s.total_questions, "generated_count": s.generated_count,
        "time_limit_sec": s.time_limit_sec,
        "timer_started_at": s.timer_started_at.isoformat() if s.timer_started_at else None,
    }


@router.get("/sessions/{session_id}/questions")
async def session_questions(
    session_id: uuid.UUID,
    user: User = Depends(current_user),
    db: AsyncSession = Depends(get_session),
):
    s = await service.get_status(db, session_id)
    if s is None or s.user_id != user.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Session not found")
    questions = await service.list_ready_questions(db, session_id)
    return [
        {
            "id": str(q.id), "seq": q.seq, "topic_id": q.topic_id, "type": q.type,
            "stem": q.stem, "artifact_kind": q.artifact_kind,
            "artifact_content": q.artifact_content, "options": q.options,
        }
        for q in questions
    ]
