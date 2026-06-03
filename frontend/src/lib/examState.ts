import type { QuestionType } from "@/lib/types";

export type AnswerMap = Record<string, string[]>;

export function toggleSelection(
  current: string[],
  key: string,
  type: QuestionType
): string[] {
  if (type === "single") {
    return [key];
  }
  return current.includes(key)
    ? current.filter((k) => k !== key)
    : [...current, key];
}

export function isQuestionReady(seq: number, generatedCount: number): boolean {
  return seq <= generatedCount;
}

export function answeredCount(map: AnswerMap): number {
  return Object.values(map).filter((sel) => sel.length > 0).length;
}
