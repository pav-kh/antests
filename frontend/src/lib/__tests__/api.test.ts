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
