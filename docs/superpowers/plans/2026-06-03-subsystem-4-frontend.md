# Subsystem 4: Frontend (Next.js) — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the IBS-styled Next.js UI that consumes the backend API — registration/login (with access code), dashboard (level/mode picker + history + topic profile), test preparation (streaming generation progress), the exam screen (timer, question navigation, Mermaid + `<pre>` artifacts, locked-question blocking), and the results screen (score, pass/fail, per-question review with explanations, topic breakdown, recommendation).

**Architecture:** Next.js App Router with client components for the interactive exam flow. A thin typed `api` client wraps `fetch` (cookies sent with `credentials: "include"`). Pure logic (timer formatting/expiry, answer-state reducer, locked-question rule, results derivation) lives in framework-free modules under `lib/` so it's unit-testable with Vitest without rendering. Pages compose those modules. The exam screen polls `/sessions/{id}/status` for generation progress and reads ready questions, blocking navigation to not-yet-generated questions and starting the official timer when the pool is ready.

**Tech Stack:** Next.js (App Router, React, TypeScript), Vitest + React Testing Library + jsdom (unit/component tests), `mermaid` (client-side diagram rendering). No state library — React state + a small reducer suffice. The backend runs at `http://localhost:8000` (configurable via `NEXT_PUBLIC_API_BASE`).

**Depends on:** Subsystems 1–3 (backend) complete and running. The frontend talks to it over HTTP.

---

## Backend API contract (consumed by this subsystem)

All under the same origin or `NEXT_PUBLIC_API_BASE`; auth via httponly `session` cookie (send `credentials: "include"`).

- `POST /auth/register` `{login, password, access_code}` → 201 `{id, login}` (sets cookie) | 403 bad code | 409 dup
- `POST /auth/login` `{login, password}` → 200 `{id, login}` | 401
- `POST /auth/logout` → 204
- `GET /auth/me` → 200 `{id, login}` | 401
- `POST /sessions` `{level, mode}` → 201 `{id, status, total_questions}` | 401 | 429 daily limit
- `GET /sessions/{id}/status` → `{id, status, level, mode, total_questions, generated_count, time_limit_sec, timer_started_at}` (status ∈ generating|ready|in_progress|finished|failed)
- `GET /sessions/{id}/questions` → `[{id, seq, topic_id, type, stem, artifact_kind, artifact_content, options}]` (NO correct_keys/explanation)
- `POST /sessions/{id}/answers` `{question_id, selected_keys}` → 200 `{question_id, recorded}` | 400 | 409 finished
- `POST /sessions/{id}/finish` → 200 `{id, score_percent, passed, status}` | 401 | 409 not finishable
- `GET /sessions/{id}/results` → `{session_id, level, mode, score_percent, passed, total_questions, answered_count, topic_breakdown:[{topic_id, answered, correct, accuracy}], recommendation, questions:[{id, seq, topic_id, type, stem, artifact_kind, artifact_content, options, correct_keys, selected_keys, is_correct, explanation}]}`

> NOTE: there is currently no backend endpoint listing a user's past sessions or competency profile for the dashboard. Task 9 adds a minimal backend endpoint `GET /me/overview` for this. This is the one backend change in this subsystem; it lives in the backend and is tested there.

---

## File Structure

```
frontend/
  package.json
  next.config.mjs
  tsconfig.json
  vitest.config.ts
  vitest.setup.ts
  .env.local.example                 # NEXT_PUBLIC_API_BASE
  src/
    lib/
      api.ts                         # typed fetch wrapper (all endpoints)
      types.ts                       # shared TS types matching the API
      timer.ts                       # formatRemaining, isExpired (pure)
      examState.ts                   # answer-state reducer + locked-question rule (pure)
      results.ts                     # results-derivation helpers (pure)
    components/
      Artifact.tsx                   # renders <pre> or Mermaid by artifact_kind
      QuestionCard.tsx               # one question: stem + artifact + options
      QuestionNav.tsx                # sidebar grid w/ answered/current/locked
      Timer.tsx                      # countdown display
    app/
      layout.tsx                     # root layout + IBS theme styles
      globals.css                    # IBS bluewhite theme
      page.tsx                       # redirects to /login or /dashboard
      login/page.tsx
      register/page.tsx
      dashboard/page.tsx
      test/[id]/prepare/page.tsx     # streaming generation progress
      test/[id]/page.tsx             # the exam screen
      test/[id]/results/page.tsx
  src/lib/__tests__/
      timer.test.ts
      examState.test.ts
      results.test.ts
  src/components/__tests__/
      Artifact.test.tsx
      QuestionCard.test.tsx
      QuestionNav.test.tsx
```

Pure logic (`timer`, `examState`, `results`) is unit-tested without rendering. Components are tested with RTL. Pages are thin compositions (smoke-tested where practical, but the bulk of behavior lives in the tested modules).

---

### Task 1: Scaffold Next.js + Vitest

**Files:**
- Create: `frontend/package.json`, `next.config.mjs`, `tsconfig.json`, `vitest.config.ts`, `vitest.setup.ts`, `.env.local.example`
- Create: `frontend/src/app/layout.tsx`, `frontend/src/app/globals.css`, `frontend/src/app/page.tsx`

- [ ] **Step 1: Create `frontend/package.json`**

```json
{
  "name": "antests-frontend",
  "version": "0.1.0",
  "private": true,
  "scripts": {
    "dev": "next dev -p 3000",
    "build": "next build",
    "start": "next start -p 3000",
    "test": "vitest run",
    "test:watch": "vitest",
    "lint": "next lint"
  },
  "dependencies": {
    "next": "^15.0.0",
    "react": "^19.0.0",
    "react-dom": "^19.0.0",
    "mermaid": "^11.0.0"
  },
  "devDependencies": {
    "@testing-library/jest-dom": "^6.5.0",
    "@testing-library/react": "^16.0.0",
    "@types/node": "^22.0.0",
    "@types/react": "^19.0.0",
    "@vitejs/plugin-react": "^4.3.0",
    "jsdom": "^25.0.0",
    "typescript": "^5.6.0",
    "vitest": "^2.1.0"
  }
}
```

- [ ] **Step 2: Create config files**

`frontend/tsconfig.json`:
```json
{
  "compilerOptions": {
    "target": "ES2020",
    "lib": ["dom", "dom.iterable", "esnext"],
    "allowJs": true,
    "skipLibCheck": true,
    "strict": true,
    "noEmit": true,
    "esModuleInterop": true,
    "module": "esnext",
    "moduleResolution": "bundler",
    "resolveJsonModule": true,
    "isolatedModules": true,
    "jsx": "preserve",
    "incremental": true,
    "plugins": [{ "name": "next" }],
    "paths": { "@/*": ["./src/*"] }
  },
  "include": ["next-env.d.ts", "**/*.ts", "**/*.tsx", ".next/types/**/*.ts"],
  "exclude": ["node_modules"]
}
```

`frontend/next.config.mjs`:
```javascript
/** @type {import('next').NextConfig} */
const nextConfig = {};
export default nextConfig;
```

`frontend/vitest.config.ts`:
```typescript
import { defineConfig } from "vitest/config";
import react from "@vitejs/plugin-react";
import path from "path";

export default defineConfig({
  plugins: [react()],
  test: {
    environment: "jsdom",
    setupFiles: ["./vitest.setup.ts"],
    globals: true,
  },
  resolve: {
    alias: { "@": path.resolve(__dirname, "./src") },
  },
});
```

`frontend/vitest.setup.ts`:
```typescript
import "@testing-library/jest-dom/vitest";
```

`frontend/.env.local.example`:
```bash
NEXT_PUBLIC_API_BASE=http://localhost:8000
```

- [ ] **Step 3: Create `frontend/src/app/globals.css` (IBS theme)**

```css
:root {
  --ibs-blue: #2f6fed;
  --ibs-navy: #1f3a5f;
  --bg: #f4f7fb;
  --card: #ffffff;
  --border: #e6ebf2;
  --text: #1d2733;
  --muted: #5a6878;
  --locked: #f0d7d7;
  --locked-text: #b06a6a;
  --ok: #18b27e;
  --err: #e0556b;
}
* { box-sizing: border-box; }
body { margin: 0; background: var(--bg); color: var(--text);
  font-family: -apple-system, "Segoe UI", Roboto, Helvetica, Arial, sans-serif; }
.card { background: var(--card); border: 1px solid var(--border); border-radius: 12px; padding: 24px; }
.btn { padding: 10px 22px; border-radius: 8px; border: none; background: var(--ibs-blue);
  color: #fff; font-size: 14px; cursor: pointer; }
.btn:disabled { opacity: .5; cursor: not-allowed; }
.btn-ghost { background: #fff; border: 1px solid #cdd6e2; color: #41526a; }
.input { width: 100%; padding: 10px 12px; border: 1px solid var(--border); border-radius: 8px; font-size: 14px; }
.label { font-size: 12px; text-transform: uppercase; letter-spacing: .5px; color: var(--muted); }
.error { color: var(--err); font-size: 14px; }
a { color: var(--ibs-blue); }
```

- [ ] **Step 4: Create `frontend/src/app/layout.tsx`**

```tsx
import "./globals.css";
import type { ReactNode } from "react";

export const metadata = { title: "Тренажёр сертификации СА" };

export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    <html lang="ru">
      <body>{children}</body>
    </html>
  );
}
```

- [ ] **Step 5: Create `frontend/src/app/page.tsx` (root redirect)**

```tsx
import { redirect } from "next/navigation";

export default function Home() {
  redirect("/dashboard");
}
```

- [ ] **Step 6: Install and verify**

Run: `cd frontend && npm install`
Then: `npm run test -- --run` (no tests yet — Vitest exits 0 with "no test files" is acceptable; if it errors on no files, that's fine to ignore at this step).
Expected: `npm install` completes; Next deps present.

- [ ] **Step 7: Commit**

```bash
git add frontend/package.json frontend/next.config.mjs frontend/tsconfig.json frontend/vitest.config.ts frontend/vitest.setup.ts frontend/.env.local.example frontend/src/app/layout.tsx frontend/src/app/globals.css frontend/src/app/page.tsx
git commit -m "chore: scaffold Next.js frontend with Vitest"
```

---

### Task 2: Shared types

**Files:**
- Create: `frontend/src/lib/types.ts`

- [ ] **Step 1: Write `frontend/src/lib/types.ts`**

```typescript
export type Level = "base" | "specialist";
export type Mode = "exam" | "adaptive";
export type SessionStatus = "generating" | "ready" | "in_progress" | "finished" | "failed";
export type ArtifactKind = "none" | "code" | "json" | "sql" | "xml" | "mermaid";
export type QuestionType = "single" | "multi";

export interface Option { key: string; text: string; }

export interface Question {
  id: string;
  seq: number;
  topic_id: string;
  type: QuestionType;
  stem: string;
  artifact_kind: ArtifactKind;
  artifact_content: string | null;
  options: Option[];
}

export interface SessionStatusResponse {
  id: string;
  status: SessionStatus;
  level: Level;
  mode: Mode;
  total_questions: number;
  generated_count: number;
  time_limit_sec: number;
  timer_started_at: string | null;
}

export interface TopicBreakdown {
  topic_id: string;
  answered: number;
  correct: number;
  accuracy: number;
}

export interface QuestionReview extends Question {
  correct_keys: string[];
  selected_keys: string[];
  is_correct: boolean;
  explanation: string;
}

export interface Results {
  session_id: string;
  level: Level;
  mode: Mode;
  score_percent: number;
  passed: boolean;
  total_questions: number;
  answered_count: number;
  topic_breakdown: TopicBreakdown[];
  recommendation: string;
  questions: QuestionReview[];
}

export interface User { id: string; login: string; }
```

- [ ] **Step 2: Type-check**

Run: `cd frontend && npx tsc --noEmit`
Expected: no errors.

- [ ] **Step 3: Commit**

```bash
git add frontend/src/lib/types.ts
git commit -m "feat: add shared frontend types matching the API"
```

---

### Task 3: Timer logic (pure)

**Files:**
- Create: `frontend/src/lib/timer.ts`
- Test: `frontend/src/lib/__tests__/timer.test.ts`

- [ ] **Step 1: Write the failing test** — `frontend/src/lib/__tests__/timer.test.ts`

```typescript
import { describe, it, expect } from "vitest";
import { formatRemaining, remainingSeconds, isExpired } from "@/lib/timer";

describe("timer", () => {
  it("formats hh:mm:ss", () => {
    expect(formatRemaining(0)).toBe("00:00:00");
    expect(formatRemaining(59)).toBe("00:00:59");
    expect(formatRemaining(3661)).toBe("01:01:01");
    expect(formatRemaining(10800)).toBe("03:00:00");
  });

  it("clamps negative to zero", () => {
    expect(formatRemaining(-5)).toBe("00:00:00");
  });

  it("computes remaining seconds from start + limit + now", () => {
    const start = "2026-06-03T10:00:00Z";
    const limit = 180 * 60; // 10800
    const now = new Date("2026-06-03T10:30:00Z").getTime();
    expect(remainingSeconds(start, limit, now)).toBe(10800 - 1800);
  });

  it("remaining is zero (not negative) past the deadline", () => {
    const start = "2026-06-03T10:00:00Z";
    const now = new Date("2026-06-03T14:00:00Z").getTime();
    expect(remainingSeconds(start, 10800, now)).toBe(0);
  });

  it("isExpired true only when no time left and timer started", () => {
    const start = "2026-06-03T10:00:00Z";
    const past = new Date("2026-06-03T14:00:00Z").getTime();
    const during = new Date("2026-06-03T10:10:00Z").getTime();
    expect(isExpired(start, 10800, past)).toBe(true);
    expect(isExpired(start, 10800, during)).toBe(false);
    expect(isExpired(null, 10800, past)).toBe(false); // not started -> not expired
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd frontend && npm run test -- timer`
Expected: FAIL (cannot find module `@/lib/timer`)

- [ ] **Step 3: Write `frontend/src/lib/timer.ts`**

```typescript
export function formatRemaining(totalSeconds: number): string {
  const s = Math.max(0, Math.floor(totalSeconds));
  const hh = Math.floor(s / 3600);
  const mm = Math.floor((s % 3600) / 60);
  const ss = s % 60;
  const pad = (n: number) => String(n).padStart(2, "0");
  return `${pad(hh)}:${pad(mm)}:${pad(ss)}`;
}

export function remainingSeconds(
  startedAtIso: string,
  limitSec: number,
  nowMs: number
): number {
  const startMs = new Date(startedAtIso).getTime();
  const elapsed = Math.floor((nowMs - startMs) / 1000);
  return Math.max(0, limitSec - elapsed);
}

export function isExpired(
  startedAtIso: string | null,
  limitSec: number,
  nowMs: number
): boolean {
  if (startedAtIso === null) return false;
  return remainingSeconds(startedAtIso, limitSec, nowMs) <= 0;
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd frontend && npm run test -- timer`
Expected: PASS (5 passed)

- [ ] **Step 5: Commit**

```bash
git add frontend/src/lib/timer.ts frontend/src/lib/__tests__/timer.test.ts
git commit -m "feat: add pure timer logic"
```

---

### Task 4: Exam-state logic (pure) — answers + locked-question rule

**Files:**
- Create: `frontend/src/lib/examState.ts`
- Test: `frontend/src/lib/__tests__/examState.test.ts`

- [ ] **Step 1: Write the failing test** — `frontend/src/lib/__tests__/examState.test.ts`

```typescript
import { describe, it, expect } from "vitest";
import {
  toggleSelection,
  isQuestionReady,
  answeredCount,
  type AnswerMap,
} from "@/lib/examState";

describe("toggleSelection", () => {
  it("single-choice replaces selection", () => {
    let a: string[] = [];
    a = toggleSelection(a, "a", "single");
    expect(a).toEqual(["a"]);
    a = toggleSelection(a, "b", "single");
    expect(a).toEqual(["b"]); // replaced, not added
  });

  it("multi-choice toggles membership", () => {
    let a: string[] = [];
    a = toggleSelection(a, "a", "multi");
    a = toggleSelection(a, "c", "multi");
    expect(a.sort()).toEqual(["a", "c"]);
    a = toggleSelection(a, "a", "multi"); // deselect
    expect(a).toEqual(["c"]);
  });
});

describe("isQuestionReady", () => {
  it("ready when seq <= generated_count", () => {
    expect(isQuestionReady(5, 5)).toBe(true);
    expect(isQuestionReady(4, 5)).toBe(true);
    expect(isQuestionReady(6, 5)).toBe(false); // not generated yet -> locked
  });
});

describe("answeredCount", () => {
  it("counts questions with a non-empty selection", () => {
    const map: AnswerMap = { q1: ["a"], q2: [], q3: ["b", "c"] };
    expect(answeredCount(map)).toBe(2);
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd frontend && npm run test -- examState`
Expected: FAIL (cannot find module)

- [ ] **Step 3: Write `frontend/src/lib/examState.ts`**

```typescript
import type { QuestionType } from "@/lib/types";

export type AnswerMap = Record<string, string[]>;

export function toggleSelection(
  current: string[],
  key: string,
  type: QuestionType
): string[] {
  if (type === "single") {
    return [key];
  }
  return current.includes(key)
    ? current.filter((k) => k !== key)
    : [...current, key];
}

/** A question (1-indexed seq) is ready/answerable iff it has been generated. */
export function isQuestionReady(seq: number, generatedCount: number): boolean {
  return seq <= generatedCount;
}

export function answeredCount(map: AnswerMap): number {
  return Object.values(map).filter((sel) => sel.length > 0).length;
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd frontend && npm run test -- examState`
Expected: PASS (5 passed)

- [ ] **Step 5: Commit**

```bash
git add frontend/src/lib/examState.ts frontend/src/lib/__tests__/examState.test.ts
git commit -m "feat: add pure exam-state logic (selection + locked rule)"
```

---

### Task 5: API client

**Files:**
- Create: `frontend/src/lib/api.ts`
- Test: `frontend/src/lib/__tests__/api.test.ts`

- [ ] **Step 1: Write the failing test** — `frontend/src/lib/__tests__/api.test.ts`

```typescript
import { describe, it, expect, vi, beforeEach } from "vitest";
import { api, ApiError } from "@/lib/api";

beforeEach(() => {
  vi.restoreAllMocks();
});

function mockFetch(status: number, body: unknown) {
  return vi.fn().mockResolvedValue({
    ok: status >= 200 && status < 300,
    status,
    json: async () => body,
  } as Response);
}

describe("api", () => {
  it("login posts credentials and returns user", async () => {
    const f = mockFetch(200, { id: "u1", login: "alice" });
    vi.stubGlobal("fetch", f);
    const user = await api.login("alice", "pw");
    expect(user.login).toBe("alice");
    const [url, init] = f.mock.calls[0];
    expect(String(url)).toContain("/auth/login");
    expect(init.method).toBe("POST");
    expect(init.credentials).toBe("include");
  });

  it("throws ApiError with status on failure", async () => {
    vi.stubGlobal("fetch", mockFetch(429, { detail: "Daily session limit reached" }));
    await expect(api.createSession("base", "exam")).rejects.toMatchObject({
      status: 429,
    });
  });

  it("createSession returns the new session id", async () => {
    vi.stubGlobal("fetch", mockFetch(201, { id: "s1", status: "generating", total_questions: 80 }));
    const s = await api.createSession("base", "exam");
    expect(s.id).toBe("s1");
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd frontend && npm run test -- api`
Expected: FAIL (cannot find module)

- [ ] **Step 3: Write `frontend/src/lib/api.ts`**

```typescript
import type {
  Level, Mode, Question, Results, SessionStatusResponse, User,
} from "@/lib/types";

const BASE = process.env.NEXT_PUBLIC_API_BASE ?? "http://localhost:8000";

export class ApiError extends Error {
  status: number;
  constructor(status: number, message: string) {
    super(message);
    this.status = status;
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    ...init,
    credentials: "include",
    headers: { "Content-Type": "application/json", ...(init?.headers ?? {}) },
  });
  if (!res.ok) {
    let detail = res.statusText;
    try {
      const body = await res.json();
      detail = body?.detail ?? detail;
    } catch { /* ignore */ }
    throw new ApiError(res.status, detail);
  }
  if (res.status === 204) return undefined as T;
  return (await res.json()) as T;
}

export const api = {
  register: (login: string, password: string, access_code: string) =>
    request<User>("/auth/register", {
      method: "POST",
      body: JSON.stringify({ login, password, access_code }),
    }),
  login: (login: string, password: string) =>
    request<User>("/auth/login", {
      method: "POST",
      body: JSON.stringify({ login, password }),
    }),
  logout: () => request<void>("/auth/logout", { method: "POST" }),
  me: () => request<User>("/auth/me"),
  createSession: (level: Level, mode: Mode) =>
    request<{ id: string; status: string; total_questions: number }>("/sessions", {
      method: "POST",
      body: JSON.stringify({ level, mode }),
    }),
  sessionStatus: (id: string) =>
    request<SessionStatusResponse>(`/sessions/${id}/status`),
  sessionQuestions: (id: string) =>
    request<Question[]>(`/sessions/${id}/questions`),
  submitAnswer: (id: string, question_id: string, selected_keys: string[]) =>
    request<{ question_id: string; recorded: boolean }>(`/sessions/${id}/answers`, {
      method: "POST",
      body: JSON.stringify({ question_id, selected_keys }),
    }),
  finish: (id: string) =>
    request<{ id: string; score_percent: number; passed: boolean; status: string }>(
      `/sessions/${id}/finish`, { method: "POST" }
    ),
  results: (id: string) => request<Results>(`/sessions/${id}/results`),
  overview: () => request<Overview>("/me/overview"),
};

export interface OverviewSession {
  id: string; level: Level; mode: Mode; status: string;
  score_percent: number | null; passed: boolean | null; created_at: string;
}
export interface OverviewTopic { topic_id: string; level: Level; accuracy: number; }
export interface Overview {
  sessions: OverviewSession[];
  competency: OverviewTopic[];
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd frontend && npm run test -- api`
Expected: PASS (3 passed)

- [ ] **Step 5: Commit**

```bash
git add frontend/src/lib/api.ts frontend/src/lib/__tests__/api.test.ts
git commit -m "feat: add typed API client"
```

---

### Task 6: Artifact component (Mermaid + pre)

**Files:**
- Create: `frontend/src/components/Artifact.tsx`
- Test: `frontend/src/components/__tests__/Artifact.test.tsx`

- [ ] **Step 1: Write the failing test** — `frontend/src/components/__tests__/Artifact.test.tsx`

```tsx
import { describe, it, expect, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import { Artifact } from "@/components/Artifact";

// Mermaid is async/canvas-y; mock it so the component test is deterministic.
vi.mock("mermaid", () => ({
  default: { initialize: vi.fn(), render: vi.fn().mockResolvedValue({ svg: "<svg/>" }) },
}));

describe("Artifact", () => {
  it("renders nothing for kind=none", () => {
    const { container } = render(<Artifact kind="none" content={null} />);
    expect(container.firstChild).toBeNull();
  });

  it("renders code/sql/json/xml in a <pre>", () => {
    render(<Artifact kind="sql" content="SELECT 1" />);
    const pre = screen.getByText("SELECT 1");
    expect(pre.tagName).toBe("PRE");
  });

  it("renders a mermaid container for kind=mermaid", () => {
    render(<Artifact kind="mermaid" content="graph TD; A-->B" />);
    expect(screen.getByTestId("mermaid")).toBeInTheDocument();
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd frontend && npm run test -- Artifact`
Expected: FAIL (cannot find module)

- [ ] **Step 3: Write `frontend/src/components/Artifact.tsx`**

```tsx
"use client";
import { useEffect, useRef, useState } from "react";
import type { ArtifactKind } from "@/lib/types";

export function Artifact({ kind, content }: { kind: ArtifactKind; content: string | null }) {
  const ref = useRef<HTMLDivElement>(null);
  const [svg, setSvg] = useState<string>("");

  useEffect(() => {
    if (kind !== "mermaid" || !content) return;
    let cancelled = false;
    (async () => {
      const mermaid = (await import("mermaid")).default;
      mermaid.initialize({ startOnLoad: false, theme: "neutral" });
      try {
        const { svg } = await mermaid.render(`m${Math.abs(hash(content))}`, content);
        if (!cancelled) setSvg(svg);
      } catch {
        if (!cancelled) setSvg("");
      }
    })();
    return () => { cancelled = true; };
  }, [kind, content]);

  if (kind === "none" || !content) return null;

  if (kind === "mermaid") {
    return (
      <div
        data-testid="mermaid"
        ref={ref}
        style={{ background: "#fff", borderRadius: 8, padding: 12, overflow: "auto" }}
        dangerouslySetInnerHTML={{ __html: svg || content }}
      />
    );
  }

  return (
    <pre
      style={{
        background: "#0f1b2d", color: "#cde2ff", borderRadius: 8, padding: "14px 16px",
        fontFamily: "ui-monospace, Menlo, monospace", fontSize: 13, overflow: "auto",
      }}
    >
      {content}
    </pre>
  );
}

function hash(s: string): number {
  let h = 0;
  for (let i = 0; i < s.length; i++) h = (h << 5) - h + s.charCodeAt(i);
  return h;
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd frontend && npm run test -- Artifact`
Expected: PASS (3 passed). The mermaid mock means the container renders with the raw content fallback initially; the test asserts the container exists.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/components/Artifact.tsx frontend/src/components/__tests__/Artifact.test.tsx
git commit -m "feat: add Artifact component (pre + mermaid)"
```

---

### Task 7: QuestionCard + QuestionNav components

**Files:**
- Create: `frontend/src/components/QuestionCard.tsx`
- Create: `frontend/src/components/QuestionNav.tsx`
- Test: `frontend/src/components/__tests__/QuestionCard.test.tsx`
- Test: `frontend/src/components/__tests__/QuestionNav.test.tsx`

- [ ] **Step 1: Write the failing tests**

`frontend/src/components/__tests__/QuestionCard.test.tsx`:
```tsx
import { describe, it, expect, vi } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import { QuestionCard } from "@/components/QuestionCard";
import type { Question } from "@/lib/types";

vi.mock("mermaid", () => ({ default: { initialize: vi.fn(), render: vi.fn() } }));

const q: Question = {
  id: "q1", seq: 1, topic_id: "data", type: "single", stem: "Pick one",
  artifact_kind: "none", artifact_content: null,
  options: [{ key: "a", text: "Alpha" }, { key: "b", text: "Beta" }],
};

describe("QuestionCard", () => {
  it("renders stem and options", () => {
    render(<QuestionCard question={q} selected={[]} onToggle={() => {}} />);
    expect(screen.getByText("Pick one")).toBeInTheDocument();
    expect(screen.getByText("Alpha")).toBeInTheDocument();
    expect(screen.getByText("Beta")).toBeInTheDocument();
  });

  it("calls onToggle with the option key when clicked", () => {
    const onToggle = vi.fn();
    render(<QuestionCard question={q} selected={[]} onToggle={onToggle} />);
    fireEvent.click(screen.getByText("Alpha"));
    expect(onToggle).toHaveBeenCalledWith("a");
  });

  it("marks selected options", () => {
    render(<QuestionCard question={q} selected={["a"]} onToggle={() => {}} />);
    expect(screen.getByText("Alpha").closest("[data-selected]")).toHaveAttribute(
      "data-selected", "true"
    );
  });
});
```

`frontend/src/components/__tests__/QuestionNav.test.tsx`:
```tsx
import { describe, it, expect, vi } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import { QuestionNav } from "@/components/QuestionNav";

describe("QuestionNav", () => {
  it("renders a cell per question and marks states", () => {
    render(
      <QuestionNav
        total={4}
        generatedCount={2}
        currentSeq={1}
        answeredSeqs={new Set([1])}
        onJump={() => {}}
      />
    );
    // 4 cells
    expect(screen.getByText("1")).toBeInTheDocument();
    expect(screen.getByText("4")).toBeInTheDocument();
    // cell 1 answered+current, cells 3/4 locked (seq>generated)
    expect(screen.getByText("3").closest("[data-locked]")).toHaveAttribute("data-locked", "true");
    expect(screen.getByText("2").closest("[data-locked]")).toHaveAttribute("data-locked", "false");
  });

  it("does not call onJump for a locked question", () => {
    const onJump = vi.fn();
    render(
      <QuestionNav total={4} generatedCount={2} currentSeq={1}
        answeredSeqs={new Set()} onJump={onJump} />
    );
    fireEvent.click(screen.getByText("4")); // locked
    expect(onJump).not.toHaveBeenCalled();
    fireEvent.click(screen.getByText("2")); // ready
    expect(onJump).toHaveBeenCalledWith(2);
  });
});
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd frontend && npm run test -- QuestionCard QuestionNav`
Expected: FAIL (cannot find modules)

- [ ] **Step 3: Write `frontend/src/components/QuestionCard.tsx`**

```tsx
"use client";
import type { Question } from "@/lib/types";
import { Artifact } from "@/components/Artifact";

export function QuestionCard({
  question, selected, onToggle,
}: {
  question: Question;
  selected: string[];
  onToggle: (key: string) => void;
}) {
  return (
    <div className="card">
      <div className="label">
        Вопрос {question.seq} · {question.topic_id} · {question.type === "single" ? "один ответ" : "несколько"}
      </div>
      <h3 style={{ margin: "8px 0 16px" }}>{question.stem}</h3>
      <Artifact kind={question.artifact_kind} content={question.artifact_content} />
      <div style={{ marginTop: 16 }}>
        {question.options.map((o) => {
          const isSel = selected.includes(o.key);
          return (
            <div
              key={o.key}
              data-selected={isSel}
              onClick={() => onToggle(o.key)}
              style={{
                display: "flex", gap: 12, alignItems: "center",
                border: `1px solid ${isSel ? "#2f6fed" : "#e3e9f1"}`,
                background: isSel ? "#f3f7ff" : "#fff",
                borderRadius: 9, padding: "13px 15px", marginBottom: 10, cursor: "pointer",
              }}
            >
              <span style={{
                width: 22, height: 22, borderRadius: question.type === "single" ? "50%" : 6,
                border: `2px solid ${isSel ? "#2f6fed" : "#c0cad8"}`,
                background: isSel ? "#2f6fed" : "#fff", flex: "none",
              }} />
              <span>{o.text}</span>
            </div>
          );
        })}
      </div>
    </div>
  );
}
```

- [ ] **Step 4: Write `frontend/src/components/QuestionNav.tsx`**

```tsx
"use client";
import { isQuestionReady } from "@/lib/examState";

export function QuestionNav({
  total, generatedCount, currentSeq, answeredSeqs, onJump,
}: {
  total: number;
  generatedCount: number;
  currentSeq: number;
  answeredSeqs: Set<number>;
  onJump: (seq: number) => void;
}) {
  const cells = Array.from({ length: total }, (_, i) => i + 1);
  return (
    <div style={{ display: "grid", gridTemplateColumns: "repeat(6, 1fr)", gap: 6 }}>
      {cells.map((seq) => {
        const ready = isQuestionReady(seq, generatedCount);
        const locked = !ready;
        const answered = answeredSeqs.has(seq);
        const current = seq === currentSeq;
        const bg = current ? "#fff" : answered ? "#2f6fed" : locked ? "#f0d7d7" : "#eef2f8";
        const color = current ? "#2f6fed" : answered ? "#fff" : locked ? "#b06a6a" : "#5a6878";
        return (
          <span
            key={seq}
            data-locked={locked}
            onClick={() => { if (ready) onJump(seq); }}
            style={{
              aspectRatio: "1", display: "flex", alignItems: "center", justifyContent: "center",
              fontSize: 12, borderRadius: 6, background: bg, color,
              outline: current ? "2px solid #2f6fed" : "none",
              fontWeight: current ? 700 : 400, cursor: ready ? "pointer" : "not-allowed",
            }}
          >
            {seq}
          </span>
        );
      })}
    </div>
  );
}
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd frontend && npm run test -- QuestionCard QuestionNav`
Expected: PASS (6 passed)

- [ ] **Step 6: Commit**

```bash
git add frontend/src/components/QuestionCard.tsx frontend/src/components/QuestionNav.tsx frontend/src/components/__tests__/QuestionCard.test.tsx frontend/src/components/__tests__/QuestionNav.test.tsx
git commit -m "feat: add QuestionCard and QuestionNav components"
```

---

### Task 8: Timer component

**Files:**
- Create: `frontend/src/components/Timer.tsx`

(Logic is already tested in Task 3; this is a thin display wrapper. No separate test — it's exercised by the exam page smoke test in Task 12.)

- [ ] **Step 1: Write `frontend/src/components/Timer.tsx`**

```tsx
"use client";
import { useEffect, useState } from "react";
import { formatRemaining, remainingSeconds } from "@/lib/timer";

export function Timer({
  startedAt, limitSec, onExpire,
}: {
  startedAt: string | null;
  limitSec: number;
  onExpire: () => void;
}) {
  const [now, setNow] = useState<number>(() => Date.now());
  useEffect(() => {
    const t = setInterval(() => setNow(Date.now()), 1000);
    return () => clearInterval(t);
  }, []);

  if (startedAt === null) {
    return <div className="label">Таймер запустится после подготовки теста</div>;
  }
  const left = remainingSeconds(startedAt, limitSec, now);
  if (left <= 0) onExpire();
  return (
    <div style={{
      background: "#fff", border: "1px solid #e0e6ee", borderRadius: 8,
      padding: "8px 16px", fontWeight: 700, color: "#1f3a5f",
      fontVariantNumeric: "tabular-nums",
    }}>
      {formatRemaining(left)}
    </div>
  );
}
```

- [ ] **Step 2: Type-check**

Run: `cd frontend && npx tsc --noEmit`
Expected: no errors.

- [ ] **Step 3: Commit**

```bash
git add frontend/src/components/Timer.tsx
git commit -m "feat: add Timer display component"
```

---

### Task 9: Backend — `GET /me/overview` endpoint (dashboard data)

**Files:**
- Create: `backend/app/overview/__init__.py` (empty)
- Create: `backend/app/overview/router.py`
- Modify: `backend/app/main.py`
- Test: `backend/tests/test_overview_api.py`

This is the one backend change in this subsystem: a read endpoint giving the dashboard a user's past sessions and competency profile.

- [ ] **Step 1: Write the failing test** — `backend/tests/test_overview_api.py`

```python
import pytest


async def _register(client, login="uo"):
    return await client.post(
        "/auth/register",
        json={"login": login, "password": "pw12345", "access_code": "TEST-CODE"},
    )


@pytest.mark.asyncio
async def test_overview_empty_for_new_user(client):
    await _register(client, "newbie")
    resp = await client.get("/me/overview")
    assert resp.status_code == 200
    body = resp.json()
    assert body["sessions"] == []
    assert body["competency"] == []


@pytest.mark.asyncio
async def test_overview_requires_auth(client):
    await client.post("/auth/logout")
    resp = await client.get("/me/overview")
    assert resp.status_code == 401
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && . .venv/bin/activate && pytest tests/test_overview_api.py -v`
Expected: FAIL (404 — route doesn't exist)

- [ ] **Step 3: Create empty `backend/app/overview/__init__.py`, then write `backend/app/overview/router.py`**

```python
from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.base import get_session
from app.db.models import TestSession, TopicCompetency, User
from app.deps import current_user

router = APIRouter(tags=["overview"])


@router.get("/me/overview")
async def overview(
    user: User = Depends(current_user),
    db: AsyncSession = Depends(get_session),
):
    sessions = (
        await db.execute(
            select(TestSession)
            .where(TestSession.user_id == user.id)
            .order_by(TestSession.created_at.desc())
        )
    ).scalars().all()
    competency = (
        await db.execute(
            select(TopicCompetency).where(TopicCompetency.user_id == user.id)
        )
    ).scalars().all()
    return {
        "sessions": [
            {
                "id": str(s.id), "level": s.level, "mode": s.mode, "status": s.status,
                "score_percent": float(s.score_percent) if s.score_percent is not None else None,
                "passed": s.passed,
                "created_at": s.created_at.isoformat(),
            }
            for s in sessions
        ],
        "competency": [
            {"topic_id": c.topic_id, "level": c.level, "accuracy": float(c.accuracy)}
            for c in competency
        ],
    }
```

- [ ] **Step 4: Include the router in `backend/app/main.py`**

Add the import and `include_router` after the assessment router:
```python
from app.overview.router import router as overview_router
# ... inside create_app(), after app.include_router(assessment_router):
    app.include_router(overview_router)
```

- [ ] **Step 5: Run test to verify it passes**

Run: `cd backend && . .venv/bin/activate && pytest tests/test_overview_api.py -v`
Expected: PASS (2 passed)

- [ ] **Step 6: Run the full backend suite and lint**

Run: `pytest -q && ruff check app tests`
Expected: all pass (was 92; +2 = 94), lint clean.

- [ ] **Step 7: Commit**

```bash
git add backend/app/overview/ backend/app/main.py backend/tests/test_overview_api.py
git commit -m "feat: add GET /me/overview for dashboard data"
```

---

### Task 10: Auth pages (register + login)

**Files:**
- Create: `frontend/src/app/login/page.tsx`
- Create: `frontend/src/app/register/page.tsx`

(These are client pages using the tested `api`. Behavior-light; the API logic they call is already tested in Task 5. No new unit test — verified in the Task 14 manual smoke run.)

- [ ] **Step 1: Write `frontend/src/app/login/page.tsx`**

```tsx
"use client";
import { useState } from "react";
import { useRouter } from "next/navigation";
import { api, ApiError } from "@/lib/api";

export default function LoginPage() {
  const router = useRouter();
  const [login, setLogin] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");

  async function onSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError("");
    try {
      await api.login(login, password);
      router.push("/dashboard");
    } catch (err) {
      setError(err instanceof ApiError ? "Неверный логин или пароль" : "Ошибка сети");
    }
  }

  return (
    <div style={{ maxWidth: 360, margin: "80px auto" }}>
      <div className="card">
        <h2>Вход</h2>
        <form onSubmit={onSubmit}>
          <div style={{ margin: "14px 0" }}>
            <div className="label">Логин</div>
            <input className="input" value={login} onChange={(e) => setLogin(e.target.value)} />
          </div>
          <div style={{ margin: "14px 0" }}>
            <div className="label">Пароль</div>
            <input className="input" type="password" value={password}
              onChange={(e) => setPassword(e.target.value)} />
          </div>
          {error && <div className="error">{error}</div>}
          <button className="btn" type="submit" style={{ marginTop: 12, width: "100%" }}>Войти</button>
        </form>
        <p style={{ marginTop: 16 }}>Нет аккаунта? <a href="/register">Регистрация</a></p>
      </div>
    </div>
  );
}
```

- [ ] **Step 2: Write `frontend/src/app/register/page.tsx`**

```tsx
"use client";
import { useState } from "react";
import { useRouter } from "next/navigation";
import { api, ApiError } from "@/lib/api";

export default function RegisterPage() {
  const router = useRouter();
  const [login, setLogin] = useState("");
  const [password, setPassword] = useState("");
  const [accessCode, setAccessCode] = useState("");
  const [error, setError] = useState("");

  async function onSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError("");
    try {
      await api.register(login, password, accessCode);
      router.push("/dashboard");
    } catch (err) {
      if (err instanceof ApiError) {
        if (err.status === 403) setError("Неверный код доступа");
        else if (err.status === 409) setError("Логин уже занят");
        else setError(err.message);
      } else setError("Ошибка сети");
    }
  }

  return (
    <div style={{ maxWidth: 360, margin: "80px auto" }}>
      <div className="card">
        <h2>Регистрация</h2>
        <form onSubmit={onSubmit}>
          <div style={{ margin: "14px 0" }}>
            <div className="label">Логин</div>
            <input className="input" value={login} onChange={(e) => setLogin(e.target.value)} />
          </div>
          <div style={{ margin: "14px 0" }}>
            <div className="label">Пароль</div>
            <input className="input" type="password" value={password}
              onChange={(e) => setPassword(e.target.value)} />
          </div>
          <div style={{ margin: "14px 0" }}>
            <div className="label">Код доступа</div>
            <input className="input" value={accessCode} onChange={(e) => setAccessCode(e.target.value)} />
          </div>
          {error && <div className="error">{error}</div>}
          <button className="btn" type="submit" style={{ marginTop: 12, width: "100%" }}>Зарегистрироваться</button>
        </form>
        <p style={{ marginTop: 16 }}>Уже есть аккаунт? <a href="/login">Вход</a></p>
      </div>
    </div>
  );
}
```

- [ ] **Step 3: Type-check**

Run: `cd frontend && npx tsc --noEmit`
Expected: no errors.

- [ ] **Step 4: Commit**

```bash
git add frontend/src/app/login/page.tsx frontend/src/app/register/page.tsx
git commit -m "feat: add login and register pages"
```

---

### Task 11: Dashboard + prepare pages

**Files:**
- Create: `frontend/src/app/dashboard/page.tsx`
- Create: `frontend/src/app/test/[id]/prepare/page.tsx`

- [ ] **Step 1: Write `frontend/src/app/dashboard/page.tsx`**

```tsx
"use client";
import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { api, ApiError, type Overview } from "@/lib/api";
import type { Level, Mode } from "@/lib/types";

export default function DashboardPage() {
  const router = useRouter();
  const [overview, setOverview] = useState<Overview | null>(null);
  const [level, setLevel] = useState<Level>("base");
  const [mode, setMode] = useState<Mode>("exam");
  const [error, setError] = useState("");

  useEffect(() => {
    api.overview().then(setOverview).catch((err) => {
      if (err instanceof ApiError && err.status === 401) router.push("/login");
    });
  }, [router]);

  async function start() {
    setError("");
    try {
      const s = await api.createSession(level, mode);
      router.push(`/test/${s.id}/prepare`);
    } catch (err) {
      if (err instanceof ApiError && err.status === 429)
        setError("Достигнут дневной лимit тестов. Попробуйте завтра.");
      else setError("Не удалось начать тест");
    }
  }

  return (
    <div style={{ maxWidth: 820, margin: "40px auto", padding: "0 16px" }}>
      <h2>Тренажёр сертификации · Системный аналитик</h2>
      <div className="card" style={{ marginTop: 16 }}>
        <div className="label">Уровень</div>
        <div style={{ display: "flex", gap: 10, margin: "8px 0 16px" }}>
          {(["base", "specialist"] as Level[]).map((l) => (
            <button key={l} className={`btn ${level === l ? "" : "btn-ghost"}`} onClick={() => setLevel(l)}>
              {l === "base" ? "Базовый" : "Специалист"}
            </button>
          ))}
        </div>
        <div className="label">Режим</div>
        <div style={{ display: "flex", gap: 10, margin: "8px 0 16px" }}>
          {(["exam", "adaptive"] as Mode[]).map((m) => (
            <button key={m} className={`btn ${mode === m ? "" : "btn-ghost"}`} onClick={() => setMode(m)}>
              {m === "exam" ? "Экзамен-симуляция" : "Тренировка слабых тем"}
            </button>
          ))}
        </div>
        {error && <div className="error">{error}</div>}
        <button className="btn" onClick={start} style={{ marginTop: 8 }}>Начать</button>
      </div>

      {overview && overview.competency.length > 0 && (
        <div className="card" style={{ marginTop: 16 }}>
          <h3>Профиль по темам</h3>
          {overview.competency.map((c) => (
            <div key={`${c.level}-${c.topic_id}`} style={{ display: "flex", gap: 10, alignItems: "center", margin: "6px 0" }}>
              <span style={{ width: 160 }}>{c.topic_id} ({c.level})</span>
              <div style={{ flex: 1, height: 8, background: "#eef2f8", borderRadius: 4 }}>
                <div style={{ width: `${Math.round(c.accuracy * 100)}%`, height: "100%", background: "#2f6fed", borderRadius: 4 }} />
              </div>
              <span>{Math.round(c.accuracy * 100)}%</span>
            </div>
          ))}
        </div>
      )}

      {overview && overview.sessions.length > 0 && (
        <div className="card" style={{ marginTop: 16 }}>
          <h3>История</h3>
          {overview.sessions.map((s) => (
            <div key={s.id} style={{ display: "flex", justifyContent: "space-between", padding: "8px 0", borderBottom: "1px solid #eef2f8" }}>
              <span>{new Date(s.created_at).toLocaleString("ru")} · {s.level} · {s.mode}</span>
              <span>
                {s.status === "finished"
                  ? `${s.score_percent}% ${s.passed ? "✓ сдан" : "✗ не сдан"}`
                  : s.status}
                {s.status === "finished" && <a href={`/test/${s.id}/results`} style={{ marginLeft: 10 }}>результаты</a>}
              </span>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
```

- [ ] **Step 2: Write `frontend/src/app/test/[id]/prepare/page.tsx`**

```tsx
"use client";
import { useEffect, useState } from "react";
import { useParams, useRouter } from "next/navigation";
import { api } from "@/lib/api";
import type { SessionStatusResponse } from "@/lib/types";

export default function PreparePage() {
  const router = useRouter();
  const { id } = useParams<{ id: string }>();
  const [status, setStatus] = useState<SessionStatusResponse | null>(null);

  useEffect(() => {
    let stop = false;
    async function poll() {
      try {
        const s = await api.sessionStatus(id);
        if (stop) return;
        setStatus(s);
        if (s.status === "ready" || s.generated_count > 0) {
          // first questions exist → user may enter the exam
        }
        if (s.status !== "ready" && s.status !== "failed") {
          setTimeout(poll, 700);
        }
      } catch {
        if (!stop) setTimeout(poll, 1500);
      }
    }
    poll();
    return () => { stop = true; };
  }, [id]);

  if (!status) return <Centered>Загрузка…</Centered>;
  if (status.status === "failed")
    return <Centered>Не удалось подготовить тест. <a href="/dashboard">Назад</a></Centered>;

  const pct = status.total_questions
    ? Math.round((status.generated_count / status.total_questions) * 100) : 0;
  const canEnter = status.generated_count > 0;

  return (
    <Centered>
      <div className="card" style={{ width: 420, textAlign: "center" }}>
        <h3>Готовим ваш тест…</h3>
        <p className="label">Сгенерировано {status.generated_count} / {status.total_questions}</p>
        <div style={{ height: 8, background: "#eef2f8", borderRadius: 4, margin: "12px 0" }}>
          <div style={{ width: `${pct}%`, height: "100%", background: "#2f6fed", borderRadius: 4 }} />
        </div>
        <button className="btn" disabled={!canEnter} onClick={() => router.push(`/test/${id}`)}>
          {status.status === "ready" ? "Начать тест" : "Начать отвечать"}
        </button>
      </div>
    </Centered>
  );
}

function Centered({ children }: { children: React.ReactNode }) {
  return (
    <div style={{ display: "flex", minHeight: "70vh", alignItems: "center", justifyContent: "center" }}>
      {children}
    </div>
  );
}
```

- [ ] **Step 3: Type-check**

Run: `cd frontend && npx tsc --noEmit`
Expected: no errors.

- [ ] **Step 4: Commit**

```bash
git add frontend/src/app/dashboard/page.tsx "frontend/src/app/test/[id]/prepare/page.tsx"
git commit -m "feat: add dashboard and test preparation pages"
```

---

### Task 12: Exam page

**Files:**
- Create: `frontend/src/app/test/[id]/page.tsx`

The exam screen: loads status + questions, polls for more while generating, renders the current question, lets the user answer (submitting each answer), navigates via the nav grid (locked questions blocked), shows the timer (starts when ready), and finishes the test.

- [ ] **Step 1: Write `frontend/src/app/test/[id]/page.tsx`**

```tsx
"use client";
import { useCallback, useEffect, useState } from "react";
import { useParams, useRouter } from "next/navigation";
import { api } from "@/lib/api";
import { QuestionCard } from "@/components/QuestionCard";
import { QuestionNav } from "@/components/QuestionNav";
import { Timer } from "@/components/Timer";
import { toggleSelection, isQuestionReady, answeredCount, type AnswerMap } from "@/lib/examState";
import type { Question, SessionStatusResponse } from "@/lib/types";

export default function ExamPage() {
  const router = useRouter();
  const { id } = useParams<{ id: string }>();
  const [status, setStatus] = useState<SessionStatusResponse | null>(null);
  const [questions, setQuestions] = useState<Question[]>([]);
  const [answers, setAnswers] = useState<AnswerMap>({});
  const [currentSeq, setCurrentSeq] = useState(1);
  const [finishing, setFinishing] = useState(false);

  // poll status + questions while generating
  useEffect(() => {
    let stop = false;
    async function poll() {
      try {
        const s = await api.sessionStatus(id);
        if (stop) return;
        setStatus(s);
        const qs = await api.sessionQuestions(id);
        if (stop) return;
        setQuestions(qs);
        if (s.status !== "ready" && s.status !== "failed" && s.status !== "finished") {
          setTimeout(poll, 800);
        }
      } catch { if (!stop) setTimeout(poll, 1500); }
    }
    poll();
    return () => { stop = true; };
  }, [id]);

  const finish = useCallback(async () => {
    if (finishing) return;
    setFinishing(true);
    try {
      await api.finish(id);
      router.push(`/test/${id}/results`);
    } catch {
      setFinishing(false);
    }
  }, [finishing, id, router]);

  if (!status) return <div style={{ padding: 40 }}>Загрузка…</div>;

  const current = questions.find((q) => q.seq === currentSeq);
  const answeredSeqs = new Set(
    questions.filter((q) => (answers[q.id]?.length ?? 0) > 0).map((q) => q.seq)
  );

  async function onToggle(key: string) {
    if (!current) return;
    const next = toggleSelection(answers[current.id] ?? [], key, current.type);
    setAnswers((prev) => ({ ...prev, [current.id]: next }));
    try { await api.submitAnswer(id, current.id, next); } catch { /* keep local; retried on next change */ }
  }

  return (
    <div style={{ display: "grid", gridTemplateColumns: "250px 1fr", minHeight: "100vh" }}>
      <aside style={{ background: "#fff", borderRight: "1px solid #e4e9f0", padding: 18 }}>
        <div className="label">Вопросы · {status.total_questions}</div>
        <div style={{ margin: "10px 0" }}>
          <QuestionNav
            total={status.total_questions}
            generatedCount={status.generated_count}
            currentSeq={currentSeq}
            answeredSeqs={answeredSeqs}
            onJump={setCurrentSeq}
          />
        </div>
        <div className="label" style={{ marginTop: 12 }}>
          Отвечено: {answeredCount(answers)} / {status.total_questions}
        </div>
      </aside>

      <main style={{ padding: "26px 32px" }}>
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 20 }}>
          <div style={{ fontWeight: 700, color: "#1f3a5f" }}>
            {status.level === "base" ? "Базовый" : "Специалист"} · {status.mode === "exam" ? "Экзамен" : "Тренировка"}
          </div>
          <Timer startedAt={status.timer_started_at} limitSec={status.time_limit_sec} onExpire={finish} />
        </div>

        {current ? (
          <QuestionCard question={current} selected={answers[current.id] ?? []} onToggle={onToggle} />
        ) : isQuestionReady(currentSeq, status.generated_count) ? (
          <div className="card">Загрузка вопроса…</div>
        ) : (
          <div className="card">Вопрос генерируется… дождитесь готовности.</div>
        )}

        <div style={{ display: "flex", justifyContent: "space-between", marginTop: 18 }}>
          <button className="btn btn-ghost" disabled={currentSeq <= 1}
            onClick={() => setCurrentSeq((s) => Math.max(1, s - 1))}>← Назад</button>
          {currentSeq < status.total_questions ? (
            <button className="btn"
              disabled={!isQuestionReady(currentSeq + 1, status.generated_count)}
              onClick={() => setCurrentSeq((s) => s + 1)}>Далее →</button>
          ) : (
            <button className="btn" disabled={finishing} onClick={finish}>Завершить тест</button>
          )}
        </div>
      </main>
    </div>
  );
}
```

- [ ] **Step 2: Type-check**

Run: `cd frontend && npx tsc --noEmit`
Expected: no errors.

- [ ] **Step 3: Commit**

```bash
git add "frontend/src/app/test/[id]/page.tsx"
git commit -m "feat: add exam screen with timer, nav, and locked-question blocking"
```

---

### Task 13: Results page + results helpers

**Files:**
- Create: `frontend/src/lib/results.ts`
- Create: `frontend/src/app/test/[id]/results/page.tsx`
- Test: `frontend/src/lib/__tests__/results.test.ts`

- [ ] **Step 1: Write the failing test** — `frontend/src/lib/__tests__/results.test.ts`

```typescript
import { describe, it, expect } from "vitest";
import { weakTopics } from "@/lib/results";
import type { TopicBreakdown } from "@/lib/types";

describe("weakTopics", () => {
  it("returns topics below the threshold, weakest first", () => {
    const tb: TopicBreakdown[] = [
      { topic_id: "data", answered: 4, correct: 1, accuracy: 0.25 },
      { topic_id: "modeling", answered: 4, correct: 4, accuracy: 1.0 },
      { topic_id: "ux", answered: 2, correct: 1, accuracy: 0.5 },
    ];
    const weak = weakTopics(tb, 0.6);
    expect(weak.map((t) => t.topic_id)).toEqual(["data", "ux"]);
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd frontend && npm run test -- results`
Expected: FAIL (cannot find module)

- [ ] **Step 3: Write `frontend/src/lib/results.ts`**

```typescript
import type { TopicBreakdown } from "@/lib/types";

export function weakTopics(breakdown: TopicBreakdown[], threshold: number): TopicBreakdown[] {
  return breakdown
    .filter((t) => t.accuracy < threshold)
    .sort((a, b) => a.accuracy - b.accuracy);
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd frontend && npm run test -- results`
Expected: PASS (1 passed)

- [ ] **Step 5: Write `frontend/src/app/test/[id]/results/page.tsx`**

```tsx
"use client";
import { useEffect, useState } from "react";
import { useParams } from "next/navigation";
import { api } from "@/lib/api";
import { Artifact } from "@/components/Artifact";
import type { Results } from "@/lib/types";

export default function ResultsPage() {
  const { id } = useParams<{ id: string }>();
  const [results, setResults] = useState<Results | null>(null);

  useEffect(() => { api.results(id).then(setResults).catch(() => {}); }, [id]);

  if (!results) return <div style={{ padding: 40 }}>Загрузка результатов…</div>;

  return (
    <div style={{ maxWidth: 820, margin: "32px auto", padding: "0 16px" }}>
      <div className="card" style={{ textAlign: "center" }}>
        <div className="label">Результат теста</div>
        <div style={{ fontSize: 44, fontWeight: 800, color: results.passed ? "#18b27e" : "#e0556b" }}>
          {results.score_percent}%
        </div>
        <div>{results.passed ? "Тест сдан ✓" : "Тест не сдан ✗"}</div>
        <div className="label" style={{ marginTop: 8 }}>
          Отвечено {results.answered_count} / {results.total_questions}
        </div>
      </div>

      <div className="card" style={{ marginTop: 16 }}>
        <h3>По темам</h3>
        {results.topic_breakdown.map((t) => (
          <div key={t.topic_id} style={{ display: "flex", gap: 10, alignItems: "center", margin: "6px 0" }}>
            <span style={{ width: 160 }}>{t.topic_id}</span>
            <div style={{ flex: 1, height: 8, background: "#eef2f8", borderRadius: 4 }}>
              <div style={{ width: `${Math.round(t.accuracy * 100)}%`, height: "100%", background: "#2f6fed", borderRadius: 4 }} />
            </div>
            <span>{t.correct}/{t.answered}</span>
          </div>
        ))}
      </div>

      <div className="card" style={{ marginTop: 16 }}>
        <h3>Персональная рекомендация</h3>
        <p style={{ whiteSpace: "pre-wrap" }}>{results.recommendation}</p>
      </div>

      <h3 style={{ marginTop: 24 }}>Разбор вопросов</h3>
      {results.questions.map((q) => (
        <div key={q.id} className="card" style={{ marginTop: 12,
          borderLeft: `4px solid ${q.is_correct ? "#18b27e" : "#e0556b"}` }}>
          <div className="label">Вопрос {q.seq} · {q.topic_id} · {q.is_correct ? "верно" : "неверно"}</div>
          <h4 style={{ margin: "8px 0" }}>{q.stem}</h4>
          <Artifact kind={q.artifact_kind} content={q.artifact_content} />
          <div style={{ marginTop: 10 }}>
            {q.options.map((o) => {
              const isCorrect = q.correct_keys.includes(o.key);
              const isSelected = q.selected_keys.includes(o.key);
              const bg = isCorrect ? "#eafaf3" : isSelected ? "#fdeef0" : "#fff";
              const mark = isCorrect ? "✓" : isSelected ? "✗" : "";
              return (
                <div key={o.key} style={{ padding: "8px 12px", borderRadius: 7, background: bg, margin: "4px 0" }}>
                  {mark} {o.text}
                </div>
              );
            })}
          </div>
          <p style={{ marginTop: 10, color: "#5a6878" }}><b>Пояснение:</b> {q.explanation}</p>
        </div>
      ))}
    </div>
  );
}
```

- [ ] **Step 6: Type-check**

Run: `cd frontend && npx tsc --noEmit`
Expected: no errors.

- [ ] **Step 7: Commit**

```bash
git add frontend/src/lib/results.ts frontend/src/lib/__tests__/results.test.ts "frontend/src/app/test/[id]/results/page.tsx"
git commit -m "feat: add results page with per-question review"
```

---

### Task 14: Full verification + manual smoke

**Files:** none

- [ ] **Step 1: Run all frontend tests**

Run: `cd frontend && npm run test -- --run`
Expected: ALL pass (timer 5, examState 5, api 3, Artifact 3, QuestionCard 3, QuestionNav 2, results 1 = ~22). Report count.

- [ ] **Step 2: Type-check + build**

Run: `cd frontend && npx tsc --noEmit && npm run build`
Expected: type-check clean; `next build` succeeds (compiles all pages).

- [ ] **Step 3: Backend full suite still green**

Run: `cd backend && . .venv/bin/activate && pytest -q`
Expected: all pass (94 with the overview endpoint).

- [ ] **Step 4: Manual end-to-end smoke** (requires a real `OPENAI_API_KEY` in `backend/.env`, or skip generation-dependent steps)

Start backend (`uvicorn app.main:app --port 8000`) and frontend (`npm run dev`). In a browser:
  - Register with the access code → lands on dashboard.
  - Start an adaptive base test → prepare screen shows progress → enter exam.
  - Answer questions, navigate (confirm locked cells are unclickable), finish.
  - Results screen shows score, breakdown, recommendation, per-question review with explanations.

Report what worked. If no OPENAI key, note that generation steps are skipped and only auth/dashboard/nav-logic were smoke-tested. (The unit tests already prove the logic; this is a real-environment confidence check.)

- [ ] **Step 5: Confirm success criteria**
  - All frontend unit/component tests pass.
  - `tsc --noEmit` clean; `next build` succeeds.
  - Backend suite green incl. `/me/overview`.
  - Manual smoke (as far as the environment allows) shows the full flow.

---

## Self-Review Notes

Checked against spec section 8 (UI screens) and the product decisions: registration with access code (Task 10), dashboard with level/mode + history + topic profile (Task 11, backed by `/me/overview` in Task 9), preparation with streaming progress (Task 11), exam screen with timer that starts at pool-ready, Mermaid + `<pre>` artifacts, question navigation, and locked-question blocking (Tasks 6–8, 12 — locked rule is pure-tested in Task 4 and enforced in QuestionNav + the Next/finish buttons), and results with score/pass/per-question review + explanation + topic breakdown + recommendation (Task 13). The answer-secrecy boundary is respected: the exam screen reads `/questions` (no answers); only the results screen reads `/results` (with answers). Visual style follows direction A (IBS bluewhite). No placeholders — every component/page/test has complete code. Type consistency: `Question`, `SessionStatusResponse`, `Results`, `AnswerMap`, `toggleSelection`, `isQuestionReady`, `answeredCount`, `formatRemaining`, `remainingSeconds`, `weakTopics`, and the `api.*` method names are consistent across tasks and match the backend contract. One backend addition (`/me/overview`, Task 9) is the only server change, tested in the backend suite. Pure logic (timer, examState, results) is unit-tested; components are RTL-tested; pages are thin compositions verified by tsc + build + manual smoke. Testing pivots from pytest (backend) to Vitest (frontend) — appropriate for the stack.
```
