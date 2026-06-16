"use client";
import { useEffect, useId, useState } from "react";
import type { ArtifactKind } from "@/lib/types";

export function Artifact({ kind, content }: { kind: ArtifactKind; content: string | null }) {
  const [svg, setSvg] = useState<string>("");
  const [failed, setFailed] = useState(false);
  // A stable, guaranteed-unique id for the mermaid render target. useId avoids
  // the collisions a content-hash could cause (same content -> same id, or hash
  // clashes). Mermaid requires the id to be a valid CSS selector, so strip the
  // colons React's useId emits.
  const reactId = useId();
  const mermaidId = `m${reactId.replace(/:/g, "")}`;

  useEffect(() => {
    if (kind !== "mermaid" || !content) return;
    let cancelled = false;
    setFailed(false);
    (async () => {
      const mermaid = (await import("mermaid")).default;
      mermaid.initialize({ startOnLoad: false, theme: "neutral" });
      try {
        const { svg } = await mermaid.render(mermaidId, content);
        if (!cancelled) setSvg(svg);
      } catch {
        // Diagram couldn't be rendered (invalid syntax etc.). Mark it failed so
        // we fall back to the raw code instead of an eternal "loading" placeholder.
        if (!cancelled) { setSvg(""); setFailed(true); }
      }
    })();
    return () => { cancelled = true; };
  }, [kind, content, mermaidId]);

  if (kind === "none" || !content) return null;

  // A monospace code block, width-capped so a long line never widens the page.
  const codeBlock = (text: string) => (
    <pre
      style={{
        background: "#0f1b2d", color: "#cde2ff", borderRadius: 8, padding: "14px 16px",
        fontFamily: "ui-monospace, Menlo, monospace", fontSize: 13,
        maxWidth: "100%", overflowX: "auto",
        whiteSpace: "pre-wrap", overflowWrap: "anywhere",
      }}
    >
      {text}
    </pre>
  );

  if (kind === "mermaid") {
    if (svg) {
      const boxStyle = {
        background: "#fff", borderRadius: 8, padding: 12,
        maxWidth: "100%", overflowX: "auto",
      } as const;
      return (
        <div data-testid="mermaid" style={boxStyle}
          dangerouslySetInnerHTML={{ __html: svg }} />
      );
    }
    // Render failed -> show the raw diagram code so the question stays answerable
    // (never leave an eternal "loading" placeholder).
    if (failed) {
      return (
        <div data-testid="mermaid">
          <div className="label" style={{ marginBottom: 6 }}>
            Диаграмма (текстовое представление):
          </div>
          {codeBlock(content)}
        </div>
      );
    }
    return (
      <div data-testid="mermaid"
        style={{ background: "#fff", borderRadius: 8, padding: 12, maxWidth: "100%" }}>
        Отрисовка диаграммы…
      </div>
    );
  }

  return codeBlock(content);
}
