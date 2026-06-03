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
