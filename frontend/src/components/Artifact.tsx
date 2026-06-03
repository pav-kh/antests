"use client";
import { useEffect, useRef, useState } from "react";
import type { ArtifactKind } from "@/lib/types";

export function Artifact({ kind, content }: { kind: ArtifactKind; content: string | null }) {
  const ref = useRef<HTMLDivElement>(null);
  const [svg, setSvg] = useState<string>("");

  useEffect(() => {
    if (kind !== "mermaid" || !content) return;
    let cancelled = false;
    (async () => {
      const mermaid = (await import("mermaid")).default;
      mermaid.initialize({ startOnLoad: false, theme: "neutral" });
      try {
        const { svg } = await mermaid.render(`m${Math.abs(hash(content))}`, content);
        if (!cancelled) setSvg(svg);
      } catch {
        if (!cancelled) setSvg("");
      }
    })();
    return () => { cancelled = true; };
  }, [kind, content]);

  if (kind === "none" || !content) return null;

  if (kind === "mermaid") {
    return (
      <div
        data-testid="mermaid"
        ref={ref}
        style={{ background: "#fff", borderRadius: 8, padding: 12, overflow: "auto" }}
        dangerouslySetInnerHTML={{ __html: svg || content }}
      />
    );
  }

  return (
    <pre
      style={{
        background: "#0f1b2d", color: "#cde2ff", borderRadius: 8, padding: "14px 16px",
        fontFamily: "ui-monospace, Menlo, monospace", fontSize: 13, overflow: "auto",
      }}
    >
      {content}
    </pre>
  );
}

function hash(s: string): number {
  let h = 0;
  for (let i = 0; i < s.length; i++) h = (h << 5) - h + s.charCodeAt(i);
  return h;
}
