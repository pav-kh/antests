import itertools
import json
import pytest
from app.generation.openai_client import OpenAIClient
from app.generation.schemas import OpenQuestion


class _Msg:
    def __init__(self, c): self.content = c
class _Choice:
    def __init__(self, c): self.message = _Msg(c); self.finish_reason = "stop"
class _Completion:
    def __init__(self, c): self.choices = [_Choice(c)]
class _Completions:
    def __init__(self, c): self._c = c
    async def create(self, **kw): return _Completion(self._c)
class _Chat:
    def __init__(self, c): self.completions = _Completions(c)
class _Client:
    def __init__(self, c): self.chat = _Chat(c)


@pytest.mark.asyncio
async def test_generate_open_questions_parses_two():
    payload = {"questions": [
        {"stem": "Опишите проблему повторных обращений и решения.",
         "rubric": "вопросы клиенту + решения", "explanation": "хороший ответ раскрывает..."},
        {"stem": "Как выявить причину задержки заявки?",
         "rubric": "диагностические вопросы", "explanation": "..."},
    ]}
    client = OpenAIClient(api_key="x", gen_model="g", validate_model="v",
                          _client=_Client(json.dumps(payload)))
    qs = await client.generate_open_questions("base", count=2)
    assert len(qs) == 2
    assert isinstance(qs[0], OpenQuestion)
    assert qs[0].rubric


@pytest.mark.asyncio
async def test_judge_open_returns_feedback():
    client = OpenAIClient(api_key="x", gen_model="g", validate_model="v",
                          _client=_Client("Хорошо, но упустили эскалацию."))
    fb = await client.judge_open(
        stem="Опишите решения.", rubric="вопросы + решения", answer="Спросить статус.")
    assert "эскалацию" in fb


import uuid
from sqlalchemy import select
from app.db.models import Question, TestSession, User
from app.generation.generator import Generator
from app.generation.schemas import (
    GeneratedBatch, GeneratedQuestion, OpenQuestion, ValidationVerdict,
)


_stem_counter = itertools.count()


def _closed_q(topic_id="data"):
    # A real model returns a distinct stem each call; mirror that. Identical
    # stems would be collapsed by the generator's session-wide dedup, leaving
    # the topic unfillable (status="failed") before the open-question step runs.
    return GeneratedQuestion(
        topic_id=topic_id, type="single", stem=f"Q{next(_stem_counter)}?",
        artifact_kind="none", artifact_content=None,
        options=[{"key": "a", "text": "x"}, {"key": "b", "text": "y"}],
        correct_keys=["a"], explanation="because",
    )


class FakeGenClient:
    async def generate_batch(self, level, mode, plan_slice, avoid_stems=None, want_artifact=False):
        n = sum(c for _, c in plan_slice)
        return GeneratedBatch(questions=[_closed_q(plan_slice[0][0]) for _ in range(n)])

    async def validate_question(self, q):
        return ValidationVerdict(valid=True, reason="ok")

    async def generate_open_questions(self, level, count=2):
        return [
            OpenQuestion(stem=f"Открытый {i}", rubric=f"критерии {i}", explanation=f"разбор {i}")
            for i in range(count)
        ]


@pytest.mark.asyncio
async def test_generator_appends_two_open_questions(db_session):
    user = User(login=f"u{uuid.uuid4().hex[:8]}", password_hash="x")
    db_session.add(user); await db_session.commit(); await db_session.refresh(user)
    s = TestSession(user_id=user.id, level="base", mode="exam", status="generating",
                    total_questions=3, generated_count=0, time_limit_sec=7200)
    db_session.add(s); await db_session.commit(); await db_session.refresh(s)

    gen = Generator(db_session, FakeGenClient(), batch_size=10)
    await gen.run(s.id, plan=[("data", 3)])
    await db_session.refresh(s)
    assert s.status == "ready"

    qs = (await db_session.execute(
        select(Question).where(Question.session_id == s.id).order_by(Question.seq))).scalars().all()
    closed = [q for q in qs if q.type in ("single", "multi")]
    openq = [q for q in qs if q.type == "open"]
    assert len(closed) == 3
    assert len(openq) == 2
    assert all(o.seq > max(c.seq for c in closed) for o in openq)
    assert all(o.rubric and o.options == [] and o.correct_keys == [] for o in openq)
    assert s.total_questions == 3
