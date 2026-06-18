"use client";
import { parseOpenStem } from "@/lib/openStem";

function Block({ label, body }: { label: string; body: string }) {
  if (!body) return null;
  return (
    <div style={{ marginTop: 12 }}>
      <div style={{ fontWeight: 700, color: "#1f3a5f", marginBottom: 2 }}>{label}</div>
      <div style={{ whiteSpace: "pre-line" }}>{body}</div>
    </div>
  );
}

export function OpenStem({ stem }: { stem: string }) {
  const p = parseOpenStem(stem);
  if (!p) {
    return <div style={{ whiteSpace: "pre-line" }}>{stem}</div>;
  }
  return (
    <div>
      {p.topicTitle && <h3 style={{ margin: "0 0 4px" }}>{p.topicTitle}</h3>}
      {p.answerHint && (
        <div style={{ fontSize: 12, color: "var(--muted)", marginBottom: 12 }}>
          {p.answerHint}
        </div>
      )}
      {p.case && (
        <div style={{ whiteSpace: "pre-line", marginBottom: 4 }}>{p.case}</div>
      )}
      <Block label="Задание" body={p.task} />
      <Block label="Фокус ответа" body={p.focus} />
      <Block label="Критерии оценки" body={p.criteria} />
    </div>
  );
}
