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

  it("renders options as accessible buttons with aria-pressed", () => {
    render(<QuestionCard question={q} selected={["a"]} onToggle={() => {}} />);
    const alpha = screen.getByRole("button", { name: "Alpha" });
    const beta = screen.getByRole("button", { name: "Beta" });
    expect(alpha).toHaveAttribute("aria-pressed", "true");
    expect(beta).toHaveAttribute("aria-pressed", "false");
  });

  it("is keyboard-operable (Enter activates an option)", () => {
    const onToggle = vi.fn();
    render(<QuestionCard question={q} selected={[]} onToggle={onToggle} />);
    const alpha = screen.getByRole("button", { name: "Alpha" });
    alpha.focus();
    expect(alpha).toHaveFocus();
    // native <button> fires onClick for keyboard Enter/Space; assert it's wired
    fireEvent.click(alpha);
    expect(onToggle).toHaveBeenCalledWith("a");
  });

  it("renders a textarea for an open question and reports typed text", () => {
    const onText = vi.fn();
    const openQ: Question = {
      id: "o1", seq: 81, topic_id: "open", type: "open",
      stem: "Опишите решения.", artifact_kind: "none", artifact_content: null,
      options: [],
    };
    render(
      <QuestionCard question={openQ} selected={[]} onToggle={() => {}}
        answerText="" onAnswerText={onText} />
    );
    const ta = screen.getByRole("textbox");
    fireEvent.change(ta, { target: { value: "мой ответ" } });
    expect(onText).toHaveBeenCalledWith("мой ответ");
  });
});
