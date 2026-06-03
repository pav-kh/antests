# Subsystem 2: Generation Engine — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the LLM-backed test generation pipeline — topic configuration, an OpenAI client wrapper, batch question generation with structured output, per-question self-validation with a cheaper model, the test-session lifecycle (create → generate in background → ready), the daily rate-limit gate, and a streaming/status API the frontend consumes.

**Architecture:** Generation is a background asyncio task per session. A `TopicPlanner` decides how many questions per topic (official proportions for `exam`, weakest-topic selection for `adaptive` — the adaptive selection reads `topic_competency`, which is created in Subsystem 3; here we tolerate an empty profile by falling back to even distribution). The `OpenAIClient` wraps generation (strong model, JSON-schema structured output, cached system prompt) and validation (cheap model). The `Generator` orchestrates batches, runs validation, persists `passed` questions, increments `generated_count`, and on completion sets `status=ready` + `timer_started_at`. A status endpoint exposes progress and ready questions for streaming; answers submitted before full readiness are accepted (answer submission itself lives in Subsystem 3, but the question-read path is here).

**Tech Stack:** Builds on Subsystem 1. Adds: `openai>=1.55` Python SDK. Uses FastAPI `BackgroundTasks`/`asyncio.create_task`, SQLAlchemy async, Pydantic v2 for the LLM JSON schema.

**Depends on:** Subsystem 1 (config, db, models base, auth/current_user, daily-usage helpers) must be complete and green.

---

## File Structure

```
backend/app/
  core/config.py              # MODIFY: add OpenAI keys/models + generation params
  db/models.py                # MODIFY: add TestSession + Question models
  generation/
    __init__.py
    topics.py                 # static topic registry + official proportions (seed data)
    planner.py                # TopicPlanner: level+mode -> [(topic_id, count), ...]
    schemas.py                # Pydantic models for LLM I/O + API responses
    openai_client.py          # OpenAIClient: generate_batch(), validate_question()
    generator.py              # Generator: orchestrates batches, validation, persistence
    service.py                # session lifecycle: create_session, get_status, list_ready_questions
    router.py                 # POST /sessions, GET /sessions/{id}/status, GET /sessions/{id}/questions
backend/tests/
  test_topics.py
  test_planner.py
  test_openai_client.py       # uses a fake OpenAI (monkeypatched), no network
  test_generator.py           # uses a fake OpenAIClient
  test_sessions_api.py
```

`openai_client.py` is the ONLY module that touches the network. Everything else is tested against a fake client, so the suite runs offline and deterministically.

---

### Task 1: Extend config for OpenAI + generation params

**Files:**
- Modify: `backend/app/core/config.py`
- Modify: `backend/app/core/.env` docs → `backend/.env.example`
- Test: `backend/tests/test_config.py` (append)

- [ ] **Step 1: Append a failing test to `backend/tests/test_config.py`**

```python
def test_settings_has_openai_and_generation(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "postgresql+asyncpg://u:p@h:5432/d")
    monkeypatch.setenv("SESSION_SECRET", "secret")
    monkeypatch.setenv("ACCESS_CODE", "X")
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    monkeypatch.setenv("OPENAI_GEN_MODEL", "strong-model")
    monkeypatch.setenv("OPENAI_VALIDATE_MODEL", "cheap-model")
    monkeypatch.setenv("GENERATION_BATCH_SIZE", "10")
    monkeypatch.setenv("ADAPTIVE_QUESTION_COUNT", "20")
    monkeypatch.setenv("WEAK_TOPIC_THRESHOLD", "0.6")
    from app.core.config import Settings
    s = Settings()
    assert s.openai_api_key == "sk-test"
    assert s.openai_gen_model == "strong-model"
    assert s.openai_validate_model == "cheap-model"
    assert s.generation_batch_size == 10
    assert s.adaptive_question_count == 20
    assert s.weak_topic_threshold == 0.6
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && . .venv/bin/activate && pytest tests/test_config.py::test_settings_has_openai_and_generation -v`
Expected: FAIL (`AttributeError` / validation error for missing fields)

- [ ] **Step 3: Add fields to `Settings` in `backend/app/core/config.py`**

Add these fields to the `Settings` class (after `daily_session_limit`):

```python
    openai_api_key: str = ""
    openai_gen_model: str = "gpt-4o"
    openai_validate_model: str = "gpt-4o-mini"
    generation_batch_size: int = 10
    adaptive_question_count: int = 20
    weak_topic_threshold: float = 0.6
```

> NOTE: `openai_gen_model` / `openai_validate_model` defaults are placeholders — verify the exact current OpenAI model IDs at implementation time and set them in `.env`. The spec mandates a strong model for generation and a cheap one for validation.

- [ ] **Step 4: Append to `backend/.env.example`**

```bash
# OpenAI
OPENAI_API_KEY=sk-...
OPENAI_GEN_MODEL=gpt-4o
OPENAI_VALIDATE_MODEL=gpt-4o-mini

# Generation tuning
GENERATION_BATCH_SIZE=10
ADAPTIVE_QUESTION_COUNT=20
WEAK_TOPIC_THRESHOLD=0.6
```

- [ ] **Step 5: Run test to verify it passes**

Run: `pytest tests/test_config.py -v`
Expected: PASS (all config tests)

- [ ] **Step 6: Commit**

```bash
git add backend/app/core/config.py backend/.env.example backend/tests/test_config.py
git commit -m "feat: add OpenAI and generation settings"
```

---

### Task 2: Topic registry + official proportions

**Files:**
- Create: `backend/app/generation/__init__.py` (empty)
- Create: `backend/app/generation/topics.py`
- Test: `backend/tests/test_topics.py`

The topic registry encodes the 10 domains (shared by both levels) and the official proportion matrix per level (from the research file's distribution table, normalized so each level's weights sum to 1.0).

- [ ] **Step 1: Write the failing test** — `backend/tests/test_topics.py`

```python
from app.generation import topics


def test_ten_topics_for_each_level():
    assert len(topics.TOPICS) == 10


def test_proportions_sum_to_one_per_level():
    for level in ("base", "specialist"):
        total = sum(t.proportions[level] for t in topics.TOPICS)
        assert abs(total - 1.0) < 1e-6, f"{level} sums to {total}"


def test_every_topic_has_id_title_and_subtopics():
    for t in topics.TOPICS:
        assert t.id
        assert t.title
        assert isinstance(t.subtopics, list) and len(t.subtopics) >= 1


def test_get_topic_by_id():
    t = topics.get_topic("requirements")
    assert t.title


def test_get_unknown_topic_raises():
    import pytest
    with pytest.raises(KeyError):
        topics.get_topic("nope")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_topics.py -v`
Expected: FAIL (`ModuleNotFoundError: No module named 'app.generation'`)

- [ ] **Step 3: Create empty `backend/app/generation/__init__.py`, then write `backend/app/generation/topics.py`**

```python
from dataclasses import dataclass


@dataclass(frozen=True)
class Topic:
    id: str
    title: str
    subtopics: list[str]
    proportions: dict[str, float]  # {"base": 0.x, "specialist": 0.y}


# Proportions derived from the research file's distribution matrix, grouped into
# the 10 domains and normalized so each level sums to 1.0. The matrix gives:
#   Theory(BABOK/SWEBOK), Modeling(UML/BPMN), Tech stack(API/SQL/DB),
#   Enterprise architecture, Normative(GOST/ISO), Situational(case-studies).
# We map those clusters onto the 10 syllabus domains below; clusters that the
# matrix lumps together are split across their member domains.
TOPICS: list[Topic] = [
    Topic("fundamentals", "Фундаментальные компетенции",
          ["Информационные системы и виды ПО", "ООП", "Системное мышление"],
          {"base": 0.10, "specialist": 0.08}),
    Topic("methodology", "Методологии и технологии разработки ПО",
          ["SDLC", "Waterfall/RUP/Scrum/Kanban/Lean/FDD/XP", "RACI", "CI/CD", "Проектная документация"],
          {"base": 0.10, "specialist": 0.10}),
    Topic("requirements", "Работа с требованиями",
          ["Виды требований", "Сбор и выявление", "Документирование", "ЖЦ и управление требованиями", "Критерии качества"],
          {"base": 0.15, "specialist": 0.14}),
    Topic("modeling", "Моделирование процессов и систем",
          ["UML (классы, use case, состояния, активности, последовательности)", "BPMN", "Иерархия моделей"],
          {"base": 0.15, "specialist": 0.14}),
    Topic("architecture", "Основные архитектурные практики",
          ["Стили архитектуры", "Клиент-сервер", "Монолит/распределённые", "Репликация/кластеры/бэкапы", "DDD/Event-Driven", "4+1/TOGAF"],
          {"base": 0.10, "specialist": 0.14}),
    Topic("data", "Хранение и обработка данных",
          ["Типы БД и СУБД", "Уровни моделирования", "ER-диаграммы", "SQL", "DDL", "ETL/витрины"],
          {"base": 0.12, "specialist": 0.12}),
    Topic("integration", "Интеграционные решения",
          ["TCP/IP/HTTP/HTTPS", "REST/OpenAPI", "SOAP/XSD", "Async (RabbitMQ/Kafka/AsyncAPI)", "DFD", "Виртуализация/контейнеры"],
          {"base": 0.10, "specialist": 0.12}),
    Topic("ux", "Проектирование пользовательских интерфейсов",
          ["Эргономика и эвристики", "Прототипы (low/high fidelity)", "CJM/карты эмпатии/A-B", "Роль СА в UI"],
          {"base": 0.06, "specialist": 0.06}),
    Topic("security", "Информационная безопасность",
          ["Аутентификация/идентификация", "OAuth/JWT/OpenID/cookies/API-key", "Авторизация и ролевая модель", "ЭЦП", "Уязвимости/мониторинг"],
          {"base": 0.06, "specialist": 0.06}),
    Topic("deployment", "Внедрение и сопровождение ПО",
          ["Виды тестирования", "Критерии качества ПО", "Управление дефектами", "ITIL/инциденты", "Релизы/пилотирование/обучение"],
          {"base": 0.06, "specialist": 0.04}),
]

_BY_ID = {t.id: t for t in TOPICS}


def get_topic(topic_id: str) -> Topic:
    return _BY_ID[topic_id]
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_topics.py -v`
Expected: PASS (5 passed). If the proportion-sum test fails, adjust the last topic's weight so each level sums to exactly 1.0.

- [ ] **Step 5: Commit**

```bash
git add backend/app/generation/__init__.py backend/app/generation/topics.py backend/tests/test_topics.py
git commit -m "feat: add topic registry with official proportions"
```

---

### Task 3: TopicPlanner — question counts per topic

**Files:**
- Create: `backend/app/generation/planner.py`
- Test: `backend/tests/test_planner.py`

- [ ] **Step 1: Write the failing test** — `backend/tests/test_planner.py`

```python
from app.generation.planner import plan_exam, plan_adaptive


def test_exam_plan_totals_match_level():
    base = plan_exam("base")
    spec = plan_exam("specialist")
    assert sum(c for _, c in base) == 80
    assert sum(c for _, c in spec) == 120


def test_exam_plan_covers_all_topics():
    plan = dict(plan_exam("specialist"))
    assert len(plan) == 10
    assert all(c >= 1 for c in plan.values())


def test_adaptive_plan_picks_weakest_topics():
    # competency: lower accuracy = weaker. Provide 4 topics; expect weakest first.
    competency = {
        "requirements": 0.9,
        "data": 0.2,
        "integration": 0.3,
        "modeling": 0.95,
    }
    plan = plan_adaptive(competency, total=10, threshold=0.6)
    chosen = {tid for tid, _ in plan}
    # Only topics below threshold (0.6) are eligible: data, integration.
    assert chosen == {"data", "integration"}
    assert sum(c for _, c in plan) == 10


def test_adaptive_falls_back_when_no_weak_topics():
    # All strong -> fall back to the weakest few regardless of threshold.
    competency = {"requirements": 0.9, "data": 0.85, "modeling": 0.95}
    plan = plan_adaptive(competency, total=6, threshold=0.6)
    assert sum(c for _, c in plan) == 6
    assert len(plan) >= 1


def test_adaptive_with_empty_competency_uses_even_distribution():
    plan = plan_adaptive({}, total=10, threshold=0.6)
    assert sum(c for _, c in plan) == 10
    assert len(plan) == 10  # all topics, evenly
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_planner.py -v`
Expected: FAIL (`ModuleNotFoundError: No module named 'app.generation.planner'`)

- [ ] **Step 3: Write `backend/app/generation/planner.py`**

```python
from app.generation.topics import TOPICS

LEVEL_TOTALS = {"base": 80, "specialist": 120}


def _largest_remainder(weights: dict[str, float], total: int) -> list[tuple[str, int]]:
    """Apportion `total` across keys by weight, guaranteeing the sum equals total."""
    raw = {k: w * total for k, w in weights.items()}
    floored = {k: int(v) for k, v in raw.items()}
    assigned = sum(floored.values())
    remainder = total - assigned
    # distribute leftover to the largest fractional parts
    frac_order = sorted(weights, key=lambda k: raw[k] - floored[k], reverse=True)
    for k in frac_order[:remainder]:
        floored[k] += 1
    return [(k, c) for k, c in floored.items() if c > 0]


def plan_exam(level: str) -> list[tuple[str, int]]:
    total = LEVEL_TOTALS[level]
    weights = {t.id: t.proportions[level] for t in TOPICS}
    plan = _largest_remainder(weights, total)
    # ensure every topic gets at least 1 (steal from the largest if needed)
    present = {tid for tid, _ in plan}
    missing = [t.id for t in TOPICS if t.id not in present]
    plan_d = dict(plan)
    for tid in missing:
        donor = max(plan_d, key=plan_d.get)
        plan_d[donor] -= 1
        plan_d[tid] = 1
    return [(tid, c) for tid, c in plan_d.items() if c > 0]


def plan_adaptive(
    competency: dict[str, float], total: int, threshold: float
) -> list[tuple[str, int]]:
    if not competency:
        # no history: even distribution across all topics
        weights = {t.id: 1 / len(TOPICS) for t in TOPICS}
        return _largest_remainder(weights, total)

    weak = {tid: acc for tid, acc in competency.items() if acc < threshold}
    if not weak:
        # fall back: take the 3 weakest by accuracy
        ranked = sorted(competency.items(), key=lambda kv: kv[1])[:3]
        weak = dict(ranked)

    # weight inversely to accuracy (weaker -> more questions); +0.01 avoids zero
    inv = {tid: (1.0 - acc) + 0.01 for tid, acc in weak.items()}
    s = sum(inv.values())
    weights = {tid: v / s for tid, v in inv.items()}
    return _largest_remainder(weights, total)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_planner.py -v`
Expected: PASS (5 passed)

- [ ] **Step 5: Commit**

```bash
git add backend/app/generation/planner.py backend/tests/test_planner.py
git commit -m "feat: add topic planner for exam and adaptive modes"
```

---

### Task 4: LLM I/O schemas

**Files:**
- Create: `backend/app/generation/schemas.py`
- Test: `backend/tests/test_generation_schemas.py`

- [ ] **Step 1: Write the failing test** — `backend/tests/test_generation_schemas.py`

```python
import pytest
from pydantic import ValidationError
from app.generation.schemas import GeneratedQuestion, ValidationVerdict


def test_single_question_requires_exactly_one_correct():
    q = GeneratedQuestion(
        topic_id="data", type="single", stem="Q?",
        artifact_kind="none", artifact_content=None,
        options=[{"key": "a", "text": "x"}, {"key": "b", "text": "y"}],
        correct_keys=["a"], explanation="because",
    )
    assert q.correct_keys == ["a"]


def test_single_with_multiple_correct_is_invalid():
    with pytest.raises(ValidationError):
        GeneratedQuestion(
            topic_id="data", type="single", stem="Q?",
            artifact_kind="none", artifact_content=None,
            options=[{"key": "a", "text": "x"}, {"key": "b", "text": "y"}],
            correct_keys=["a", "b"], explanation="because",
        )


def test_correct_keys_must_exist_in_options():
    with pytest.raises(ValidationError):
        GeneratedQuestion(
            topic_id="data", type="single", stem="Q?",
            artifact_kind="none", artifact_content=None,
            options=[{"key": "a", "text": "x"}],
            correct_keys=["z"], explanation="because",
        )


def test_validation_verdict():
    v = ValidationVerdict(valid=True, reason="ok")
    assert v.valid is True
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_generation_schemas.py -v`
Expected: FAIL (`ModuleNotFoundError: No module named 'app.generation.schemas'`)

- [ ] **Step 3: Write `backend/app/generation/schemas.py`**

```python
from typing import Literal

from pydantic import BaseModel, model_validator


class Option(BaseModel):
    key: str
    text: str


class GeneratedQuestion(BaseModel):
    topic_id: str
    type: Literal["single", "multi"]
    stem: str
    artifact_kind: Literal["none", "code", "json", "sql", "xml", "mermaid"]
    artifact_content: str | None
    options: list[Option]
    correct_keys: list[str]
    explanation: str

    @model_validator(mode="after")
    def _check(self):
        keys = {o.key for o in self.options}
        if len(self.options) < 2:
            raise ValueError("need at least 2 options")
        if not self.correct_keys:
            raise ValueError("need at least one correct key")
        if not set(self.correct_keys).issubset(keys):
            raise ValueError("correct_keys must reference existing options")
        if self.type == "single" and len(self.correct_keys) != 1:
            raise ValueError("single-choice must have exactly one correct key")
        if self.artifact_kind != "none" and not self.artifact_content:
            raise ValueError("artifact_content required when artifact_kind != none")
        return self


class GeneratedBatch(BaseModel):
    questions: list[GeneratedQuestion]


class ValidationVerdict(BaseModel):
    valid: bool
    reason: str
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_generation_schemas.py -v`
Expected: PASS (4 passed)

- [ ] **Step 5: Commit**

```bash
git add backend/app/generation/schemas.py backend/tests/test_generation_schemas.py
git commit -m "feat: add LLM I/O schemas with question validation"
```

---

### Task 5: Add TestSession and Question models

**Files:**
- Modify: `backend/app/db/models.py`
- Modify: `backend/alembic` (autogenerate migration)

- [ ] **Step 1: Append models to `backend/app/db/models.py`**

Add these imports if not present (merge with existing):

```python
from sqlalchemy import Boolean, Numeric, Text
from sqlalchemy.dialects.postgresql import JSONB
```

Append:

```python
class TestSession(Base):
    __tablename__ = "test_sessions"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=False, index=True
    )
    level: Mapped[str] = mapped_column(String, nullable=False)        # base | specialist
    mode: Mapped[str] = mapped_column(String, nullable=False)         # exam | adaptive
    status: Mapped[str] = mapped_column(String, nullable=False, default="generating")
    total_questions: Mapped[int] = mapped_column(Integer, nullable=False)
    generated_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    time_limit_sec: Mapped[int] = mapped_column(Integer, nullable=False)
    timer_started_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    score_percent: Mapped[float | None] = mapped_column(Numeric, nullable=True)
    passed: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    recommendation: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    finished_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )


class Question(Base):
    __tablename__ = "questions"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    session_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("test_sessions.id"), nullable=False, index=True
    )
    seq: Mapped[int] = mapped_column(Integer, nullable=False)
    topic_id: Mapped[str] = mapped_column(String, nullable=False)
    type: Mapped[str] = mapped_column(String, nullable=False)         # single | multi
    stem: Mapped[str] = mapped_column(Text, nullable=False)
    artifact_kind: Mapped[str] = mapped_column(String, nullable=False, default="none")
    artifact_content: Mapped[str | None] = mapped_column(Text, nullable=True)
    options: Mapped[list] = mapped_column(JSONB, nullable=False)
    correct_keys: Mapped[list] = mapped_column(JSONB, nullable=False)
    explanation: Mapped[str] = mapped_column(Text, nullable=False)
    validation_status: Mapped[str] = mapped_column(
        String, nullable=False, default="pending"
    )
```

- [ ] **Step 2: Sanity import check**

Run: `cd backend && . .venv/bin/activate && python -c "from app.db.models import TestSession, Question; print('ok')"`
Expected: prints `ok`

- [ ] **Step 3: Generate and apply migration**

Run:
```bash
alembic revision --autogenerate -m "test_sessions and questions"
alembic upgrade head
```
Expected: migration creates `test_sessions` and `questions`; upgrade succeeds.

- [ ] **Step 4: Commit**

```bash
git add backend/app/db/models.py backend/alembic/versions/
git commit -m "feat: add TestSession and Question models with migration"
```

---

### Task 6: OpenAIClient (the only networked module)

**Files:**
- Create: `backend/app/generation/openai_client.py`
- Test: `backend/tests/test_openai_client.py` (monkeypatches the SDK — no network)

The client exposes two async methods: `generate_batch(level, mode, plan_slice)` returning a `GeneratedBatch`, and `validate_question(q)` returning a `ValidationVerdict`. Both use the OpenAI structured-output API (`response_format` with a JSON schema). The system prompt is a module constant so prompt caching applies.

- [ ] **Step 1: Write the failing test** — `backend/tests/test_openai_client.py`

```python
import json
import pytest
from app.generation.openai_client import OpenAIClient, build_generation_system_prompt
from app.generation.schemas import GeneratedQuestion


class _FakeMessage:
    def __init__(self, content): self.content = content


class _FakeChoice:
    def __init__(self, content): self.message = _FakeMessage(content)


class _FakeCompletion:
    def __init__(self, content): self.choices = [_FakeChoice(content)]


class _FakeCompletions:
    def __init__(self, payload): self._payload = payload
    async def create(self, **kwargs):
        return _FakeCompletion(json.dumps(self._payload))


class _FakeChat:
    def __init__(self, payload): self.completions = _FakeCompletions(payload)


class _FakeOpenAI:
    def __init__(self, payload): self.chat = _FakeChat(payload)


def _valid_question_payload():
    return {
        "topic_id": "data", "type": "single", "stem": "Q?",
        "artifact_kind": "none", "artifact_content": None,
        "options": [{"key": "a", "text": "x"}, {"key": "b", "text": "y"}],
        "correct_keys": ["a"], "explanation": "because",
    }


@pytest.mark.asyncio
async def test_generate_batch_parses_questions():
    payload = {"questions": [_valid_question_payload(), _valid_question_payload()]}
    client = OpenAIClient(api_key="x", gen_model="g", validate_model="v",
                          _client=_FakeOpenAI(payload))
    batch = await client.generate_batch("specialist", "exam", [("data", 2)])
    assert len(batch.questions) == 2
    assert isinstance(batch.questions[0], GeneratedQuestion)


@pytest.mark.asyncio
async def test_validate_question_returns_verdict():
    payload = {"valid": True, "reason": "looks correct"}
    client = OpenAIClient(api_key="x", gen_model="g", validate_model="v",
                          _client=_FakeOpenAI(payload))
    q = GeneratedQuestion(**_valid_question_payload())
    verdict = await client.validate_question(q)
    assert verdict.valid is True


def test_system_prompt_mentions_quality_rules():
    p = build_generation_system_prompt()
    assert "однознач" in p.lower() or "ровно один" in p.lower()
    assert "mermaid" in p.lower()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_openai_client.py -v`
Expected: FAIL (`ModuleNotFoundError: No module named 'app.generation.openai_client'`)

- [ ] **Step 3: Write `backend/app/generation/openai_client.py`**

```python
import json

from openai import AsyncOpenAI

from app.generation.schemas import GeneratedBatch, GeneratedQuestion, ValidationVerdict
from app.generation.topics import get_topic


def build_generation_system_prompt() -> str:
    return (
        "Ты — экзаменатор сертификации системных аналитиков IBS. "
        "Генерируй вопросы строго закрытого типа (single или multi choice) на русском языке. "
        "Требования к качеству:\n"
        "- Вопрос однозначен; для single-choice верен РОВНО ОДИН вариант.\n"
        "- 4 правдоподобных варианта; дистракторы — типичные ошибки из смежных тем, "
        "не случайный мусор.\n"
        "- Если нужен артефакт — встрой его в вопрос: код/JSON/SQL/XML как текст, "
        "диаграммы — как Mermaid-код (artifact_kind='mermaid'). Никаких внешних ресурсов.\n"
        "- К каждому вопросу — короткое объяснение, почему верный ответ верен.\n"
        "Верни СТРОГО JSON по заданной схеме."
    )


def _generation_schema() -> dict:
    return {
        "type": "object",
        "properties": {
            "questions": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "topic_id": {"type": "string"},
                        "type": {"enum": ["single", "multi"]},
                        "stem": {"type": "string"},
                        "artifact_kind": {
                            "enum": ["none", "code", "json", "sql", "xml", "mermaid"]
                        },
                        "artifact_content": {"type": ["string", "null"]},
                        "options": {
                            "type": "array",
                            "items": {
                                "type": "object",
                                "properties": {
                                    "key": {"type": "string"},
                                    "text": {"type": "string"},
                                },
                                "required": ["key", "text"],
                            },
                        },
                        "correct_keys": {"type": "array", "items": {"type": "string"}},
                        "explanation": {"type": "string"},
                    },
                    "required": [
                        "topic_id", "type", "stem", "artifact_kind",
                        "artifact_content", "options", "correct_keys", "explanation",
                    ],
                },
            }
        },
        "required": ["questions"],
    }


def _verdict_schema() -> dict:
    return {
        "type": "object",
        "properties": {
            "valid": {"type": "boolean"},
            "reason": {"type": "string"},
        },
        "required": ["valid", "reason"],
    }


class OpenAIClient:
    def __init__(self, api_key, gen_model, validate_model, _client=None):
        self.gen_model = gen_model
        self.validate_model = validate_model
        self._client = _client or AsyncOpenAI(api_key=api_key)

    async def generate_batch(self, level, mode, plan_slice):
        # plan_slice: list[(topic_id, count)]
        topic_lines = []
        for tid, count in plan_slice:
            t = get_topic(tid)
            topic_lines.append(
                f"- {count} вопрос(ов) по теме '{t.title}' "
                f"(подтемы: {', '.join(t.subtopics)})"
            )
        user_prompt = (
            f"Уровень: {level}. Сгенерируй вопросы:\n" + "\n".join(topic_lines)
        )
        resp = await self._client.chat.completions.create(
            model=self.gen_model,
            messages=[
                {"role": "system", "content": build_generation_system_prompt()},
                {"role": "user", "content": user_prompt},
            ],
            response_format={
                "type": "json_schema",
                "json_schema": {
                    "name": "question_batch",
                    "schema": _generation_schema(),
                    "strict": False,
                },
            },
        )
        data = json.loads(resp.choices[0].message.content)
        return GeneratedBatch(**data)

    async def validate_question(self, q: GeneratedQuestion) -> ValidationVerdict:
        prompt = (
            "Проверь корректность тренировочного вопроса по сертификации СА. "
            "Верни valid=false, если: вопрос двусмысленный, помеченный верный ответ "
            "неверен, дистрактор тоже верен, или артефакт не соответствует вопросу.\n\n"
            f"ВОПРОС:\n{q.model_dump_json(indent=2)}"
        )
        resp = await self._client.chat.completions.create(
            model=self.validate_model,
            messages=[
                {"role": "system", "content": "Ты — строгий рецензент тестовых вопросов."},
                {"role": "user", "content": prompt},
            ],
            response_format={
                "type": "json_schema",
                "json_schema": {
                    "name": "verdict",
                    "schema": _verdict_schema(),
                    "strict": False,
                },
            },
        )
        data = json.loads(resp.choices[0].message.content)
        return ValidationVerdict(**data)
```

> NOTE on the API surface: this uses `chat.completions.create` with `response_format=json_schema`, which is stable as of the January 2026 knowledge cutoff. At implementation time, confirm the current OpenAI Python SDK signature and `response_format` shape against the live docs; if the SDK has moved to a `responses` API or `client.chat.completions.parse`, adapt these two methods only — the rest of the subsystem depends solely on `generate_batch`/`validate_question` returning the Pydantic models, so changes stay isolated here.

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_openai_client.py -v`
Expected: PASS (3 passed)

- [ ] **Step 5: Commit**

```bash
git add backend/app/generation/openai_client.py backend/tests/test_openai_client.py
git commit -m "feat: add OpenAI client for batch generation and validation"
```

---

### Task 7: Generator — orchestrate batches, validate, persist

**Files:**
- Create: `backend/app/generation/generator.py`
- Test: `backend/tests/test_generator.py` (uses a fake client)

The `Generator.run(session_id)` loads the session, builds the plan, generates in batches, validates each question, persists `passed` ones with incrementing `seq`/`generated_count`, retries rejected slots up to 2×, and on completion sets `status=ready` + `timer_started_at`. On unrecoverable batch failure it sets `status=failed`.

- [ ] **Step 1: Write the failing test** — `backend/tests/test_generator.py`

```python
import datetime as dt
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
    """Returns N questions per batch; marks every question valid."""
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
async def test_generator_retries_rejected_questions(db_session):
    s = await _make_session(db_session, total=3)
    # reject the first 2 validations, then accept -> generator must retry to reach 3
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_generator.py -v`
Expected: FAIL (`ModuleNotFoundError: No module named 'app.generation.generator'`)

- [ ] **Step 3: Write `backend/app/generation/generator.py`**

```python
import asyncio
import datetime as dt

from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Question, TestSession


class Generator:
    def __init__(self, session: AsyncSession, client, batch_size=10,
                 max_slot_retries=2, max_batch_retries=3):
        self.db = session
        self.client = client
        self.batch_size = batch_size
        self.max_slot_retries = max_slot_retries
        self.max_batch_retries = max_batch_retries

    async def run(self, session_id, plan):
        session = await self.db.get(TestSession, session_id)
        if session is None:
            return
        try:
            seq = session.generated_count
            # remaining[topic] = how many still needed
            remaining = {tid: count for tid, count in plan}
            slot_attempts = 0
            while sum(remaining.values()) > 0:
                slice_ = self._next_slice(remaining)
                batch = await self._generate_with_retry(
                    session.level, session.mode, slice_
                )
                for q in batch.questions:
                    if remaining.get(q.topic_id, 0) <= 0:
                        continue
                    verdict = await self.client.validate_question(q)
                    if not verdict.valid:
                        continue
                    seq += 1
                    self.db.add(Question(
                        session_id=session.id, seq=seq, topic_id=q.topic_id,
                        type=q.type, stem=q.stem, artifact_kind=q.artifact_kind,
                        artifact_content=q.artifact_content,
                        options=[o.model_dump() for o in q.options],
                        correct_keys=q.correct_keys, explanation=q.explanation,
                        validation_status="passed",
                    ))
                    remaining[q.topic_id] -= 1
                    session.generated_count = seq
                await self.db.commit()
                # guard against infinite loops if validation keeps rejecting
                slot_attempts += 1
                if slot_attempts > (session.total_questions + 1) * (self.max_slot_retries + 1):
                    break

            if sum(remaining.values()) > 0:
                # could not fill the pool
                session.status = "failed"
                await self.db.commit()
                return

            session.status = "ready"
            session.timer_started_at = dt.datetime.now(dt.timezone.utc)
            await self.db.commit()
        except Exception:
            session.status = "failed"
            await self.db.commit()

    def _next_slice(self, remaining):
        slice_ = []
        budget = self.batch_size
        for tid, need in remaining.items():
            if need <= 0:
                continue
            take = min(need, budget)
            if take <= 0:
                break
            slice_.append((tid, take))
            budget -= take
            if budget <= 0:
                break
        return slice_

    async def _generate_with_retry(self, level, mode, slice_):
        delay = 0.0
        last = None
        for attempt in range(self.max_batch_retries):
            try:
                return await self.client.generate_batch(level, mode, slice_)
            except Exception as e:  # noqa: BLE001
                last = e
                if delay:
                    await asyncio.sleep(delay)
                delay = (delay or 0.1) * 2
        raise last
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_generator.py -v`
Expected: PASS (3 passed)

- [ ] **Step 5: Commit**

```bash
git add backend/app/generation/generator.py backend/tests/test_generator.py
git commit -m "feat: add generator orchestration with validation and retries"
```

---

### Task 8: Session service + lifecycle

**Files:**
- Create: `backend/app/generation/service.py`
- Test: covered by API tests in Task 9 (service is thin; integration-tested end to end)

`create_session` enforces the daily limit (using Subsystem 1's helpers), computes the plan, persists the session, increments usage, and kicks off background generation. `get_status` and `list_ready_questions` are read helpers.

- [ ] **Step 1: Write `backend/app/generation/service.py`**

```python
import datetime as dt

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import service as auth_service
from app.db.models import Question, TestSession
from app.generation.planner import LEVEL_TOTALS, plan_adaptive, plan_exam

LEVEL_TIME_LIMITS = {"base": 120 * 60, "specialist": 180 * 60}


class DailyLimitExceeded(Exception):
    pass


async def _load_competency(db: AsyncSession, user_id, level) -> dict[str, float]:
    # topic_competency table is created in Subsystem 3. Until then (or when the
    # user has no history) this returns {} and the planner uses even distribution.
    try:
        from app.db.models import TopicCompetency  # type: ignore
    except ImportError:
        return {}
    rows = (
        await db.execute(
            select(TopicCompetency).where(
                TopicCompetency.user_id == user_id,
                TopicCompetency.level == level,
            )
        )
    ).scalars().all()
    return {r.topic_id: float(r.accuracy) for r in rows}


async def create_session(
    db: AsyncSession, user_id, level: str, mode: str,
    daily_limit: int, adaptive_count: int, weak_threshold: float,
) -> tuple[TestSession, list]:
    today = dt.date.today()
    if not await auth_service.is_within_daily_limit(db, user_id, today, daily_limit):
        raise DailyLimitExceeded()

    if mode == "exam":
        plan = plan_exam(level)
        total = LEVEL_TOTALS[level]
    else:
        competency = await _load_competency(db, user_id, level)
        plan = plan_adaptive(competency, total=adaptive_count, threshold=weak_threshold)
        total = adaptive_count

    session = TestSession(
        user_id=user_id, level=level, mode=mode, status="generating",
        total_questions=total, generated_count=0,
        time_limit_sec=LEVEL_TIME_LIMITS[level],
    )
    db.add(session)
    await db.commit()
    await db.refresh(session)
    await auth_service.increment_usage(db, user_id, today)
    return session, plan


async def get_status(db: AsyncSession, session_id) -> TestSession | None:
    return await db.get(TestSession, session_id)


async def list_ready_questions(db: AsyncSession, session_id) -> list[Question]:
    rows = (
        await db.execute(
            select(Question)
            .where(Question.session_id == session_id)
            .order_by(Question.seq)
        )
    ).scalars().all()
    return rows
```

- [ ] **Step 2: Sanity import check**

Run: `python -c "from app.generation.service import create_session, get_status; print('ok')"`
Expected: prints `ok`

- [ ] **Step 3: Commit**

```bash
git add backend/app/generation/service.py
git commit -m "feat: add session lifecycle service with daily-limit gate"
```

---

### Task 9: Sessions router + background generation wiring

**Files:**
- Create: `backend/app/generation/router.py`
- Modify: `backend/app/main.py` (include router)
- Test: `backend/tests/test_sessions_api.py`

The router creates a session, launches generation as an asyncio background task using a fresh DB session (so it outlives the request), and exposes status + questions. The question payload sent to the frontend **omits `correct_keys`** (so answers can't be read off the wire) — those are revealed only at results time (Subsystem 3).

- [ ] **Step 1: Write the failing test** — `backend/tests/test_sessions_api.py`

```python
import asyncio
import pytest

from app.generation.schemas import GeneratedBatch, GeneratedQuestion, ValidationVerdict


def _q(topic_id="data"):
    return GeneratedQuestion(
        topic_id=topic_id, type="single", stem="Q?",
        artifact_kind="none", artifact_content=None,
        options=[{"key": "a", "text": "x"}, {"key": "b", "text": "y"}],
        correct_keys=["a"], explanation="because",
    )


class FakeClient:
    async def generate_batch(self, level, mode, plan_slice):
        n = sum(c for _, c in plan_slice)
        return GeneratedBatch(questions=[_q(plan_slice[0][0]) for _ in range(n)])

    async def validate_question(self, q):
        return ValidationVerdict(valid=True, reason="ok")


@pytest.fixture(autouse=True)
def _patch_client(monkeypatch):
    # Force the router to use the fake client instead of real OpenAI.
    from app.generation import router as gen_router
    monkeypatch.setattr(gen_router, "build_openai_client", lambda: FakeClient())


async def _register(client, login="kate"):
    return await client.post(
        "/auth/register",
        json={"login": login, "password": "pw12345", "access_code": "TEST-CODE"},
    )


@pytest.mark.asyncio
async def test_create_adaptive_session_generates_and_becomes_ready(client):
    await _register(client, "kate")
    resp = await client.post("/sessions", json={"level": "base", "mode": "adaptive"})
    assert resp.status_code == 201
    sid = resp.json()["id"]

    # poll status until ready (background task fills the small adaptive pool)
    for _ in range(50):
        st = await client.get(f"/sessions/{sid}/status")
        body = st.json()
        if body["status"] == "ready":
            break
        await asyncio.sleep(0.05)
    assert body["status"] == "ready"
    assert body["generated_count"] == body["total_questions"]

    qs = await client.get(f"/sessions/{sid}/questions")
    items = qs.json()
    assert len(items) == body["total_questions"]
    # correct_keys must NOT leak to the client
    assert "correct_keys" not in items[0]
    assert "explanation" not in items[0]
    assert {"id", "seq", "topic_id", "type", "stem", "options"} <= set(items[0].keys())


@pytest.mark.asyncio
async def test_create_session_requires_auth(client):
    await client.post("/auth/logout")
    resp = await client.post("/sessions", json={"level": "base", "mode": "exam"})
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_daily_limit_blocks_after_threshold(client):
    # conftest sets DAILY_SESSION_LIMIT=3
    await _register(client, "leo")
    for _ in range(3):
        r = await client.post("/sessions", json={"level": "base", "mode": "adaptive"})
        assert r.status_code == 201
    blocked = await client.post("/sessions", json={"level": "base", "mode": "adaptive"})
    assert blocked.status_code == 429
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_sessions_api.py -v`
Expected: FAIL (`ModuleNotFoundError: No module named 'app.generation.router'`)

- [ ] **Step 3: Write `backend/app/generation/router.py`**

```python
import asyncio
import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.db.base import SessionLocal, get_session
from app.db.models import User
from app.deps import current_user
from app.generation import service
from app.generation.generator import Generator
from app.generation.openai_client import OpenAIClient

router = APIRouter(tags=["sessions"])


class CreateSessionRequest(BaseModel):
    level: str  # base | specialist
    mode: str   # exam | adaptive


def build_openai_client():
    s = get_settings()
    return OpenAIClient(
        api_key=s.openai_api_key,
        gen_model=s.openai_gen_model,
        validate_model=s.openai_validate_model,
    )


async def _run_generation(session_id, plan):
    # Fresh DB session so generation outlives the originating request.
    settings = get_settings()
    async with SessionLocal() as db:
        gen = Generator(db, build_openai_client(), batch_size=settings.generation_batch_size)
        await gen.run(session_id, plan)


@router.post("/sessions", status_code=status.HTTP_201_CREATED)
async def create_session(
    req: CreateSessionRequest,
    user: User = Depends(current_user),
    db: AsyncSession = Depends(get_session),
):
    if req.level not in ("base", "specialist") or req.mode not in ("exam", "adaptive"):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Invalid level or mode")
    settings = get_settings()
    try:
        session, plan = await service.create_session(
            db, user.id, req.level, req.mode,
            daily_limit=settings.daily_session_limit,
            adaptive_count=settings.adaptive_question_count,
            weak_threshold=settings.weak_topic_threshold,
        )
    except service.DailyLimitExceeded:
        raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS, "Daily session limit reached")

    asyncio.create_task(_run_generation(session.id, plan))
    return {"id": str(session.id), "status": session.status,
            "total_questions": session.total_questions}


@router.get("/sessions/{session_id}/status")
async def session_status(
    session_id: uuid.UUID,
    user: User = Depends(current_user),
    db: AsyncSession = Depends(get_session),
):
    s = await service.get_status(db, session_id)
    if s is None or s.user_id != user.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Session not found")
    return {
        "id": str(s.id), "status": s.status, "level": s.level, "mode": s.mode,
        "total_questions": s.total_questions, "generated_count": s.generated_count,
        "time_limit_sec": s.time_limit_sec,
        "timer_started_at": s.timer_started_at.isoformat() if s.timer_started_at else None,
    }


@router.get("/sessions/{session_id}/questions")
async def session_questions(
    session_id: uuid.UUID,
    user: User = Depends(current_user),
    db: AsyncSession = Depends(get_session),
):
    s = await service.get_status(db, session_id)
    if s is None or s.user_id != user.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Session not found")
    questions = await service.list_ready_questions(db, session_id)
    # NEVER expose correct_keys or explanation before results.
    return [
        {
            "id": str(q.id), "seq": q.seq, "topic_id": q.topic_id, "type": q.type,
            "stem": q.stem, "artifact_kind": q.artifact_kind,
            "artifact_content": q.artifact_content, "options": q.options,
        }
        for q in questions
    ]
```

- [ ] **Step 4: Include the router in `backend/app/main.py`**

Add the import and `include_router` call in `create_app`:

```python
from app.generation.router import router as sessions_router
# ... inside create_app(), after auth_router:
    app.include_router(sessions_router)
```

- [ ] **Step 5: Run test to verify it passes**

Run: `pytest tests/test_sessions_api.py -v`
Expected: PASS (3 passed). The background task runs against the test DB because the override and `SessionLocal` both point at `antests_test` (conftest sets `DATABASE_URL` before app import).

> NOTE: If the background task can't see committed rows because conftest's single shared `db_session` differs from `SessionLocal()`, the test polls via the request path which uses the override `db_session`; the generator commits via its own `SessionLocal()` to the same physical `antests_test` DB, so rows are visible after commit. If isolation causes flakiness, the implementer may switch the test to assert on a direct DB query instead of the HTTP poll — but try the HTTP poll first.

- [ ] **Step 6: Commit**

```bash
git add backend/app/generation/router.py backend/app/main.py backend/tests/test_sessions_api.py
git commit -m "feat: add sessions API with background generation"
```

---

### Task 10: Final verification of Subsystem 2

**Files:** none

- [ ] **Step 1: Run the entire suite**

Run: `cd backend && . .venv/bin/activate && pytest -v`
Expected: ALL tests pass (Subsystem 1 + 2). Report the count.

- [ ] **Step 2: Lint**

Run: `ruff check app tests`
Expected: no errors.

- [ ] **Step 3: Optional real-OpenAI smoke (only if a real key is set)**

With a real `OPENAI_API_KEY` in `.env`, start the server and create an adaptive session, then poll status until `ready` and fetch questions. Confirm questions are well-formed Russian single/multi-choice with explanations hidden from the wire. **Skip if no key — the fake-client tests already prove the pipeline.**

- [ ] **Step 4: Confirm success criteria:**
  - Full `pytest` green.
  - `alembic upgrade head` applied `test_sessions` + `questions`.
  - Generation pipeline (planner → client → generator → API) works against the fake client end to end, including retry-on-reject and fail-on-error paths.
  - `correct_keys`/`explanation` never appear in the `/questions` payload.

---

## Self-Review Notes

Checked against spec sections 2 (decisions 1–9), 4 (Generation subsystem), 5 (`test_sessions`, `questions` models match), 6 (full generation/validation/streaming flow: batches ✓, self-validation with cheap model ✓, retry on reject ✓, status=ready + timer_started_at on completion ✓, status=failed on error ✓), and 7 (batch size configurable). Daily rate-limit gate from Subsystem 1 is consumed here at session creation (429). Adaptive mode reads `topic_competency` defensively (returns `{}` if the table/profile is absent, since it's created in Subsystem 3) and the planner falls back to even distribution — so this subsystem is independently testable before Subsystem 3 exists. No placeholders: every step has complete code. Type consistency: `generate_batch`/`validate_question` signatures match between `OpenAIClient`, the fakes, and `Generator`; `GeneratedQuestion`/`GeneratedBatch`/`ValidationVerdict` field names align across schemas, client, and generator; `plan_exam`/`plan_adaptive`/`LEVEL_TOTALS`/`LEVEL_TIME_LIMITS` names consistent across planner and service. The one cross-subsystem coupling (`TopicCompetency` import) is guarded with try/except so it cannot break this subsystem's tests. The `correct_keys` omission in the questions API is a deliberate security boundary noted in the test.
```
