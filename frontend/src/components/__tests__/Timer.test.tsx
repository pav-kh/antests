import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { render, screen, act } from "@testing-library/react";
import { Timer } from "@/components/Timer";

describe("Timer", () => {
  beforeEach(() => {
    vi.useFakeTimers();
    vi.setSystemTime(new Date("2026-06-03T12:00:00Z"));
  });
  afterEach(() => vi.useRealTimers());

  it("shows the not-started message when startedAt is null", () => {
    render(<Timer startedAt={null} limitSec={100} onExpire={() => {}} />);
    expect(screen.getByText(/Таймер запустится/)).toBeInTheDocument();
  });

  it("does not call onExpire during render while time remains", () => {
    const onExpire = vi.fn();
    const future = new Date(Date.now()).toISOString();
    render(<Timer startedAt={future} limitSec={3600} onExpire={onExpire} />);
    expect(onExpire).not.toHaveBeenCalled();
  });

  it("calls onExpire once when time runs out", () => {
    const onExpire = vi.fn();
    // started 2 hours ago, limit 1 hour -> already expired
    const past = new Date(Date.now() - 2 * 3600 * 1000).toISOString();
    render(<Timer startedAt={past} limitSec={3600} onExpire={onExpire} />);
    // effect runs after mount
    expect(onExpire).toHaveBeenCalledTimes(1);
    // advance a few ticks; must not call again
    act(() => {
      vi.advanceTimersByTime(3000);
    });
    expect(onExpire).toHaveBeenCalledTimes(1);
  });
});
