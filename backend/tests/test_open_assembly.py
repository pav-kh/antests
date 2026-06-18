import itertools
import uuid

import pytest
from sqlalchemy import select

from app.db.models import Question, TestSession, User
from app.generation.generator import (
    Generator, LEVEL_OPEN_COUNT, LEVEL_ARTIFACT_TOPICS, OPEN_TOPICS_BASE_SPEC,
)
from app.generation.schemas import (
    GeneratedBatch, GeneratedQuestion, OpenQuestion, ValidationVerdict,
)

_c = itertools.count()


def _closed(topic_id):
    return GeneratedQuestion(
        topic_id=topic_id, type="single", stem=f"Q{next(_c)}?",
        artifact_kind="none", artifact_content=None,
        options=[{"key": "a", "text": "x"}, {"key": "b", "text": "y"}],
        correct_keys=["a"], explanation="b",
    )


class FakeClient:
    async def generate_batch(self, level, mode, plan_slice, avoid_stems=None,
                             want_artifact=False, multi_ratio=None, mermaid_only=False):
        n = sum(c for _, c in plan_slice)
        return GeneratedBatch(questions=[_closed(plan_slice[0][0]) for _ in range(n)])

    async def validate_question(self, q):
        return ValidationVerdict(valid=True, reason="ok")

    async def generate_open_questions(self, level, count=3):
        return [OpenQuestion(stem=f"Пул {i}", rubric=f"r{i}", explanation=f"e{i}")
                for i in range(count)]

    async def generate_open_on_topic(self, topic_title, hint):
        return OpenQuestion(stem=f"Тема: {topic_title}", rubric="rt", explanation="et")


def test_level_open_count_and_artifact_config():
    assert LEVEL_OPEN_COUNT["base"] == 3
    assert LEVEL_OPEN_COUNT["specialist"] == 3
    assert LEVEL_OPEN_COUNT["ba"] == 2
    assert LEVEL_ARTIFACT_TOPICS["base"] == set()
    assert LEVEL_ARTIFACT_TOPICS["specialist"] == set()
    assert len(OPEN_TOPICS_BASE_SPEC) == 2
    titles = [t for t, _ in OPEN_TOPICS_BASE_SPEC]
    assert any("нтеграц" in t for t in titles)
    assert any("истемн" in t for t in titles)


async def _seed_session(db, level):
    user = User(login=f"u{uuid.uuid4().hex[:8]}", password_hash="x")
    db.add(user)
    await db.commit()
    await db.refresh(user)
    s = TestSession(user_id=user.id, level=level, mode="exam", status="generating",
                    total_questions=3, generated_count=0, time_limit_sec=7200)
    db.add(s)
    await db.commit()
    await db.refresh(s)
    return s


class VolunteersArtifactClient(FakeClient):
    """Returns an artifact on EVERY closed question even though want_artifact is
    False — mirrors the model spontaneously adding code/data the prompt didn't
    ask for. On an artifacts-off level it must be stripped to text-only."""

    async def generate_batch(self, level, mode, plan_slice, avoid_stems=None,
                             want_artifact=False, multi_ratio=None, mermaid_only=False):
        n = sum(c for _, c in plan_slice)
        tid = plan_slice[0][0]
        out = []
        for i in range(n):
            q = _closed(tid)
            q.artifact_kind = "sql"
            q.artifact_content = "SELECT 1;"
            out.append(q)
        return GeneratedBatch(questions=out)


@pytest.mark.asyncio
async def test_base_strips_volunteered_artifacts(db_session):
    # Artifacts-off levels (base/specialist) must NOT store an artifact the model
    # volunteers unprompted — it's stripped to text-only. Use 10 closed so the
    # 20% cap (floor(0.20*10)=2) does NOT mask the bug: without the artifacts-off
    # strip, the first 2 volunteered artifacts would be stored (cap not yet hit).
    s = await _seed_session(db_session, "base")
    gen = Generator(db_session, VolunteersArtifactClient(), batch_size=10)
    await gen.run(s.id, plan=[("requirements", 10)])
    await db_session.refresh(s)
    assert s.status == "ready"
    closed = (await db_session.execute(
        select(Question).where(Question.session_id == s.id, Question.type != "open"))).scalars().all()
    assert len(closed) == 10
    assert all(q.artifact_kind == "none" for q in closed)
    assert all(q.artifact_content is None for q in closed)


@pytest.mark.asyncio
async def test_base_session_has_3_open_seed_plus_two_themed(db_session):
    s = await _seed_session(db_session, "base")
    gen = Generator(db_session, FakeClient(), batch_size=10)
    await gen.run(s.id, plan=[("requirements", 3)])
    await db_session.refresh(s)
    assert s.status == "ready"
    qs = (await db_session.execute(
        select(Question).where(Question.session_id == s.id).order_by(Question.seq))).scalars().all()
    closed = [q for q in qs if q.type in ("single", "multi")]
    openq = [q for q in qs if q.type == "open"]
    assert len(closed) == 3
    assert len(openq) == 3  # 1 seed + 2 themed
    open_stems = " ".join(o.stem for o in openq)
    assert "Тема: Описание интеграции" in open_stems
    assert "Тема: Системное мышление" in open_stems
    assert all(q.artifact_kind == "none" for q in closed)
    assert s.generated_count == max(q.seq for q in qs)


@pytest.mark.asyncio
async def test_base_themed_failure_degrades_softly(db_session):
    class BoomTopic(FakeClient):
        async def generate_open_on_topic(self, topic_title, hint):
            raise RuntimeError("llm down")
    s = await _seed_session(db_session, "base")
    gen = Generator(db_session, BoomTopic(), batch_size=10)
    await gen.run(s.id, plan=[("requirements", 3)])
    await db_session.refresh(s)
    assert s.status == "ready"
    openq = (await db_session.execute(
        select(Question).where(Question.session_id == s.id, Question.type == "open"))).scalars().all()
    assert len(openq) == 1  # only the seed; both themed failed


@pytest.mark.asyncio
async def test_ba_session_unchanged_two_open(db_session):
    s = await _seed_session(db_session, "ba")
    gen = Generator(db_session, FakeClient(), batch_size=10)
    await gen.run(s.id, plan=[("requirements", 3)])
    await db_session.refresh(s)
    openq = (await db_session.execute(
        select(Question).where(Question.session_id == s.id, Question.type == "open"))).scalars().all()
    assert len(openq) == 2  # ba keeps the pool logic
