# BA-Level Test (42 questions) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a third test level `ba` — 40 closed questions (~70% multi) across 18 business-analysis topics + 2 open questions — selectable on the dashboard.

**Architecture:** `ba` is a new `level` string. It reuses the existing exam pipeline: planner apportions 40 questions across all 18 topics by `proportions["ba"]`; the generator threads a soft `multi_ratio` into the prompt; open questions reuse the seed+LLM pool. No DB migration — level is a string, topics are Python constants, competency is generic by topic_id.

**Tech Stack:** FastAPI, SQLAlchemy async, Pydantic v2, OpenAI SDK; Next.js/React/TypeScript, pytest, Vitest.

**Spec:** `docs/superpowers/specs/2026-06-17-ba-level-test-design.md`

**Working dir backend:** `cd /Users/pavel/Developer/antests/backend && . .venv/bin/activate`
**Working dir frontend:** `cd /Users/pavel/Developer/antests/frontend`

---

### Task 1: Topics — add `ba` weights to the 10 existing topics + update topics tests

**Files:**
- Modify: `backend/app/generation/topics.py` (add `"ba": <w>` to each of the 10 `Topic.proportions`; reword `methodology`'s RACI subtopic)
- Test: `backend/tests/test_topics.py` (update the count + sum assertions)

This task ONLY touches the 10 existing topics (adds their `ba` weight) and the RACI rewording. The 8 NEW topics come in Task 2 — so after Task 1, `len(TOPICS)` is still 10. Accordingly, Task 1 leaves `test_ten_topics_for_each_level` UNCHANGED (still passes at 10) and only updates the proportion-sum tests + RACI assertion. Task 2 then bumps the count test to 18. This keeps every task green on its own.

- [ ] **Step 1: Reword the methodology RACI subtopic and add ba weights to the 10 topics**

In `backend/app/generation/topics.py`, for the `methodology` topic change the subtopic string `"RACI"` to `"RACI как распределение ролей по задачам проекта"`. Then add a `"ba"` key to every existing topic's `proportions`. The 10 edits (keep base/specialist exactly as-is, append `"ba"`):

```python
    Topic("fundamentals", "Фундаментальные компетенции",
          ["Информационные системы и виды ПО", "ООП", "Системное мышление"],
          {"base": 0.10, "specialist": 0.08, "ba": 0.02}),
    Topic("methodology", "Методологии и технологии разработки ПО",
          ["SDLC", "Waterfall/RUP/Scrum/Kanban/Lean/FDD/XP", "RACI как распределение ролей по задачам проекта", "CI/CD", "Проектная документация"],
          {"base": 0.10, "specialist": 0.10, "ba": 0.04}),
    Topic("requirements", "Работа с требованиями",
          ["Виды требований", "Сбор и выявление", "Документирование", "ЖЦ и управление требованиями", "Критерии качества"],
          {"base": 0.15, "specialist": 0.14, "ba": 0.12}),
    Topic("modeling", "Моделирование процессов и систем",
          ["UML (классы, use case, состояния, активности, последовательности)", "BPMN", "Иерархия моделей"],
          {"base": 0.15, "specialist": 0.14, "ba": 0.06}),
    Topic("architecture", "Основные архитектурные практики",
          ["Стили архитектуры", "Клиент-сервер", "Монолит/распределённые", "Репликация/кластеры/бэкапы", "DDD/Event-Driven", "4+1/TOGAF"],
          {"base": 0.10, "specialist": 0.14, "ba": 0.015}),
    Topic("data", "Хранение и обработка данных",
          ["Типы БД и СУБД", "Уровни моделирования", "ER-диаграммы", "SQL", "DDL", "ETL/витрины"],
          {"base": 0.12, "specialist": 0.12, "ba": 0.03}),
    Topic("integration", "Интеграционные решения",
          ["TCP/IP/HTTP/HTTPS", "REST/OpenAPI", "SOAP/XSD", "Async (RabbitMQ/Kafka/AsyncAPI)", "DFD", "Виртуализация/контейнеры"],
          {"base": 0.10, "specialist": 0.12, "ba": 0.015}),
    Topic("ux", "Проектирование пользовательских интерфейсов",
          ["Эргономика и эвристики", "Прототипы (low/high fidelity)", "CJM/карты эмпатии/A-B", "Роль СА в UI"],
          {"base": 0.06, "specialist": 0.06, "ba": 0.02}),
    Topic("security", "Информационная безопасность",
          ["Аутентификация/идентификация", "OAuth/JWT/OpenID/cookies/API-key", "Авторизация и ролевая модель", "ЭЦП", "Уязвимости/мониторинг"],
          {"base": 0.06, "specialist": 0.06, "ba": 0.01}),
    Topic("deployment", "Внедрение и сопровождение ПО",
          ["Виды тестирования", "Критерии качества ПО", "Управление дефектами", "ITIL/инциденты", "Релизы/пилотирование/обучение"],
          {"base": 0.06, "specialist": 0.04, "ba": 0.015}),
```

- [ ] **Step 2: Update `test_topics.py` for ba (these assertions hold after Task 1, before Task 2 adds count)**

Replace `test_proportions_sum_to_one_per_level` and ADD a ba check. base/specialist must STILL sum to 1.0 (the 10 existing topics' base/specialist weights are unchanged; the 8 new topics in Task 2 will carry base=specialist=0, so the sum stays 1.0). For `ba`, weights are NOT required to sum to 1.0 (the planner normalizes via `_largest_remainder`), so assert ba sums to a positive value > 0:

```python
def test_proportions_sum_to_one_per_level():
    # base/specialist proportions are designed to sum to 1.0
    for level in ("base", "specialist"):
        total = sum(t.proportions[level] for t in topics.TOPICS)
        assert abs(total - 1.0) < 1e-6, f"{level} sums to {total}"


def test_ba_proportions_present_and_positive():
    # ba weights need not sum to 1.0 — the planner normalizes them. Every topic
    # must carry a ba weight (>=0), and the total must be positive.
    ba_total = sum(t.proportions["ba"] for t in topics.TOPICS)
    assert ba_total > 0
    assert all("ba" in t.proportions for t in topics.TOPICS)


def test_methodology_raci_is_project-role_angle():
    m = topics.get_topic("methodology")
    joined = " ".join(m.subtopics)
    assert "RACI как распределение ролей" in joined
```

Note: rename the last test function to a valid identifier — use `test_methodology_raci_is_project_role_angle` (underscores, no hyphen). Keep the body as shown.

Leave `test_ten_topics_for_each_level` UNCHANGED for now — it still passes (TOPICS is still 10 after Task 1). Task 2 updates it.

- [ ] **Step 3: Run topics tests**

Run: `cd /Users/pavel/Developer/antests/backend && . .venv/bin/activate && pytest tests/test_topics.py -v`
Expected: all pass (TOPICS still 10; base/specialist sum 1.0; ba positive; RACI reworded).

- [ ] **Step 4: Run planner tests (regression — base/specialist unchanged)**

Run: `pytest tests/test_planner.py -v`
Expected: PASS — base/specialist plans unchanged (adding a `ba` key to proportions doesn't affect `plan_exam("base")`/`("specialist")`).

- [ ] **Step 5: Commit**

```bash
ruff check app tests
git add app/generation/topics.py tests/test_topics.py
git commit -m "feat: add ba proportions to existing topics; reword methodology RACI angle"
```

---

### Task 2: Topics — add the 8 new BA topics

**Files:**
- Modify: `backend/app/generation/topics.py` (append 8 `Topic` entries to TOPICS)
- Test: `backend/tests/test_topics.py` (update count to 18; assert new topics exist with ba>0 and base=specialist=0)

- [ ] **Step 1: Write the failing/updated tests**

In `backend/tests/test_topics.py`, update `test_ten_topics_for_each_level` and add a new-topic check:

```python
def test_eighteen_topics_total():
    assert len(topics.TOPICS) == 18


NEW_BA_TOPIC_IDS = {
    "stakeholders", "strategy", "process_analysis", "elicitation",
    "solution_value", "agile_ba", "ba_planning", "soft_skills",
}


def test_new_ba_topics_present_and_ba_only():
    by_id = {t.id: t for t in topics.TOPICS}
    for tid in NEW_BA_TOPIC_IDS:
        assert tid in by_id, f"missing new topic {tid}"
        t = by_id[tid]
        assert t.proportions["ba"] > 0
        # New BA topics must NOT appear in base/specialist plans
        assert t.proportions["base"] == 0.0
        assert t.proportions["specialist"] == 0.0
        assert len(t.subtopics) >= 3


def test_stakeholders_owns_raci_analysis_angle():
    s = topics.get_topic("stakeholders")
    joined = " ".join(s.subtopics)
    assert "RACI как инструмент анализа стейкхолдеров" in joined
```

DELETE the old `test_ten_topics_for_each_level` (replaced by `test_eighteen_topics_total`).

- [ ] **Step 2: Run to verify it fails**

Run: `pytest tests/test_topics.py -v`
Expected: FAIL — only 10 topics; new ids missing.

- [ ] **Step 3: Append the 8 new topics**

In `backend/app/generation/topics.py`, append these 8 `Topic` entries to the `TOPICS` list (after `deployment`, before the closing `]`):

```python
    Topic("stakeholders", "Анализ и управление стейкхолдерами",
          ["Идентификация стейкхолдеров, реестр (stakeholder list)",
           "Матрица власть/интерес, карты вовлечённости",
           "RACI как инструмент анализа стейкхолдеров (кто вовлечён, влияние/интерес)",
           "Персоны и анализ потребностей",
           "План коммуникаций и управление ожиданиями"],
          {"base": 0.0, "specialist": 0.0, "ba": 0.09}),
    Topic("strategy", "Стратегический анализ и бизнес-обоснование",
          ["Бизнес-потребность и определение проблемы (problem statement)",
           "Анализ текущего/целевого состояния (current/future state, gap analysis)",
           "SWOT, бизнес-модель, цели и метрики",
           "Бизнес-кейс, оценка выгод, ROI/NPV/TCO",
           "Оценка и управление рисками, стратегия изменений"],
          {"base": 0.0, "specialist": 0.0, "ba": 0.09}),
    Topic("process_analysis", "Анализ и улучшение бизнес-процессов",
          ["As-Is / To-Be анализ процессов",
           "Выявление узких мест, потерь, корневых причин (5 почему, Ишикава)",
           "Реинжиниринг и оптимизация процессов",
           "Метрики процессов (время цикла, стоимость, KPI)",
           "Связь процессов с требованиями и решением"],
          {"base": 0.0, "specialist": 0.0, "ba": 0.10}),
    Topic("elicitation", "Выявление требований: техники",
          ["Интервью и анкетирование (surveys)",
           "Воркшопы и фасилитация, мозговой штурм",
           "Наблюдение, анализ документов, анализ интерфейсов",
           "Прототипирование как техника выявления",
           "Подтверждение и согласование результатов"],
          {"base": 0.0, "specialist": 0.0, "ba": 0.08}),
    Topic("solution_value", "Оценка и приёмка решения",
          ["KPI и метрики ценности решения",
           "Измерение производительности решения, benefits realization",
           "Анализ ограничений решения и организации",
           "Приёмочное тестирование (UAT), критерии приёмки",
           "Рекомендации: расширять / заменить / вывести из эксплуатации"],
          {"base": 0.0, "specialist": 0.0, "ba": 0.07}),
    Topic("agile_ba", "Бизнес-анализ в Agile",
          ["User Stories, формат «Как… я хочу… чтобы…», INVEST",
           "Критерии приёмки (Acceptance Criteria), Definition of Done",
           "Управление product backlog, epics, груминг",
           "Приоритизация: MoSCoW, Kano, RICE, value-vs-effort, WSJF",
           "Story mapping, оценка (story points, planning poker)"],
          {"base": 0.0, "specialist": 0.0, "ba": 0.07}),
    Topic("ba_planning", "Планирование и мониторинг БА-работ",
          ["Выбор подхода к бизнес-анализу (predictive/adaptive)",
           "Планирование вовлечения стейкхолдеров и governance",
           "Управление информацией о требованиях",
           "Метрики и улучшение эффективности БА-работ"],
          {"base": 0.0, "specialist": 0.0, "ba": 0.04}),
    Topic("soft_skills", "Коммуникации и софт-скиллы аналитика",
          ["Фасилитация и проведение встреч",
           "Деловая коммуникация и переговоры",
           "Презентация и защита решений",
           "Работа с конфликтами и заинтересованными сторонами",
           "Аналитическое и системное мышление"],
          {"base": 0.0, "specialist": 0.0, "ba": 0.05}),
```

- [ ] **Step 4: Run to verify it passes**

Run: `pytest tests/test_topics.py -v`
Expected: PASS (18 topics; new ids present with ba>0, base=specialist=0; RACI angles split).

- [ ] **Step 5: Commit**

```bash
ruff check app tests
git add app/generation/topics.py tests/test_topics.py
git commit -m "feat: add 8 BA topics (BABOK-aligned) for the ba level"
```

---

### Task 3: Planner — `LEVEL_TOTALS["ba"] = 40`

**Files:**
- Modify: `backend/app/generation/planner.py:3` (add `"ba": 40`)
- Test: `backend/tests/test_planner.py` (add ba totals + coverage tests)

- [ ] **Step 1: Write the failing tests**

Add to `backend/tests/test_planner.py`:

```python
def test_exam_plan_ba_total_is_40():
    plan = plan_exam("ba")
    assert sum(c for _, c in plan) == 40


def test_exam_plan_ba_covers_all_18_topics():
    plan = dict(plan_exam("ba"))
    assert len(plan) == 18  # every topic with ba>0 gets >=1
    assert all(c >= 1 for c in plan.values())


def test_exam_plan_ba_core_topics_dominate():
    # BA-core topics should carry the majority of the 40 questions.
    plan = dict(plan_exam("ba"))
    core = ["requirements", "process_analysis", "stakeholders", "strategy",
            "elicitation", "solution_value", "agile_ba"]
    core_count = sum(plan[t] for t in core)
    assert core_count >= 20  # >= half of 40
```

- [ ] **Step 2: Run to verify it fails**

Run: `pytest tests/test_planner.py -k ba -v`
Expected: FAIL — `KeyError: 'ba'` in `LEVEL_TOTALS`.

- [ ] **Step 3: Add the ba total**

In `backend/app/generation/planner.py`, change line 3:

```python
LEVEL_TOTALS = {"base": 80, "specialist": 120, "ba": 40}
```

- [ ] **Step 4: Run to verify it passes**

Run: `pytest tests/test_planner.py -v`
Expected: PASS — ba sums to 40, all 18 topics present (≥1), core ≥ 20. base/specialist tests still pass.

- [ ] **Step 5: Commit**

```bash
ruff check app tests
git add app/generation/planner.py tests/test_planner.py
git commit -m "feat: planner total of 40 for the ba level"
```

---

### Task 4: Generator + prompt — soft ~70% multi quota for ba

**Files:**
- Modify: `backend/app/generation/planner.py` (add `LEVEL_MULTI_TARGET`)
- Modify: `backend/app/generation/openai_client.py` (`generate_batch` accepts `multi_ratio`, adds prompt instruction)
- Modify: `backend/app/generation/generator.py` (`run` reads target, threads through `_generate_with_retry` → `generate_batch`)
- Test: `backend/tests/test_open_generation.py` (prompt-content unit via a spy client) — OR a focused new test file `backend/tests/test_multi_quota.py`

Use a new test file `backend/tests/test_multi_quota.py` to keep this isolated.

- [ ] **Step 1: Write the failing test**

Create `backend/tests/test_multi_quota.py`:

```python
import json

import pytest

from app.generation.openai_client import OpenAIClient
from app.generation.planner import LEVEL_MULTI_TARGET


class _CaptureCompletions:
    def __init__(self, payload):
        self.payload = payload
        self.last_user_prompt = None

    async def create(self, **kw):
        # capture the user message so we can assert prompt content
        for m in kw["messages"]:
            if m["role"] == "user":
                self.last_user_prompt = m["content"]

        class _M:
            def __init__(s, c): s.content = c
        class _C:
            def __init__(s, c): s.message = _M(c); s.finish_reason = "stop"
        class _Comp:
            def __init__(s, c): s.choices = [_C(c)]
        return _Comp(json.dumps(self.payload))


class _CaptureChat:
    def __init__(self, comp): self.completions = comp


class _CaptureClient:
    def __init__(self, comp): self.chat = comp and _CaptureChat(comp)


_VALID_BATCH = {"questions": [{
    "topic_id": "requirements", "type": "multi", "stem": "Q?",
    "artifact_kind": "none", "artifact_content": None,
    "options": [{"key": "a", "text": "x"}, {"key": "b", "text": "y"}],
    "correct_keys": ["a", "b"], "explanation": "e",
}]}


def test_ba_has_multi_target():
    assert LEVEL_MULTI_TARGET.get("ba") == 0.7
    # base/specialist intentionally have NO target (behaviour unchanged)
    assert "base" not in LEVEL_MULTI_TARGET
    assert "specialist" not in LEVEL_MULTI_TARGET


@pytest.mark.asyncio
async def test_generate_batch_adds_multi_instruction_when_ratio_set():
    comp = _CaptureCompletions(_VALID_BATCH)
    client = OpenAIClient(api_key="x", gen_model="g", validate_model="v",
                          _client=_CaptureClient(comp))
    await client.generate_batch("ba", "exam", [("requirements", 1)], multi_ratio=0.7)
    assert "несколько верных" in comp.last_user_prompt
    assert "70%" in comp.last_user_prompt


@pytest.mark.asyncio
async def test_generate_batch_no_multi_instruction_when_ratio_none():
    comp = _CaptureCompletions(_VALID_BATCH)
    client = OpenAIClient(api_key="x", gen_model="g", validate_model="v",
                          _client=_CaptureClient(comp))
    await client.generate_batch("base", "exam", [("requirements", 1)])
    assert "несколько верных" not in (comp.last_user_prompt or "")
```

- [ ] **Step 2: Run to verify it fails**

Run: `pytest tests/test_multi_quota.py -v`
Expected: FAIL — `LEVEL_MULTI_TARGET` doesn't exist; `generate_batch` has no `multi_ratio` param.

- [ ] **Step 3a: Add `LEVEL_MULTI_TARGET` to planner.py**

In `backend/app/generation/planner.py`, after `LEVEL_TOTALS`:

```python
# Target share of multi-answer (multiple correct) questions, per level. Soft
# quota: passed into the generation prompt as guidance, not enforced by
# discarding. Levels absent here keep the default (no multi steering).
LEVEL_MULTI_TARGET = {"ba": 0.7}
```

- [ ] **Step 3b: Thread `multi_ratio` through `generate_batch` in openai_client.py**

In `backend/app/generation/openai_client.py`, change the `generate_batch` signature and add the instruction. Current signature (line ~181):
```python
    async def generate_batch(
        self, level, mode, plan_slice, avoid_stems=None, want_artifact=False
    ):
```
Change to:
```python
    async def generate_batch(
        self, level, mode, plan_slice, avoid_stems=None, want_artifact=False,
        multi_ratio=None,
    ):
```
Then, AFTER the `if want_artifact:` block (just before `resp = await self._client.chat.completions.create(`), add:
```python
        if multi_ratio:
            pct = round(multi_ratio * 100)
            user_prompt += (
                f"\n\nВАЖНО про тип: не менее ~{pct}% вопросов в этом наборе делай "
                "типа multi — где ВЕРНЫ НЕСКОЛЬКО вариантов (обычно 2–3 из 4–5), и в "
                "correct_keys перечисли все верные. Остальные — single (ровно один "
                "верный). Делай multi-вопросы честными: несколько вариантов "
                "действительно корректны, а не искусственно."
            )
```

- [ ] **Step 3c: Thread `multi_ratio` through the generator**

In `backend/app/generation/generator.py`:

(a) Add import at top (it already imports from planner indirectly? No — add it):
```python
from app.generation.planner import LEVEL_MULTI_TARGET
```
(Place it near `from app.generation.open_seed import SEED_OPEN_QUESTIONS`.)

(b) In `run()`, before the topic loop (right after `seq = session.generated_count` area, anywhere before the `for topic_id, count in plan:` loop), compute:
```python
            multi_ratio = LEVEL_MULTI_TARGET.get(session.level)
```

(c) In `run()`, update the `_generate_with_retry` call (currently around lines 90-93) to pass `multi_ratio`:
```python
                    batch = await self._generate_with_retry(
                        session.level, session.mode, [(topic_id, take)],
                        avoid_stems=recent_stems, want_artifact=want_artifact,
                        multi_ratio=multi_ratio,
                    )
```

(d) Update `_generate_with_retry` signature + its `generate_batch` call (currently around lines 199-208):
```python
    async def _generate_with_retry(
        self, level, mode, slice_, avoid_stems=None, want_artifact=False,
        multi_ratio=None,
    ):
```
and inside it, the `self.client.generate_batch(...)` call must pass `multi_ratio=multi_ratio`:
```python
                return await self.client.generate_batch(
                    level, mode, slice_,
                    avoid_stems=avoid_stems, want_artifact=want_artifact,
                    multi_ratio=multi_ratio,
                )
```
(Preserve whatever other args/positional order are already there — only ADD `multi_ratio=multi_ratio`.)

- [ ] **Step 4: Run to verify it passes**

Run: `pytest tests/test_multi_quota.py -v`
Expected: PASS (target present; instruction added when ratio set; absent when None).

- [ ] **Step 5: Run full backend suite (regression — base/specialist generation unchanged) + lint, commit**

Run: `pytest -q && ruff check app tests`
Expected: many generator/session tests will FAIL FIRST with `TypeError: generate_batch() got an unexpected keyword argument 'multi_ratio'`, because the generator now passes `multi_ratio=...` to every fake `generate_batch`. You MUST widen every test fake's `generate_batch` signature to accept `multi_ratio=None`.

Run `grep -rn "def generate_batch" backend/tests` to get the full list. As of now it is:
- `tests/test_generator.py` — 7 fakes with explicit signatures (lines ~55, ~118, ~176, ~212, ~255, ~295, ~382) + 1 already-safe `(self, *a, **k)` at ~155 (no change needed for that one).
- `tests/test_sessions_api.py` — 1 fake (line ~28).
- `tests/test_assessment_api.py` — 1 fake (line ~23).
- `tests/test_open_generation.py:174` — `FakeGenClient.generate_batch` (one line signature).

For EACH explicit-signature fake, add `, multi_ratio=None` to the end of the parameter list (before the closing `)`). The `(self, *a, **k)` fake already absorbs it — leave it. The fake bodies don't need to USE multi_ratio (they ignore it).

After widening all fakes, re-run `pytest -q` — expect green (base/specialist call with `multi_ratio=None` → identical prompt as before). Report exactly which fakes (file:line) you updated.

```bash
git add app/generation/planner.py app/generation/openai_client.py app/generation/generator.py \
        tests/test_multi_quota.py tests/test_generator.py tests/test_sessions_api.py \
        tests/test_assessment_api.py tests/test_open_generation.py
git commit -m "feat: soft ~70% multi quota for ba level via generation prompt"
```
(Add exactly the test files whose fakes you widened — confirm with `git status` before committing.)

---

### Task 5: Session service + router — ba time limit and level validation

**Files:**
- Modify: `backend/app/generation/service.py` (add `LEVEL_TIME_LIMITS["ba"]`)
- Modify: `backend/app/generation/router.py:95` (accept `ba` in level validation)
- Test: `backend/tests/test_sessions_api.py` (add a ba create-session test)

- [ ] **Step 1: Write the failing test**

`backend/tests/test_sessions_api.py` already has: an autouse `_patch_client` fixture (monkeypatches `build_openai_client` to `FakeClient`), a `_register(client, login)` helper, and a `client` fixture. The `FakeClient.generate_batch` fills `sum(count)` questions across the plan, so it handles any total. Add this test (it reuses the existing helpers verbatim — no new fixtures):

```python
@pytest.mark.asyncio
async def test_create_ba_session_uses_40_and_90min(client):
    await _register(client, "ba_user")
    resp = await client.post("/sessions", json={"level": "ba", "mode": "exam"})
    assert resp.status_code == 201
    sid = resp.json()["id"]

    for _ in range(50):
        st = await client.get(f"/sessions/{sid}/status")
        if st.json()["status"] == "ready":
            break
        await asyncio.sleep(0.05)

    body = (await client.get(f"/sessions/{sid}/status")).json()
    assert body["level"] == "ba"
    assert body["time_limit_sec"] == 90 * 60
    assert body["total_questions"] == 40

    qs = (await client.get(f"/sessions/{sid}/questions")).json()
    closed = [q for q in qs if q["type"] in ("single", "multi")]
    openq = [q for q in qs if q["type"] == "open"]
    assert len(closed) == 40
    assert len(openq) == 2
```

NOTE: this depends on Task 4 having added `multi_ratio=None` to `FakeClient.generate_batch` in this file (the generator now passes `multi_ratio=...`). If Task 4 missed it, this test fails with `TypeError: generate_batch() got an unexpected keyword argument 'multi_ratio'` — fix the fake's signature, don't change the generator.

- [ ] **Step 2: Run to verify it fails**

Run: `pytest tests/test_sessions_api.py -k ba -v`
Expected: FAIL — router rejects `level="ba"` with 400 (validation), so status_code != 201.

- [ ] **Step 3a: Add the ba time limit**

In `backend/app/generation/service.py`, change `LEVEL_TIME_LIMITS` (line ~10):

```python
LEVEL_TIME_LIMITS = {"base": 120 * 60, "specialist": 180 * 60, "ba": 90 * 60}
```

- [ ] **Step 3b: Accept ba in router validation**

In `backend/app/generation/router.py:95`, change:

```python
    if req.level not in ("base", "specialist", "ba") or req.mode not in ("exam", "adaptive"):
```

- [ ] **Step 4: Run to verify it passes**

Run: `pytest tests/test_sessions_api.py -v`
Expected: PASS — ba session created, total 40, time 5400, 40 closed + 2 open.

- [ ] **Step 5: Run full backend suite, lint, commit**

Run: `pytest -q && ruff check app tests`
Expected: all pass.

```bash
git add app/generation/service.py app/generation/router.py tests/test_sessions_api.py
git commit -m "feat: ba level — 90min time limit and router validation"
```

---

### Task 6: Frontend — `ba` level type, dashboard button, test-page label

**Files:**
- Modify: `frontend/src/lib/types.ts:1` (`Level` union)
- Modify: `frontend/src/app/dashboard/page.tsx` (3rd level button + label map)
- Modify: `frontend/src/app/test/[id]/page.tsx:138` (level label branch)
- Test: none required (small wiring; covered by build + tsc). Optional: none.

- [ ] **Step 1: Add `ba` to the Level type**

In `frontend/src/lib/types.ts`, line 1:

```typescript
export type Level = "base" | "specialist" | "ba";
```

- [ ] **Step 2: Add the dashboard button + label**

In `frontend/src/app/dashboard/page.tsx`, the level buttons block currently maps `["base", "specialist"]` with label `l === "base" ? "Базовый" : "Специалист"`. Replace that block:

```tsx
        <div style={{ display: "flex", gap: 10, margin: "8px 0 16px" }}>
          {(["base", "specialist", "ba"] as Level[]).map((l) => (
            <button key={l} className={`btn ${level === l ? "" : "btn-ghost"}`} onClick={() => setLevel(l)}>
              {l === "base" ? "Базовый" : l === "specialist" ? "Специалист" : "Бизнес-анализ"}
            </button>
          ))}
        </div>
```

- [ ] **Step 3: Update the test-page level label**

In `frontend/src/app/test/[id]/page.tsx`, line ~138, the label is:
```tsx
            {status.level === "base" ? "Базовый" : "Специалист"} · {status.mode === "exam" ? "Экзамен" : "Тренировка"}
```
Change the level part to handle ba:
```tsx
            {status.level === "base" ? "Базовый" : status.level === "specialist" ? "Специалист" : "Бизнес-анализ"} · {status.mode === "exam" ? "Экзамен" : "Тренировка"}
```

- [ ] **Step 4: Typecheck + build + run existing frontend tests**

Run: `cd /Users/pavel/Developer/antests/frontend && npx tsc --noEmit && npx vitest run`
Expected: tsc clean; all 39 tests still pass (no test changes; the Level union widening is backward-compatible).

- [ ] **Step 5: Commit**

```bash
cd /Users/pavel/Developer/antests
git add frontend/src/lib/types.ts "frontend/src/app/dashboard/page.tsx" "frontend/src/app/test/[id]/page.tsx"
git commit -m "feat: ba level on dashboard + test-page label"
```

---

### Task 7: Full verification + live smoke

**Files:** none (verification only)

- [ ] **Step 1: Full backend suite + lint**

Run: `cd /Users/pavel/Developer/antests/backend && . .venv/bin/activate && pytest -q && ruff check app tests`
Expected: all pass, lint clean.

- [ ] **Step 2: Full frontend suite + typecheck + build**

Run: `cd /Users/pavel/Developer/antests/frontend && npx vitest run && npx tsc --noEmit && npm run build`
Expected: all pass, tsc clean, build succeeds.

- [ ] **Step 3: Live smoke — ba session shape**

Start backend, create a `ba`+`exam` session, poll to ready, fetch `/questions`. Confirm:
- `total_questions == 40`, `time_limit_sec == 5400`;
- closed count == 40, open count == 2 (42 total), open seqs are the last two;
- topic coverage is broad: count distinct `topic_id` among closed — expect close to 18 distinct (every BA topic represented), including new ones (`stakeholders`, `strategy`, `process_analysis`, etc.);
- multi share among closed is clearly above 50% (target ~70%, soft — don't assert exact);
- open questions carry no `rubric`/`correct_keys`.

Use a urllib+cookiejar venv-python script analogous to prior live smokes.

- [ ] **Step 4: Live smoke — base/specialist regression**

Create a `base`+`exam` session the same way; confirm it still produces 80 closed + 2 open and the multi share is NOT forced to 70% (i.e. base behaviour unchanged — just confirm it generates and is ready; no multi assertion).

- [ ] **Step 5: Stop servers; report**

Stop uvicorn/next; report all results with evidence (counts, distinct topic_ids, multi share, sample BA-topic stems).

---

## Notes for the implementer

- **No DB migration.** `level` is a string; topics are Python constants; competency is generic by topic_id.
- **base/specialist must stay byte-identical in behaviour.** They have no `ba` influence: new topics carry base=specialist=0; `LEVEL_MULTI_TARGET` lacks them (→ `multi_ratio=None` → original prompt). Any base/specialist test that changes count is a RED FLAG — investigate, don't paper over.
- **Soft multi quota:** prompt guidance only, never discard a question for being single. Don't add post-filtering.
- **Test-fake signatures:** Task 4 widens `generate_batch` with `multi_ratio`; update every test fake's `generate_batch` to accept `multi_ratio=None` or the generator call raises TypeError.
- **42 vs 40 in UI:** intentional — `total_questions`=40 (closed), open +2 reachable via existing `maxSeq`. Consistent with base/specialist. No "show 42" change.
