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
  const [openText, setOpenText] = useState<Record<string, string>>({});
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

  // Start the official timer the moment the user opens the exam screen
  // (idempotent server-side: first entry wins, re-entry does not reset).
  useEffect(() => {
    api.startTimer(id)
      .then((r) => {
        setStatus((prev) => prev ? { ...prev, timer_started_at: r.timer_started_at } : prev);
      })
      .catch(() => { /* non-fatal; status poll will still carry timer_started_at */ });
  }, [id]);

  // Restore previously-submitted answers (for resume).
  useEffect(() => {
    let stop = false;
    api.listAnswers(id).then((prior) => {
      if (stop) return;
      const map: AnswerMap = {};
      const omap: Record<string, string> = {};
      for (const a of prior) {
        if (a.selected_keys?.length) map[a.question_id] = a.selected_keys;
        if (a.answer_text) omap[a.question_id] = a.answer_text;
      }
      setAnswers((prev) => ({ ...map, ...prev })); // local edits win over restored
      setOpenText((prev) => ({ ...omap, ...prev }));
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
    questions
      .filter((q) =>
        (answers[q.id]?.length ?? 0) > 0 || (openText[q.id]?.trim().length ?? 0) > 0)
      .map((q) => q.seq)
  );

  async function onToggle(key: string) {
    if (!current) return;
    const next = toggleSelection(answers[current.id] ?? [], key, current.type);
    setAnswers((prev) => ({ ...prev, [current.id]: next }));
    try { await api.submitAnswer(id, current.id, { selected_keys: next }); } catch { /* keep local */ }
  }

  if (finishing) {
    return (
      <div style={{ display: "flex", minHeight: "100vh", alignItems: "center", justifyContent: "center", flexDirection: "column", gap: 16 }}>
        <div style={{ width: 40, height: 40, border: "4px solid #e6ebf2", borderTopColor: "#2f6fed", borderRadius: "50%", animation: "spin 0.8s linear infinite" }} />
        <div className="label">Проверяем ответы и готовим результаты…</div>
        <style>{`@keyframes spin { to { transform: rotate(360deg); } }`}</style>
      </div>
    );
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

      {/* minWidth:0 lets this grid track shrink below its content width so a
          wide artifact is clipped/scrolled inside, not pushed onto the page. */}
      <main style={{ padding: "26px 32px", minWidth: 0 }}>
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 20 }}>
          <div style={{ fontWeight: 700, color: "#1f3a5f" }}>
            {status.level === "base" ? "Базовый" : "Специалист"} · {status.mode === "exam" ? "Экзамен" : "Тренировка"}
          </div>
          <Timer startedAt={status.timer_started_at} limitSec={status.time_limit_sec} onExpire={finish} />
        </div>

        {current ? (
          <QuestionCard
            question={current}
            selected={answers[current.id] ?? []}
            answerText={openText[current.id] ?? ""}
            onToggle={onToggle}
            onAnswerText={(text) => {
              setOpenText((prev) => ({ ...prev, [current.id]: text }));
              api.submitAnswer(id, current.id, { answer_text: text }).catch(() => {});
            }}
          />
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
