export interface ParsedOpenStem {
  topicTitle: string;
  answerHint: string;
  case: string;
  task: string;
  focus: string;
  criteria: string;
}

const ANSWER = "Ответ:";
const TYPE = "Тип: открытый кейс.";
const TASK = "Задание:";
const FOCUS = "Фокус ответа:";
const CRITERIA = "Критерии оценки:";

/**
 * Split an assembled open-question stem (from the backend's build_open_stem)
 * into its sections. Returns null if the expected anchors are missing, so the
 * caller can fall back to rendering the raw stem.
 *
 * Anchors appear in a fixed order: Ответ → Тип → case → Задание → Фокус → Критерии.
 * Each section runs from the FIRST occurrence of its anchor to the start of the
 * next anchor. (Known limitation: a coincidental label word inside the case
 * could shift a section boundary — it never breaks the null/order guards, only
 * which text lands in a section. build_open_stem never emits such input.)
 */
export function parseOpenStem(stem: string): ParsedOpenStem | null {
  const iType = stem.indexOf(TYPE);
  const iTask = stem.indexOf(TASK);
  const iFocus = stem.indexOf(FOCUS);
  const iCriteria = stem.indexOf(CRITERIA);
  if (iType < 0 || iTask < 0 || iFocus < 0 || iCriteria < 0) return null;
  if (!(iType < iTask && iTask < iFocus && iFocus < iCriteria)) return null;

  const iAnswer = stem.indexOf(ANSWER);
  const answerHint =
    iAnswer >= 0 ? stem.slice(iAnswer + ANSWER.length, iType).trim() : "";
  const typeLineEnd = stem.indexOf("\n", iType);
  const topicTitle = stem
    .slice(iType + TYPE.length, typeLineEnd < 0 ? undefined : typeLineEnd)
    .trim();
  const caseText = stem.slice(typeLineEnd < 0 ? iType : typeLineEnd, iTask).trim();
  const task = stem.slice(iTask + TASK.length, iFocus).trim();
  const focus = stem.slice(iFocus + FOCUS.length, iCriteria).trim();
  const criteria = stem.slice(iCriteria + CRITERIA.length).trim();

  return { topicTitle, answerHint, case: caseText, task, focus, criteria };
}
