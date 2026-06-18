# Base/Specialist Revamp Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make base/specialist 53 questions (50 closed + 3 open), 120-min limit, zero artifacts, with 3 open = 1 random seed + 1 LLM "Интеграция" + 1 LLM "Системное мышление". Leave `ba` unchanged.

**Architecture:** All changes are Python constants + generator logic — no DB migration. Per-level config dicts (`LEVEL_TOTALS`, `LEVEL_TIME_LIMITS`, `LEVEL_OPEN_COUNT`, `LEVEL_ARTIFACT_TOPICS`) drive behavior. A new `generate_open_on_topic` client method produces a single themed open question; the generator assembles base/specialist open questions deterministically while `ba` keeps its pool logic.

**Tech Stack:** FastAPI, SQLAlchemy async, Pydantic v2, OpenAI SDK (strict json_schema); pytest.

**Spec:** `docs/superpowers/specs/2026-06-18-base-specialist-revamp-design.md`

**Working dir:** `cd /Users/pavel/Developer/antests/backend && . .venv/bin/activate`

---

### Task 1: Totals (50) and specialist time limit (120 min)

**Files:**
- Modify: `backend/app/generation/planner.py:3` (LEVEL_TOTALS)
- Modify: `backend/app/generation/service.py:10` (LEVEL_TIME_LIMITS)
- Test: `backend/tests/test_planner.py`, `backend/tests/test_sessions_api.py`

- [ ] **Step 1: Update planner & sessions-api regression tests**

In `backend/tests/test_planner.py`, the existing `test_exam_plan_totals_match_level` asserts base==80, spec==120. Replace those two asserts:
```python
def test_exam_plan_totals_match_level():
    base = plan_exam("base")
    spec = plan_exam("specialist")
    assert sum(c for _, c in base) == 50
    assert sum(c for _, c in spec) == 50
```
Add a coverage assert (both still cover all 10 SA topics at 50):
```python
def test_exam_plan_base_specialist_cover_all_10_topics_at_50():
    for level in ("base", "specialist"):
        plan = dict(plan_exam(level))
        assert sum(plan.values()) == 50
        assert len(plan) == 10
        assert all(c >= 1 for c in plan.values())
```

- [ ] **Step 2: Run to verify it fails**

Run: `pytest tests/test_planner.py -v`
Expected: FAIL — base/spec still sum to 80/120.

- [ ] **Step 3: Update LEVEL_TOTALS and LEVEL_TIME_LIMITS**

`backend/app/generation/planner.py:3`:
```python
LEVEL_TOTALS = {"base": 50, "specialist": 50, "ba": 40}
```
`backend/app/generation/service.py:10`:
```python
LEVEL_TIME_LIMITS = {"base": 120 * 60, "specialist": 120 * 60, "ba": 90 * 60}
```

- [ ] **Step 4: Run to verify it passes**

Run: `pytest tests/test_planner.py -v`
Expected: PASS (base/spec sum 50, 10 topics each).

- [ ] **Step 5: Update the sessions-api time-limit expectation if present**

In `backend/tests/test_sessions_api.py`, search for any assertion on specialist time (e.g. `time_limit_sec == 180 * 60` or `== 10800`) or base/specialist total (`== 80`/`== 120`). If found, update specialist time to `120 * 60` and base/spec totals to `50`. The ba test (`test_create_ba_session_uses_40_and_90min`) is unaffected. Run `grep -n "10800\|180 \* 60\|== 80\|== 120\|total_questions" backend/tests/test_sessions_api.py` and fix any base/specialist-specific numbers. Report what you changed.

- [ ] **Step 6: Run full suite, lint, commit**

Run: `pytest -q && ruff check app tests`
Expected: all pass. (Some generator/api tests may still assume old totals — fix any base/specialist count assertions you find, leave ba alone, report them.)

```bash
git add app/generation/planner.py app/generation/service.py tests/test_planner.py tests/test_sessions_api.py
git commit -m "feat: base/specialist 50 closed questions, 120-min limit"
```

---

### Task 2: `generate_open_on_topic` — one themed open question

**Files:**
- Modify: `backend/app/generation/openai_client.py` (add method after `generate_open_questions`, which ends at line ~416, before `judge_open`)
- Test: `backend/tests/test_open_generation.py`

This mirrors `generate_open_questions` but takes a `topic_title`/`hint`, asks for ONE question, and returns a single `OpenQuestion`.

- [ ] **Step 1: Write the failing test**

Add to `backend/tests/test_open_generation.py` (uses existing `_Client`, `json`, `OpenAIClient`, `OpenQuestion`):
```python
@pytest.mark.asyncio
async def test_generate_open_on_topic_builds_one_question():
    payload = {
        "topic_title": "Описание интеграции",
        "case": "Двум системам нужно обмениваться заявками.",
        "task": "Опишите требования, уточняющие вопросы, критерии приёмки, риски.",
        "focus": "Не проектируйте код; сфокусируйтесь на интеграционных аспектах.",
        "criteria_visible": "полнота требований; качество вопросов; критерии приёмки; риски.",
        "rubric": "Скрытые подробные критерии для судьи по интеграции.",
        "explanation": "Проверяется системный подход к описанию интеграции.",
    }
    client = OpenAIClient(api_key="x", gen_model="g", validate_model="v",
                          _client=_Client(json.dumps(payload)))
    q = await client.generate_open_on_topic("Описание интеграции", "раскрой требования и критерии приёмки")
    assert isinstance(q, OpenQuestion)
    assert "Задание: Опишите требования" in q.stem
    assert "Тип: открытый кейс. Описание интеграции" in q.stem
    assert q.rubric == "Скрытые подробные критерии для судьи по интеграции."
    assert q.rubric not in q.stem
    assert q.explanation
```

- [ ] **Step 2: Run to verify it fails**

Run: `pytest tests/test_open_generation.py::test_generate_open_on_topic_builds_one_question -v`
Expected: FAIL — `AttributeError: 'OpenAIClient' object has no attribute 'generate_open_on_topic'`.

- [ ] **Step 3: Implement the method**

In `backend/app/generation/openai_client.py`, insert AFTER `generate_open_questions` (after its final `raise last_err`, line ~416) and BEFORE `async def judge_open`:
```python
    async def generate_open_on_topic(
        self, topic_title: str, hint: str
    ) -> OpenQuestion:
        prompt = (
            f"Сгенерируй 1 ОТКРЫТЫЙ вопрос-кейс по теме «{topic_title}» для "
            "сертификации системного аналитика, в формате реального экзамена — "
            "практическая ситуация, требующая развёрнутого текстового ответа (НЕ "
            "выбор варианта), объёмом ответа до 2500 знаков с пробелами.\n"
            f"Ориентир по содержанию: {hint}\n"
            "Верни структурные части:\n"
            "- topic_title: короткая тема кейса (используй данную тему);\n"
            "- case: описание практической ситуации (2–4 предложения);\n"
            "- task: что именно сделать, с числовыми рамками где уместно;\n"
            "- focus: на чём сфокусироваться и что НЕ нужно делать;\n"
            "- criteria_visible: краткие критерии оценки через точку с запятой "
            "(показываются студенту);\n"
            "- rubric: ПОДРОБНЫЕ скрытые критерии для проверяющего (студенту НЕ "
            "показывается, детальнее criteria_visible);\n"
            "- explanation: краткий разбор, что отличает сильный ответ.\n"
            "Пиши по-русски. Верни СТРОГО JSON по схеме."
        )
        response_format = {
            "type": "json_schema",
            "json_schema": {
                "name": "open_one",
                "schema": {
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
                item = _parse_json_content(resp)
                return OpenQuestion(
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
            except Exception as e:  # noqa: BLE001 — retry on any failure, raise the last
                last_err = e
        assert last_err is not None  # loop ran ≥1 time, so this is always bound
        raise last_err
```

- [ ] **Step 4: Run to verify it passes**

Run: `pytest tests/test_open_generation.py -v`
Expected: PASS (new test + existing open-generation tests).

- [ ] **Step 5: Lint and commit**

Run: `ruff check app tests`
```bash
git add app/generation/openai_client.py tests/test_open_generation.py
git commit -m "feat: add generate_open_on_topic for themed open questions"
```

---

### Task 3: Generator — per-level open assembly, open-count, artifacts off

**Files:**
- Modify: `backend/app/generation/generator.py` (constants ~24-33; the open-question block ~169-197)
- Test: `backend/tests/test_generator.py` (or a focused `backend/tests/test_open_assembly.py`)

- [ ] **Step 1: Write the failing tests**

Create `backend/tests/test_open_assembly.py`:
```python
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
import itertools

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
    db.add(user); await db.commit(); await db.refresh(user)
    s = TestSession(user_id=user.id, level=level, mode="exam", status="generating",
                    total_questions=3, generated_count=0, time_limit_sec=7200)
    db.add(s); await db.commit(); await db.refresh(s)
    return s


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
    # the two themed questions carry the topic titles
    open_stems = " ".join(o.stem for o in openq)
    assert "Тема: Описание интеграции" in open_stems
    assert "Тема: Системное мышление" in open_stems
    # closed questions carry NO artifact
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
    assert len(openq) == 1  # only the seed; both themed failed -> soft degradation


@pytest.mark.asyncio
async def test_ba_session_unchanged_two_open(db_session):
    s = await _seed_session(db_session, "ba")
    gen = Generator(db_session, FakeClient(), batch_size=10)
    await gen.run(s.id, plan=[("requirements", 3)])
    await db_session.refresh(s)
    openq = (await db_session.execute(
        select(Question).where(Question.session_id == s.id, Question.type == "open"))).scalars().all()
    assert len(openq) == 2  # ba keeps the pool logic, 2 open
```

NOTE: `total_questions=3` in the seed is just to satisfy the column; the generator fills `plan` (3 closed) then appends open. The closed count == 3 because plan asks for 3.

- [ ] **Step 2: Run to verify it fails**

Run: `pytest tests/test_open_assembly.py -v`
Expected: FAIL — `LEVEL_OPEN_COUNT`/`OPEN_TOPICS_BASE_SPEC` don't exist; generator still pools for all levels.

- [ ] **Step 3: Update generator constants**

In `backend/app/generation/generator.py`, change the constants block (currently lines ~24-33). Replace `LEVEL_ARTIFACT_TOPICS`, and replace `OPEN_PER_SESSION = 2` with the per-level config + themed topics:
```python
# Per-level override of artifact-friendly topics. ba only gets diagrams on
# modeling/process_analysis; base/specialist get NO artifacts (empty set) — code
# and data artifacts lost their pedagogical value there. Levels absent here use
# ARTIFACT_TOPICS.
LEVEL_ARTIFACT_TOPICS = {
    "ba": {"modeling", "process_analysis"},
    "base": set(),
    "specialist": set(),
}
# Levels whose artifacts must be Mermaid diagrams only (no sql/json/xml/code).
LEVEL_ARTIFACT_MERMAID_ONLY = {"ba"}

# How many LLM candidates the pool-based open generation produces (ba only).
LLM_OPEN_CANDIDATES = 3
# Open questions per session, per level. base/specialist=3, ba=2, default 2.
LEVEL_OPEN_COUNT = {"base": 3, "specialist": 3, "ba": 2}
DEFAULT_OPEN_COUNT = 2
# Themed open questions for base/specialist: (topic_title, hint). Each is one
# LLM-generated open question via generate_open_on_topic.
OPEN_TOPICS_BASE_SPEC = [
    ("Описание интеграции",
     "Опиши, как ты подойдёшь к описанию интеграции между системами: какие "
     "требования к интеграции собрать, какие уточняющие вопросы задать (формат, "
     "протокол, объёмы, SLA, ошибки), какие критерии приёмки зафиксировать и "
     "какие риски/ошибки учесть (сбои, задержки, недоступность внешней системы, "
     "идемпотентность, ретраи)."),
    ("Системное мышление",
     "Кейс на системное мышление: декомпозиция задачи, выявление связей и "
     "зависимостей между компонентами, границы системы, причинно-следственные "
     "связи, целостный взгляд на проблему вместо локального."),
]
```

- [ ] **Step 4: Rewrite the open-question block in `run()`**

Replace the existing open block (currently ~lines 169-197, the `try: pool = list(SEED_OPEN_QUESTIONS) ...` through `session.generated_count = seq; await self.db.commit()`) with per-level assembly:
```python
            # Append open (free-text) questions after the closed pool. base/
            # specialist get a fixed mix (1 random seed + 1 themed «интеграция» +
            # 1 themed «системное мышление»); ba keeps the seed+LLM pool. A
            # failure in any single open question degrades softly (skip it) — open
            # questions are a bonus section and must not block readiness.
            try:
                rng = random.Random(str(session.id))
                if session.level in ("base", "specialist"):
                    chosen = [rng.choice(SEED_OPEN_QUESTIONS)]
                    for topic_title, hint in OPEN_TOPICS_BASE_SPEC:
                        try:
                            chosen.append(
                                await self.client.generate_open_on_topic(topic_title, hint))
                        except Exception:
                            logger.exception(
                                "Themed open question '%s' failed for session %s",
                                topic_title, session_id)
                else:
                    open_count = LEVEL_OPEN_COUNT.get(session.level, DEFAULT_OPEN_COUNT)
                    pool = list(SEED_OPEN_QUESTIONS)
                    try:
                        pool += await self.client.generate_open_questions(
                            session.level, count=LLM_OPEN_CANDIDATES)
                    except Exception:
                        logger.exception(
                            "LLM open-question generation failed for session %s "
                            "(falling back to seed pool)", session_id)
                    chosen = _sample_open_pool(pool, open_count, rng)
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

NOTE: `OPEN_PER_SESSION` no longer exists — confirm nothing else references it (`grep -rn OPEN_PER_SESSION backend/`). The old block referenced it only here.

- [ ] **Step 5: Run to verify it passes**

Run: `pytest tests/test_open_assembly.py -v`
Expected: PASS (base 3 open with themes; soft degradation; ba 2 open; artifacts off).

- [ ] **Step 6: Lint and commit**

Run: `ruff check app tests`
```bash
git add app/generation/generator.py tests/test_open_assembly.py
git commit -m "feat: per-level open assembly (base/specialist themed 3), no artifacts on base/specialist"
```

---

### Task 4: Fix existing generator/api test fakes & assertions

**Files:**
- Modify: `backend/tests/test_generator.py`, `backend/tests/test_sessions_api.py`, `backend/tests/test_open_generation.py` (fakes used in base/specialist generation that now need `generate_open_on_topic`)

The generator now calls `generate_open_on_topic` for base/specialist sessions. Any test fake driving a base/specialist `Generator.run` that lacks this method will hit the soft-degradation path (AttributeError caught → fewer open questions), changing open-question counts. Also, base/specialist tests asserting old totals (80/120) or `generated_count` need updating. THREE distinct breakages to handle:

**(a) Open count 2→3.** `test_generator.py` uses `_make_session(..., level="base")` by default. Every base test now produces **3** open questions (1 seed + 2 themed), not 2. All `generated_count == total + 2` / hardcoded `== 7`/`== 5`/`== 6` asserts (lines ~99, 133, 149, 197, 239, 282, 326, 409) become `+ 3`. `test_sessions_api.py:87` (`== total_questions + 2`) and any base `len(openq) == 2` → `== 3`.

**(b) Fakes need `generate_open_on_topic`.** `FakeClient` (test_generator.py:50) and every subclass used at base level, plus `test_sessions_api.py` `FakeClient` (line ~38) need the new method, else themed-open AttributeError → only 1 open (seed) → asserts fail.

**(c) Artifact tests now target ba, not base.** The artifact-quota tests in `test_generator.py` (`ArtifactClient` at ~254 and ~295, `AlwaysArtifactClient` at ~383) use `_make_session` (level="base") with artifact topics (`data`/`integration`) and assert artifacts ARE produced. base now has `LEVEL_ARTIFACT_TOPICS["base"]=set()` → ZERO artifacts → these break. Fix: switch those tests to `level="ba"` and ba's artifact topics. ba artifacts are Mermaid-only on `modeling`/`process_analysis`, so the plan slice must use those topics and the fake must return `artifact_kind="mermaid"` (check `_artifact_q`'s kind — if it returns "sql", change the test's fake to mermaid for the ba path, or assert on `artifact_kind != "none"` count rather than a specific kind). Preserve each test's INTENT (the ~15% quota / 20% cap still works on ba) — retarget the level, don't delete coverage.

- [ ] **Step 1: Inventory the impact**

Run:
```
grep -rn "def generate_open_questions\|def generate_open_on_topic" backend/tests
grep -rn "generated_count ==\|len(openq)\|len(open\|== 80\|== 120\|total + 2\|total_questions ==\|_make_session\|level=" backend/tests/test_generator.py backend/tests/test_sessions_api.py
grep -rn "OPEN_PER_SESSION" backend/tests
grep -n "_artifact_q\|artifact_kind" backend/tests/test_generator.py
```
List every fake class lacking `generate_open_on_topic`, every base/specialist count assertion, the artifact tests, and the `OPEN_PER_SESSION` references (see (d) below).

**(d) `OPEN_PER_SESSION` removed.** `test_open_generation.py` (lines ~260-273, `test_open_sampling_reproducible_for_session_id`) imports `OPEN_PER_SESSION` from the generator and uses it as the sample size. The revamp removes that constant. Update that test to use a literal `2` (it tests `_sample_open_pool` generically — the constant value, not the symbol, is what matters): replace `from app.generation.generator import _sample_open_pool, OPEN_PER_SESSION` with `from app.generation.generator import _sample_open_pool`, and replace each `OPEN_PER_SESSION` usage with `2`.

- [ ] **Step 2: Add `generate_open_on_topic` to those fakes**

For EACH fake class (in `test_generator.py`, `test_sessions_api.py`, and the `FakeGenClient`/`FailingOpenClient` in `test_open_generation.py`) that defines `generate_open_questions`, add a sibling method:
```python
    async def generate_open_on_topic(self, topic_title, hint):
        from app.generation.schemas import OpenQuestion
        return OpenQuestion(stem=f"Тема: {topic_title}", rubric="rt", explanation="et")
```
(Use the file's existing `OpenQuestion` import if present; otherwise the local import above is fine.)

- [ ] **Step 3: Fix base/specialist count assertions**

Any base/specialist generation test that asserted `generated_count == total + 2` (the old 2-open behavior) must become `+ 3` for base/specialist (3 open now). And any base/specialist closed-count or total assertion using 80/120 must use 50. Update each. The `test_generator_appends_two_open_questions` test (if it uses level="base"/"exam") now yields 3 open — update its `len(openq) == 2` to `== 3` and `generated_count` accordingly, OR retarget it to ba if it was meant to test the pool path. Read each test's intent and fix to match the new spec; report each change.

IMPORTANT: ba tests must stay at 2 open. `test_create_ba_session_uses_40_and_90min` and the open-generation pool tests are unaffected (ba unchanged). Do NOT change ba expectations.

- [ ] **Step 4: Run full suite until green**

Run: `pytest -q`
Expected: all pass. Iterate on any remaining base/specialist count mismatch. `ruff check app tests` clean.

- [ ] **Step 5: Commit**

```bash
git add tests/
git commit -m "test: update fakes + base/specialist counts for 50q/3-open revamp"
```

---

### Task 5: Full verification + live smoke

**Files:** none (verification only)

- [ ] **Step 1: Full backend suite + lint**

Run: `pytest -q && ruff check app tests`
Expected: all pass, lint clean.

- [ ] **Step 2: Frontend unaffected — quick check**

Run: `cd /Users/pavel/Developer/antests/frontend && npx vitest run && npx tsc --noEmit`
Expected: 44 tests pass, tsc clean (no frontend changes in this feature; 53 renders via maxSeq).

- [ ] **Step 3: Live smoke — base session shape**

Start backend, create a `base`+`exam` session, poll to ready, fetch `/questions`. Confirm:
- `total_questions == 50`, `time_limit_sec == 7200` (120 min);
- closed count == 50, open count == 3 (53 total), open seqs are the last three;
- **zero artifacts**: every closed question has `artifact_kind == "none"`;
- the 3 open: one is a seed BA case (stem contains «От бизнес-проблемы к требованиям» OR «Изменение, приёмка и готовность результата»), one references интеграция, one references системное мышление (stem contains «Описание интеграции» / «Системное мышление» topic line);
- open questions carry no `rubric`/`correct_keys`.

Use a urllib+cookiejar venv-python script (one session, generous polling, no concurrency — base generates 50 closed, ~3-4 min).

- [ ] **Step 4: Live smoke — specialist + ba regression**

specialist session: confirm 50 closed + 3 open, 120 min, zero artifacts. ba session: confirm STILL 40 closed + 2 open, 90 min, and that ba may still carry Mermaid artifacts on modeling/process_analysis (unchanged). Run these one at a time (no concurrency).

- [ ] **Step 5: Stop servers; report**

Stop uvicorn; report all results with evidence (counts, time limits, artifact counts, sample open-question topics).

---

## Notes for the implementer

- **No DB migration.** All config is Python constants; competency is generic by topic_id.
- **ba is untouched.** It keeps 40 closed / 2 open / 90 min / Mermaid artifacts on modeling+process_analysis. Any change to ba behavior is a RED FLAG.
- **Artifacts off** for base/specialist via empty `LEVEL_ARTIFACT_TOPICS` set — no new flag, the quota/cap just go unused.
- **Soft degradation:** a themed-open LLM failure skips that one question (base/specialist may end with <3 open). Never block readiness.
- **Themed open generation** reuses `build_open_stem` (single format source) and the hidden-rubric pattern — rubric never serialized to the client.
- **Seq/generated_count:** open questions keep going after the closed pool; `generated_count` covers them so the exam UI unlocks them (and the counter fix shows 53).
