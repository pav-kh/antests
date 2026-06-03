import uuid

import pytest

from app.assessment import service
from app.db.models import Answer, Question, TestSession, User


class FakeRecoClient:
    async def recommend(self, level, weak_topics):
        return "Совет: повторите слабые темы."


async def _seed_session(db, level="base", threshold_total=4):
    user = User(login=f"u{uuid.uuid4().hex[:8]}", password_hash="x")
    db.add(user)
    await db.commit()
    await db.refresh(user)
    s = TestSession(
        user_id=user.id, level=level, mode="exam", status="ready",
        total_questions=threshold_total, generated_count=threshold_total,
        time_limit_sec=7200,
    )
    db.add(s)
    await db.commit()
    await db.refresh(s)
    qs = []
    for i, (topic, correct) in enumerate(
        [("data", ["a"]), ("data", ["a"]), ("modeling", ["a"]), ("modeling", ["a"])],
        start=1,
    ):
        q = Question(
            session_id=s.id, seq=i, topic_id=topic, type="single", stem="Q?",
            artifact_kind="none", artifact_content=None,
            options=[{"key": "a", "text": "x"}, {"key": "b", "text": "y"}],
            correct_keys=correct, explanation="because", validation_status="passed",
        )
        db.add(q)
        qs.append(q)
    await db.commit()
    for q in qs:
        await db.refresh(q)
    return user, s, qs


@pytest.mark.asyncio
async def test_submit_answer_persists_and_scores(db_session):
    user, s, qs = await _seed_session(db_session)
    await service.submit_answer(db_session, s.id, qs[0].id, ["a"])
    await service.submit_answer(db_session, s.id, qs[1].id, ["b"])
    from sqlalchemy import select
    rows = (await db_session.execute(
        select(Answer).where(Answer.session_id == s.id))).scalars().all()
    by_q = {r.question_id: r for r in rows}
    assert by_q[qs[0].id].is_correct is True
    assert by_q[qs[1].id].is_correct is False


@pytest.mark.asyncio
async def test_resubmit_overwrites_answer(db_session):
    user, s, qs = await _seed_session(db_session)
    await service.submit_answer(db_session, s.id, qs[0].id, ["b"])
    await service.submit_answer(db_session, s.id, qs[0].id, ["a"])
    from sqlalchemy import select
    rows = (await db_session.execute(
        select(Answer).where(
            Answer.session_id == s.id, Answer.question_id == qs[0].id
        ))).scalars().all()
    assert len(rows) == 1
    assert rows[0].is_correct is True


@pytest.mark.asyncio
async def test_finish_scores_session_and_updates_competency(db_session):
    user, s, qs = await _seed_session(db_session)
    await service.submit_answer(db_session, s.id, qs[0].id, ["a"])
    await service.submit_answer(db_session, s.id, qs[1].id, ["a"])
    await service.submit_answer(db_session, s.id, qs[2].id, ["a"])
    await service.submit_answer(db_session, s.id, qs[3].id, ["b"])
    await service.finish_session(db_session, s.id, FakeRecoClient(), weak_threshold=0.6)
    await db_session.refresh(s)
    assert s.status == "finished"
    assert float(s.score_percent) == 75.0
    assert s.passed is True


@pytest.mark.asyncio
async def test_double_finish_does_not_double_count_competency(db_session):
    from sqlalchemy import select

    from app.assessment.competency import load_competency
    from app.db.models import TopicCompetency

    async def raw_tallies():
        rows = (
            await db_session.execute(
                select(TopicCompetency).where(TopicCompetency.user_id == user.id)
            )
        ).scalars().all()
        for r in rows:
            await db_session.refresh(r)
        return {r.topic_id: (r.total_answered, r.total_correct) for r in rows}

    user, s, qs = await _seed_session(db_session)
    for q in qs:
        await service.submit_answer(db_session, s.id, q.id, ["a"])
    await service.finish_session(db_session, s.id, FakeRecoClient(), weak_threshold=0.6)
    prof1 = await load_competency(db_session, user.id, "base")
    tallies1 = await raw_tallies()
    # second finish must be a no-op for competency (idempotent)
    await service.finish_session(db_session, s.id, FakeRecoClient(), weak_threshold=0.6)
    prof2 = await load_competency(db_session, user.id, "base")
    tallies2 = await raw_tallies()
    assert prof1 == prof2
    # Raw tallies must not double; accuracy alone can hide an all-correct double-count.
    assert tallies1 == tallies2


@pytest.mark.asyncio
async def test_finish_rejects_generating_session(db_session):
    user, s, qs = await _seed_session(db_session)
    s.status = "generating"
    await db_session.commit()
    with pytest.raises(service.SessionNotFinishable):
        await service.finish_session(db_session, s.id, FakeRecoClient(), weak_threshold=0.6)


@pytest.mark.asyncio
async def test_submit_after_finish_rejected(db_session):
    user, s, qs = await _seed_session(db_session)
    await service.submit_answer(db_session, s.id, qs[0].id, ["a"])
    await service.finish_session(db_session, s.id, FakeRecoClient(), weak_threshold=0.6)
    with pytest.raises(service.SessionNotFinishable):
        await service.submit_answer(db_session, s.id, qs[1].id, ["a"])


@pytest.mark.asyncio
async def test_finish_succeeds_even_if_recommendation_fails(db_session):
    user, s, qs = await _seed_session(db_session)
    await service.submit_answer(db_session, s.id, qs[0].id, ["a"])  # data correct
    await service.submit_answer(db_session, s.id, qs[1].id, ["a"])  # data correct
    await service.submit_answer(db_session, s.id, qs[2].id, ["b"])  # modeling wrong
    await service.submit_answer(db_session, s.id, qs[3].id, ["b"])  # modeling wrong

    class BoomReco:
        async def recommend(self, level, weak_topics):
            raise RuntimeError("openai down")

    finished = await service.finish_session(db_session, s.id, BoomReco(), weak_threshold=0.6)
    assert finished.status == "finished"
    assert finished.recommendation == ""
