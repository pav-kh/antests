import { describe, it, expect, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import { Artifact } from "@/components/Artifact";

vi.mock("mermaid", () => ({
  default: { initialize: vi.fn(), render: vi.fn().mockResolvedValue({ svg: "<svg/>" }) },
}));

describe("Artifact", () => {
  it("renders nothing for kind=none", () => {
    const { container } = render(<Artifact kind="none" content={null} />);
    expect(container.firstChild).toBeNull();
  });

  it("renders code/sql/json/xml in a <pre>", () => {
    render(<Artifact kind="sql" content="SELECT 1" />);
    const pre = screen.getByText("SELECT 1");
    expect(pre.tagName).toBe("PRE");
  });

  it("renders a mermaid container for kind=mermaid", () => {
    render(<Artifact kind="mermaid" content="graph TD; A-->B" />);
    expect(screen.getByTestId("mermaid")).toBeInTheDocument();
  });
});
