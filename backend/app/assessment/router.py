import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.assessment import service
from app.assessment.schemas import SubmitAnswerRequest
from app.core.config import get_settings
from app.db.base import get_session
from app.db.models import TestSession, User
from app.deps import current_user
from app.generation.router import build_openai_client

router = APIRouter(tags=["assessment"])


async def _owned_session(db, session_id, user) -> TestSession:
    s = await db.get(TestSession, session_id)
    if s is None or s.user_id != user.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Session not found")
    return s


@router.post("/sessions/{session_id}/answers")
async def submit_answer(
    session_id: uuid.UUID,
    req: SubmitAnswerRequest,
    user: User = Depends(current_user),
    db: AsyncSession = Depends(get_session),
):
    await _owned_session(db, session_id, user)
    try:
        answer = await service.submit_answer(
            db, session_id, uuid.UUID(req.question_id),
            selected_keys=req.selected_keys, answer_text=req.answer_text,
        )
    except service.SessionNotFinishable:
        raise HTTPException(status.HTTP_409_CONFLICT, "Session is not in a finishable state")
    except ValueError:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Invalid question")
    return {"question_id": str(answer.question_id), "recorded": True}


@router.get("/sessions/{session_id}/answers")
async def list_answers(
    session_id: uuid.UUID,
    user: User = Depends(current_user),
    db: AsyncSession = Depends(get_session),
):
    await _owned_session(db, session_id, user)
    return await service.list_answers(db, session_id)


@router.post("/sessions/{session_id}/finish")
async def finish(
    session_id: uuid.UUID,
    user: User = Depends(current_user),
    db: AsyncSession = Depends(get_session),
):
    await _owned_session(db, session_id, user)
    settings = get_settings()
    # Building the OpenAI client can fail (e.g. missing OPENAI_API_KEY raises at
    # construction). That must not block finishing the test — scoring and the
    # competency update don't need the LLM. Pass None so finish_session skips the
    # recommendation (its build_recommendation call is already failure-tolerant).
    try:
        openai_client = build_openai_client()
    except Exception:
        openai_client = None
    try:
        session = await service.finish_session(
            db, session_id, openai_client,
            weak_threshold=settings.weak_topic_threshold,
        )
    except service.SessionNotFinishable:
        raise HTTPException(status.HTTP_409_CONFLICT, "Session is not in a finishable state")
    return {"id": str(session.id), "score_percent": float(session.score_percent),
            "passed": session.passed, "status": session.status}


@router.get("/sessions/{session_id}/results")
async def results(
    session_id: uuid.UUID,
    user: User = Depends(current_user),
    db: AsyncSession = Depends(get_session),
):
    await _owned_session(db, session_id, user)
    return await service.get_results(db, session_id)
