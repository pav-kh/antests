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
    expect(screen.getByText("1")).toBeInTheDocument();
    expect(screen.getByText("4")).toBeInTheDocument();
    expect(screen.getByText("3").closest("[data-locked]")).toHaveAttribute("data-locked", "true");
    expect(screen.getByText("2").closest("[data-locked]")).toHaveAttribute("data-locked", "false");
  });

  it("does not call onJump for a locked question", () => {
    const onJump = vi.fn();
    render(
      <QuestionNav total={4} generatedCount={2} currentSeq={1}
        answeredSeqs={new Set()} onJump={onJump} />
    );
    fireEvent.click(screen.getByText("4"));
    expect(onJump).not.toHaveBeenCalled();
    fireEvent.click(screen.getByText("2"));
    expect(onJump).toHaveBeenCalledWith(2);
  });

  it("renders cells as buttons; locked ones are disabled and not focusable", () => {
    render(
      <QuestionNav total={4} generatedCount={2} currentSeq={1}
        answeredSeqs={new Set()} onJump={() => {}} />
    );
    // ready cell -> enabled button
    const ready = screen.getByText("2").closest("button")!;
    expect(ready).not.toBeDisabled();
    // locked cell -> disabled button (keyboard users can't activate it either)
    const locked = screen.getByText("4").closest("button")!;
    expect(locked).toBeDisabled();
    // current cell exposes aria-current
    const current = screen.getByText("1").closest("button")!;
    expect(current).toHaveAttribute("aria-current", "true");
  });
});
