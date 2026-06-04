import uuid

import pytest
from sqlalchemy import select

from app.db.models import Question, TestSession, User
from app.generation.generator import Generator
from app.generation.schemas import GeneratedBatch, GeneratedQuestion, ValidationVerdict


def _q(topic_id="data"):
    return GeneratedQuestion(
        topic_id=topic_id, type="single", stem="Q?",
        artifact_kind="none", artifact_content=None,
        options=[{"key": "a", "text": "x"}, {"key": "b", "text": "y"}],
        correct_keys=["a"], explanation="because",
    )


class FakeClient:
    def __init__(self, reject_first=0):
        self.reject_first = reject_first
        self._validated = 0

    async def generate_batch(self, level, mode, plan_slice):
        n = sum(c for _, c in plan_slice)
        return GeneratedBatch(questions=[_q(plan_slice[0][0]) for _ in range(n)])

    async def validate_question(self, q):
        self._validated += 1
        if self._validated <= self.reject_first:
            return ValidationVerdict(valid=False, reason="rejected for test")
        return ValidationVerdict(valid=True, reason="ok")


async def _make_session(db, total=5, mode="exam", level="base"):
    user = User(login=f"u{uuid.uuid4().hex[:8]}", password_hash="x")
    db.add(user)
    await db.commit()
    await db.refresh(user)
    s = TestSession(
        user_id=user.id, level=level, mode=mode, status="generating",
        total_questions=total, generated_count=0, time_limit_sec=7200,
    )
    db.add(s)
    await db.commit()
    await db.refresh(s)
    return s


@pytest.mark.asyncio
async def test_generator_fills_pool_and_marks_ready(db_session):
    s = await _make_session(db_session, total=5)
    gen = Generator(db_session, FakeClient(), batch_size=10)
    await gen.run(s.id, plan=[("data", 5)])
    await db_session.refresh(s)
    assert s.status == "ready"
    assert s.generated_count == 5
    assert s.timer_started_at is not None
    qs = (await db_session.execute(
        select(Question).where(Question.session_id == s.id))).scalars().all()
    assert len(qs) == 5
    assert sorted(q.seq for q in qs) == [1, 2, 3, 4, 5]
    assert all(q.validation_status == "passed" for q in qs)


@pytest.mark.asyncio
async def test_generator_completes_when_model_returns_topic_title_not_key(db_session):
    # Regression: the real LLM returns the topic TITLE (e.g. "Хранение и обработка
    # данных") as topic_id, not the requested key ("data"). The generator must NOT
    # filter those out and loop forever — it must assign the correct key and finish.
    from app.generation.topics import get_topic

    class TitleEchoClient(FakeClient):
        async def generate_batch(self, level, mode, plan_slice):
            n = sum(c for _, c in plan_slice)
            title = get_topic(plan_slice[0][0]).title  # model echoes the TITLE
            return GeneratedBatch(questions=[_q(title) for _ in range(n)])

    s = await _make_session(db_session, total=3)
    gen = Generator(db_session, TitleEchoClient(), batch_size=10)
    await gen.run(s.id, plan=[("data", 3)])
    await db_session.refresh(s)
    assert s.status == "ready"
    assert s.generated_count == 3
    qs = (await db_session.execute(
        select(Question).where(Question.session_id == s.id))).scalars().all()
    # stored topic_id must be the canonical KEY, not the title the model returned
    assert all(q.topic_id == "data" for q in qs)


@pytest.mark.asyncio
async def test_generator_retries_rejected_questions(db_session):
    s = await _make_session(db_session, total=3)
    gen = Generator(db_session, FakeClient(reject_first=2), batch_size=10)
    await gen.run(s.id, plan=[("data", 3)])
    await db_session.refresh(s)
    assert s.status == "ready"
    assert s.generated_count == 3


@pytest.mark.asyncio
async def test_generator_marks_failed_on_client_error(db_session):
    s = await _make_session(db_session, total=3)

    class BoomClient(FakeClient):
        async def generate_batch(self, *a, **k):
            raise RuntimeError("openai down")

    gen = Generator(db_session, BoomClient(), batch_size=10, max_batch_retries=2)
    await gen.run(s.id, plan=[("data", 3)])
    await db_session.refresh(s)
    assert s.status == "failed"
