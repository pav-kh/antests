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
    const limit = 180 * 60;
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
    expect(isExpired(null, 10800, past)).toBe(false);
  });

  it("falls back to the full limit (not expired) for a malformed start string", () => {
    // A malformed timestamp must NOT instantly expire the exam; degrade to the
    // full time limit instead of "expired".
    const now = new Date("2026-06-03T10:30:00Z").getTime();
    expect(remainingSeconds("not-a-date", 10800, now)).toBe(10800);
    expect(isExpired("not-a-date", 10800, now)).toBe(false);
  });
});
