import type { Question, QuestionType } from "@/lib/types";

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

/**
 * Count answered questions across BOTH closed selections and open text answers.
 * A question counts as answered if it has a non-empty closed selection OR a
 * non-empty (trimmed) open-text answer. Use this for the "Отвечено N / total"
 * progress so open questions are included, matching the navigation grid.
 */
export function countAnswered(
  questions: Question[],
  answers: AnswerMap,
  openText: Record<string, string>
): number {
  return questions.filter(
    (q) =>
      (answers[q.id]?.length ?? 0) > 0 ||
      (openText[q.id]?.trim().length ?? 0) > 0
  ).length;
}
