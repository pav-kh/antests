# Open Questions with LLM Evaluation — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add exactly 2 free-text open questions (beyond the closed pool) to every test, evaluated by an LLM judge into feedback that does NOT affect the deterministic pass/fail score.

**Architecture:** Reuse existing `questions`/`answers` tables — add `type="open"` + `rubric` to questions, `answer_text`+`feedback` to answers. The generator produces 2 open questions after the closed pool fills (seq after the closed ones). On finish, open answers are judged in parallel with the recommendation; the score/topic-breakdown count CLOSED questions only. The frontend renders a `<textarea>` for open questions and an "Open questions" section on results.

**Tech Stack:** Existing — FastAPI, SQLAlchemy/Alembic, Postgres, OpenAI SDK, Next.js/Vitest. No new deps.

**Depends on:** Spec `docs/superpowers/specs/2026-06-04-open-questions-design.md`.

---

## File Structure

```
backend/app/
  db/models.py                 # MODIFY: Question.rubric; Answer.answer_text, .feedback, is_correct nullable
  generation/schemas.py        # MODIFY: allow type="open"; add OpenQuestion schema
  generation/openai_client.py  # MODIFY: generate_open_questions(), judge_open()
  generation/generator.py      # MODIFY: after closed pool, generate 2 open questions
  assessment/scoring.py        # MODIFY: closed-only counting helper
  assessment/service.py        # MODIFY: submit_answer(open), finish_session (judge open, count closed-only), get_results (open_questions section)
  assessment/open_eval.py      # CREATE: judge one open answer (empty-guard + LLM)
  assessment/router.py         # MODIFY: submit accepts answer_text
  assessment/schemas.py        # MODIFY: SubmitAnswerRequest gets optional answer_text
backend/tests/
  test_open_schemas.py         # CREATE
  test_open_eval.py            # CREATE
  test_open_generation.py      # CREATE
  test_open_assessment.py      # CREATE
  (modify) test_assessment_api.py, test_sessions_api.py
frontend/src/
  lib/types.ts                 # MODIFY: QuestionType += "open"; Results += open_questions
  lib/api.ts                   # MODIFY: submitAnswer accepts answer_text
  components/QuestionCard.tsx   # MODIFY: textarea for type="open"
  app/test/[id]/page.tsx       # MODIFY: open answers via answer_text
  app/test/[id]/results/page.tsx # MODIFY: "Open questions" section
```

---

### Task 1: DB model changes + migration

**Files:**
- Modify: `backend/app/db/models.py`
- Create: migration under `backend/alembic/versions/`

- [ ] **Step 1: Add `rubric` to `Question` and `answer_text`/`feedback` to `Answer`; make `Answer.is_correct` nullable**

In `backend/app/db/models.py`, in class `Question`, after the `explanation` column add:
```python
    rubric: Mapped[str | None] = mapped_column(Text, nullable=True)
```

In class `Answer`, change the `is_correct` column to nullable and add two fields. Replace:
```python
    is_correct: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
```
with:
```python
    is_correct: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    answer_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    feedback: Mapped[str | None] = mapped_column(Text, nullable=True)
```

- [ ] **Step 2: Sanity import**

Run: `cd backend && . .venv/bin/activate && python -c "from app.db.models import Question, Answer; print('ok')"`
Expected: `ok`

- [ ] **Step 3: Generate + apply migration**

Run (env from `.env`):
```bash
alembic revision --autogenerate -m "open questions: rubric, answer_text, feedback, nullable is_correct"
alembic upgrade head
```
Open the generated migration and CONFIRM it adds `rubric` to `questions`, `answer_text`+`feedback` to `answers`, and alters `is_correct` to nullable. Then:
`docker exec antests-pg psql -U postgres -d antests -c "\d answers"` shows `answer_text`, `feedback`, and `is_correct` nullable.

> NOTE: existing rows have `is_correct=false`; the alter to nullable keeps them valid. The autogenerate may emit `alter_column(..., nullable=True)` — that's correct.

- [ ] **Step 4: Commit**

```bash
git add backend/app/db/models.py backend/alembic/versions/
git commit -m "feat: add rubric/answer_text/feedback columns for open questions"
```

---

### Task 2: Allow `type="open"` in the generation schema

**Files:**
- Modify: `backend/app/generation/schemas.py`
- Create: `backend/tests/test_open_schemas.py`

- [ ] **Step 1: Write the failing test** — `backend/tests/test_open_schemas.py`

```python
import pytest
from pydantic import ValidationError
from app.generation.schemas import GeneratedQuestion, OpenQuestion


def test_open_question_schema_minimal():
    oq = OpenQuestion(stem="Опишите проблему и решения.", rubric="должен задать вопросы и предложить решения", explanation="хороший ответ...")
    assert oq.stem
    assert oq.rubric
    assert oq.explanation


def test_open_question_requires_rubric():
    with pytest.raises(ValidationError):
        OpenQuestion(stem="Q", rubric="", explanation="x")


def test_generated_question_still_rejects_open_type():
    # closed-question schema is single/multi only; open uses its own schema
    with pytest.raises(ValidationError):
        GeneratedQuestion(
            topic_id="data", type="open", stem="Q",
            artifact_kind="none", artifact_content=None,
            options=[], correct_keys=[], explanation="x",
        )
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && . .venv/bin/activate && pytest tests/test_open_schemas.py -v`
Expected: FAIL (`ImportError: cannot import name 'OpenQuestion'`)

- [ ] **Step 3: Add `OpenQuestion` schema**

In `backend/app/generation/schemas.py`, append (after `GeneratedBatch`):
```python
class OpenQuestion(BaseModel):
    stem: str
    rubric: str
    explanation: str

    @model_validator(mode="after")
    def _check(self):
        if not self.stem.strip():
            raise ValueError("stem required")
        if not self.rubric.strip():
            raise ValueError("rubric required")
        if not self.explanation.strip():
            raise ValueError("explanation required")
        return self


class OpenBatch(BaseModel):
    questions: list[OpenQuestion]
```
(The `GeneratedQuestion` `type` field stays `Literal["single", "multi"]` — open questions use `OpenQuestion`, not `GeneratedQuestion`, so the third test already passes.)

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_open_schemas.py -v`
Expected: PASS (3 passed)

- [ ] **Step 5: Commit**

```bash
git add backend/app/generation/schemas.py backend/tests/test_open_schemas.py
git commit -m "feat: add OpenQuestion/OpenBatch schemas"
```

---

### Task 3: `generate_open_questions` on OpenAIClient

**Files:**
- Modify: `backend/app/generation/openai_client.py`
- Test: `backend/tests/test_open_generation.py`

- [ ] **Step 1: Write the failing test** — `backend/tests/test_open_generation.py`

```python
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_open_generation.py -v`
Expected: FAIL (`AttributeError: ... has no attribute 'generate_open_questions'`)

- [ ] **Step 3: Add the method**

In `backend/app/generation/openai_client.py`, import `OpenBatch`/`OpenQuestion` (extend the existing schemas import line to include them), and add this method to `OpenAIClient` (after `validate_question`):
```python
    async def generate_open_questions(self, level: str, count: int = 2) -> list:
        prompt = (
            f"Сгенерируй {count} ОТКРЫТЫХ вопроса-кейса для системного аналитика "
            f"(уровень {level}). Каждый — короткая практическая ситуация, требующая "
            "развёрнутого текстового ответа (НЕ выбор варианта). Пример: «Клиенты "
            "часто пишут повторно, потому что не понимают, где их заявка и почему "
            "задержка. Какие вопросы задать клиенту для выявления причин и какие "
            "пути решения предложить?». Для КАЖДОГО верни: stem (текст задания), "
            "rubric (критерии хорошего ответа — что обязательно раскрыть; "
            "пользователю НЕ показывается), explanation (разбор: что отличает "
            "сильный ответ — показывается на результатах). Пиши по-русски. "
            "Верни СТРОГО JSON по схеме."
        )
        resp = await self._client.chat.completions.create(
            model=self.gen_model,
            messages=[
                {"role": "system",
                 "content": "Ты — экзаменатор сертификации системных аналитиков IBS."},
                {"role": "user", "content": prompt},
            ],
            response_format={
                "type": "json_schema",
                "json_schema": {
                    "name": "open_batch",
                    "schema": {
                        "type": "object",
                        "properties": {
                            "questions": {
                                "type": "array",
                                "items": {
                                    "type": "object",
                                    "properties": {
                                        "stem": {"type": "string"},
                                        "rubric": {"type": "string"},
                                        "explanation": {"type": "string"},
                                    },
                                    "required": ["stem", "rubric", "explanation"],
                                },
                            }
                        },
                        "required": ["questions"],
                    },
                    "strict": False,
                },
            },
        )
        data = _parse_json_content(resp)
        return OpenBatch(**data).questions
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_open_generation.py -v`
Expected: PASS (1 passed)

- [ ] **Step 5: Commit**

```bash
git add backend/app/generation/openai_client.py backend/tests/test_open_generation.py
git commit -m "feat: add generate_open_questions to OpenAIClient"
```

---

### Task 4: `judge_open` on OpenAIClient

**Files:**
- Modify: `backend/app/generation/openai_client.py`
- Test: `backend/tests/test_open_generation.py` (append)

- [ ] **Step 1: Append the failing test**

```python
@pytest.mark.asyncio
async def test_judge_open_returns_feedback():
    client = OpenAIClient(api_key="x", gen_model="g", validate_model="v",
                          _client=_Client("Хорошо, но упустили эскалацию."))
    fb = await client.judge_open(
        stem="Опишите решения.", rubric="вопросы + решения", answer="Спросить статус.")
    assert "эскалацию" in fb
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_open_generation.py::test_judge_open_returns_feedback -v`
Expected: FAIL (`AttributeError: ... 'judge_open'`)

- [ ] **Step 3: Add the method** (after `generate_open_questions`)

```python
    async def judge_open(self, stem: str, rubric: str, answer: str) -> str:
        prompt = (
            "Оцени ответ студента на открытый вопрос по сертификации СА и дай "
            "развёрнутую обратную связь (что хорошо, что упущено, как улучшить). "
            "Опирайся на критерии (rubric). НЕ ставь балл — только текст. "
            "Пиши по-русски, конкретно и доброжелательно.\n\n"
            f"ВОПРОС:\n{stem}\n\nКРИТЕРИИ (rubric):\n{rubric}\n\n"
            f"ОТВЕТ СТУДЕНТА:\n{answer}"
        )
        resp = await self._client.chat.completions.create(
            model=self.validate_model,
            messages=[
                {"role": "system",
                 "content": "Ты — наставник, оценивающий ответы системных аналитиков."},
                {"role": "user", "content": prompt},
            ],
        )
        content = resp.choices[0].message.content
        if not content:
            raise OpenAIResponseError("empty judge content")
        return content
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_open_generation.py -v`
Expected: PASS (2 passed)

- [ ] **Step 5: Commit**

```bash
git add backend/app/generation/openai_client.py backend/tests/test_open_generation.py
git commit -m "feat: add judge_open to OpenAIClient"
```

---

### Task 5: Open-answer evaluation module (empty-guard + judge)

**Files:**
- Create: `backend/app/assessment/open_eval.py`
- Test: `backend/tests/test_open_eval.py`

- [ ] **Step 1: Write the failing test** — `backend/tests/test_open_eval.py`

```python
import pytest
from app.assessment.open_eval import evaluate_open


class FakeJudge:
    async def judge_open(self, stem, rubric, answer):
        return f"feedback for: {answer}"


@pytest.mark.asyncio
async def test_empty_answer_skips_llm():
    fb = await evaluate_open(FakeJudge(), stem="Q", rubric="что раскрыть", answer="")
    assert "не ответ" in fb.lower() or "не дан" in fb.lower()


@pytest.mark.asyncio
async def test_too_short_answer_skips_llm():
    fb = await evaluate_open(FakeJudge(), stem="Q", rubric="r", answer="  нет  ")
    # 'нет' is 3 non-space chars < 10 -> stub, no LLM
    assert "feedback for" not in fb


@pytest.mark.asyncio
async def test_real_answer_uses_judge():
    answer = "Спросить статус заявки, сроки, причины задержки; предложить уведомления."
    fb = await evaluate_open(FakeJudge(), stem="Q", rubric="r", answer=answer)
    assert fb == f"feedback for: {answer}"


@pytest.mark.asyncio
async def test_judge_failure_is_non_fatal():
    class Boom:
        async def judge_open(self, *a, **k):
            raise RuntimeError("openai down")
    fb = await evaluate_open(Boom(), stem="Q", rubric="r",
                             answer="достаточно длинный ответ для оценки судьёй")
    assert fb == ""  # non-fatal: finishing must not break
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_open_eval.py -v`
Expected: FAIL (`ModuleNotFoundError: No module named 'app.assessment.open_eval'`)

- [ ] **Step 3: Write `backend/app/assessment/open_eval.py`**

```python
MIN_ANSWER_CHARS = 10

EMPTY_FEEDBACK = (
    "Вы не ответили на этот вопрос (или ответ слишком короткий). "
    "Для сильного ответа стоило раскрыть пункты из разбора ниже."
)


async def evaluate_open(judge_client, stem: str, rubric: str, answer: str) -> str:
    """Feedback for one open answer. Empty/too-short answers get a stub without
    an LLM call. A judge failure is non-fatal (returns '') so finishing the test
    never breaks."""
    if len((answer or "").strip()) < MIN_ANSWER_CHARS:
        return EMPTY_FEEDBACK
    try:
        return await judge_client.judge_open(stem, rubric, answer)
    except Exception:
        return ""
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_open_eval.py -v`
Expected: PASS (4 passed)

- [ ] **Step 5: Commit**

```bash
git add backend/app/assessment/open_eval.py backend/tests/test_open_eval.py
git commit -m "feat: add open-answer evaluation (empty guard + judge, non-fatal)"
```

---

### Task 6: Generator produces 2 open questions after the closed pool

**Files:**
- Modify: `backend/app/generation/generator.py`
- Test: `backend/tests/test_open_generation.py` (append a generator test)

The generator, after the closed pool is filled and BEFORE `status="ready"`, generates 2 open questions and stores them with `type="open"`, `seq` after the closed ones, `rubric` set, `options=[]`, `correct_keys=[]`.

- [ ] **Step 1: Append the failing test** — `backend/tests/test_open_generation.py`

```python
import uuid
from sqlalchemy import select
from app.db.models import Question, TestSession, User
from app.generation.generator import Generator
from app.generation.schemas import (
    GeneratedBatch, GeneratedQuestion, OpenQuestion, ValidationVerdict,
)


def _closed_q(topic_id="data"):
    return GeneratedQuestion(
        topic_id=topic_id, type="single", stem="Q?",
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
    # open questions come AFTER the closed ones
    assert all(o.seq > max(c.seq for c in closed) for o in openq)
    # open questions carry a rubric and have no options/correct_keys
    assert all(o.rubric and o.options == [] and o.correct_keys == [] for o in openq)
    # total_questions (closed pool) is unchanged
    assert s.total_questions == 3
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_open_generation.py::test_generator_appends_two_open_questions -v`
Expected: FAIL (no open questions stored)

- [ ] **Step 3: Add open generation in `Generator.run`**

In `backend/app/generation/generator.py`, find the block that sets `session.status = "ready"` (near the end of `run`). IMMEDIATELY BEFORE that line, insert:
```python
            # Append exactly 2 open (free-text) questions after the closed pool.
            # They use seq after all closed questions, carry a rubric for the
            # LLM judge, and have no options/correct_keys. A failure here must not
            # block readiness — open questions are a bonus section.
            try:
                open_qs = await self.client.generate_open_questions(session.level, count=2)
                for oq in open_qs:
                    seq += 1
                    self.db.add(Question(
                        session_id=session.id, seq=seq, topic_id="open",
                        type="open", stem=oq.stem, artifact_kind="none",
                        artifact_content=None, options=[], correct_keys=[],
                        explanation=oq.explanation, rubric=oq.rubric,
                        validation_status="passed",
                    ))
                await self.db.commit()
            except Exception:
                logger.exception("Open-question generation failed for session %s", session_id)
```
> NOTE: `seq` is the running counter already used by the closed loop. `topic_id="open"` keeps these out of `ARTIFACT_TOPICS`/competency topic buckets. Open questions are NOT shuffled (the closed shuffle runs earlier; these are appended after).

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_open_generation.py -v`
Expected: PASS (all). Also run `pytest tests/test_generator.py -v` to confirm existing generator tests still pass (their fake clients don't define `generate_open_questions` — so add a no-op to those fakes OR make the call defensive). 

> IMPORTANT: existing `tests/test_generator.py` `FakeClient` has no `generate_open_questions`, so the new code's call would `AttributeError` (caught by the try/except → logged, open questions skipped, status still ready). Verify those tests still pass (they assert closed-question behavior only). If any now fail because they count total questions, they shouldn't — they query closed types. Confirm by running them.

- [ ] **Step 5: Commit**

```bash
git add backend/app/generation/generator.py backend/tests/test_open_generation.py
git commit -m "feat: generator appends 2 open questions after the closed pool"
```

---

### Task 7: Assessment — submit open answer, finish judges open, score counts closed-only

**Files:**
- Modify: `backend/app/assessment/scoring.py`, `backend/app/assessment/service.py`, `backend/app/assessment/schemas.py`, `backend/app/assessment/router.py`
- Test: `backend/tests/test_open_assessment.py`

- [ ] **Step 1: Write the failing test** — `backend/tests/test_open_assessment.py`

```python
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
    db.add(user); await db.commit(); await db.refresh(user)
    s = TestSession(user_id=user.id, level="base", mode="exam", status="ready",
                    total_questions=2, generated_count=2, time_limit_sec=7200)
    db.add(s); await db.commit(); await db.refresh(s)
    qs = []
    for i in range(2):  # 2 closed
        q = Question(session_id=s.id, seq=i + 1, topic_id="data", type="single",
                     stem="Q?", artifact_kind="none", artifact_content=None,
                     options=[{"key": "a", "text": "x"}, {"key": "b", "text": "y"}],
                     correct_keys=["a"], explanation="b", validation_status="passed")
        db.add(q); qs.append(q)
    if with_open:
        oq = Question(session_id=s.id, seq=3, topic_id="open", type="open",
                      stem="Опишите решения.", artifact_kind="none", artifact_content=None,
                      options=[], correct_keys=[], explanation="разбор",
                      rubric="вопросы+решения", validation_status="passed")
        db.add(oq); qs.append(oq)
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
    assert a.is_correct is None  # open answers don't count


@pytest.mark.asyncio
async def test_score_counts_closed_only_and_judges_open(db_session):
    user, s, qs = await _seed(db_session)
    # both closed correct, open answered
    await service.submit_answer(db_session, s.id, qs[0].id, selected_keys=["a"])
    await service.submit_answer(db_session, s.id, qs[1].id, selected_keys=["a"])
    await service.submit_answer(db_session, s.id, qs[2].id, selected_keys=None,
                                answer_text="Достаточно длинный ответ для судьи про эскалацию.")
    await service.finish_session(db_session, s.id, FakeJudgeClient(), weak_threshold=0.6)
    await db_session.refresh(s)
    # 2/2 closed = 100% (open does NOT dilute it)
    assert float(s.score_percent) == 100.0
    assert s.passed is True
    # open answer got judged feedback
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
    # closed questions only in 'questions'; open in 'open_questions'
    assert all(q["type"] in ("single", "multi") for q in res["questions"])
    assert len(res["open_questions"]) == 1
    o = res["open_questions"][0]
    assert o["stem"] and o["answer_text"].startswith("Длинный") and o["feedback"]
    assert "rubric" not in o  # rubric stays secret
    # total_questions for the score reflects CLOSED count (2), not 3
    assert res["total_questions"] == 2
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_open_assessment.py -v`
Expected: FAIL (`submit_answer` doesn't accept `answer_text`)

- [ ] **Step 3: Add a closed-only counting helper to `scoring.py`**

In `backend/app/assessment/scoring.py`, append:
```python
def is_closed(question_type: str) -> bool:
    """Open (free-text) questions are graded by an LLM and excluded from the
    deterministic pass/fail score; only single/multi count."""
    return question_type in ("single", "multi")
```

- [ ] **Step 4: Update `submit_answer` in `service.py`** to accept open answers

Replace the `submit_answer` function with:
```python
async def submit_answer(
    db: AsyncSession, session_id, question_id,
    selected_keys: list[str] | None = None,
    answer_text: str | None = None,
) -> Answer:
    q = await _get_question(db, session_id, question_id)
    if q is None:
        raise ValueError("question not in session")
    session = await db.get(TestSession, session_id)
    if session is None:
        raise ValueError("session not found")
    if session.status == "finished":
        raise SessionNotFinishable("cannot submit answers to a finished session")
    if session.status == "ready":
        session.status = "in_progress"

    if q.type == "open":
        sel: list[str] = []
        correct = None
        text = answer_text or ""
    else:
        sel = selected_keys or []
        correct = is_answer_correct(sel, q.correct_keys)
        text = None

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
            selected_keys=sel, is_correct=correct, answer_text=text,
        )
        db.add(existing)
    else:
        existing.selected_keys = sel
        existing.is_correct = correct
        existing.answer_text = text
    await db.commit()
    await db.refresh(existing)
    return existing
```
Add the import at the top of `service.py`: change `from app.assessment.scoring import is_answer_correct, score` to also import `is_closed`:
```python
from app.assessment.scoring import is_answer_correct, is_closed, score
```

- [ ] **Step 5: Update `finish_session`** — count closed-only, judge open in parallel with recommendation

In `finish_session`, replace the per-topic/score block and the recommendation block. Replace from `per_topic: dict...` through the `recommendation = ""` except block with:
```python
    import asyncio
    from app.assessment.open_eval import evaluate_open

    closed = [q for q in questions if is_closed(q.type)]
    open_qs = [q for q in questions if q.type == "open"]

    per_topic: dict[str, list[int]] = {}
    correct_count = 0
    for q in closed:
        a = answer_by_q.get(q.id)
        cor = 1 if (a is not None and a.is_correct) else 0
        correct_count += cor
        bucket = per_topic.setdefault(q.topic_id, [0, 0])
        bucket[0] += 1
        bucket[1] += cor

    total = len(closed)  # pass/fail counts CLOSED questions only
    result = score(correct_count, total, LEVEL_THRESHOLDS[session.level])

    await update_competency(
        db, session.user_id, session.level,
        {tid: (a, c) for tid, (a, c) in per_topic.items()},
    )
    topic_accuracy = await load_competency(db, session.user_id, session.level)

    # Judge each open answer + build the recommendation, all in parallel.
    async def _safe_reco():
        try:
            return await build_recommendation(
                openai_client, session.level, topic_accuracy, weak_threshold)
        except Exception:
            return ""

    async def _judge(q):
        a = answer_by_q.get(q.id)
        return q.id, await evaluate_open(
            openai_client, q.stem, q.rubric or "", (a.answer_text if a else "") or "")

    reco_task = _safe_reco()
    judge_tasks = [_judge(q) for q in open_qs]
    reco, *judged = await asyncio.gather(reco_task, *judge_tasks)
    recommendation = reco

    for qid, feedback in judged:
        a = answer_by_q.get(qid)
        if a is not None:
            a.feedback = feedback
```
Keep the existing lines that set `session.score_percent`, `passed`, `recommendation`, `status`, `finished_at`, and the final `commit`/`refresh`/`return` exactly as they are after this block.

- [ ] **Step 6: Update `get_results`** — split closed vs open, add `open_questions`, count closed for total

In `get_results`, change the `per_topic` loop to iterate closed only, the `question_reviews` loop to closed only, build an `open_reviews` list, and report closed total. Replace from `per_topic: dict...` through the final `return {...}` with:
```python
    closed = [q for q in questions if q.type in ("single", "multi")]
    open_qs = [q for q in questions if q.type == "open"]

    per_topic: dict[str, list[int]] = {}
    for q in closed:
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
    for q in closed:
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

    open_reviews = []
    for q in open_qs:
        a = answer_by_q.get(q.id)
        open_reviews.append({
            "id": str(q.id), "seq": q.seq, "stem": q.stem,
            "answer_text": (a.answer_text if a else "") or "",
            "feedback": (a.feedback if a else "") or "",
            "explanation": q.explanation,
        })

    answered_closed = sum(
        1 for q in closed if (answer_by_q.get(q.id) and answer_by_q[q.id].selected_keys)
    )

    return {
        "session_id": str(session.id), "level": session.level, "mode": session.mode,
        "score_percent": float(session.score_percent) if session.score_percent is not None else 0.0,
        "passed": bool(session.passed),
        "total_questions": len(closed),
        "answered_count": answered_closed,
        "topic_breakdown": topic_breakdown,
        "recommendation": session.recommendation or "",
        "questions": question_reviews,
        "open_questions": open_reviews,
    }
```

- [ ] **Step 7: Update the request schema + router** to carry `answer_text`

In `backend/app/assessment/schemas.py`, change `SubmitAnswerRequest`:
```python
class SubmitAnswerRequest(BaseModel):
    question_id: str
    selected_keys: list[str] | None = None
    answer_text: str | None = None
```
In `backend/app/assessment/router.py`, in the `submit_answer` endpoint, update the service call to pass both:
```python
        answer = await service.submit_answer(
            db, session_id, uuid.UUID(req.question_id),
            selected_keys=req.selected_keys, answer_text=req.answer_text,
        )
```

- [ ] **Step 8: Run tests to verify they pass**

Run: `pytest tests/test_open_assessment.py tests/test_assessment_service.py tests/test_assessment_api.py -v`
Expected: PASS. The existing assessment tests still pass because closed-only counting equals the old behavior when there are no open questions, and `submit_answer`'s signature change is backward-compatible (`selected_keys` is still accepted as a keyword; existing calls pass it positionally — VERIFY existing call sites still pass positionally and update them to keyword if needed: `submit_answer(db, sid, qid, selected_keys=[...])`).

> NOTE: existing tests call `service.submit_answer(db, s.id, q.id, ["a"])` positionally — the 4th positional arg is now `selected_keys` (still position 4), so they keep working. Confirm by running them.

- [ ] **Step 9: Update `list_answers`** to include open answers (for resume)

In `service.py` `list_answers`, include `answer_text`:
```python
async def list_answers(db: AsyncSession, session_id) -> list[dict]:
    rows = (
        await db.execute(
            select(Answer).where(Answer.session_id == session_id)
        )
    ).scalars().all()
    return [
        {"question_id": str(a.question_id),
         "selected_keys": a.selected_keys,
         "answer_text": a.answer_text or ""}
        for a in rows
    ]
```

- [ ] **Step 10: Run the full backend suite + lint**

Run: `pytest -q && ruff check app tests`
Expected: all pass, lint clean.

- [ ] **Step 11: Commit**

```bash
git add backend/app/assessment/ backend/tests/test_open_assessment.py
git commit -m "feat: open answers — submit text, judge on finish, score closed-only, results section"
```

---

### Task 8: Frontend types + API client

**Files:**
- Modify: `frontend/src/lib/types.ts`, `frontend/src/lib/api.ts`

- [ ] **Step 1: Extend types** — `frontend/src/lib/types.ts`

Change `QuestionType`:
```typescript
export type QuestionType = "single" | "multi" | "open";
```
Add an `OpenReview` type and extend `Results`:
```typescript
export interface OpenReview {
  id: string;
  seq: number;
  stem: string;
  answer_text: string;
  feedback: string;
  explanation: string;
}
```
In the `Results` interface, add the field:
```typescript
  open_questions: OpenReview[];
```

- [ ] **Step 2: Update `submitAnswer`** — `frontend/src/lib/api.ts`

Replace the `submitAnswer` method with one that accepts either selection or text:
```typescript
  submitAnswer: (
    id: string,
    question_id: string,
    payload: { selected_keys?: string[]; answer_text?: string },
  ) =>
    request<{ question_id: string; recorded: boolean }>(`/sessions/${id}/answers`, {
      method: "POST",
      body: JSON.stringify({ question_id, ...payload }),
    }),
```

- [ ] **Step 3: Type-check**

Run: `cd frontend && npx tsc --noEmit`
Expected: errors at existing `submitAnswer` call sites (they pass `selected_keys` as a positional array). That's expected — the next task fixes the exam page. For now, confirm the ONLY errors are about `submitAnswer` arguments.

- [ ] **Step 4: Commit**

```bash
git add frontend/src/lib/types.ts frontend/src/lib/api.ts
git commit -m "feat: frontend types for open questions; submitAnswer accepts text"
```

---

### Task 9: QuestionCard textarea + exam page wiring

**Files:**
- Modify: `frontend/src/components/QuestionCard.tsx`
- Modify: `frontend/src/app/test/[id]/page.tsx`
- Test: `frontend/src/components/__tests__/QuestionCard.test.tsx` (append)

- [ ] **Step 1: Append the failing test** — `frontend/src/components/__tests__/QuestionCard.test.tsx`

```tsx
  it("renders a textarea for an open question and reports typed text", () => {
    const onText = vi.fn();
    const openQ: Question = {
      id: "o1", seq: 81, topic_id: "open", type: "open",
      stem: "Опишите решения.", artifact_kind: "none", artifact_content: null,
      options: [],
    };
    render(
      <QuestionCard question={openQ} selected={[]} onToggle={() => {}}
        answerText="" onAnswerText={onText} />
    );
    const ta = screen.getByRole("textbox");
    fireEvent.change(ta, { target: { value: "мой ответ" } });
    expect(onText).toHaveBeenCalledWith("мой ответ");
  });
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd frontend && npm run test -- QuestionCard`
Expected: FAIL (no textarea / props don't exist)

- [ ] **Step 3: Update `QuestionCard.tsx`** to support open questions

Add two optional props and an open branch. Change the component signature and add the textarea path:
```tsx
export function QuestionCard({
  question, selected, onToggle, answerText = "", onAnswerText,
}: {
  question: Question;
  selected: string[];
  onToggle: (key: string) => void;
  answerText?: string;
  onAnswerText?: (text: string) => void;
}) {
```
Right after the `<Artifact .../>` line and before the options block, add:
```tsx
      {question.type === "open" ? (
        <textarea
          value={answerText}
          onChange={(e) => onAnswerText?.(e.target.value)}
          placeholder="Введите развёрнутый ответ…"
          style={{
            width: "100%", minHeight: 160, marginTop: 12, padding: "12px 14px",
            border: "1px solid #e3e9f1", borderRadius: 9, font: "inherit",
            resize: "vertical",
          }}
        />
      ) : (
```
and CLOSE that ternary after the existing options `<div>...</div>` block with `)}`. (The options block becomes the `else` branch.)

- [ ] **Step 4: Wire the exam page** — `frontend/src/app/test/[id]/page.tsx`

The page stores answers in `answers: AnswerMap` (Record<string, string[]>). Open answers need text. Add a parallel `openAnswers` state and handlers. Add near the other `useState`:
```tsx
  const [openText, setOpenText] = useState<Record<string, string>>({});
```
Update the submit-on-toggle handler and add a text handler. Find `onToggle` (calls `api.submitAnswer`) — update its call to the new signature, and add `onAnswerText`. The current question render becomes:
```tsx
        {current ? (
          <QuestionCard
            question={current}
            selected={answers[current.id] ?? []}
            answerText={openText[current.id] ?? ""}
            onToggle={onToggle}
            onAnswerText={(text) => {
              setOpenText((prev) => ({ ...prev, [current.id]: text }));
              api.submitAnswer(id, current.id, { answer_text: text }).catch(() => {});
            }}
          />
        ) : ...
```
And update the existing `onToggle` body's submit call to the new payload shape:
```tsx
    try { await api.submitAnswer(id, current.id, { selected_keys: next }); } catch { /* keep local */ }
```
Also, on load, restore open answers from `api.listAnswers` (which now returns `answer_text`): in the effect that restores prior answers, also populate `openText`:
```tsx
      const map: AnswerMap = {};
      const omap: Record<string, string> = {};
      for (const a of prior) {
        if (a.selected_keys?.length) map[a.question_id] = a.selected_keys;
        if (a.answer_text) omap[a.question_id] = a.answer_text;
      }
      setAnswers((prev) => ({ ...map, ...prev }));
      setOpenText((prev) => ({ ...omap, ...prev }));
```
(Adjust `api.listAnswers` return type in `api.ts` to include `answer_text: string`.)

For the nav "answered" indicator, count an open question as answered when its text is non-empty: update `answeredSeqs` to also include open questions with text. Find where `answeredSeqs` is computed and OR-in the open condition:
```tsx
  const answeredSeqs = new Set(
    questions
      .filter((q) =>
        (answers[q.id]?.length ?? 0) > 0 || (openText[q.id]?.trim().length ?? 0) > 0)
      .map((q) => q.seq)
  );
```

- [ ] **Step 5: Run tests + typecheck + build**

Run: `cd frontend && npm run test -- --run && npx tsc --noEmit && npm run build`
Expected: all tests pass, tsc clean, build succeeds.

- [ ] **Step 6: Commit**

```bash
git add frontend/src/components/QuestionCard.tsx "frontend/src/app/test/[id]/page.tsx" frontend/src/components/__tests__/QuestionCard.test.tsx frontend/src/lib/api.ts
git commit -m "feat: textarea for open questions on the exam screen"
```

---

### Task 10: Results page — "Open questions" section

**Files:**
- Modify: `frontend/src/app/test/[id]/results/page.tsx`

- [ ] **Step 1: Add the open-questions section**

In `frontend/src/app/test/[id]/results/page.tsx`, after the "Разбор вопросов" (closed questions) block and before the component's closing `</div>`, add:
```tsx
      {results.open_questions.length > 0 && (
        <>
          <h3 style={{ marginTop: 24 }}>Открытые вопросы</h3>
          {results.open_questions.map((o) => (
            <div key={o.id} className="card" style={{ marginTop: 12, borderLeft: "4px solid #2f6fed" }}>
              <div className="label">Открытый вопрос {o.seq}</div>
              <h4 style={{ margin: "8px 0" }}>{o.stem}</h4>
              <div className="label" style={{ marginTop: 8 }}>Ваш ответ:</div>
              <p style={{ whiteSpace: "pre-wrap", marginTop: 4 }}>
                {o.answer_text || "— (ответ не дан)"}
              </p>
              <div className="label" style={{ marginTop: 12 }}>Обратная связь:</div>
              <p style={{ whiteSpace: "pre-wrap", marginTop: 4, color: "#1f3a5f" }}>{o.feedback}</p>
              <p style={{ marginTop: 10, color: "#5a6878" }}><b>Разбор:</b> {o.explanation}</p>
            </div>
          ))}
        </>
      )}
```

- [ ] **Step 2: Typecheck + build**

Run: `cd frontend && npx tsc --noEmit && npm run build`
Expected: tsc clean, build succeeds.

- [ ] **Step 3: Commit**

```bash
git add "frontend/src/app/test/[id]/results/page.tsx"
git commit -m "feat: results page shows open questions with LLM feedback"
```

---

### Task 11: Full verification + live smoke

**Files:** none

- [ ] **Step 1: Backend suite + lint**

Run: `cd backend && . .venv/bin/activate && pytest -q && ruff check app tests`
Expected: all pass, lint clean. Run twice for determinism.

- [ ] **Step 2: Frontend suite + build**

Run: `cd frontend && npm run test -- --run && npx tsc --noEmit && npm run build`
Expected: all pass, tsc clean, build succeeds.

- [ ] **Step 3: Live smoke** (needs a real `OPENAI_API_KEY`)

Start the backend, create an adaptive base session, poll to ready, fetch `/questions` and confirm:
  - 2 questions have `type: "open"` and NO `rubric`/`correct_keys` field.
  - The open questions' seq are the last two.
Submit a text answer to an open question, finish, fetch `/results`, confirm:
  - `open_questions` has 2 entries with `feedback`.
  - `score_percent` reflects closed questions only (open answers don't change it).
Report the observed values. If no key, skip and note the unit tests already prove the logic.

- [ ] **Step 4: Confirm success criteria**
  - 2 open questions appear after the closed pool, every session.
  - Open answers get LLM feedback; empty answers get the stub (no LLM call).
  - `score_percent`/`passed`/`topic_breakdown` count closed questions only.
  - `rubric` never leaves the backend; `/questions` and `/results` open section omit it.

---

## Self-Review Notes

Checked against spec sections 2–7. Coverage: §3 model changes → Task 1; §4 generation → Tasks 3, 6; §5 evaluation → Tasks 4, 5, 7; results `open_questions` → Tasks 7, 10; §6 frontend → Tasks 8–10; closed-only scoring (the critical §3 invariant) → Task 7 Steps 5–6 (explicit `is_closed` filter, `total = len(closed)`). Decision 6 (empty-answer stub, no LLM) → Task 5. Decision 7 (rubric secret) → Tasks 6 (not in `/questions` — the existing `/questions` handler already allowlists fields and won't include `rubric`), 7 (results open section omits `rubric`, asserted). Parallel judging (decision 4) → Task 7 Step 5 (`asyncio.gather`). No placeholders — every step has complete code. Type consistency: `OpenQuestion`/`OpenBatch`, `generate_open_questions`/`judge_open`, `evaluate_open`, `is_closed`, `submit_answer(selected_keys=, answer_text=)`, `open_questions`/`OpenReview`, `onAnswerText`/`answerText` are consistent across backend and frontend tasks. One coupling note: Task 8 intentionally leaves tsc failing at exam-page call sites; Task 9 fixes them — flagged in Task 8 Step 3. Existing-test compatibility (submit_answer positional `selected_keys`, generator fakes lacking `generate_open_questions`) is explicitly addressed in Task 6 Step 4 and Task 7 Step 8.
```
