import itertools
import json
import uuid

import pytest
from sqlalchemy import select

from app.db.models import Question, TestSession, User
from app.generation.generator import Generator
from app.generation.openai_client import OpenAIClient
from app.generation.schemas import (
    GeneratedBatch,
    GeneratedQuestion,
    OpenQuestion,
    ValidationVerdict,
)


class _Msg:
    def __init__(self, c):
        self.content = c


class _Choice:
    def __init__(self, c):
        self.message = _Msg(c)
        self.finish_reason = "stop"


class _Completion:
    def __init__(self, c):
        self.choices = [_Choice(c)]


class _Completions:
    def __init__(self, c):
        self._c = c

    async def create(self, **kw):
        return _Completion(self._c)


class _Chat:
    def __init__(self, c):
        self.completions = _Completions(c)


class _Client:
    def __init__(self, c):
        self.chat = _Chat(c)


class _SeqCompletions:
    """Returns each queued content string in turn, one per create() call."""

    def __init__(self, contents):
        self._contents = list(contents)
        self.calls = 0

    async def create(self, **kw):
        i = min(self.calls, len(self._contents) - 1)
        self.calls += 1
        return _Completion(self._contents[i])


class _SeqClient:
    def __init__(self, contents):
        self.chat = type("C", (), {"completions": _SeqCompletions(contents)})()


_OPEN_PAYLOAD = {"questions": [
    {"topic_title": "Повторные обращения клиентов",
     "case": "Клиенты часто пишут повторно по статусу заявки.",
     "task": "Сформулируйте до 5 уточняющих вопросов и до 4 решений.",
     "focus": "Не проектируйте архитектуру; выявите причины.",
     "criteria_visible": "качество вопросов; проверяемость решений.",
     "rubric": "вопросы клиенту + решения", "explanation": "хороший ответ раскрывает..."},
    {"topic_title": "Диагностика задержки заявки",
     "case": "Заявка задерживается на этапе согласования.",
     "task": "Перечислите до 4 диагностических вопросов и гипотез.",
     "focus": "Сфокусируйтесь на причинах, а не на UI.",
     "criteria_visible": "полнота гипотез; приоритеты.",
     "rubric": "диагностические вопросы", "explanation": "..."},
]}

# What the model erroneously echoes ~50% of the time under strict:false — the
# JSON Schema document itself instead of data conforming to it.
_SCHEMA_ECHO = json.dumps({
    "type": "object",
    "properties": {"questions": {"type": "array", "items": {"type": "object"}}},
})


@pytest.mark.asyncio
async def test_generate_open_questions_parses_two():
    client = OpenAIClient(api_key="x", gen_model="g", validate_model="v",
                          _client=_Client(json.dumps(_OPEN_PAYLOAD)))
    qs = await client.generate_open_questions("base", count=2)
    assert len(qs) == 2
    assert isinstance(qs[0], OpenQuestion)
    # The stem is ASSEMBLED from parts via build_open_stem; the raw rubric stays
    # separate and must not leak into the visible stem.
    assert "Задание: Сформулируйте до 5 уточняющих вопросов" in qs[0].stem
    assert qs[0].rubric == "вопросы клиенту + решения"
    assert qs[0].rubric not in qs[0].stem


@pytest.mark.asyncio
async def test_generate_open_questions_retries_on_schema_echo():
    # The model sometimes returns the schema document instead of data; one bad
    # response must not fail generation — retry and succeed on the next call.
    client = OpenAIClient(
        api_key="x", gen_model="g", validate_model="v",
        _client=_SeqClient([_SCHEMA_ECHO, json.dumps(_OPEN_PAYLOAD)]))
    qs = await client.generate_open_questions("base", count=2)
    assert len(qs) == 2
    # Second (valid) call's parts were assembled into the visible stem.
    assert "Задание:" in qs[0].stem
    assert qs[0].rubric


@pytest.mark.asyncio
async def test_generate_open_questions_assembles_stem_from_parts():
    # The model returns structured PARTS; the client must assemble the visible
    # stem via build_open_stem and keep rubric/explanation separate.
    payload = {"questions": [{
        "topic_title": "От бизнес-проблемы к требованиям",
        "case": "В компании растёт число обращений по статусу заявки.",
        "task": "Сформулируйте до 5 уточняющих вопросов и до 4 требований.",
        "focus": "Не проектируйте архитектуру; перейдите к требованиям.",
        "criteria_visible": "качество вопросов; проверяемость; приоритеты.",
        "rubric": "Скрытые подробные критерии для судьи, которых нет в stem.",
        "explanation": "Проверяется переход от проблемы к требованиям.",
    }]}
    client = OpenAIClient(api_key="x", gen_model="g", validate_model="v",
                          _client=_Client(json.dumps(payload)))
    qs = await client.generate_open_questions("base", count=1)
    assert len(qs) == 1
    q = qs[0]
    assert "Задание: Сформулируйте до 5 уточняющих вопросов" in q.stem
    assert "Фокус ответа: Не проектируйте архитектуру" in q.stem
    assert "Критерии оценки: качество вопросов" in q.stem
    assert "Тип: открытый кейс. От бизнес-проблемы к требованиям" in q.stem
    assert q.rubric == "Скрытые подробные критерии для судьи, которых нет в stem."
    assert q.rubric not in q.stem
    assert q.explanation


@pytest.mark.asyncio
async def test_judge_open_returns_feedback():
    client = OpenAIClient(api_key="x", gen_model="g", validate_model="v",
                          _client=_Client("Хорошо, но упустили эскалацию."))
    fb = await client.judge_open(
        stem="Опишите решения.", rubric="вопросы + решения", answer="Спросить статус.")
    assert "эскалацию" in fb


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
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    s = TestSession(user_id=user.id, level="base", mode="exam", status="generating",
                    total_questions=3, generated_count=0, time_limit_sec=7200)
    db_session.add(s)
    await db_session.commit()
    await db_session.refresh(s)

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
    # generated_count must cover the open questions, else the exam UI's
    # readiness check (seq <= generated_count) leaves them locked/unreachable.
    assert s.generated_count == max(q.seq for q in qs)
    assert s.generated_count >= max(o.seq for o in openq)
