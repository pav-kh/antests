"use client";
import type { Question } from "@/lib/types";
import { Artifact } from "@/components/Artifact";

export function QuestionCard({
  question, selected, onToggle,
}: {
  question: Question;
  selected: string[];
  onToggle: (key: string) => void;
}) {
  return (
    <div className="card">
      <div className="label">
        Вопрос {question.seq} · {question.topic_id} · {question.type === "single" ? "один ответ" : "несколько"}
      </div>
      <h3 style={{ margin: "8px 0 16px" }}>{question.stem}</h3>
      <Artifact kind={question.artifact_kind} content={question.artifact_content} />
      <div style={{ marginTop: 16 }}>
        {question.options.map((o) => {
          const isSel = selected.includes(o.key);
          return (
            <div
              key={o.key}
              data-selected={isSel}
              onClick={() => onToggle(o.key)}
              style={{
                display: "flex", gap: 12, alignItems: "center",
                border: `1px solid ${isSel ? "#2f6fed" : "#e3e9f1"}`,
                background: isSel ? "#f3f7ff" : "#fff",
                borderRadius: 9, padding: "13px 15px", marginBottom: 10, cursor: "pointer",
              }}
            >
              <span style={{
                width: 22, height: 22, borderRadius: question.type === "single" ? "50%" : 6,
                border: `2px solid ${isSel ? "#2f6fed" : "#c0cad8"}`,
                background: isSel ? "#2f6fed" : "#fff", flex: "none",
              }} />
              <span>{o.text}</span>
            </div>
          );
        })}
      </div>
    </div>
  );
}
