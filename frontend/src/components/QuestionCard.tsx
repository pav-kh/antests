"use client";
import type { Question } from "@/lib/types";
import { Artifact } from "@/components/Artifact";

export function QuestionCard({
  question, selected, onToggle, answerText = "", onAnswerText,
}: {
  question: Question;
  selected: string[];
  onToggle: (key: string) => void;
  answerText?: string;
  onAnswerText?: (text: string) => void;
}) {
  return (
    <div className="card">
      <div className="label">
        Вопрос {question.seq} · {question.topic_id} · {question.type === "single" ? "один ответ" : question.type === "multi" ? "несколько" : "развёрнутый ответ"}
      </div>
      <h3 style={{ margin: "8px 0 16px" }}>{question.stem}</h3>
      <Artifact kind={question.artifact_kind} content={question.artifact_content} />
      {question.type === "open" ? (
        <textarea
          value={answerText}
          onChange={(e) => onAnswerText?.(e.target.value)}
          placeholder="Введите развёрнутый ответ…"
          style={{
            width: "100%", minHeight: 160, marginTop: 12, padding: "12px 14px",
            border: "1px solid #e3e9f1", borderRadius: 9, font: "inherit",
            resize: "vertical",
          }}
        />
      ) : (
        <div role="group" aria-label="Варианты ответа" style={{ marginTop: 16 }}>
          {question.options.map((o) => {
            const isSel = selected.includes(o.key);
            return (
              <button
                key={o.key}
                type="button"
                data-selected={isSel}
                aria-pressed={isSel}
                onClick={() => onToggle(o.key)}
                style={{
                  display: "flex", gap: 12, alignItems: "center", width: "100%",
                  textAlign: "left", font: "inherit", color: "inherit",
                  border: `1px solid ${isSel ? "#2f6fed" : "#e3e9f1"}`,
                  background: isSel ? "#f3f7ff" : "#fff",
                  borderRadius: 9, padding: "13px 15px", marginBottom: 10, cursor: "pointer",
                }}
              >
                <span aria-hidden="true" style={{
                  width: 22, height: 22, borderRadius: question.type === "single" ? "50%" : 6,
                  border: `2px solid ${isSel ? "#2f6fed" : "#c0cad8"}`,
                  background: isSel ? "#2f6fed" : "#fff", flex: "none",
                }} />
                <span>{o.text}</span>
              </button>
            );
          })}
        </div>
      )}
    </div>
  );
}
