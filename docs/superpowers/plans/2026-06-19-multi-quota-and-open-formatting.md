# 70% multi (base/specialist) + Open-Question Block Formatting Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** base/specialist get the same soft ~70% multi quota as ba, and open-question stems render as readable blocks (header / case / Задание / Фокус ответа / Критерии оценки) on both the exam and results pages.

**Architecture:** The multi quota is one dict entry — the existing prompt-steering mechanism does the rest. The formatting is frontend-only: a pure `parseOpenStem` helper splits the assembled stem string into sections, and an `OpenStem` component renders them (falling back to plain pre-line text if parsing fails). No backend/DB change for formatting; works with existing sessions.

**Tech Stack:** FastAPI (backend, 1 line), Next.js/React/TypeScript, Vitest + RTL, pytest.

**Spec:** `docs/superpowers/specs/2026-06-19-multi-quota-and-open-formatting-design.md`

**Working dirs:** backend `cd /Users/pavel/Developer/antests/backend && . .venv/bin/activate`; frontend `cd /Users/pavel/Developer/antests/frontend`.

---

### Task 1: base/specialist 70% multi quota

**Files:**
- Modify: `backend/app/generation/planner.py:8` (LEVEL_MULTI_TARGET)
- Test: `backend/tests/test_multi_quota.py`

- [ ] **Step 1: Update the tests**

In `backend/tests/test_multi_quota.py`, `test_ba_has_multi_target` currently asserts base/specialist are absent. Replace it:
```python
def test_ba_has_multi_target():
    assert LEVEL_MULTI_TARGET.get("ba") == 0.7
    # base/specialist now also steer ~70% multi
    assert LEVEL_MULTI_TARGET.get("base") == 0.7
    assert LEVEL_MULTI_TARGET.get("specialist") == 0.7
```
(Leave `test_generate_batch_no_multi_instruction_when_ratio_none` unchanged — it calls `generate_batch("base", ...)` WITHOUT passing `multi_ratio`, so it still tests the `multi_ratio=None` path of the method itself. That remains valid.)

- [ ] **Step 2: Run to verify it fails**

Run: `cd /Users/pavel/Developer/antests/backend && . .venv/bin/activate && pytest tests/test_multi_quota.py::test_ba_has_multi_target -v`
Expected: FAIL — base/specialist not in LEVEL_MULTI_TARGET yet.

- [ ] **Step 3: Update LEVEL_MULTI_TARGET**

`backend/app/generation/planner.py:8`:
```python
LEVEL_MULTI_TARGET = {"ba": 0.7, "base": 0.7, "specialist": 0.7}
```

- [ ] **Step 4: Run to verify it passes**

Run: `pytest tests/test_multi_quota.py -v`
Expected: PASS (all multi-quota tests).

- [ ] **Step 5: Run full backend suite, lint, commit**

Run: `pytest -q && ruff check app tests`
Expected: all pass. (The generator already reads `LEVEL_MULTI_TARGET.get(session.level)` and threads `multi_ratio` — no generator change needed. base/specialist generator tests use a `FakeClient.generate_batch` that accepts `multi_ratio` and ignores it, so they're unaffected.)

```bash
git add app/generation/planner.py tests/test_multi_quota.py
git commit -m "feat: base/specialist ~70% multi quota (same soft steering as ba)"
```

---

### Task 2: `parseOpenStem` — pure section parser

**Files:**
- Create: `frontend/src/lib/openStem.ts`
- Test: `frontend/src/lib/__tests__/openStem.test.ts` (create)

The open stem is assembled by the backend `build_open_stem` with this exact shape:
```
Ответ: до 2500 знаков с пробелами; достаточно тезисного, структурированного ответа.
Тип: открытый кейс. {topicTitle}

{case}

Задание: {task}
Фокус ответа: {focus}
Критерии оценки: {criteria}
```

- [ ] **Step 1: Write the failing test**

Create `frontend/src/lib/__tests__/openStem.test.ts`:
```typescript
import { describe, it, expect } from "vitest";
import { parseOpenStem } from "@/lib/openStem";

const STEM = [
  "Ответ: до 2500 знаков с пробелами; достаточно тезисного, структурированного ответа.",
  "Тип: открытый кейс. Системное мышление",
  "",
  "Компания внедряет сервис. После запуска часть возвратов зависает.",
  "",
  "Задание: Опишите анализ: 1) границы; 2) подпроблемы.",
  "Фокус ответа: Сфокусируйтесь на декомпозиции.",
  "Критерии оценки: границы системы; декомпозиция; цепочки причин.",
].join("\n");

describe("parseOpenStem", () => {
  it("splits the assembled stem into sections", () => {
    const p = parseOpenStem(STEM);
    expect(p).not.toBeNull();
    expect(p!.topicTitle).toBe("Системное мышление");
    expect(p!.answerHint).toContain("2500");
    expect(p!.case).toContain("Компания внедряет сервис");
    expect(p!.case).not.toContain("Задание:");        // case stops before Задание
    expect(p!.task).toBe("Опишите анализ: 1) границы; 2) подпроблемы.");
    expect(p!.focus).toBe("Сфокусируйтесь на декомпозиции.");
    expect(p!.criteria).toBe("границы системы; декомпозиция; цепочки причин.");
  });

  it("returns null for a stem without the expected anchors", () => {
    expect(parseOpenStem("Просто текст без меток.")).toBeNull();
    expect(parseOpenStem("")).toBeNull();
  });

  it("tolerates a multi-line case block", () => {
    const stem = [
      "Ответ: до 2500 знаков.",
      "Тип: открытый кейс. Описание интеграции",
      "",
      "Первая строка кейса.",
      "Вторая строка кейса.",
      "",
      "Задание: Опишите интеграцию.",
      "Фокус ответа: Не пишите код.",
      "Критерии оценки: полнота; риски.",
    ].join("\n");
    const p = parseOpenStem(stem)!;
    expect(p.case).toContain("Первая строка");
    expect(p.case).toContain("Вторая строка");
    expect(p.task).toBe("Опишите интеграцию.");
  });
});
```

- [ ] **Step 2: Run to verify it fails**

Run: `cd /Users/pavel/Developer/antests/frontend && npx vitest run src/lib/__tests__/openStem.test.ts`
Expected: FAIL — `parseOpenStem` doesn't exist.

- [ ] **Step 3: Implement the parser**

Create `frontend/src/lib/openStem.ts`:
```typescript
export interface ParsedOpenStem {
  topicTitle: string;
  answerHint: string;
  case: string;
  task: string;
  focus: string;
  criteria: string;
}

const ANSWER = "Ответ:";
const TYPE = "Тип: открытый кейс.";
const TASK = "Задание:";
const FOCUS = "Фокус ответа:";
const CRITERIA = "Критерии оценки:";

/**
 * Split an assembled open-question stem (from the backend's build_open_stem)
 * into its sections. Returns null if the expected anchors are missing, so the
 * caller can fall back to rendering the raw stem.
 *
 * Anchors appear in a fixed order: Ответ → Тип → case → Задание → Фокус → Критерии.
 * Each section runs from the FIRST occurrence of its anchor to the start of the
 * next anchor, so a stray label-like word inside the case can't break parsing.
 */
export function parseOpenStem(stem: string): ParsedOpenStem | null {
  const iType = stem.indexOf(TYPE);
  const iTask = stem.indexOf(TASK);
  const iFocus = stem.indexOf(FOCUS);
  const iCriteria = stem.indexOf(CRITERIA);
  // Require the full structured shape; otherwise fall back.
  if (iType < 0 || iTask < 0 || iFocus < 0 || iCriteria < 0) return null;
  if (!(iType < iTask && iTask < iFocus && iFocus < iCriteria)) return null;

  const iAnswer = stem.indexOf(ANSWER);
  const answerHint =
    iAnswer >= 0 ? stem.slice(iAnswer + ANSWER.length, iType).trim() : "";
  // topicTitle is the rest of the "Тип:" line after the prefix.
  const typeLineEnd = stem.indexOf("\n", iType);
  const topicTitle = stem
    .slice(iType + TYPE.length, typeLineEnd < 0 ? undefined : typeLineEnd)
    .trim();
  const caseText = stem.slice(typeLineEnd < 0 ? iType : typeLineEnd, iTask).trim();
  const task = stem.slice(iTask + TASK.length, iFocus).trim();
  const focus = stem.slice(iFocus + FOCUS.length, iCriteria).trim();
  const criteria = stem.slice(iCriteria + CRITERIA.length).trim();

  return { topicTitle, answerHint, case: caseText, task, focus, criteria };
}
```

- [ ] **Step 4: Run to verify it passes**

Run: `npx vitest run src/lib/__tests__/openStem.test.ts`
Expected: PASS (all 3 tests).

- [ ] **Step 5: Typecheck + commit**

Run: `npx tsc --noEmit`
```bash
cd /Users/pavel/Developer/antests
git add frontend/src/lib/openStem.ts frontend/src/lib/__tests__/openStem.test.ts
git commit -m "feat: parseOpenStem — split assembled open stem into sections"
```

---

### Task 3: `OpenStem` component — render the blocks

**Files:**
- Create: `frontend/src/components/OpenStem.tsx`
- Test: `frontend/src/components/__tests__/OpenStem.test.tsx` (create)

- [ ] **Step 1: Write the failing test**

Create `frontend/src/components/__tests__/OpenStem.test.tsx`:
```typescript
import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import { OpenStem } from "@/components/OpenStem";

const STEM = [
  "Ответ: до 2500 знаков с пробелами.",
  "Тип: открытый кейс. Системное мышление",
  "",
  "Компания внедряет сервис.",
  "",
  "Задание: Опишите анализ.",
  "Фокус ответа: Декомпозиция.",
  "Критерии оценки: границы; связи.",
].join("\n");

describe("OpenStem", () => {
  it("renders the topic, case and the three labelled blocks", () => {
    render(<OpenStem stem={STEM} />);
    expect(screen.getByText("Системное мышление")).toBeInTheDocument();
    expect(screen.getByText(/Компания внедряет сервис/)).toBeInTheDocument();
    // Block labels are present
    expect(screen.getByText("Задание")).toBeInTheDocument();
    expect(screen.getByText("Фокус ответа")).toBeInTheDocument();
    expect(screen.getByText("Критерии оценки")).toBeInTheDocument();
    // Block bodies are present
    expect(screen.getByText("Опишите анализ.")).toBeInTheDocument();
    expect(screen.getByText("Декомпозиция.")).toBeInTheDocument();
    expect(screen.getByText("границы; связи.")).toBeInTheDocument();
    // The answer-limit hint is shown (muted)
    expect(screen.getByText(/2500 знаков/)).toBeInTheDocument();
  });

  it("falls back to raw text when the stem is not structured", () => {
    render(<OpenStem stem="Просто вопрос без меток." />);
    expect(screen.getByText("Просто вопрос без меток.")).toBeInTheDocument();
  });
});
```

- [ ] **Step 2: Run to verify it fails**

Run: `npx vitest run src/components/__tests__/OpenStem.test.tsx`
Expected: FAIL — `OpenStem` doesn't exist.

- [ ] **Step 3: Implement the component**

Create `frontend/src/components/OpenStem.tsx`:
```tsx
"use client";
import { parseOpenStem } from "@/lib/openStem";

function Block({ label, body }: { label: string; body: string }) {
  if (!body) return null;
  return (
    <div style={{ marginTop: 12 }}>
      <div style={{ fontWeight: 700, color: "#1f3a5f", marginBottom: 2 }}>{label}</div>
      <div style={{ whiteSpace: "pre-line" }}>{body}</div>
    </div>
  );
}

export function OpenStem({ stem }: { stem: string }) {
  const p = parseOpenStem(stem);
  if (!p) {
    // Fallback: render the raw stem with newlines preserved.
    return <div style={{ whiteSpace: "pre-line" }}>{stem}</div>;
  }
  return (
    <div>
      {p.topicTitle && (
        <h3 style={{ margin: "0 0 4px" }}>{p.topicTitle}</h3>
      )}
      {p.answerHint && (
        <div style={{ fontSize: 12, color: "var(--muted)", marginBottom: 12 }}>
          {p.answerHint}
        </div>
      )}
      {p.case && (
        <div style={{ whiteSpace: "pre-line", marginBottom: 4 }}>{p.case}</div>
      )}
      <Block label="Задание" body={p.task} />
      <Block label="Фокус ответа" body={p.focus} />
      <Block label="Критерии оценки" body={p.criteria} />
    </div>
  );
}
```

- [ ] **Step 4: Run to verify it passes**

Run: `npx vitest run src/components/__tests__/OpenStem.test.tsx`
Expected: PASS (both tests).

- [ ] **Step 5: Typecheck + commit**

Run: `npx tsc --noEmit`
```bash
cd /Users/pavel/Developer/antests
git add frontend/src/components/OpenStem.tsx frontend/src/components/__tests__/OpenStem.test.tsx
git commit -m "feat: OpenStem component renders open question in labelled blocks"
```

---

### Task 4: Wire `OpenStem` into exam + results; fix the stale QuestionCard test

**Files:**
- Modify: `frontend/src/components/QuestionCard.tsx` (open-stem render + remove the now-duplicate hint)
- Modify: `frontend/src/app/test/[id]/results/page.tsx:115` (open stem render)
- Modify: `frontend/src/components/__tests__/QuestionCard.test.tsx` (update the stale multiline-stem test)

- [ ] **Step 1: Update the stale QuestionCard test**

In `frontend/src/components/__tests__/QuestionCard.test.tsx`, the test `renders an open question's multiline stem and a length hint` (≈ lines 71-85) asserts the stem is an `<h3>` with `whiteSpace: pre-line` and a "2500 знаков" hint. After this task, the open stem renders via `OpenStem` (blocks), not a pre-line `<h3>`, and the duplicate hint div is removed. Replace that test with one that asserts the block rendering. Give the open question a structured stem so OpenStem parses it:
```typescript
  it("renders an open question's stem as labelled blocks", () => {
    const openQ: Question = {
      id: "o1", seq: 81, topic_id: "open", type: "open",
      stem: [
        "Ответ: до 2500 знаков с пробелами.",
        "Тип: открытый кейс. Системное мышление",
        "",
        "Кейс про возвраты.",
        "",
        "Задание: сделайте X",
        "Фокус ответа: Y",
        "Критерии оценки: Z",
      ].join("\n"),
      artifact_kind: "none", artifact_content: null, options: [],
    };
    render(
      <QuestionCard question={openQ} selected={[]} onToggle={() => {}}
        answerText="" onAnswerText={() => {}} />
    );
    expect(screen.getByText("Системное мышление")).toBeInTheDocument();
    expect(screen.getByText("Задание")).toBeInTheDocument();
    expect(screen.getByText("Критерии оценки")).toBeInTheDocument();
    expect(screen.getByText(/2500 знаков/)).toBeInTheDocument();
    // textarea still present
    expect(screen.getByRole("textbox")).toBeInTheDocument();
  });
```
(The other open test, `renders a textarea for an open question and reports typed text` at ≈ line 55, uses `stem: "Опишите решения."` — an unstructured stem. OpenStem will fall back to raw text for it, and `getByRole("textbox")` still works, so that test stays GREEN unchanged. Verify it still passes after the wiring.)

- [ ] **Step 2: Run to verify it fails**

Run: `npx vitest run src/components/__tests__/QuestionCard.test.tsx`
Expected: FAIL — the new block test fails (still an `<h3>`, no "Задание" label element).

- [ ] **Step 3: Wire OpenStem into QuestionCard**

In `frontend/src/components/QuestionCard.tsx`:
(a) Add the import at the top (after the Artifact import):
```tsx
import { OpenStem } from "@/components/OpenStem";
```
(b) Replace the stem heading line (line 19):
```tsx
      <h3 style={{ margin: "8px 0 16px", whiteSpace: question.type === "open" ? "pre-line" : undefined }}>{question.stem}</h3>
```
with a conditional — open questions render via `OpenStem`, closed keep the `<h3>`:
```tsx
      {question.type === "open" ? (
        <div style={{ margin: "8px 0 16px" }}>
          <OpenStem stem={question.stem} />
        </div>
      ) : (
        <h3 style={{ margin: "8px 0 16px" }}>{question.stem}</h3>
      )}
```
(c) Remove the now-duplicate hint div under the textarea (lines 33-35, the `<div style={{ marginTop: 6, fontSize: 12, color: "var(--muted)" }}>До 2500 знаков...</div>`) — the limit is now shown in OpenStem's header (`answerHint`). Delete that div, leaving the textarea and its wrapping `<div>`.

- [ ] **Step 4: Wire OpenStem into the results page**

In `frontend/src/app/test/[id]/results/page.tsx`:
(a) Add the import near the other imports:
```tsx
import { OpenStem } from "@/components/OpenStem";
```
(b) Replace `<h4 style={{ margin: "8px 0" }}>{o.stem}</h4>` (≈ line 115) with:
```tsx
              <div style={{ margin: "8px 0" }}><OpenStem stem={o.stem} /></div>
```

- [ ] **Step 5: Run to verify it passes**

Run: `npx vitest run src/components/__tests__/QuestionCard.test.tsx`
Expected: PASS — block test passes; the textarea test still passes (fallback path).

- [ ] **Step 6: Typecheck, full frontend suite, build, commit**

Run: `npx tsc --noEmit && npx vitest run && npm run build`
Expected: tsc clean, all tests pass, build succeeds.

```bash
cd /Users/pavel/Developer/antests
git add frontend/src/components/QuestionCard.tsx "frontend/src/app/test/[id]/results/page.tsx" frontend/src/components/__tests__/QuestionCard.test.tsx
git commit -m "feat: render open questions as blocks (OpenStem) on exam + results"
```

---

### Task 5: Full verification + live smoke

**Files:** none (verification only)

- [ ] **Step 1: Full backend suite + lint**

Run: `cd /Users/pavel/Developer/antests/backend && . .venv/bin/activate && pytest -q && ruff check app tests`
Expected: all pass, lint clean.

- [ ] **Step 2: Full frontend suite + typecheck + build**

Run: `cd /Users/pavel/Developer/antests/frontend && npx vitest run && npx tsc --noEmit && npm run build`
Expected: all pass, tsc clean, build succeeds.

- [ ] **Step 3: Live smoke — base/specialist multi share**

Start backend, create a `base`+`exam` session, poll to ready, fetch `/questions`. Confirm:
- closed count == 50, multi share among closed is clearly above 50% (target ~70%, soft — don't assert exact);
- the 3 open questions' stems still parse into sections (contain "Задание:", "Фокус ответа:", "Критерии оценки:" — the OpenStem parser will format them).
Repeat for `specialist` (one session at a time, no concurrency — base/specialist generate 50 closed, ~3-4 min each). Confirm specialist multi share also elevated.

- [ ] **Step 4: Live smoke — formatting (visual or DOM)**

If the Claude Preview / Chrome MCP is available, render the exam page and the results page for an open question and confirm the blocks (topic heading, muted answer hint, case text, Задание/Фокус ответа/Критерии оценки labelled blocks) display separately. If no browser tooling is available, verify at the data+unit level: the open stems from the live smoke parse correctly through `parseOpenStem` (run a node one-liner feeding a real fetched stem), and rely on the OpenStem RTL tests for render correctness. Report which path was used.

- [ ] **Step 5: Stop servers; report**

Stop uvicorn; report results (multi shares for base & specialist, confirmation that open stems parse into blocks).

---

## Notes for the implementer

- **Multi quota is soft** — prompt guidance only, no post-filtering. ba was already 0.7; this just adds base/specialist.
- **Formatting is frontend-only & migration-free** — `parseOpenStem` works on any stem from `build_open_stem`; unstructured stems fall back to plain pre-line text (never blank).
- **No duplicate hint** — once OpenStem shows the answer-limit in its header, remove the separate hint div under the exam textarea.
- **Closed questions unchanged** — only the open-question stem rendering changes; the `<h3>` path stays for single/multi.
- **The two open tests in QuestionCard** — one uses a structured stem (update to assert blocks), one uses an unstructured stem "Опишите решения." (stays green via fallback).
