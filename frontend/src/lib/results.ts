import type { TopicBreakdown } from "@/lib/types";

export function weakTopics(breakdown: TopicBreakdown[], threshold: number): TopicBreakdown[] {
  return breakdown
    .filter((t) => t.accuracy < threshold)
    .sort((a, b) => a.accuracy - b.accuracy);
}
