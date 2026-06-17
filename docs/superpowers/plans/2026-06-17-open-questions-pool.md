# Open-Question Pool (fixed seed + LLM) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Open questions are drawn from a pool of fixed real-world cases plus LLM-generated cases (2 chosen at random per session), formatted like the real BA certification (visible "Фокус ответа" / "Критерии оценки", 2500-char hint), with a separate hidden rubric for the judge.

**Architecture:** A single `build_open_stem()` helper is the one source of the visible stem format, used by both the seed module and the LLM path. `open_seed.py` holds the 2 real cases as `OpenQuestion`s built via that helper. `generate_open_questions` returns LLM cases in the same format. The generator builds `pool = seed + LLM`, deterministically samples 2 by session id, and writes them exactly as today (seq after closed, `generated_count` bumped).

**Tech Stack:** FastAPI, SQLAlchemy async, Pydantic v2, OpenAI SDK (AsyncOpenAI, strict json_schema), pytest; Next.js/React/TypeScript, Vitest.

**Spec:** `docs/superpowers/specs/2026-06-17-open-questions-pool-design.md`

**Working dir for backend commands:** `cd /Users/pavel/Developer/antests/backend && . .venv/bin/activate`
**Working dir for frontend commands:** `cd /Users/pavel/Developer/antests/frontend`

---

### Task 1: `build_open_stem` helper — the single source of the visible stem format

**Files:**
- Modify: `backend/app/generation/openai_client.py` (add a module-level function near the top, after the existing helpers like `_parse_json_content` around line 64–98)
- Test: `backend/tests/test_open_stem.py` (create)

This helper assembles the full visible stem (header + case + task + focus + visible criteria) from parts. Both the seed module (Task 2) and the LLM path (Task 3) call it, so the format is identical and DRY.

- [ ] **Step 1: Write the failing test**

Create `backend/tests/test_open_stem.py`:

```python
from app.generation.openai_client import build_open_stem


def test_build_open_stem_has_all_blocks():
    stem = build_open_stem(
        topic_title="От бизнес-проблемы к требованиям",
        case="В финтех-компании растёт количество обращений.",
        task="Сформулируйте до 5 уточняющих вопросов.",
        focus="Не нужно проектировать архитектуру.",
        criteria_visible="понимание бизнес-потребности; качество вопросов.",
    )
    # Header lines
    assert "до 2500 знаков с пробелами" in stem
    assert "Тип: открытый кейс. От бизнес-проблемы к требованиям" in stem
    # Body blocks, each on its own labelled line
    assert "В финтех-компании растёт количество обращений." in stem
    assert "Задание: Сформулируйте до 5 уточняющих вопросов." in stem
    assert "Фокус ответа: Не нужно проектировать архитектуру." in stem
    assert "Критерии оценки: понимание бизнес-потребности; качество вопросов." in stem
    # Blocks are newline-separated so the frontend can render them on separate lines
    assert "\n" in stem
    assert stem.count("\n\n") >= 1  # blank line between header/case and blocks
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /Users/pavel/Developer/antests/backend && . .venv/bin/activate && pytest tests/test_open_stem.py -v`
Expected: FAIL with `ImportError: cannot import name 'build_open_stem'`

- [ ] **Step 3: Write the implementation**

In `backend/app/generation/openai_client.py`, add after `_parse_json_content` (around line 73, before `build_generation_system_prompt`):

```python
def build_open_stem(
    topic_title: str, case: str, task: str, focus: str, criteria_visible: str
) -> str:
    """Assemble the full visible stem of an open question.

    Single source of the open-question format — used by both the seed module
    and the LLM generation path so fixed and generated questions look identical.
    The blocks are newline-separated; the frontend renders the stem with
    white-space: pre-line so they appear on separate labelled lines, matching
    the real BA certification layout.
    """
    return (
        "Ответ: до 2500 знаков с пробелами; достаточно тезисного, "
        "структурированного ответа.\n"
        f"Тип: открытый кейс. {topic_title.strip()}\n\n"
        f"{case.strip()}\n\n"
        f"Задание: {task.strip()}\n"
        f"Фокус ответа: {focus.strip()}\n"
        f"Критерии оценки: {criteria_visible.strip()}"
    )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_open_stem.py -v`
Expected: PASS

- [ ] **Step 5: Lint and commit**

```bash
ruff check app tests
git add app/generation/openai_client.py tests/test_open_stem.py
git commit -m "feat: add build_open_stem — single source of open-question format"
```

---

### Task 2: `open_seed.py` — the 2 real BA cases as a fixed pool

**Files:**
- Create: `backend/app/generation/open_seed.py`
- Test: `backend/tests/test_open_seed.py` (create)

Holds the two real cases (БА-1, БА-2) as `OpenQuestion` objects, each built via `build_open_stem`. Stores parts, not pre-assembled text, so a format change in `build_open_stem` propagates here too.

- [ ] **Step 1: Write the failing test**

Create `backend/tests/test_open_seed.py`:

```python
from app.generation.open_seed import SEED_OPEN_QUESTIONS
from app.generation.schemas import OpenQuestion


def test_seed_pool_nonempty_and_valid():
    assert len(SEED_OPEN_QUESTIONS) >= 2
    for q in SEED_OPEN_QUESTIONS:
        assert isinstance(q, OpenQuestion)  # passes OpenQuestion._check (non-empty fields)
        # Visible stem carries the labelled blocks the real test shows
        assert "Задание:" in q.stem
        assert "Фокус ответа:" in q.stem
        assert "Критерии оценки:" in q.stem
        assert "до 2500 знаков" in q.stem
        # Hidden rubric is separate from the visible stem and non-trivial
        assert q.rubric and q.rubric not in q.stem
        assert q.explanation


def test_seed_pool_covers_the_two_known_cases():
    titles = " ".join(q.stem for q in SEED_OPEN_QUESTIONS)
    assert "От бизнес-проблемы к требованиям" in titles
    assert "Изменение, приемка и готовность результата" in titles \
        or "Изменение, приёмка и готовность результата" in titles
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_open_seed.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.generation.open_seed'`

- [ ] **Step 3: Write the implementation**

Create `backend/app/generation/open_seed.py`:

```python
"""Fixed pool of real open-ended certification cases.

These are real BA-certification cases (base level). They live alongside
LLM-generated open questions in the candidate pool; the generator samples 2
per session. Add future cases by appending to SEED_OPEN_QUESTIONS.

Each case stores its PARTS and is assembled with build_open_stem so the format
stays identical to LLM-generated questions (DRY).
"""

from app.generation.openai_client import build_open_stem
from app.generation.schemas import OpenQuestion

# --- БА-1: От бизнес-проблемы к требованиям ---
_BA1 = OpenQuestion(
    stem=build_open_stem(
        topic_title="От бизнес-проблемы к требованиям",
        case=(
            "В финтех-компании растёт количество обращений клиентов по статусу "
            "заявки на продукт. Руководитель клиентского сервиса говорит: "
            "«Клиенты часто пишут повторно, потому что не понимают, где находится "
            "заявка и почему она задержалась». Сейчас статусы ведутся в нескольких "
            "системах, а операторы вручную уточняют информацию у смежных "
            "подразделений."
        ),
        task=(
            "Сформулируйте до 5 уточняющих вопросов к заинтересованным сторонам, "
            "до 4 требований верхнего уровня к будущему решению и укажите, какие "
            "1–2 требования должны быть приоритетными для первой реализации и почему."
        ),
        focus=(
            "Не нужно проектировать архитектуру. Нужно показать переход от "
            "проблемы к проверяемым требованиям: цель, пользователи, статусы, "
            "данные, критерии приёмки и приоритетность объёма."
        ),
        criteria_visible=(
            "понимание бизнес-потребности; качество уточняющих вопросов; "
            "проверяемость требований; учёт заинтересованных сторон; обоснование "
            "приоритетов; структура ответа."
        ),
    ),
    rubric=(
        "Сильный ответ: (1) формулирует бизнес-цель и метрику успеха (снижение "
        "повторных обращений, прозрачность статуса); (2) задаёт уточняющие "
        "вопросы про источники статусов, единый источник правды, SLA смежных "
        "подразделений, каналы уведомления клиента, права доступа; (3) выводит "
        "проверяемые требования верхнего уровня (единый статус заявки, "
        "самообслуживание клиента, нотификации при смене статуса, объяснение "
        "задержки); (4) выделяет 1–2 приоритетных требования с обоснованием "
        "(быстрая ценность / снижение нагрузки); (5) разделяет пользовательские, "
        "бизнес- и системные требования; структура и реалистичный объём."
    ),
    explanation=(
        "Проверяется умение аналитика не прыгать в решение, а перейти от "
        "бизнес-проблемы к проверяемым требованиям: уточнить контекст у "
        "стейкхолдеров, описать цель и приоритеты, обосновать порядок реализации."
    ),
)

# --- БА-2: Изменение, приёмка и готовность результата ---
_BA2 = OpenQuestion(
    stem=build_open_stem(
        topic_title="Изменение, приёмка и готовность результата",
        case=(
            "Перед релизом заказчик просит добавить новый признак «повышенный "
            "риск» для заявок. Признак должен отображаться оператору, передаваться "
            "в систему проверки и учитываться при ручном согласовании. Часть "
            "данных приходит из внешнего сервиса, который иногда отвечает с "
            "задержкой."
        ),
        task=(
            "Опишите, какие вопросы нужно уточнить до принятия изменения в релиз, "
            "и какие критерии приёмки нужно зафиксировать."
        ),
        focus=(
            "Нужно не описывать полную процедуру изменения, а выделить влияние на "
            "требования, данные, интеграции, статусы, приёмку и риски релиза."
        ),
        criteria_visible=(
            "выявление влияния изменения; качество вопросов; приёмочные критерии; "
            "учёт интеграции и задержек; реалистичность объёма ответа."
        ),
    ),
    rubric=(
        "Сильный ответ: (1) уточняет смысл и источник признака «повышенный риск», "
        "правила его расчёта, кто и когда его выставляет; (2) разбирает влияние на "
        "требования, данные, интеграции (внешний сервис), статусы и ручное "
        "согласование; (3) учитывает задержки/недоступность внешнего сервиса — "
        "таймауты, поведение при отсутствии данных, фолбэк; (4) формулирует "
        "проверяемые критерии приёмки (отображение оператору, передача в проверку, "
        "учёт при согласовании, обработка ошибок интеграции); (5) оценивает риски "
        "релиза и реалистичность объёма изменения."
    ),
    explanation=(
        "Проверяется умение оценить влияние изменения перед релизом: выделить "
        "затронутые требования, данные и интеграции, продумать поведение при "
        "задержках внешнего сервиса и зафиксировать проверяемые критерии приёмки."
    ),
)

SEED_OPEN_QUESTIONS: list[OpenQuestion] = [_BA1, _BA2]
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_open_seed.py -v`
Expected: PASS (both tests)

- [ ] **Step 5: Lint and commit**

```bash
ruff check app tests
git add app/generation/open_seed.py tests/test_open_seed.py
git commit -m "feat: add open_seed with the 2 real BA certification cases"
```

---

### Task 3: LLM path returns parts and assembles stem via the shared helper

**Files:**
- Modify: `backend/app/generation/openai_client.py` — rewrite the prompt, json_schema, and parse step of `generate_open_questions` (currently lines ~277–344)
- Test: `backend/tests/test_open_generation.py` — add a test (file already exists)

The LLM now returns `topic_title, case, task, focus, criteria_visible, rubric, explanation`. The code calls `build_open_stem(...)` for each and constructs `OpenQuestion(stem=…, rubric=…, explanation=…)`. The strict json_schema is widened to the new fields.

- [ ] **Step 1: Write the failing test**

Add to `backend/tests/test_open_generation.py` (the file has `_Client`, `_SeqClient`, `_Completion` helpers — reuse `_Client`):

```python
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
    # Visible stem assembled with the labelled blocks
    assert "Задание: Сформулируйте до 5 уточняющих вопросов" in q.stem
    assert "Фокус ответа: Не проектируйте архитектуру" in q.stem
    assert "Критерии оценки: качество вопросов" in q.stem
    assert "Тип: открытый кейс. От бизнес-проблемы к требованиям" in q.stem
    # Hidden rubric stays out of the visible stem
    assert q.rubric == "Скрытые подробные критерии для судьи, которых нет в stem."
    assert q.rubric not in q.stem
    assert q.explanation
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_open_generation.py::test_generate_open_questions_assembles_stem_from_parts -v`
Expected: FAIL — the current code expects `stem` in the payload and would raise a ValidationError / KeyError on the new shape (model returns parts, not `stem`).

- [ ] **Step 3: Rewrite `generate_open_questions`**

Replace the body of `generate_open_questions` in `backend/app/generation/openai_client.py` (the method spanning ~277–344). Keep the retry loop and `OpenAIResponseError` handling; change the prompt, schema, and the parse/return step. New full method:

```python
    async def generate_open_questions(
        self, level: str, count: int = 3
    ) -> list[OpenQuestion]:
        prompt = (
            f"Сгенерируй {count} ОТКРЫТЫХ вопроса-кейса для сертификации системного "
            f"аналитика (уровень {level}), в формате реального экзамена. Каждый — "
            "практическая ситуация, требующая развёрнутого текстового ответа (НЕ "
            "выбор варианта), объёмом ответа до 2500 знаков с пробелами. Для "
            "КАЖДОГО верни структурные части:\n"
            "- topic_title: короткая тема кейса (напр. «От бизнес-проблемы к "
            "требованиям»);\n"
            "- case: описание практической ситуации (2–4 предложения);\n"
            "- task: что именно сделать, с числовыми рамками (напр. «до 5 "
            "уточняющих вопросов, до 4 требований…»);\n"
            "- focus: на чём сфокусироваться и что НЕ нужно делать;\n"
            "- criteria_visible: краткие критерии оценки через точку с запятой "
            "(показываются студенту);\n"
            "- rubric: ПОДРОБНЫЕ скрытые критерии для проверяющего — что обязательно "
            "должно быть в сильном ответе (студенту НЕ показывается, должен быть "
            "детальнее, чем criteria_visible);\n"
            "- explanation: краткий разбор, что отличает сильный ответ (показывается "
            "на результатах).\n"
            "Пиши по-русски. Верни СТРОГО JSON по схеме."
        )
        response_format = {
            "type": "json_schema",
            "json_schema": {
                "name": "open_batch",
                "schema": {
                    "type": "object",
                    "additionalProperties": False,
                    "properties": {
                        "questions": {
                            "type": "array",
                            "items": {
                                "type": "object",
                                "additionalProperties": False,
                                "properties": {
                                    "topic_title": {"type": "string"},
                                    "case": {"type": "string"},
                                    "task": {"type": "string"},
                                    "focus": {"type": "string"},
                                    "criteria_visible": {"type": "string"},
                                    "rubric": {"type": "string"},
                                    "explanation": {"type": "string"},
                                },
                                "required": [
                                    "topic_title", "case", "task", "focus",
                                    "criteria_visible", "rubric", "explanation",
                                ],
                            },
                        }
                    },
                    "required": ["questions"],
                },
                "strict": True,
            },
        }
        last_err: Exception | None = None
        for _attempt in range(3):
            try:
                resp = await self._client.chat.completions.create(
                    model=self.gen_model,
                    messages=[
                        {"role": "system",
                         "content": "Ты — экзаменатор сертификации системных аналитиков IBS."},
                        {"role": "user", "content": prompt},
                    ],
                    response_format=response_format,
                )
                data = _parse_json_content(resp)
                return [
                    OpenQuestion(
                        stem=build_open_stem(
                            topic_title=item["topic_title"],
                            case=item["case"],
                            task=item["task"],
                            focus=item["focus"],
                            criteria_visible=item["criteria_visible"],
                        ),
                        rubric=item["rubric"],
                        explanation=item["explanation"],
                    )
                    for item in data["questions"]
                ]
            except Exception as e:  # noqa: BLE001 — retry on any failure, raise the last
                last_err = e
        assert last_err is not None  # loop ran ≥1 time, so this is always bound
        raise last_err
```

Note: `OpenBatch` is no longer used by this method (the parse is now a list comprehension over `data["questions"]`). Leave the `OpenBatch` import/class in place if other code references it; otherwise it is harmless. Do NOT remove the `OpenQuestion` import.

- [ ] **Step 4: Run the test and the existing open-generation suite**

Run: `pytest tests/test_open_generation.py -v`
Expected: the new test PASSES. NOTE: pre-existing tests `test_generate_open_questions_parses_two` and `test_generate_open_questions_retries_on_schema_echo` feed the OLD payload shape (`stem/rubric/explanation`) and will now FAIL because the method expects the new parts. Update those two tests to the new shape: replace their `_OPEN_PAYLOAD`/inline payloads so each question dict has `topic_title, case, task, focus, criteria_visible, rubric, explanation` (mirror the payload from Step 1). The retry test's valid payload must also use the new shape; the `_SCHEMA_ECHO` constant stays as-is (it tests the echo→retry path, still valid). After updating, all open-generation tests pass.

- [ ] **Step 5: Run, lint, commit**

Run: `pytest tests/test_open_generation.py -q && ruff check app tests`
Expected: all pass, lint clean

```bash
git add app/generation/openai_client.py tests/test_open_generation.py
git commit -m "feat: open-question LLM path returns parts, assembles stem via build_open_stem"
```

---

### Task 4: Generator builds the pool (seed + LLM) and samples 2

**Files:**
- Modify: `backend/app/generation/generator.py` — the open-question block (currently lines 142–164) and add a module constant near the top (after `ARTIFACT_TOPICS`, ~line 18)
- Test: `backend/tests/test_open_generation.py` — add tests (file exists; has `FakeGenClient`, `_closed_q`)

- [ ] **Step 1: Write the failing tests**

Add to `backend/tests/test_open_generation.py`. First, a class-level helper to make the fake client's open generation observable and switchable:

```python
class FailingOpenClient(FakeGenClient):
    async def generate_open_questions(self, level, count=3):
        raise RuntimeError("openai down")


@pytest.mark.asyncio
async def test_generator_samples_two_from_pool(db_session):
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

    qs = (await db_session.execute(
        select(Question).where(Question.session_id == s.id).order_by(Question.seq))).scalars().all()
    openq = [q for q in qs if q.type == "open"]
    assert len(openq) == 2  # exactly 2 sampled from the pool
    assert s.generated_count == max(q.seq for q in qs)


@pytest.mark.asyncio
async def test_generator_uses_seed_when_llm_fails(db_session):
    # If the LLM open-generation fails, the pool is still the seed cases, so the
    # session still gets 2 open questions (more robust than before).
    user = User(login=f"u{uuid.uuid4().hex[:8]}", password_hash="x")
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    s = TestSession(user_id=user.id, level="base", mode="exam", status="generating",
                    total_questions=3, generated_count=0, time_limit_sec=7200)
    db_session.add(s)
    await db_session.commit()
    await db_session.refresh(s)

    gen = Generator(db_session, FailingOpenClient(), batch_size=10)
    await gen.run(s.id, plan=[("data", 3)])
    await db_session.refresh(s)
    assert s.status == "ready"
    openq = (await db_session.execute(
        select(Question).where(Question.session_id == s.id, Question.type == "open"))).scalars().all()
    assert len(openq) == 2  # seed pool alone fills the 2 slots
    assert s.generated_count == 5  # 3 closed + 2 open


@pytest.mark.asyncio
async def test_generator_open_sampling_is_deterministic(db_session):
    # Two sessions with the SAME id would sample the same questions. We can't
    # reuse an id across sessions, so assert the sampling helper is seeded by
    # session id by checking the chosen stems are reproducible for a fixed seed.
    import random
    from app.generation.generator import _sample_open_pool
    pool = [f"q{i}" for i in range(5)]
    a = _sample_open_pool(pool, 2, random.Random("seed-x"))
    b = _sample_open_pool(pool, 2, random.Random("seed-x"))
    assert a == b
    assert len(a) == 2
    assert len(set(a)) == 2  # no duplicates
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_open_generation.py -k "pool or seed_when_llm or deterministic" -v`
Expected: FAIL — `_sample_open_pool` doesn't exist; `FakeGenClient.generate_open_questions` currently returns 2 (so `test_generator_samples_two_from_pool` may pass incidentally, but the deterministic + seed tests fail on the missing import).

- [ ] **Step 3: Implement the pool + sampling in the generator**

In `backend/app/generation/generator.py`:

(a) Add imports at the top (the file already imports `random`):

```python
from app.db.models import Question, TestSession
from app.generation.open_seed import SEED_OPEN_QUESTIONS
```

(b) Add a module constant after `ARTIFACT_TOPICS` (~line 18):

```python
# How many open-question candidates the LLM generates. Pool = seed + this; we
# sample 2. 3 gives variety (sometimes both real, sometimes a mix) without
# extra cost. Raise as the seed pool grows.
LLM_OPEN_CANDIDATES = 3
OPEN_PER_SESSION = 2
```

(c) Add a module-level sampling helper (after the constants, before `class Generator`):

```python
def _sample_open_pool(pool, k, rng):
    """Pick k distinct items from pool using rng. Returns ≤k items (all of pool
    if it has fewer than k). Seeded rng → deterministic, reproducible choice."""
    if len(pool) <= k:
        return list(pool)
    return rng.sample(pool, k)
```

(d) Replace the open-question block (current lines 142–164) with:

```python
            # Build a pool of open-question candidates (fixed real cases + LLM)
            # and sample OPEN_PER_SESSION of them. seq after the closed pool; a
            # failure in LLM generation just shrinks the pool to the seed cases,
            # so the session still gets its open questions. The whole block must
            # not block readiness — open questions are a bonus section.
            try:
                pool = list(SEED_OPEN_QUESTIONS)
                try:
                    pool += await self.client.generate_open_questions(
                        session.level, count=LLM_OPEN_CANDIDATES)
                except Exception:
                    logger.exception(
                        "LLM open-question generation failed for session %s "
                        "(falling back to seed pool)", session_id)
                rng = random.Random(str(session.id))
                chosen = _sample_open_pool(pool, OPEN_PER_SESSION, rng)
                for oq in chosen:
                    seq += 1
                    self.db.add(Question(
                        session_id=session.id, seq=seq, topic_id="open",
                        type="open", stem=oq.stem, artifact_kind="none",
                        artifact_content=None, options=[], correct_keys=[],
                        explanation=oq.explanation, rubric=oq.rubric,
                        validation_status="passed",
                    ))
                # Bump generated_count to include the open questions so the exam
                # UI's readiness check (seq <= generated_count) unlocks them.
                session.generated_count = seq
                await self.db.commit()
            except Exception:
                logger.exception("Open-question step failed for session %s", session_id)
```

Note: the outer `try/except` now guards the sampling/DB write; the inner `try/except` guards only the LLM call so the seed pool survives an LLM failure.

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_open_generation.py -v`
Expected: all PASS, including the existing `test_generator_appends_two_open_questions` (still 2 open, seq after closed, `generated_count` covers them). Pool math: `FakeGenClient.generate_open_questions(count=LLM_OPEN_CANDIDATES)` returns 3 LLM items + 2 seed = pool of 5, sampled to 2; the assertion `len(openq) == 2` holds regardless of pool size.

- [ ] **Step 5: Run full backend suite, lint, commit**

Run: `pytest -q && ruff check app tests`
Expected: all pass, lint clean

```bash
git add app/generation/generator.py tests/test_open_generation.py
git commit -m "feat: generator samples 2 open questions from seed+LLM pool"
```

---

### Task 5: Frontend — multiline stem + 2500-char hint

**Files:**
- Modify: `frontend/src/components/QuestionCard.tsx` (the `<h3>` stem at line 19 and the open `<textarea>` block at lines 21–31)
- Test: `frontend/src/components/__tests__/QuestionCard.test.tsx` (file exists; has the open-question test)

The assembled stem has newlines (`Задание:` / `Фокус ответа:` / `Критерии оценки:` on separate lines). The default `<h3>` collapses whitespace, so add `white-space: pre-line` for open questions. Add a hint about the 2500-char limit near the textarea.

- [ ] **Step 1: Write the failing test**

Add to `frontend/src/components/__tests__/QuestionCard.test.tsx`, inside the `describe("QuestionCard", …)` block:

```typescript
  it("renders an open question's multiline stem and a length hint", () => {
    const openQ: Question = {
      id: "o1", seq: 81, topic_id: "open", type: "open",
      stem: "Кейс…\n\nЗадание: сделайте X\nФокус ответа: Y\nКритерии оценки: Z",
      artifact_kind: "none", artifact_content: null, options: [],
    };
    render(
      <QuestionCard question={openQ} selected={[]} onToggle={() => {}}
        answerText="" onAnswerText={() => {}} />
    );
    // Stem heading preserves newlines (pre-line) so blocks aren't collapsed
    const heading = screen.getByRole("heading", { level: 3 });
    expect(heading).toHaveStyle({ whiteSpace: "pre-line" });
    // A hint about the 2500-char limit is visible
    expect(screen.getByText(/2500 знаков/)).toBeInTheDocument();
  });
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /Users/pavel/Developer/antests/frontend && npx vitest run src/components/__tests__/QuestionCard.test.tsx`
Expected: FAIL — the `<h3>` has no `whiteSpace: pre-line`, and there is no "2500 знаков" text.

- [ ] **Step 3: Implement the changes**

In `frontend/src/components/QuestionCard.tsx`:

(a) Change the stem heading (line 19) so open questions preserve newlines:

```tsx
      <h3 style={{ margin: "8px 0 16px", whiteSpace: question.type === "open" ? "pre-line" : undefined }}>{question.stem}</h3>
```

(b) Replace the open `<textarea>` block (lines 21–31) to add the hint below the textarea:

```tsx
      {question.type === "open" ? (
        <div>
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
          <div className="label" style={{ marginTop: 6 }}>
            До 2500 знаков с пробелами; достаточно тезисного, структурированного ответа.
          </div>
        </div>
      ) : (
```

- [ ] **Step 4: Run test to verify it passes**

Run: `npx vitest run src/components/__tests__/QuestionCard.test.tsx`
Expected: PASS (the existing open-question test that types into the textbox still passes — `getByRole("textbox")` still resolves).

- [ ] **Step 5: Typecheck, full frontend suite, commit**

Run: `npx tsc --noEmit && npx vitest run`
Expected: tsc clean; all tests pass

```bash
cd /Users/pavel/Developer/antests
git add frontend/src/components/QuestionCard.tsx frontend/src/components/__tests__/QuestionCard.test.tsx
git commit -m "feat: render open-question multiline stem + 2500-char hint"
```

---

### Task 6: Full verification + live smoke

**Files:** none (verification only)

- [ ] **Step 1: Full backend suite + lint**

Run: `cd /Users/pavel/Developer/antests/backend && . .venv/bin/activate && pytest -q && ruff check app tests`
Expected: all pass, lint clean.

- [ ] **Step 2: Full frontend suite + typecheck + build**

Run: `cd /Users/pavel/Developer/antests/frontend && npx vitest run && npx tsc --noEmit && npm run build`
Expected: all tests pass, tsc clean, build succeeds.

- [ ] **Step 3: Live smoke — pool sampling produces 2 well-formatted open questions**

Start the backend, create a base adaptive session, poll to ready, fetch `/questions`. Confirm:
- exactly 2 questions have `type: "open"`, at the last two seq (> closed count);
- each open `stem` contains `Задание:`, `Фокус ответа:`, `Критерии оценки:` and `до 2500 знаков`;
- NO `rubric` or `correct_keys` field on the open questions (secrecy preserved).

Use a script analogous to the prior live smoke (urllib + cookiejar, venv python). Run several sessions and confirm the sampling varies (sometimes a real case appears, sometimes an LLM one) — at minimum confirm one session contains a real-case marker (`От бизнес-проблемы к требованиям` or `Изменение, приёмка и готовность результата`) across a few runs, proving seed cases reach the pool.

- [ ] **Step 4: Live smoke — answer + finish + results unchanged**

Submit a text answer to one open question, finish, fetch `/results`. Confirm: `open_questions` has 2 entries with feedback; `score_percent` reflects closed questions only; `rubric` not present in the results payload.

- [ ] **Step 5: Stop servers; report**

Stop uvicorn/next. Report results of all steps with evidence (counts, sample stems, score).

---

## Notes for the implementer

- **DRY:** `build_open_stem` is the ONLY place that defines the visible open-question format. Seed and LLM both go through it.
- **Hidden rubric:** never add `rubric` to any client response. It stays out of `stem` by construction (the LLM returns it as a separate field; seed stores it separately).
- **Determinism:** open sampling uses `random.Random(str(session.id))`, matching the closed-question shuffle. Same session id → same sample.
- **Robustness:** an LLM failure no longer zeroes out open questions — the seed pool (≥2) covers the 2 slots.
- **No DB migration:** this feature adds no columns. `open_seed.py` is a plain Python module.
