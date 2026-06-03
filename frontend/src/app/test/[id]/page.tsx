"use client";
import { useCallback, useEffect, useState } from "react";
import { useParams, useRouter } from "next/navigation";
import { api, isUnauthorized } from "@/lib/api";
import { QuestionCard } from "@/components/QuestionCard";
import { QuestionNav } from "@/components/QuestionNav";
import { Timer } from "@/components/Timer";
import { toggleSelection, isQuestionReady, answeredCount, type AnswerMap } from "@/lib/examState";
import type { Question, SessionStatusResponse } from "@/lib/types";

export default function ExamPage() {
  const router = useRouter();
  const { id } = useParams<{ id: string }>();
  const [status, setStatus] = useState<SessionStatusResponse | null>(null);
  const [questions, setQuestions] = useState<Question[]>([]);
  const [answers, setAnswers] = useState<AnswerMap>({});
  const [currentSeq, setCurrentSeq] = useState(1);
  const [finishing, setFinishing] = useState(false);

  useEffect(() => {
    let stop = false;
    async function poll() {
      try {
        const s = await api.sessionStatus(id);
        if (stop) return;
        setStatus(s);
        const qs = await api.sessionQuestions(id);
        if (stop) return;
        setQuestions(qs);
        if (s.status !== "ready" && s.status !== "failed" && s.status !== "finished") {
          setTimeout(poll, 800);
        }
      } catch (err) {
        if (isUnauthorized(err)) { router.push("/login"); return; }
        if (!stop) setTimeout(poll, 1500);
      }
    }
    poll();
    return () => { stop = true; };
  }, [id, router]);

  // Restore previously-submitted answers (for resume).
  useEffect(() => {
    let stop = false;
    api.listAnswers(id).then((prior) => {
      if (stop) return;
      const map: AnswerMap = {};
      for (const a of prior) map[a.question_id] = a.selected_keys;
      setAnswers((prev) => ({ ...map, ...prev })); // local edits win over restored
    }).catch(() => { /* no prior answers / not critical */ });
    return () => { stop = true; };
  }, [id]);

  const finish = useCallback(async () => {
    if (finishing) return;
    setFinishing(true);
    try {
      await api.finish(id);
      router.push(`/test/${id}/results`);
    } catch {
      setFinishing(false);
    }
  }, [finishing, id, router]);

  if (!status) return <div style={{ padding: 40 }}>Загрузка…</div>;

  const current = questions.find((q) => q.seq === currentSeq);
  const answeredSeqs = new Set(
    questions.filter((q) => (answers[q.id]?.length ?? 0) > 0).map((q) => q.seq)
  );

  async function onToggle(key: string) {
    if (!current) return;
    const next = toggleSelection(answers[current.id] ?? [], key, current.type);
    setAnswers((prev) => ({ ...prev, [current.id]: next }));
    try { await api.submitAnswer(id, current.id, next); } catch { /* keep local */ }
  }

  return (
    <div style={{ display: "grid", gridTemplateColumns: "250px 1fr", minHeight: "100vh" }}>
      <aside style={{ background: "#fff", borderRight: "1px solid #e4e9f0", padding: 18 }}>
        <div className="label">Вопросы · {status.total_questions}</div>
        <div style={{ margin: "10px 0" }}>
          <QuestionNav
            total={status.total_questions}
            generatedCount={status.generated_count}
            currentSeq={currentSeq}
            answeredSeqs={answeredSeqs}
            onJump={setCurrentSeq}
          />
        </div>
        <div className="label" style={{ marginTop: 12 }}>
          Отвечено: {answeredCount(answers)} / {status.total_questions}
        </div>
      </aside>

      <main style={{ padding: "26px 32px" }}>
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 20 }}>
          <div style={{ fontWeight: 700, color: "#1f3a5f" }}>
            {status.level === "base" ? "Базовый" : "Специалист"} · {status.mode === "exam" ? "Экзамен" : "Тренировка"}
          </div>
          <Timer startedAt={status.timer_started_at} limitSec={status.time_limit_sec} onExpire={finish} />
        </div>

        {current ? (
          <QuestionCard question={current} selected={answers[current.id] ?? []} onToggle={onToggle} />
        ) : isQuestionReady(currentSeq, status.generated_count) ? (
          <div className="card">Загрузка вопроса…</div>
        ) : (
          <div className="card">Вопрос генерируется… дождитесь готовности.</div>
        )}

        <div style={{ display: "flex", justifyContent: "space-between", marginTop: 18 }}>
          <button className="btn btn-ghost" disabled={currentSeq <= 1}
            onClick={() => setCurrentSeq((s) => Math.max(1, s - 1))}>← Назад</button>
          {currentSeq < status.total_questions ? (
            <button className="btn"
              disabled={!isQuestionReady(currentSeq + 1, status.generated_count)}
              onClick={() => setCurrentSeq((s) => s + 1)}>Далее →</button>
          ) : (
            <button className="btn" disabled={finishing} onClick={finish}>Завершить тест</button>
          )}
        </div>
      </main>
    </div>
  );
}
