import itertools
import uuid

import pytest
from sqlalchemy import select

from app.db.models import Question, TestSession, User
from app.generation.generator import Generator, _stem_references_artifact
from app.generation.schemas import (
    GeneratedBatch, GeneratedQuestion, OpenQuestion, ValidationVerdict,
)

_c = itertools.count()


def _q(topic_id, stem, kind="none", content=None, qtype="single", correct=None):
    return GeneratedQuestion(
        topic_id=topic_id, type=qtype, stem=stem,
        artifact_kind=kind, artifact_content=content,
        options=[{"key": "a", "text": "x"}, {"key": "b", "text": "y"},
                 {"key": "c", "text": "z"}],
        correct_keys=correct or ["a"], explanation="e",
    )


def test_detector_flags_diagram_references():
    assert _stem_references_artifact("Какие элементы на приведённой диаграмме относятся к событиям?")
    assert _stem_references_artifact("Что на приведённой схеме моделирует переход?")
    assert _stem_references_artifact("Найдите ошибку в показанном запросе.")
    # artifact noun + ниже/выше (in either order) IS a reference
    assert _stem_references_artifact("На схеме ниже найдите событие.")
    assert _stem_references_artifact("Ниже приведена диаграмма; что она моделирует?")
    # conceptual questions about diagrams in general are NOT flagged
    assert not _stem_references_artifact("Чем диаграмма состояний отличается от диаграммы активности?")
    assert not _stem_references_artifact("Какой тип UML-диаграммы описывает поведение во времени?")
    # bare comparatives ниже/выше must NOT trigger a false positive
    assert not _stem_references_artifact("Какие требования имеют приоритет ниже среднего?")
    assert not _stem_references_artifact("Что делать, если нагрузка выше нормы?")


class DanglingThenCleanClient:
    """On base, returns modeling questions: first a diagram-REFERENCING one with a
    mermaid artifact (which will be stripped -> must be DROPPED), then clean
    conceptual ones. Verifies the topic still fills with answerable questions."""
    def __init__(self):
        self._n = 0
    async def generate_batch(self, level, mode, plan_slice, avoid_stems=None,
                             want_artifact=False, multi_ratio=None,
                             mermaid_only=False, artifacts_disabled=False):
        n = sum(c for _, c in plan_slice)
        tid = plan_slice[0][0]
        out = []
        for _ in range(n):
            self._n += 1
            if self._n % 2 == 1:
                # dangling: references a diagram + has a mermaid artifact
                out.append(_q(tid, f"На приведённой диаграмме {self._n}: что является событием?",
                              kind="mermaid", content="flowchart TD\n A-->B"))
            else:
                out.append(_q(tid, f"Чем отличается диаграмма состояний от активности? {self._n}"))
        return GeneratedBatch(questions=out)
    async def validate_question(self, q):
        return ValidationVerdict(valid=True, reason="ok")
    async def generate_open_questions(self, level, count=3):
        return [OpenQuestion(stem=f"O{i}", rubric="r", explanation="e") for i in range(count)]
    async def generate_open_on_topic(self, topic_title, hint):
        return OpenQuestion(stem=f"T {topic_title}", rubric="r", explanation="e")


async def _seed(db, level="base"):
    user = User(login=f"u{uuid.uuid4().hex[:8]}", password_hash="x")
    db.add(user)
    await db.commit()
    await db.refresh(user)
    s = TestSession(user_id=user.id, level=level, mode="exam", status="generating",
                    total_questions=4, generated_count=0, time_limit_sec=7200)
    db.add(s)
    await db.commit()
    await db.refresh(s)
    return s


@pytest.mark.asyncio
async def test_base_drops_dangling_modeling_questions(db_session):
    s = await _seed(db_session, "base")
    gen = Generator(db_session, DanglingThenCleanClient(), batch_size=4)
    await gen.run(s.id, plan=[("modeling", 4)])
    await db_session.refresh(s)
    assert s.status == "ready"
    closed = (await db_session.execute(
        select(Question).where(Question.session_id == s.id,
                               Question.type.in_(("single", "multi"))))).scalars().all()
    assert len(closed) == 4  # topic filled despite drops
    # NO stored closed question both references an artifact AND lacks one
    for q in closed:
        if _stem_references_artifact(q.stem):
            assert q.artifact_kind != "none", f"dangling: {q.stem!r}"
    # on base, artifacts are off entirely -> none stored, so all stems must be clean
    assert all(q.artifact_kind == "none" for q in closed)
    assert all(not _stem_references_artifact(q.stem) for q in closed)
