import { describe, it, expect } from "vitest";
import { weakTopics, correctCount } from "@/lib/results";
import type { TopicBreakdown } from "@/lib/types";

describe("weakTopics", () => {
  it("returns topics below the threshold, weakest first", () => {
    const tb: TopicBreakdown[] = [
      { topic_id: "data", answered: 4, correct: 1, accuracy: 0.25 },
      { topic_id: "modeling", answered: 4, correct: 4, accuracy: 1.0 },
      { topic_id: "ux", answered: 2, correct: 1, accuracy: 0.5 },
    ];
    const weak = weakTopics(tb, 0.6);
    expect(weak.map((t) => t.topic_id)).toEqual(["data", "ux"]);
  });
});

describe("correctCount", () => {
  it("sums correct answers across all topics", () => {
    const tb: TopicBreakdown[] = [
      { topic_id: "data", answered: 4, correct: 1, accuracy: 0.25 },
      { topic_id: "modeling", answered: 4, correct: 4, accuracy: 1.0 },
      { topic_id: "ux", answered: 2, correct: 1, accuracy: 0.5 },
    ];
    expect(correctCount(tb)).toBe(6);
  });

  it("returns 0 for an empty breakdown", () => {
    expect(correctCount([])).toBe(0);
  });
});
