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
    expect(a).toEqual(["b"]);
  });

  it("multi-choice toggles membership", () => {
    let a: string[] = [];
    a = toggleSelection(a, "a", "multi");
    a = toggleSelection(a, "c", "multi");
    expect(a.sort()).toEqual(["a", "c"]);
    a = toggleSelection(a, "a", "multi");
    expect(a).toEqual(["c"]);
  });
});

describe("isQuestionReady", () => {
  it("ready when seq <= generated_count", () => {
    expect(isQuestionReady(5, 5)).toBe(true);
    expect(isQuestionReady(4, 5)).toBe(true);
    expect(isQuestionReady(6, 5)).toBe(false);
  });
});

describe("answeredCount", () => {
  it("counts questions with a non-empty selection", () => {
    const map: AnswerMap = { q1: ["a"], q2: [], q3: ["b", "c"] };
    expect(answeredCount(map)).toBe(2);
  });
});
