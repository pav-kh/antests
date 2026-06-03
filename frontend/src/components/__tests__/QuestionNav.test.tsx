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
});
