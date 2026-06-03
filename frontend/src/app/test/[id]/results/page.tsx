"use client";
import { useEffect, useState } from "react";
import { useParams } from "next/navigation";
import { api } from "@/lib/api";
import { Artifact } from "@/components/Artifact";
import type { Results } from "@/lib/types";

export default function ResultsPage() {
  const { id } = useParams<{ id: string }>();
  const [results, setResults] = useState<Results | null>(null);

  useEffect(() => { api.results(id).then(setResults).catch(() => {}); }, [id]);

  if (!results) return <div style={{ padding: 40 }}>Загрузка результатов…</div>;

  return (
    <div style={{ maxWidth: 820, margin: "32px auto", padding: "0 16px" }}>
      <div className="card" style={{ textAlign: "center" }}>
        <div className="label">Результат теста</div>
        <div style={{ fontSize: 44, fontWeight: 800, color: results.passed ? "#18b27e" : "#e0556b" }}>
          {results.score_percent}%
        </div>
        <div>{results.passed ? "Тест сдан ✓" : "Тест не сдан ✗"}</div>
        <div className="label" style={{ marginTop: 8 }}>
          Отвечено {results.answered_count} / {results.total_questions}
        </div>
      </div>

      <div className="card" style={{ marginTop: 16 }}>
        <h3>По темам</h3>
        {results.topic_breakdown.map((t) => (
          <div key={t.topic_id} style={{ display: "flex", gap: 10, alignItems: "center", margin: "6px 0" }}>
            <span style={{ width: 160 }}>{t.topic_id}</span>
            <div style={{ flex: 1, height: 8, background: "#eef2f8", borderRadius: 4 }}>
              <div style={{ width: `${Math.round(t.accuracy * 100)}%`, height: "100%", background: "#2f6fed", borderRadius: 4 }} />
            </div>
            <span>{t.correct}/{t.answered}</span>
          </div>
        ))}
      </div>

      <div className="card" style={{ marginTop: 16 }}>
        <h3>Персональная рекомендация</h3>
        <p style={{ whiteSpace: "pre-wrap" }}>{results.recommendation}</p>
      </div>

      <h3 style={{ marginTop: 24 }}>Разбор вопросов</h3>
      {results.questions.map((q) => (
        <div key={q.id} className="card" style={{ marginTop: 12,
          borderLeft: `4px solid ${q.is_correct ? "#18b27e" : "#e0556b"}` }}>
          <div className="label">Вопрос {q.seq} · {q.topic_id} · {q.is_correct ? "верно" : "неверно"}</div>
          <h4 style={{ margin: "8px 0" }}>{q.stem}</h4>
          <Artifact kind={q.artifact_kind} content={q.artifact_content} />
          <div style={{ marginTop: 10 }}>
            {q.options.map((o) => {
              const isCorrect = q.correct_keys.includes(o.key);
              const isSelected = q.selected_keys.includes(o.key);
              const bg = isCorrect ? "#eafaf3" : isSelected ? "#fdeef0" : "#fff";
              const mark = isCorrect ? "✓" : isSelected ? "✗" : "";
              return (
                <div key={o.key} style={{ padding: "8px 12px", borderRadius: 7, background: bg, margin: "4px 0" }}>
                  {mark} {o.text}
                </div>
              );
            })}
          </div>
          <p style={{ marginTop: 10, color: "#5a6878" }}><b>Пояснение:</b> {q.explanation}</p>
        </div>
      ))}
    </div>
  );
}
