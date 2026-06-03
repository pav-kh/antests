import { describe, it, expect, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import { Artifact } from "@/components/Artifact";

vi.mock("mermaid", () => ({
  default: {
    initialize: vi.fn(),
    render: vi.fn().mockResolvedValue({ svg: "<svg data-testid='diagram'></svg>" }),
  },
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

  it("renders mermaid svg after render resolves", async () => {
    render(<Artifact kind="mermaid" content="graph TD; A-->B" />);
    const el = await screen.findByTestId("mermaid");
    // the injected svg appears once mermaid.render resolves
    await vi.waitFor(() => {
      expect(el.querySelector("svg")).toBeInTheDocument();
    });
  });

  it("does not inject raw content as HTML before svg is ready", () => {
    // synchronous render: svg state is still "" -> placeholder, NOT raw content
    render(<Artifact kind="mermaid" content="<img src=x onerror=alert(1)>" />);
    const el = screen.getByTestId("mermaid");
    // must NOT contain an injected img from the raw content
    expect(el.querySelector("img")).toBeNull();
  });
});
