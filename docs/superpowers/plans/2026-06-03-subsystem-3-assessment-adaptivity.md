# Subsystem 3: Assessment + Adaptivity — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let a user submit answers, finish a test, get deterministically scored against the stored correct keys, update a per-topic competency profile (which powers adaptive mode), and receive a results payload — per-question review with explanations, topic breakdown, and a final LLM recommendation.

**Architecture:** Answers are persisted as the user goes (`answers` table). On finish, a pure `scoring` module compares each answer to the question's `correct_keys` (set equality — exact match for single and multi), computes the percent and pass/fail against the level threshold, and writes per-question correctness. A `TopicCompetency` model accumulates per-(user, level, topic) accuracy across all finished tests; finishing a test upserts into it. A `recommendation` module makes one LLM call summarizing weak topics into advice. A results endpoint returns the full review payload — and only now reveals `correct_keys` + `explanation`. Once `TopicCompetency` exists, Subsystem 2's `_load_competency` stub starts returning real data, so adaptive mode comes alive end to end.

**Tech Stack:** Builds on Subsystems 1 & 2. Reuses `OpenAIClient` (extended with a `recommend` method), the existing models, FastAPI router patterns, pytest + fake-client tests. No new third-party deps.

**Depends on:** Subsystems 1 & 2 complete (auth, db, `TestSession`, `Question`, generation, sessions router). All must be green.

---

## File Structure

```
backend/app/
  db/models.py                    # MODIFY: add Answer + TopicCompetency models
  generation/openai_client.py     # MODIFY: add recommend() method + schema
  assessment/
    __init__.py
    scoring.py                    # pure scoring: is_answer_correct, score_session
    competency.py                 # update_competency_profile (upsert accuracy)
    recommendation.py             # build weak-topic recommendation (LLM)
    schemas.py                    # API request/response models
    service.py                    # submit_answer, finish_session, get_results
    router.py                     # POST /sessions/{id}/answers, POST /sessions/{id}/finish, GET /sessions/{id}/results
backend/tests/
  test_scoring.py
  test_competency.py
  test_assessment_service.py
  test_assessment_api.py
  test_recommendation.py
```

`scoring.py` and `competency.py` are pure/DB-only logic, independently testable. `recommendation.py` is the only module needing the LLM (faked in tests). `router.py` is thin HTTP glue. After this subsystem, also un-stub Subsystem 2's `_load_competency` (Task 9).

---

### Task 1: Add Answer and TopicCompetency models + migration

**Files:**
- Modify: `backend/app/db/models.py`
- Create: migration under `backend/alembic/versions/`

- [ ] **Step 1: Append models to `backend/app/db/models.py`**

The imports needed (`UUID`, `JSONB`, `Boolean`, `DateTime`, `ForeignKey`, `Integer`, `Numeric`, `String`, `func`, `Mapped`, `mapped_column`, `uuid`, `datetime`, `UniqueConstraint`) are already imported by the existing file from Subsystems 1–2. Verify `UniqueConstraint` is imported (it was used by an earlier DailyUsage version but may have been removed); if missing, add it to the `from sqlalchemy import ...` line. Then append:

```python
class Answer(Base):
    __tablename__ = "answers"
    __table_args__ = (
        UniqueConstraint("session_id", "question_id", name="uq_answer_session_question"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    session_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("test_sessions.id"), nullable=False, index=True
    )
    question_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("questions.id"), nullable=False, index=True
    )
    selected_keys: Mapped[list] = mapped_column(JSONB, nullable=False)
    is_correct: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    answered_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class TopicCompetency(Base):
    __tablename__ = "topic_competency"

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), primary_key=True
    )
    topic_id: Mapped[str] = mapped_column(String, primary_key=True)
    level: Mapped[str] = mapped_column(String, primary_key=True)
    total_answered: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    total_correct: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    accuracy: Mapped[float] = mapped_column(Numeric, nullable=False, default=0)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
```

> NOTE: `TopicCompetency` has a composite PK `(user_id, topic_id, level)` — the profile is per-level, matching the spec.

- [ ] **Step 2: Sanity import**

Run: `cd backend && . .venv/bin/activate && python -c "from app.db.models import Answer, TopicCompetency; print('ok')"` (env from `.env`)
Expected: `ok`

- [ ] **Step 3: Generate + apply migration**

Run:
```bash
alembic revision --autogenerate -m "answers and topic_competency"
alembic upgrade head
```
Open the generated migration and CONFIRM it creates `answers` and `topic_competency` with the right columns/FKs/PK. Then:
`docker exec antests-pg psql -U postgres -d antests -c "\dt"` should now also list `answers` and `topic_competency`.

- [ ] **Step 4: Commit**

```bash
git add backend/app/db/models.py backend/alembic/versions/
git commit -m "feat: add Answer and TopicCompetency models with migration"
```

---

### Task 2: Scoring (pure logic)

**Files:**
- Create: `backend/app/assessment/__init__.py` (empty)
- Create: `backend/app/assessment/scoring.py`
- Test: `backend/tests/test_scoring.py`

- [ ] **Step 1: Write the failing test** — `backend/tests/test_scoring.py`

```python
from app.assessment.scoring import is_answer_correct, score


def test_single_correct():
    assert is_answer_correct(["a"], ["a"]) is True


def test_single_wrong():
    assert is_answer_correct(["b"], ["a"]) is False


def test_multi_exact_match_correct():
    assert is_answer_correct(["a", "c"], ["c", "a"]) is True  # order-independent


def test_multi_partial_is_wrong():
    # exact-match scoring: missing one correct key = wrong
    assert is_answer_correct(["a"], ["a", "c"]) is False


def test_multi_extra_is_wrong():
    assert is_answer_correct(["a", "b", "c"], ["a", "c"]) is False


def test_empty_selection_is_wrong():
    assert is_answer_correct([], ["a"]) is False


def test_score_percent_and_pass():
    # 7 of 10 correct = 70%
    result = score(correct_count=7, total=10, threshold_percent=70)
    assert result.percent == 70.0
    assert result.passed is True


def test_score_below_threshold_fails():
    result = score(correct_count=7, total=10, threshold_percent=75)
    assert result.percent == 70.0
    assert result.passed is False


def test_score_zero_total_is_safe():
    result = score(correct_count=0, total=0, threshold_percent=70)
    assert result.percent == 0.0
    assert result.passed is False
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_scoring.py -v`
Expected: FAIL (`ModuleNotFoundError: No module named 'app.assessment'`)

- [ ] **Step 3: Create empty `backend/app/assessment/__init__.py`, then write `backend/app/assessment/scoring.py`**

```python
from dataclasses import dataclass


def is_answer_correct(selected_keys: list[str], correct_keys: list[str]) -> bool:
    """Exact-match scoring for both single and multi choice: the selected set
    must equal the correct set exactly (no partial credit)."""
    return set(selected_keys) == set(correct_keys)


@dataclass(frozen=True)
class ScoreResult:
    percent: float
    passed: bool


def score(correct_count: int, total: int, threshold_percent: float) -> ScoreResult:
    percent = round(100.0 * correct_count / total, 2) if total > 0 else 0.0
    return ScoreResult(percent=percent, passed=percent >= threshold_percent)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_scoring.py -v`
Expected: PASS (9 passed)

- [ ] **Step 5: Commit**

```bash
git add backend/app/assessment/__init__.py backend/app/assessment/scoring.py backend/tests/test_scoring.py
git commit -m "feat: add deterministic answer scoring"
```

---

### Task 3: Competency profile update (DB logic)

**Files:**
- Create: `backend/app/assessment/competency.py`
- Test: `backend/tests/test_competency.py`

- [ ] **Step 1: Write the failing test** — `backend/tests/test_competency.py`

```python
import uuid

import pytest
from sqlalchemy import select

from app.assessment.competency import update_competency, load_competency
from app.db.models import TopicCompetency, User


async def _user(db):
    u = User(login=f"u{uuid.uuid4().hex[:8]}", password_hash="x")
    db.add(u)
    await db.commit()
    await db.refresh(u)
    return u


@pytest.mark.asyncio
async def test_update_creates_rows_and_computes_accuracy(db_session):
    u = await _user(db_session)
    # per-topic (answered, correct) tallies from one finished test
    await update_competency(
        db_session, u.id, level="base",
        per_topic={"data": (4, 2), "modeling": (2, 2)},
    )
    rows = (await db_session.execute(
        select(TopicCompetency).where(TopicCompetency.user_id == u.id))).scalars().all()
    by_topic = {r.topic_id: r for r in rows}
    assert float(by_topic["data"].accuracy) == 0.5
    assert by_topic["data"].total_answered == 4
    assert float(by_topic["modeling"].accuracy) == 1.0


@pytest.mark.asyncio
async def test_update_accumulates_across_tests(db_session):
    u = await _user(db_session)
    await update_competency(db_session, u.id, "base", {"data": (4, 2)})
    await update_competency(db_session, u.id, "base", {"data": (6, 6)})
    row = (await db_session.execute(
        select(TopicCompetency).where(
            TopicCompetency.user_id == u.id, TopicCompetency.topic_id == "data"
        ))).scalar_one()
    # 8 correct of 10 total = 0.8
    assert row.total_answered == 10
    assert row.total_correct == 8
    assert float(row.accuracy) == 0.8


@pytest.mark.asyncio
async def test_levels_are_separate(db_session):
    u = await _user(db_session)
    await update_competency(db_session, u.id, "base", {"data": (2, 2)})
    await update_competency(db_session, u.id, "specialist", {"data": (2, 0)})
    base = await load_competency(db_session, u.id, "base")
    spec = await load_competency(db_session, u.id, "specialist")
    assert base["data"] == 1.0
    assert spec["data"] == 0.0


@pytest.mark.asyncio
async def test_load_empty_returns_empty_dict(db_session):
    u = await _user(db_session)
    assert await load_competency(db_session, u.id, "base") == {}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_competency.py -v`
Expected: FAIL (`ModuleNotFoundError: No module named 'app.assessment.competency'`)

- [ ] **Step 3: Write `backend/app/assessment/competency.py`**

```python
import datetime as dt
import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import TopicCompetency


async def update_competency(
    session: AsyncSession,
    user_id: uuid.UUID,
    level: str,
    per_topic: dict[str, tuple[int, int]],
) -> None:
    """Accumulate per-topic (answered, correct) tallies into the user's
    competency profile for a level, recomputing accuracy. Upsert per topic."""
    now = dt.datetime.now(dt.timezone.utc)
    for topic_id, (answered, correct) in per_topic.items():
        row = (
            await session.execute(
                select(TopicCompetency).where(
                    TopicCompetency.user_id == user_id,
                    TopicCompetency.topic_id == topic_id,
                    TopicCompetency.level == level,
                )
            )
        ).scalar_one_or_none()
        if row is None:
            row = TopicCompetency(
                user_id=user_id, topic_id=topic_id, level=level,
                total_answered=0, total_correct=0, accuracy=0,
            )
            session.add(row)
        row.total_answered += answered
        row.total_correct += correct
        row.accuracy = (
            row.total_correct / row.total_answered if row.total_answered > 0 else 0
        )
        row.updated_at = now
    await session.commit()


async def load_competency(
    session: AsyncSession, user_id: uuid.UUID, level: str
) -> dict[str, float]:
    rows = (
        await session.execute(
            select(TopicCompetency).where(
                TopicCompetency.user_id == user_id,
                TopicCompetency.level == level,
            )
        )
    ).scalars().all()
    return {r.topic_id: float(r.accuracy) for r in rows}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_competency.py -v`
Expected: PASS (4 passed)

- [ ] **Step 5: Commit**

```bash
git add backend/app/assessment/competency.py backend/tests/test_competency.py
git commit -m "feat: add topic competency profile accumulation"
```

---

### Task 4: Recommendation method on OpenAIClient

**Files:**
- Modify: `backend/app/generation/openai_client.py`
- Create: `backend/app/assessment/recommendation.py`
- Test: `backend/tests/test_recommendation.py`

- [ ] **Step 1: Write the failing test** — `backend/tests/test_recommendation.py`

```python
import json
import pytest
from app.assessment.recommendation import build_recommendation


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


class FakeOpenAIClient:
    def __init__(self, text):
        self._text = text
    async def recommend(self, level, weak_topics):
        return self._text


@pytest.mark.asyncio
async def test_build_recommendation_uses_weak_topics():
    fake = FakeOpenAIClient("Подтяните SQL и интеграции.")
    text = await build_recommendation(
        fake, level="base",
        topic_accuracy={"data": 0.3, "integration": 0.4, "requirements": 0.9},
        threshold=0.6,
    )
    assert "SQL" in text or text  # non-empty advice returned


@pytest.mark.asyncio
async def test_build_recommendation_no_weak_topics_returns_praise():
    fake = FakeOpenAIClient("SHOULD NOT BE CALLED")
    text = await build_recommendation(
        fake, level="base",
        topic_accuracy={"data": 0.9, "modeling": 0.95},
        threshold=0.6,
    )
    # When nothing is below threshold, we short-circuit without an LLM call.
    assert "SHOULD NOT BE CALLED" not in text
    assert len(text) > 0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_recommendation.py -v`
Expected: FAIL (`ModuleNotFoundError: No module named 'app.assessment.recommendation'`)

- [ ] **Step 3: Add a `recommend` method to `OpenAIClient` in `backend/app/generation/openai_client.py`**

Append this method to the `OpenAIClient` class (after `validate_question`):

```python
    async def recommend(self, level: str, weak_topics: list[tuple[str, float]]) -> str:
        lines = [
            f"- {get_topic(tid).title}: {round(acc * 100)}% верных"
            for tid, acc in weak_topics
        ]
        prompt = (
            "Дай студенту краткую персональную рекомендацию по подготовке к "
            f"сертификации (уровень {level}). Слабые темы (точность ниже порога):\n"
            + "\n".join(lines)
            + "\n\nДля каждой слабой темы — что повторить и на что обратить внимание. "
            "Пиши по-русски, дружелюбно и конкретно, без воды."
        )
        resp = await self._client.chat.completions.create(
            model=self.gen_model,
            messages=[
                {"role": "system",
                 "content": "Ты — наставник по подготовке системных аналитиков."},
                {"role": "user", "content": prompt},
            ],
        )
        content = resp.choices[0].message.content
        if not content:
            raise OpenAIResponseError("empty recommendation content")
        return content
```

(`get_topic` and `OpenAIResponseError` are already imported/defined in this module.)

- [ ] **Step 4: Write `backend/app/assessment/recommendation.py`**

```python
PASS_PRAISE = (
    "Отличный результат — слабых тем не выявлено. Поддерживайте уровень: "
    "периодически повторяйте материал и пробуйте полные экзамены-симуляции."
)


async def build_recommendation(
    openai_client,
    level: str,
    topic_accuracy: dict[str, float],
    threshold: float,
) -> str:
    """Pick topics below the threshold and ask the LLM for targeted advice.
    If there are none, return praise without an LLM call."""
    weak = sorted(
        ((tid, acc) for tid, acc in topic_accuracy.items() if acc < threshold),
        key=lambda kv: kv[1],
    )
    if not weak:
        return PASS_PRAISE
    return await openai_client.recommend(level, weak)
```

- [ ] **Step 5: Run test to verify it passes**

Run: `pytest tests/test_recommendation.py -v`
Expected: PASS (2 passed)

- [ ] **Step 6: Commit**

```bash
git add backend/app/generation/openai_client.py backend/app/assessment/recommendation.py backend/tests/test_recommendation.py
git commit -m "feat: add weak-topic recommendation via LLM"
```

---

### Task 5: Assessment schemas

**Files:**
- Create: `backend/app/assessment/schemas.py`

- [ ] **Step 1: Write `backend/app/assessment/schemas.py`**

```python
from pydantic import BaseModel


class SubmitAnswerRequest(BaseModel):
    question_id: str
    selected_keys: list[str]


class TopicBreakdown(BaseModel):
    topic_id: str
    answered: int
    correct: int
    accuracy: float


class QuestionReview(BaseModel):
    id: str
    seq: int
    topic_id: str
    type: str
    stem: str
    artifact_kind: str
    artifact_content: str | None
    options: list
    correct_keys: list[str]   # revealed only at results time
    selected_keys: list[str]
    is_correct: bool
    explanation: str          # revealed only at results time


class ResultsResponse(BaseModel):
    session_id: str
    level: str
    mode: str
    score_percent: float
    passed: bool
    total_questions: int
    answered_count: int
    topic_breakdown: list[TopicBreakdown]
    recommendation: str
    questions: list[QuestionReview]
```

- [ ] **Step 2: Sanity import**

Run: `python -c "from app.assessment.schemas import ResultsResponse, SubmitAnswerRequest; print('ok')"`
Expected: `ok`

- [ ] **Step 3: Commit**

```bash
git add backend/app/assessment/schemas.py
git commit -m "feat: add assessment API schemas"
```

---

### Task 6: Assessment service — submit, finish, results

**Files:**
- Create: `backend/app/assessment/service.py`
- Test: `backend/tests/test_assessment_service.py`

- [ ] **Step 1: Write the failing test** — `backend/tests/test_assessment_service.py`

```python
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
    # 4 questions across 2 topics
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
    await service.submit_answer(db_session, s.id, qs[0].id, ["a"])  # correct
    await service.submit_answer(db_session, s.id, qs[1].id, ["b"])  # wrong
    from sqlalchemy import select
    rows = (await db_session.execute(
        select(Answer).where(Answer.session_id == s.id))).scalars().all()
    by_q = {r.question_id: r for r in rows}
    assert by_q[qs[0].id].is_correct is True
    assert by_q[qs[1].id].is_correct is False


@pytest.mark.asyncio
async def test_resubmit_overwrites_answer(db_session):
    user, s, qs = await _seed_session(db_session)
    await service.submit_answer(db_session, s.id, qs[0].id, ["b"])  # wrong first
    await service.submit_answer(db_session, s.id, qs[0].id, ["a"])  # corrected
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
    # answer 3 of 4 correctly (data: 2/2, modeling: 1/2)
    await service.submit_answer(db_session, s.id, qs[0].id, ["a"])
    await service.submit_answer(db_session, s.id, qs[1].id, ["a"])
    await service.submit_answer(db_session, s.id, qs[2].id, ["a"])
    await service.submit_answer(db_session, s.id, qs[3].id, ["b"])
    await service.finish_session(db_session, s.id, FakeRecoClient(), weak_threshold=0.6)
    await db_session.refresh(s)
    assert s.status == "finished"
    assert float(s.score_percent) == 75.0  # 3/4
    assert s.passed is False  # base threshold 70 -> 75 >= 70 actually True!
```

> NOTE on the last assertion: base threshold is 70%, and 75% ≥ 70% means **passed should be True**. Fix the test assertion to `assert s.passed is True` before running — the comment above is intentionally flagging that 75% passes the base 70% bar. (Threshold values: base=70, specialist=75; defined in Task 6 Step 3.)

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_assessment_service.py -v`
Expected: FAIL (`ModuleNotFoundError: No module named 'app.assessment.service'`)

- [ ] **Step 3: Write `backend/app/assessment/service.py`**

```python
import datetime as dt
import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.assessment.competency import update_competency
from app.assessment.recommendation import build_recommendation
from app.assessment.scoring import is_answer_correct, score
from app.db.models import Answer, Question, TestSession

LEVEL_THRESHOLDS = {"base": 70.0, "specialist": 75.0}


class SessionNotReady(Exception):
    pass


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

    # per-topic (answered, correct) and overall correct
    per_topic: dict[str, list[int]] = {}
    correct_count = 0
    for q in questions:
        a = answer_by_q.get(q.id)
        ans = 1
        cor = 1 if (a is not None and a.is_correct) else 0
        correct_count += cor
        bucket = per_topic.setdefault(q.topic_id, [0, 0])
        bucket[0] += ans
        bucket[1] += cor

    total = len(questions)
    result = score(correct_count, total, LEVEL_THRESHOLDS[session.level])

    # update competency profile (accumulates across tests)
    await update_competency(
        db, session.user_id, session.level,
        {tid: (a, c) for tid, (a, c) in per_topic.items()},
    )

    # recommendation from the freshly-updated profile
    from app.assessment.competency import load_competency
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
```

- [ ] **Step 4: Fix the flagged test assertion** in `test_assessment_service.py` (Step 1): change the last line `assert s.passed is False` to `assert s.passed is True` (75% ≥ 70% base threshold passes).

- [ ] **Step 5: Run test to verify it passes**

Run: `pytest tests/test_assessment_service.py -v`
Expected: PASS (3 passed)

- [ ] **Step 6: Commit**

```bash
git add backend/app/assessment/service.py backend/tests/test_assessment_service.py
git commit -m "feat: add assessment service (submit, finish, results)"
```

---

### Task 7: Assessment router

**Files:**
- Create: `backend/app/assessment/router.py`
- Modify: `backend/app/main.py` (include router)
- Test: `backend/tests/test_assessment_api.py`

The router owns answer submission, finishing, and results. It reuses the sessions router's `build_openai_client` factory. All endpoints check session ownership.

- [ ] **Step 1: Write the failing test** — `backend/tests/test_assessment_api.py`

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

    async def recommend(self, level, weak_topics):
        return "Совет по подготовке."


@pytest.fixture(autouse=True)
def _patch_clients(monkeypatch):
    from app.generation import router as gen_router
    from app.assessment import router as asm_router
    monkeypatch.setattr(gen_router, "build_openai_client", lambda: FakeClient())
    monkeypatch.setattr(asm_router, "build_openai_client", lambda: FakeClient())


async def _register(client, login="quinn"):
    return await client.post(
        "/auth/register",
        json={"login": login, "password": "pw12345", "access_code": "TEST-CODE"},
    )


async def _make_ready_session(client):
    resp = await client.post("/sessions", json={"level": "base", "mode": "adaptive"})
    sid = resp.json()["id"]
    for _ in range(50):
        st = await client.get(f"/sessions/{sid}/status")
        if st.json()["status"] == "ready":
            break
        await asyncio.sleep(0.05)
    qs = (await client.get(f"/sessions/{sid}/questions")).json()
    return sid, qs


@pytest.mark.asyncio
async def test_full_flow_submit_finish_results(client):
    await _register(client, "quinn")
    sid, qs = await _make_ready_session(client)
    # answer all correctly (fake always makes "a" correct)
    for q in qs:
        r = await client.post(
            f"/sessions/{sid}/answers",
            json={"question_id": q["id"], "selected_keys": ["a"]},
        )
        assert r.status_code == 200
    fin = await client.post(f"/sessions/{sid}/finish")
    assert fin.status_code == 200

    res = await client.get(f"/sessions/{sid}/results")
    assert res.status_code == 200
    body = res.json()
    assert body["passed"] is True
    assert body["score_percent"] == 100.0
    assert body["recommendation"]
    # results DO reveal correct_keys + explanation (unlike the /questions endpoint)
    assert "correct_keys" in body["questions"][0]
    assert "explanation" in body["questions"][0]
    assert len(body["topic_breakdown"]) >= 1


@pytest.mark.asyncio
async def test_results_requires_ownership(client):
    await _register(client, "rita")
    sid, qs = await _make_ready_session(client)
    # second user cannot read first user's results
    await client.post("/auth/logout")
    await _register(client, "sam")
    res = await client.get(f"/sessions/{sid}/results")
    assert res.status_code == 404


@pytest.mark.asyncio
async def test_finish_requires_auth(client):
    await _register(client, "tom")
    sid, qs = await _make_ready_session(client)
    await client.post("/auth/logout")
    fin = await client.post(f"/sessions/{sid}/finish")
    assert fin.status_code == 401
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_assessment_api.py -v`
Expected: FAIL (`ModuleNotFoundError: No module named 'app.assessment.router'`)

- [ ] **Step 3: Write `backend/app/assessment/router.py`**

```python
import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.assessment import service
from app.assessment.schemas import SubmitAnswerRequest
from app.core.config import get_settings
from app.db.base import get_session
from app.db.models import User
from app.deps import current_user
from app.generation.router import build_openai_client

router = APIRouter(tags=["assessment"])


async def _owned_session(db, session_id, user):
    s = await service_get_session(db, session_id)
    if s is None or s.user_id != user.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Session not found")
    return s


async def service_get_session(db, session_id):
    from app.db.models import TestSession
    return await db.get(TestSession, session_id)


@router.post("/sessions/{session_id}/answers")
async def submit_answer(
    session_id: uuid.UUID,
    req: SubmitAnswerRequest,
    user: User = Depends(current_user),
    db: AsyncSession = Depends(get_session),
):
    await _owned_session(db, session_id, user)
    try:
        answer = await service.submit_answer(
            db, session_id, uuid.UUID(req.question_id), req.selected_keys
        )
    except ValueError:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Invalid question")
    return {"question_id": str(answer.question_id), "recorded": True}


@router.post("/sessions/{session_id}/finish")
async def finish(
    session_id: uuid.UUID,
    user: User = Depends(current_user),
    db: AsyncSession = Depends(get_session),
):
    await _owned_session(db, session_id, user)
    settings = get_settings()
    session = await service.finish_session(
        db, session_id, build_openai_client(),
        weak_threshold=settings.weak_topic_threshold,
    )
    return {"id": str(session.id), "score_percent": float(session.score_percent),
            "passed": session.passed, "status": session.status}


@router.get("/sessions/{session_id}/results")
async def results(
    session_id: uuid.UUID,
    user: User = Depends(current_user),
    db: AsyncSession = Depends(get_session),
):
    await _owned_session(db, session_id, user)
    return await service.get_results(db, session_id)
```

- [ ] **Step 4: Include the router in `backend/app/main.py`**

Add the import and `include_router` in `create_app` (after the sessions router):

```python
from app.assessment.router import router as assessment_router
# ... inside create_app(), after app.include_router(sessions_router):
    app.include_router(assessment_router)
```

- [ ] **Step 5: Run test to verify it passes**

Run: `pytest tests/test_assessment_api.py -v`
Expected: PASS (3 passed)

- [ ] **Step 6: Commit**

```bash
git add backend/app/assessment/router.py backend/app/main.py backend/tests/test_assessment_api.py
git commit -m "feat: add assessment API (answers, finish, results)"
```

---

### Task 8: Wire real competency into adaptive generation (un-stub Subsystem 2)

**Files:**
- Modify: `backend/app/generation/service.py`
- Test: `backend/tests/test_adaptive_wiring.py`

Subsystem 2's `_load_competency` was a guarded stub returning `{}`. Now `TopicCompetency` exists, so adaptive generation should use the real profile.

- [ ] **Step 1: Write the failing test** — `backend/tests/test_adaptive_wiring.py`

```python
import uuid

import pytest

from app.assessment.competency import update_competency
from app.generation import service as gen_service
from app.db.models import User


async def _user(db):
    u = User(login=f"u{uuid.uuid4().hex[:8]}", password_hash="x")
    db.add(u)
    await db.commit()
    await db.refresh(u)
    return u


@pytest.mark.asyncio
async def test_adaptive_plan_targets_weak_topics_from_profile(db_session):
    u = await _user(db_session)
    # make "data" weak and "modeling" strong in the profile
    await update_competency(db_session, u.id, "base", {"data": (10, 2)})     # 0.2
    await update_competency(db_session, u.id, "base", {"modeling": (10, 9)})  # 0.9
    session, plan = await gen_service.create_session(
        db_session, u.id, "base", "adaptive",
        daily_limit=99, adaptive_count=10, weak_threshold=0.6,
    )
    plan_d = dict(plan)
    # "data" (0.2 < 0.6) must be targeted; "modeling" (0.9) must not
    assert "data" in plan_d
    assert "modeling" not in plan_d
    assert sum(plan_d.values()) == 10
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_adaptive_wiring.py -v`
Expected: FAIL — because `_load_competency` still returns `{}` (the stub), so the plan falls back to even distribution and includes "modeling".

- [ ] **Step 3: Replace the stub in `backend/app/generation/service.py`**

Replace the entire `_load_competency` function:

```python
async def _load_competency(db: AsyncSession, user_id, level) -> dict[str, float]:
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
```

with a direct delegation to the assessment module (now that it exists):

```python
async def _load_competency(db: AsyncSession, user_id, level) -> dict[str, float]:
    from app.assessment.competency import load_competency
    return await load_competency(db, user_id, level)
```

(The `select` import in service.py may now be unused — if ruff flags it, remove it.)

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_adaptive_wiring.py -v`
Expected: PASS (1 passed). Also run `pytest tests/test_sessions_api.py -v` to confirm Subsystem 2's adaptive tests still pass (they used an empty profile → even distribution; with no competency rows for new users, `load_competency` returns `{}` and behavior is unchanged).

- [ ] **Step 5: Commit**

```bash
git add backend/app/generation/service.py backend/tests/test_adaptive_wiring.py
git commit -m "feat: wire real competency profile into adaptive generation"
```

---

### Task 9: Final verification of Subsystem 3

**Files:** none

- [ ] **Step 1: Run the entire suite**

Run: `cd backend && . .venv/bin/activate && pytest -v`
Expected: ALL tests pass (Subsystems 1 + 2 + 3). Report the count. Run twice for determinism.

- [ ] **Step 2: Lint**

Run: `ruff check app tests`
Expected: no errors (fix any).

- [ ] **Step 3: Confirm success criteria** (do not claim done until all true):
  - Full `pytest` green, deterministic.
  - `alembic upgrade head` applied `answers` + `topic_competency`.
  - End-to-end assessment flow works in the API test (submit → finish → results), with results revealing `correct_keys`/`explanation` while the earlier `/questions` endpoint still hides them.
  - Adaptive generation now targets real weak topics from the competency profile.

---

## Self-Review Notes

Checked against spec sections 2 (decisions 3 adaptivity, 7 recommendation), 4 (Assessment subsystem), 5 (`answers`, `topic_competency` models match column-for-column), and 8 (results screen data: score, pass/fail, per-question review with explanation, topic breakdown, recommendation). The `correct_keys`/`explanation` reveal boundary is explicit: Subsystem 2's `/questions` omits them; this subsystem's `/results` includes them — both covered by tests. Scoring is exact-match set equality (deterministic, no LLM judge), matching decision 4. The final recommendation is one LLM call (decision 7) and short-circuits to praise with no call when no weak topics. Competency accumulates across tests and is per-level. Task 8 closes the loop: adaptive mode (stubbed in Subsystem 2) now reads the real profile. No placeholders — all code/tests complete. Type consistency verified: `is_answer_correct`/`score`/`ScoreResult`, `update_competency`/`load_competency` (signature `(db, user_id, level, per_topic)` and `(db, user_id, level)`), `submit_answer`/`finish_session`/`get_results`, `recommend(level, weak_topics)` on the client and `build_recommendation(client, level, topic_accuracy, threshold)` are consistent across tasks. The flagged test assertion in Task 6 (75% passes base 70%) is corrected in Step 4. One coupling note: `assessment/router.py` imports `build_openai_client` from `generation/router.py` — reuse, not duplication; the assessment API test patches both module references.
```
