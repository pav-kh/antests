"use client";
import { useEffect, useState } from "react";
import { useParams, useRouter } from "next/navigation";
import { api, isUnauthorized } from "@/lib/api";
import { Artifact } from "@/components/Artifact";
import { Markdown } from "@/components/Markdown";
import { OpenStem } from "@/components/OpenStem";
import { weakTopics, correctCount } from "@/lib/results";
import { topicTitle } from "@/lib/topics";
import type { Results } from "@/lib/types";

export default function ResultsPage() {
  const router = useRouter();
  const { id } = useParams<{ id: string }>();
  const [results, setResults] = useState<Results | null>(null);
  const [error, setError] = useState("");

  useEffect(() => {
    api.results(id).then(setResults).catch((err) => {
      if (isUnauthorized(err)) { router.push("/login"); return; }
      setError("Не удалось загрузить результаты.");
    });
  }, [id, router]);

  if (error) return <div style={{ padding: 40 }}>{error} <a href="/dashboard">На главную</a></div>;
  if (!results) return <div style={{ padding: 40 }}>Загрузка результатов…</div>;

  const weak = weakTopics(results.topic_breakdown, 0.6);
  const correct = correctCount(results.topic_breakdown);

  return (
    <div style={{ maxWidth: 820, margin: "32px auto", padding: "0 16px" }}>
      <div style={{ marginBottom: 16 }}>
        <button className="btn btn-ghost" onClick={() => router.push("/dashboard")}>
          ← На главную
        </button>
      </div>
      <div className="card" style={{ textAlign: "center" }}>
        <div className="label">Результат теста</div>
        <div style={{ fontSize: 44, fontWeight: 800, color: results.passed ? "#18b27e" : "#e0556b" }}>
          {results.score_percent}%
        </div>
        <div>{results.passed ? "Тест сдан ✓" : "Тест не сдан ✗"}</div>
        <div style={{ marginTop: 8, fontWeight: 600, color: "#1f3a5f" }}>
          Правильных ответов: {correct} / {results.total_questions}
        </div>
        <div className="label" style={{ marginTop: 4 }}>
          Отвечено {results.answered_count} / {results.total_questions}
        </div>
      </div>

      {weak.length > 0 && (
        <div className="card" style={{ marginTop: 16 }}>
          <h3>Рекомендуем подтянуть</h3>
          <div style={{ display: "flex", flexWrap: "wrap", gap: 8 }}>
            {weak.map((t) => (
              <span key={t.topic_id} style={{
                background: "#fdeef0", color: "#b0556a", borderRadius: 20,
                padding: "4px 12px", fontSize: 13,
              }}>
                {topicTitle(t.topic_id)} · {Math.round(t.accuracy * 100)}%
              </span>
            ))}
          </div>
        </div>
      )}

      <div className="card" style={{ marginTop: 16 }}>
        <h3>По темам</h3>
        {results.topic_breakdown.map((t) => (
          <div key={t.topic_id} style={{ display: "flex", gap: 10, alignItems: "center", margin: "6px 0" }}>
            <span style={{ width: 160 }}>{topicTitle(t.topic_id)}</span>
            <div style={{ flex: 1, height: 8, background: "#eef2f8", borderRadius: 4 }}>
              <div style={{ width: `${Math.round(t.accuracy * 100)}%`, height: "100%", background: "#2f6fed", borderRadius: 4 }} />
            </div>
            <span>{t.correct}/{t.answered}</span>
          </div>
        ))}
      </div>

      <div className="card" style={{ marginTop: 16 }}>
        <h3>Персональная рекомендация</h3>
        <Markdown text={results.recommendation} />
      </div>

      <h3 style={{ marginTop: 24 }}>Разбор вопросов</h3>
      {results.questions.map((q) => (
        <div key={q.id} className="card" style={{ marginTop: 12,
          borderLeft: `4px solid ${q.is_correct ? "#18b27e" : "#e0556b"}` }}>
          <div className="label">Вопрос {q.seq} · {topicTitle(q.topic_id)} · {q.is_correct ? "верно" : "неверно"}</div>
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

      {results.open_questions.length > 0 && (
        <>
          <h3 style={{ marginTop: 24 }}>Открытые вопросы</h3>
          {results.open_questions.map((o) => (
            <div key={o.id} className="card" style={{ marginTop: 12, borderLeft: "4px solid #2f6fed" }}>
              <div className="label">Открытый вопрос {o.seq}</div>
              <div style={{ margin: "8px 0" }}><OpenStem stem={o.stem} /></div>
              <div className="label" style={{ marginTop: 8 }}>Ваш ответ:</div>
              <p style={{ whiteSpace: "pre-wrap", marginTop: 4 }}>
                {o.answer_text || "— (ответ не дан)"}
              </p>
              <div className="label" style={{ marginTop: 12 }}>Обратная связь:</div>
              <p style={{ whiteSpace: "pre-wrap", marginTop: 4, color: "#1f3a5f" }}>{o.feedback}</p>
              <p style={{ marginTop: 10, color: "#5a6878" }}><b>Разбор:</b> {o.explanation}</p>
            </div>
          ))}
        </>
      )}
    </div>
  );
}
