import { describe, it, expect } from "vitest";
import { topicTitle } from "@/lib/topics";
describe("topicTitle", () => {
  it("maps known keys to Russian", () => {
    expect(topicTitle("data")).toBe("Хранение и обработка данных");
    expect(topicTitle("ux")).toBe("Проектирование пользовательских интерфейсов");
  });
  it("falls back to the key for unknown topics", () => {
    expect(topicTitle("nope")).toBe("nope");
  });
});
