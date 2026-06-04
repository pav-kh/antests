import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import { Markdown } from "@/components/Markdown";
describe("Markdown", () => {
  it("renders headings, bold, and lists without raw markdown chars", () => {
    render(<Markdown text={"## Заголовок\n\nТекст с **жирным**.\n\n- пункт один\n- пункт два"} />);
    expect(screen.getByRole("heading", { level: 3, name: "Заголовок" })).toBeInTheDocument();
    expect(screen.getByText("жирным").tagName).toBe("STRONG");
    expect(screen.getAllByRole("listitem")).toHaveLength(2);
    // the raw "##" and "**" must NOT appear as visible text
    expect(screen.queryByText(/##/)).toBeNull();
  });
});
