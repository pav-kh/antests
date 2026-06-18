import { describe, it, expect } from "vitest";
import {
  toggleSelection,
  isQuestionReady,
  answeredCount,
  countAnswered,
  type AnswerMap,
} from "@/lib/examState";
import type { Question, QuestionType } from "@/lib/types";

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

describe("countAnswered", () => {
  const q = (id: string, seq: number, type: QuestionType): Question => ({
    id, seq, type, topic_id: "t", stem: "s",
    artifact_kind: "none", artifact_content: null, options: [],
  });

  it("counts BOTH closed selections and non-empty open answers", () => {
    const questions: Question[] = [
      q("c1", 1, "single"),
      q("c2", 2, "multi"),
      q("o1", 41, "open"),
      q("o2", 42, "open"),
    ];
    const answers: AnswerMap = { c1: ["a"] };          // 1 closed answered
    const openText: Record<string, string> = {
      o1: "развёрнутый ответ",                          // open answered
      o2: "   ",                                        // whitespace-only → NOT answered
    };
    // c1 (closed) + o1 (open) = 2; c2 unanswered, o2 blank
    expect(countAnswered(questions, answers, openText)).toBe(2);
  });

  it("returns 0 when nothing is answered", () => {
    const questions: Question[] = [q("c1", 1, "single"), q("o1", 41, "open")];
    expect(countAnswered(questions, {}, {})).toBe(0);
  });

  it("counts a question once even if it had a selection that was cleared", () => {
    const questions: Question[] = [q("c1", 1, "multi")];
    expect(countAnswered(questions, { c1: [] }, {})).toBe(0);
  });
});
