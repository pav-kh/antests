import datetime as dt

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.assessment.competency import load_competency, update_competency
from app.assessment.recommendation import build_recommendation
from app.assessment.scoring import is_answer_correct, score
from app.db.models import Answer, Question, TestSession

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
    db: AsyncSession, session_id, question_id, selected_keys: list[str]
) -> Answer:
    q = await _get_question(db, session_id, question_id)
    if q is None:
        raise ValueError("question not in session")
    correct = is_answer_correct(selected_keys, q.correct_keys)
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
            selected_keys=selected_keys, is_correct=correct,
        )
        db.add(existing)
    else:
        existing.selected_keys = selected_keys
        existing.is_correct = correct
    await db.commit()
    await db.refresh(existing)
    return existing


async def finish_session(
    db: AsyncSession, session_id, openai_client, weak_threshold: float
) -> TestSession:
    session = await db.get(TestSession, session_id)
    if session is None:
        raise ValueError("session not found")

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

    per_topic: dict[str, list[int]] = {}
    correct_count = 0
    for q in questions:
        a = answer_by_q.get(q.id)
        cor = 1 if (a is not None and a.is_correct) else 0
        correct_count += cor
        bucket = per_topic.setdefault(q.topic_id, [0, 0])
        bucket[0] += 1
        bucket[1] += cor

    total = len(questions)
    result = score(correct_count, total, LEVEL_THRESHOLDS[session.level])

    await update_competency(
        db, session.user_id, session.level,
        {tid: (a, c) for tid, (a, c) in per_topic.items()},
    )

    topic_accuracy = await load_competency(db, session.user_id, session.level)
    recommendation = await build_recommendation(
        openai_client, session.level, topic_accuracy, weak_threshold
    )

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

    per_topic: dict[str, list[int]] = {}
    for q in questions:
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
    for q in questions:
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

    return {
        "session_id": str(session.id), "level": session.level, "mode": session.mode,
        "score_percent": float(session.score_percent) if session.score_percent is not None else 0.0,
        "passed": bool(session.passed),
        "total_questions": session.total_questions,
        "answered_count": len(answers),
        "topic_breakdown": topic_breakdown,
        "recommendation": session.recommendation or "",
        "questions": question_reviews,
    }
