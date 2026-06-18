import type { TopicBreakdown } from "@/lib/types";

export function weakTopics(breakdown: TopicBreakdown[], threshold: number): TopicBreakdown[] {
  return breakdown
    .filter((t) => t.accuracy < threshold)
    .sort((a, b) => a.accuracy - b.accuracy);
}

/** Total correct closed answers across all topics (sum of per-topic `correct`). */
export function correctCount(breakdown: TopicBreakdown[]): number {
  return breakdown.reduce((sum, t) => sum + t.correct, 0);
}
