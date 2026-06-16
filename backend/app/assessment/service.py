import datetime as dt

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.assessment.competency import load_competency, update_competency
from app.assessment.recommendation import build_recommendation
from app.assessment.scoring import is_answer_correct, is_closed, score
from app.db.models import Answer, Question, TestSession


class SessionNotFinishable(Exception):
    """Raised when finishing or answering a session whose status doesn't allow it."""


LEVEL_THRESHOLDS = {"base": 70.0, "specialist": 75.0}


async def _get_question(db: AsyncSession, session_id, question_id) -> Question | None:
    return (
        await db.execute(
            select(Question).where(
                Question.id == question_id, Question.session_id == session_id
            )
        )
    ).scalar_one_or_none()


async def submit_answer(
    db: AsyncSession, session_id, question_id,
    selected_keys: list[str] | None = None,
    answer_text: str | None = None,
) -> Answer:
    q = await _get_question(db, session_id, question_id)
    if q is None:
        raise ValueError("question not in session")
    session = await db.get(TestSession, session_id)
    if session is None:
        raise ValueError("session not found")
    if session.status == "finished":
        raise SessionNotFinishable("cannot submit answers to a finished session")
    if session.status == "ready":
        session.status = "in_progress"

    if q.type == "open":
        sel: list[str] = []
        correct = None
        text = answer_text or ""
    else:
        sel = selected_keys or []
        correct = is_answer_correct(sel, q.correct_keys)
        text = None

    existing = (
        await db.execute(
            select(Answer).where(
                Answer.session_id == session_id, Answer.question_id == question_id
            )
        )
    ).scalar_one_or_none()
    if existing is None:
        existing = Answer(
            session_id=session_id, question_id=question_id,
            selected_keys=sel, is_correct=correct, answer_text=text,
        )
        db.add(existing)
    else:
        existing.selected_keys = sel
        existing.is_correct = correct
        existing.answer_text = text
    await db.commit()
    await db.refresh(existing)
    return existing


async def list_answers(db: AsyncSession, session_id) -> list[dict]:
    rows = (
        await db.execute(
            select(Answer).where(Answer.session_id == session_id)
        )
    ).scalars().all()
    return [
        {"question_id": str(a.question_id),
         "selected_keys": a.selected_keys,
         "answer_text": a.answer_text or ""}
        for a in rows
    ]


async def finish_session(
    db: AsyncSession, session_id, openai_client, weak_threshold: float
) -> TestSession:
    session = await db.get(TestSession, session_id)
    if session is None:
        raise ValueError("session not found")

    if session.status == "finished":
        # Idempotent: already finished, return as-is without re-tallying
        # (re-tallying would double-count the competency profile).
        return session
    if session.status not in ("ready", "in_progress"):
        # Cannot finish a session that is still generating or has failed.
        raise SessionNotFinishable(f"session status '{session.status}' is not finishable")

    questions = (
        await db.execute(
            select(Question).where(Question.session_id == session_id)
        )
    ).scalars().all()
    answers = (
        await db.execute(
            select(Answer).where(Answer.session_id == session_id)
        )
    ).scalars().all()
    answer_by_q = {a.question_id: a for a in answers}

    import asyncio
    from app.assessment.open_eval import evaluate_open

    closed = [q for q in questions if is_closed(q.type)]
    open_qs = [q for q in questions if q.type == "open"]

    per_topic: dict[str, list[int]] = {}
    correct_count = 0
    for q in closed:
        a = answer_by_q.get(q.id)
        cor = 1 if (a is not None and a.is_correct) else 0
        correct_count += cor
        bucket = per_topic.setdefault(q.topic_id, [0, 0])
        bucket[0] += 1
        bucket[1] += cor

    total = len(closed)  # pass/fail counts CLOSED questions only
    result = score(correct_count, total, LEVEL_THRESHOLDS[session.level])

    await update_competency(
        db, session.user_id, session.level,
        {tid: (a, c) for tid, (a, c) in per_topic.items()},
    )
    topic_accuracy = await load_competency(db, session.user_id, session.level)

    async def _safe_reco():
        try:
            return await build_recommendation(
                openai_client, session.level, topic_accuracy, weak_threshold)
        except Exception:
            return ""

    async def _judge(q):
        a = answer_by_q.get(q.id)
        return q.id, await evaluate_open(
            openai_client, q.stem, q.rubric or "", (a.answer_text if a else "") or "")

    reco_task = _safe_reco()
    judge_tasks = [_judge(q) for q in open_qs]
    reco, *judged = await asyncio.gather(reco_task, *judge_tasks)
    recommendation = reco

    for qid, feedback in judged:
        a = answer_by_q.get(qid)
        if a is not None:
            a.feedback = feedback

    session.score_percent = result.percent
    session.passed = result.passed
    session.recommendation = recommendation
    session.status = "finished"
    session.finished_at = dt.datetime.now(dt.timezone.utc)
    await db.commit()
    await db.refresh(session)
    return session


async def get_results(db: AsyncSession, session_id) -> dict:
    session = await db.get(TestSession, session_id)
    if session is None:
        raise ValueError("session not found")
    questions = (
        await db.execute(
            select(Question).where(Question.session_id == session_id).order_by(Question.seq)
        )
    ).scalars().all()
    answers = (
        await db.execute(
            select(Answer).where(Answer.session_id == session_id)
        )
    ).scalars().all()
    answer_by_q = {a.question_id: a for a in answers}

    closed = [q for q in questions if q.type in ("single", "multi")]
    open_qs = [q for q in questions if q.type == "open"]

    per_topic: dict[str, list[int]] = {}
    for q in closed:
        a = answer_by_q.get(q.id)
        bucket = per_topic.setdefault(q.topic_id, [0, 0])
        bucket[0] += 1
        if a is not None and a.is_correct:
            bucket[1] += 1

    topic_breakdown = [
        {
            "topic_id": tid, "answered": ans, "correct": cor,
            "accuracy": round(cor / ans, 2) if ans else 0.0,
        }
        for tid, (ans, cor) in per_topic.items()
    ]

    question_reviews = []
    for q in closed:
        a = answer_by_q.get(q.id)
        question_reviews.append({
            "id": str(q.id), "seq": q.seq, "topic_id": q.topic_id, "type": q.type,
            "stem": q.stem, "artifact_kind": q.artifact_kind,
            "artifact_content": q.artifact_content, "options": q.options,
            "correct_keys": q.correct_keys,
            "selected_keys": a.selected_keys if a else [],
            "is_correct": a.is_correct if a else False,
            "explanation": q.explanation,
        })

    open_reviews = []
    for q in open_qs:
        a = answer_by_q.get(q.id)
        open_reviews.append({
            "id": str(q.id), "seq": q.seq, "stem": q.stem,
            "answer_text": (a.answer_text if a else "") or "",
            "feedback": (a.feedback if a else "") or "",
            "explanation": q.explanation,
        })

    answered_closed = sum(
        1 for q in closed if (answer_by_q.get(q.id) and answer_by_q[q.id].selected_keys)
    )

    return {
        "session_id": str(session.id), "level": session.level, "mode": session.mode,
        "score_percent": float(session.score_percent) if session.score_percent is not None else 0.0,
        "passed": bool(session.passed),
        "total_questions": len(closed),
        "answered_count": answered_closed,
        "topic_breakdown": topic_breakdown,
        "recommendation": session.recommendation or "",
        "questions": question_reviews,
        "open_questions": open_reviews,
    }
