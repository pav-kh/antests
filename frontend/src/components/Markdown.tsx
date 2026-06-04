"use client";
import { Fragment } from "react";

// Minimal, safe markdown renderer for the recommendation text. Supports:
// ## / ### headings, **bold**, --- rules, "- " bullet lists, blank-line
// paragraphs. No raw HTML is injected (no dangerouslySetInnerHTML), so it is
// XSS-safe by construction.
function renderInline(text: string, keyPrefix: string) {
  // split on **bold**
  const parts = text.split(/(\*\*[^*]+\*\*)/g);
  return parts.map((p, i) => {
    if (p.startsWith("**") && p.endsWith("**")) {
      return <strong key={`${keyPrefix}-${i}`}>{p.slice(2, -2)}</strong>;
    }
    return <Fragment key={`${keyPrefix}-${i}`}>{p}</Fragment>;
  });
}

export function Markdown({ text }: { text: string }) {
  const lines = (text ?? "").split("\n");
  const blocks: React.ReactNode[] = [];
  let list: string[] = [];
  let para: string[] = [];

  const flushList = (k: string) => {
    if (list.length) {
      blocks.push(
        <ul key={k} style={{ margin: "6px 0 12px", paddingLeft: 20 }}>
          {list.map((li, i) => <li key={i}>{renderInline(li, `${k}-${i}`)}</li>)}
        </ul>
      );
      list = [];
    }
  };
  const flushPara = (k: string) => {
    if (para.length) {
      blocks.push(<p key={k} style={{ margin: "8px 0" }}>{renderInline(para.join(" "), k)}</p>);
      para = [];
    }
  };

  lines.forEach((raw, idx) => {
    const line = raw.trimEnd();
    const k = `b${idx}`;
    if (line.startsWith("### ")) {
      flushList(k); flushPara(k);
      blocks.push(<h4 key={k} style={{ margin: "14px 0 6px" }}>{renderInline(line.slice(4), k)}</h4>);
    } else if (line.startsWith("## ")) {
      flushList(k); flushPara(k);
      blocks.push(<h3 key={k} style={{ margin: "16px 0 8px" }}>{renderInline(line.slice(3), k)}</h3>);
    } else if (line.trim() === "---") {
      flushList(k); flushPara(k);
      blocks.push(<hr key={k} style={{ border: "none", borderTop: "1px solid #e6ebf2", margin: "12px 0" }} />);
    } else if (line.startsWith("- ")) {
      flushPara(k);
      list.push(line.slice(2));
    } else if (line.trim() === "") {
      flushList(k); flushPara(k);
    } else {
      flushList(k);
      para.push(line.trim());
    }
  });
  flushList("end"); flushPara("end");
  return <div>{blocks}</div>;
}
