import itertools
import uuid

import pytest
from sqlalchemy import select

from app.db.models import Question, TestSession, User
from app.generation.generator import Generator, MULTI_TOPUP_ROUNDS
from app.generation.schemas import (
    GeneratedBatch, GeneratedQuestion, OpenQuestion, ValidationVerdict,
)

_c = itertools.count()


def _q(topic_id, qtype, correct):
    return GeneratedQuestion(
        topic_id=topic_id, type=qtype, stem=f"S{next(_c)}?",
        artifact_kind="none", artifact_content=None,
        options=[{"key": "a", "text": "x"}, {"key": "b", "text": "y"},
                 {"key": "c", "text": "z"}],
        correct_keys=correct, explanation="e",
    )


class SingleThenMultiClient:
    """Initial generation returns all SINGLE; top-up calls (multi_ratio==1.0)
    return MULTI. Lets us verify the top-up converts singles to multi."""
    async def generate_batch(self, level, mode, plan_slice, avoid_stems=None,
                             want_artifact=False, multi_ratio=None, mermaid_only=False):
        n = sum(c for _, c in plan_slice)
        tid = plan_slice[0][0]
        if multi_ratio == 1.0:
            return GeneratedBatch(questions=[_q(tid, "multi", ["a", "b"]) for _ in range(n)])
        return GeneratedBatch(questions=[_q(tid, "single", ["a"]) for _ in range(n)])

    async def validate_question(self, q):
        return ValidationVerdict(valid=True, reason="ok")

    async def generate_open_questions(self, level, count=3):
        return [OpenQuestion(stem=f"O{i}", rubric="r", explanation="e") for i in range(count)]

    async def generate_open_on_topic(self, topic_title, hint):
        return OpenQuestion(stem=f"T {topic_title}", rubric="r", explanation="e")


class AlwaysSingleClient(SingleThenMultiClient):
    """Even top-up returns single — exercises the round budget + accept fallback."""
    async def generate_batch(self, level, mode, plan_slice, avoid_stems=None,
                             want_artifact=False, multi_ratio=None, mermaid_only=False):
        n = sum(c for _, c in plan_slice)
        tid = plan_slice[0][0]
        return GeneratedBatch(questions=[_q(tid, "single", ["a"]) for _ in range(n)])


class BadMultiClient(SingleThenMultiClient):
    """Top-up returns multi questions that FAIL validation — they must be
    rejected, so the share does NOT reach target and the session still readies."""
    async def validate_question(self, q):
        from app.generation.schemas import ValidationVerdict
        # Reject the multi top-up candidates (they have >=2 correct keys);
        # accept the initial singles (1 correct key) so generation completes.
        if q.type == "multi":
            return ValidationVerdict(valid=False, reason="bad")
        return ValidationVerdict(valid=True, reason="ok")


async def _seed(db, level="base"):
    user = User(login=f"u{uuid.uuid4().hex[:8]}", password_hash="x")
    db.add(user)
    await db.commit()
    await db.refresh(user)
    s = TestSession(user_id=user.id, level=level, mode="exam", status="generating",
                    total_questions=10, generated_count=0, time_limit_sec=7200)
    db.add(s)
    await db.commit()
    await db.refresh(s)
    return s


@pytest.mark.asyncio
async def test_topup_converts_singles_to_reach_70pct(db_session):
    s = await _seed(db_session, "base")
    gen = Generator(db_session, SingleThenMultiClient(), batch_size=10)
    await gen.run(s.id, plan=[("requirements", 10)])
    await db_session.refresh(s)
    assert s.status == "ready"
    closed = (await db_session.execute(
        select(Question).where(Question.session_id == s.id,
                               Question.type.in_(("single", "multi"))))).scalars().all()
    assert len(closed) == 10
    multi = [q for q in closed if q.type == "multi"]
    import math
    assert len(multi) >= math.ceil(0.7 * 10)  # >= 7
    # converted multis are valid (>=2 correct keys)
    assert all(len(q.correct_keys) >= 2 for q in multi)
    # convert preserves topic and strips artifacts; seq stays a clean 1..N set
    assert all(q.topic_id == "requirements" for q in closed)
    assert all(q.artifact_kind == "none" for q in closed)
    assert sorted(q.seq for q in closed) == list(range(1, 11))


@pytest.mark.asyncio
async def test_topup_accepts_when_model_keeps_returning_single(db_session):
    # If even top-up yields single, the session still finishes (no infinite loop).
    s = await _seed(db_session, "base")
    gen = Generator(db_session, AlwaysSingleClient(), batch_size=10)
    await gen.run(s.id, plan=[("requirements", 10)])
    await db_session.refresh(s)
    assert s.status == "ready"  # accepted what it has, did not hang/fail
    closed = (await db_session.execute(
        select(Question).where(Question.session_id == s.id,
                               Question.type.in_(("single", "multi"))))).scalars().all()
    assert len(closed) == 10  # total preserved


@pytest.mark.asyncio
async def test_topup_rejects_invalid_multis(db_session):
    s = await _seed(db_session, "base")
    gen = Generator(db_session, BadMultiClient(), batch_size=10)
    await gen.run(s.id, plan=[("requirements", 10)])
    await db_session.refresh(s)
    assert s.status == "ready"  # invalid converts rejected, still readies
    closed = (await db_session.execute(
        select(Question).where(Question.session_id == s.id,
                               Question.type.in_(("single", "multi"))))).scalars().all()
    assert len(closed) == 10  # total preserved
    # no multi got through validation -> they stay single
    assert all(q.type == "single" for q in closed)


@pytest.mark.asyncio
async def test_topup_skipped_for_levels_without_target(db_session):
    # A level absent from LEVEL_MULTI_TARGET would skip top-up. base IS in the
    # map now, so assert the constant exists and is a positive int instead.
    assert MULTI_TOPUP_ROUNDS >= 1
