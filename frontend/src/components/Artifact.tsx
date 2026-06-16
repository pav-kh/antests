"use client";
import { useEffect, useId, useState } from "react";
import type { ArtifactKind } from "@/lib/types";

export function Artifact({ kind, content }: { kind: ArtifactKind; content: string | null }) {
  const [svg, setSvg] = useState<string>("");
  // A stable, guaranteed-unique id for the mermaid render target. useId avoids
  // the collisions a content-hash could cause (same content -> same id, or hash
  // clashes). Mermaid requires the id to be a valid CSS selector, so strip the
  // colons React's useId emits.
  const reactId = useId();
  const mermaidId = `m${reactId.replace(/:/g, "")}`;

  useEffect(() => {
    if (kind !== "mermaid" || !content) return;
    let cancelled = false;
    (async () => {
      const mermaid = (await import("mermaid")).default;
      mermaid.initialize({ startOnLoad: false, theme: "neutral" });
      try {
        const { svg } = await mermaid.render(mermaidId, content);
        if (!cancelled) setSvg(svg);
      } catch {
        if (!cancelled) setSvg("");
      }
    })();
    return () => { cancelled = true; };
  }, [kind, content, mermaidId]);

  if (kind === "none" || !content) return null;

  if (kind === "mermaid") {
    const boxStyle = {
      background: "#fff", borderRadius: 8, padding: 12,
      // Cap to the container and scroll inside the box rather than widening the
      // page if the diagram is large.
      maxWidth: "100%", overflowX: "auto",
    } as const;
    return svg
      ? <div data-testid="mermaid" style={boxStyle} dangerouslySetInnerHTML={{ __html: svg }} />
      : <div data-testid="mermaid" style={boxStyle}>Отрисовка диаграммы…</div>;
  }

  return (
    <pre
      style={{
        background: "#0f1b2d", color: "#cde2ff", borderRadius: 8, padding: "14px 16px",
        fontFamily: "ui-monospace, Menlo, monospace", fontSize: 13,
        // A long single-line artifact (e.g. minified JSON) must never push the
        // page wider: cap width to the container, wrap long tokens, and keep any
        // remaining overflow as a scrollbar INSIDE this block.
        maxWidth: "100%", overflowX: "auto",
        whiteSpace: "pre-wrap", overflowWrap: "anywhere",
      }}
    >
      {content}
    </pre>
  );
}
