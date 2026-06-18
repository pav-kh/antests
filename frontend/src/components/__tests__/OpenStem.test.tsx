import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import { OpenStem } from "@/components/OpenStem";

const STEM = [
  "Ответ: до 2500 знаков с пробелами.",
  "Тип: открытый кейс. Системное мышление",
  "",
  "Компания внедряет сервис.",
  "",
  "Задание: Опишите анализ.",
  "Фокус ответа: Декомпозиция.",
  "Критерии оценки: границы; связи.",
].join("\n");

describe("OpenStem", () => {
  it("renders the topic, case and the three labelled blocks", () => {
    render(<OpenStem stem={STEM} />);
    expect(screen.getByText("Системное мышление")).toBeInTheDocument();
    expect(screen.getByText(/Компания внедряет сервис/)).toBeInTheDocument();
    expect(screen.getByText("Задание")).toBeInTheDocument();
    expect(screen.getByText("Фокус ответа")).toBeInTheDocument();
    expect(screen.getByText("Критерии оценки")).toBeInTheDocument();
    expect(screen.getByText("Опишите анализ.")).toBeInTheDocument();
    expect(screen.getByText("Декомпозиция.")).toBeInTheDocument();
    expect(screen.getByText("границы; связи.")).toBeInTheDocument();
    expect(screen.getByText(/2500 знаков/)).toBeInTheDocument();
  });

  it("falls back to raw text when the stem is not structured", () => {
    render(<OpenStem stem="Просто вопрос без меток." />);
    expect(screen.getByText("Просто вопрос без меток.")).toBeInTheDocument();
  });
});
