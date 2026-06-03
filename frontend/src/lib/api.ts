import type {
  Level, Mode, Question, Results, SessionStatus, SessionStatusResponse, User,
} from "@/lib/types";

// Default to same-origin ("") when unset so a production build behind a reverse
// proxy uses relative URLs instead of a hardcoded localhost (which would fail
// for users and be mixed-content-blocked under HTTPS). Local dev sets
// NEXT_PUBLIC_API_BASE=http://localhost:8000 in .env.local.
const BASE = process.env.NEXT_PUBLIC_API_BASE ?? "";

export class ApiError extends Error {
  status: number;
  constructor(status: number, message: string) {
    super(message);
    this.status = status;
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  // Only declare a JSON content type when we actually send a body — bodyless
  // GETs/POSTs shouldn't advertise a request body.
  const baseHeaders: Record<string, string> = init?.body
    ? { "Content-Type": "application/json" }
    : {};
  const res = await fetch(`${BASE}${path}`, {
    ...init,
    credentials: "include",
    headers: { ...baseHeaders, ...(init?.headers ?? {}) },
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
    request<{ id: string; status: SessionStatus; total_questions: number }>("/sessions", {
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
  listAnswers: (id: string) =>
    request<{ question_id: string; selected_keys: string[] }[]>(`/sessions/${id}/answers`),
  finish: (id: string) =>
    request<{ id: string; score_percent: number; passed: boolean; status: SessionStatus }>(
      `/sessions/${id}/finish`, { method: "POST" }
    ),
  results: (id: string) => request<Results>(`/sessions/${id}/results`),
  overview: () => request<Overview>("/me/overview"),
};

/** Returns true if the error is a 401 (caller should redirect to /login). */
export function isUnauthorized(err: unknown): boolean {
  return err instanceof ApiError && err.status === 401;
}

export interface OverviewSession {
  id: string; level: Level; mode: Mode; status: SessionStatus;
  score_percent: number | null; passed: boolean | null; created_at: string;
}
export interface OverviewTopic { topic_id: string; level: Level; accuracy: number; }
export interface Overview {
  sessions: OverviewSession[];
  competency: OverviewTopic[];
}
