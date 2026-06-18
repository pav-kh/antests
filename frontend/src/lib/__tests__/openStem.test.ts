import { describe, it, expect } from "vitest";
import { parseOpenStem } from "@/lib/openStem";

const STEM = [
  "Ответ: до 2500 знаков с пробелами; достаточно тезисного, структурированного ответа.",
  "Тип: открытый кейс. Системное мышление",
  "",
  "Компания внедряет сервис. После запуска часть возвратов зависает.",
  "",
  "Задание: Опишите анализ: 1) границы; 2) подпроблемы.",
  "Фокус ответа: Сфокусируйтесь на декомпозиции.",
  "Критерии оценки: границы системы; декомпозиция; цепочки причин.",
].join("\n");

describe("parseOpenStem", () => {
  it("splits the assembled stem into sections", () => {
    const p = parseOpenStem(STEM);
    expect(p).not.toBeNull();
    expect(p!.topicTitle).toBe("Системное мышление");
    expect(p!.answerHint).toContain("2500");
    expect(p!.case).toContain("Компания внедряет сервис");
    expect(p!.case).not.toContain("Задание:");
    expect(p!.task).toBe("Опишите анализ: 1) границы; 2) подпроблемы.");
    expect(p!.focus).toBe("Сфокусируйтесь на декомпозиции.");
    expect(p!.criteria).toBe("границы системы; декомпозиция; цепочки причин.");
  });

  it("returns null for a stem without the expected anchors", () => {
    expect(parseOpenStem("Просто текст без меток.")).toBeNull();
    expect(parseOpenStem("")).toBeNull();
  });

  it("tolerates a multi-line case block", () => {
    const stem = [
      "Ответ: до 2500 знаков.",
      "Тип: открытый кейс. Описание интеграции",
      "",
      "Первая строка кейса.",
      "Вторая строка кейса.",
      "",
      "Задание: Опишите интеграцию.",
      "Фокус ответа: Не пишите код.",
      "Критерии оценки: полнота; риски.",
    ].join("\n");
    const p = parseOpenStem(stem)!;
    expect(p.case).toContain("Первая строка");
    expect(p.case).toContain("Вторая строка");
    expect(p.task).toBe("Опишите интеграцию.");
  });

  it("parses with an empty answerHint when no 'Ответ:' line is present", () => {
    const stem = [
      "Тип: открытый кейс. Описание интеграции",
      "",
      "Кейс про интеграцию.",
      "",
      "Задание: Опишите интеграцию.",
      "Фокус ответа: Не пишите код.",
      "Критерии оценки: полнота; риски.",
    ].join("\n");
    const p = parseOpenStem(stem);
    expect(p).not.toBeNull();
    expect(p!.answerHint).toBe("");
    expect(p!.topicTitle).toBe("Описание интеграции");
    expect(p!.case).toContain("Кейс про интеграцию");
  });
});
