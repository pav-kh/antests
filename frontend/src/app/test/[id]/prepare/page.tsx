"use client";
import { useEffect, useState } from "react";
import { useParams, useRouter } from "next/navigation";
import { api } from "@/lib/api";
import type { SessionStatusResponse } from "@/lib/types";

export default function PreparePage() {
  const router = useRouter();
  const { id } = useParams<{ id: string }>();
  const [status, setStatus] = useState<SessionStatusResponse | null>(null);

  useEffect(() => {
    let stop = false;
    async function poll() {
      try {
        const s = await api.sessionStatus(id);
        if (stop) return;
        setStatus(s);
        if (s.status !== "ready" && s.status !== "failed") {
          setTimeout(poll, 700);
        }
      } catch {
        if (!stop) setTimeout(poll, 1500);
      }
    }
    poll();
    return () => { stop = true; };
  }, [id]);

  if (!status) return <Centered>Загрузка…</Centered>;
  if (status.status === "failed")
    return <Centered>Не удалось подготовить тест. <a href="/dashboard">Назад</a></Centered>;

  const pct = status.total_questions
    ? Math.round((status.generated_count / status.total_questions) * 100) : 0;
  const canEnter = status.generated_count > 0;

  return (
    <Centered>
      <div className="card" style={{ width: 420, textAlign: "center" }}>
        <h3>Готовим ваш тест…</h3>
        <p className="label">Сгенерировано {status.generated_count} / {status.total_questions}</p>
        <div style={{ height: 8, background: "#eef2f8", borderRadius: 4, margin: "12px 0" }}>
          <div style={{ width: `${pct}%`, height: "100%", background: "#2f6fed", borderRadius: 4 }} />
        </div>
        <button className="btn" disabled={!canEnter} onClick={() => router.push(`/test/${id}`)}>
          {status.status === "ready" ? "Начать тест" : "Начать отвечать"}
        </button>
      </div>
    </Centered>
  );
}

function Centered({ children }: { children: React.ReactNode }) {
  return (
    <div style={{ display: "flex", minHeight: "70vh", alignItems: "center", justifyContent: "center" }}>
      {children}
    </div>
  );
}
