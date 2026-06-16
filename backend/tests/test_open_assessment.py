import uuid
import pytest
from sqlalchemy import select
from app.assessment import service
from app.db.models import Answer, Question, TestSession, User


class FakeJudgeClient:
    async def recommend(self, level, weak_topics):
        return "rec"
    async def judge_open(self, stem, rubric, answer):
        return f"JUDGED:{answer}"


async def _seed(db, with_open=True):
    user = User(login=f"u{uuid.uuid4().hex[:8]}", password_hash="x")
    db.add(user)
    await db.commit()
    await db.refresh(user)
    s = TestSession(user_id=user.id, level="base", mode="exam", status="ready",
                    total_questions=2, generated_count=2, time_limit_sec=7200)
    db.add(s)
    await db.commit()
    await db.refresh(s)
    qs = []
    for i in range(2):
        q = Question(session_id=s.id, seq=i + 1, topic_id="data", type="single",
                     stem="Q?", artifact_kind="none", artifact_content=None,
                     options=[{"key": "a", "text": "x"}, {"key": "b", "text": "y"}],
                     correct_keys=["a"], explanation="b", validation_status="passed")
        db.add(q)
        qs.append(q)
    if with_open:
        oq = Question(session_id=s.id, seq=3, topic_id="open", type="open",
                      stem="Опишите решения.", artifact_kind="none", artifact_content=None,
                      options=[], correct_keys=[], explanation="разбор",
                      rubric="вопросы+решения", validation_status="passed")
        db.add(oq)
        qs.append(oq)
    await db.commit()
    for q in qs:
        await db.refresh(q)
    return user, s, qs


@pytest.mark.asyncio
async def test_submit_open_answer_stores_text(db_session):
    user, s, qs = await _seed(db_session)
    openq = qs[2]
    await service.submit_answer(db_session, s.id, openq.id, selected_keys=None,
                                answer_text="Мой развёрнутый ответ про статус и эскалацию.")
    a = (await db_session.execute(
        select(Answer).where(Answer.question_id == openq.id))).scalar_one()
    assert a.answer_text.startswith("Мой развёрнутый")
    assert a.is_correct is None


@pytest.mark.asyncio
async def test_score_counts_closed_only_and_judges_open(db_session):
    user, s, qs = await _seed(db_session)
    await service.submit_answer(db_session, s.id, qs[0].id, selected_keys=["a"])
    await service.submit_answer(db_session, s.id, qs[1].id, selected_keys=["a"])
    await service.submit_answer(db_session, s.id, qs[2].id, selected_keys=None,
                                answer_text="Достаточно длинный ответ для судьи про эскалацию.")
    await service.finish_session(db_session, s.id, FakeJudgeClient(), weak_threshold=0.6)
    await db_session.refresh(s)
    assert float(s.score_percent) == 100.0
    assert s.passed is True
    a = (await db_session.execute(
        select(Answer).where(Answer.question_id == qs[2].id))).scalar_one()
    assert a.feedback.startswith("JUDGED:")


@pytest.mark.asyncio
async def test_results_has_open_section(db_session):
    user, s, qs = await _seed(db_session)
    await service.submit_answer(db_session, s.id, qs[0].id, selected_keys=["a"])
    await service.submit_answer(db_session, s.id, qs[2].id, selected_keys=None,
                                answer_text="Длинный ответ про статус и решения для оценки.")
    await service.finish_session(db_session, s.id, FakeJudgeClient(), weak_threshold=0.6)
    res = await service.get_results(db_session, s.id)
    assert all(q["type"] in ("single", "multi") for q in res["questions"])
    assert len(res["open_questions"]) == 1
    o = res["open_questions"][0]
    assert o["stem"] and o["answer_text"].startswith("Длинный") and o["feedback"]
    assert "rubric" not in o
    assert res["total_questions"] == 2


@pytest.mark.asyncio
async def test_competency_excludes_open_topic(db_session):
    # Open questions (topic_id="open") must NOT pollute the competency profile.
    from app.assessment.competency import load_competency
    user, s, qs = await _seed(db_session)
    await service.submit_answer(db_session, s.id, qs[0].id, selected_keys=["a"])
    await service.submit_answer(db_session, s.id, qs[1].id, selected_keys=["a"])
    await service.finish_session(db_session, s.id, FakeJudgeClient(), weak_threshold=0.6)
    prof = await load_competency(db_session, user.id, "base")
    assert "open" not in prof
