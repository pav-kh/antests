"use client";
import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { api, ApiError, isUnauthorized, type Overview } from "@/lib/api";
import type { Level, Mode } from "@/lib/types";

export default function DashboardPage() {
  const router = useRouter();
  const [overview, setOverview] = useState<Overview | null>(null);
  const [level, setLevel] = useState<Level>("base");
  const [mode, setMode] = useState<Mode>("exam");
  const [error, setError] = useState("");

  useEffect(() => {
    api.overview().then(setOverview).catch((err) => {
      if (isUnauthorized(err)) router.push("/login");
    });
  }, [router]);

  async function logout() {
    try { await api.logout(); } catch { /* ignore */ }
    router.push("/login");
  }

  async function start() {
    setError("");
    try {
      const s = await api.createSession(level, mode);
      router.push(`/test/${s.id}/prepare`);
    } catch (err) {
      if (err instanceof ApiError && err.status === 429)
        setError("Достигнут дневной лимит тестов. Попробуйте завтра.");
      else setError("Не удалось начать тест");
    }
  }

  return (
    <div style={{ maxWidth: 820, margin: "40px auto", padding: "0 16px" }}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
        <h2>Тренажёр сертификации · Системный аналитик</h2>
        <button className="btn btn-ghost" onClick={logout}>Выйти</button>
      </div>
      <div className="card" style={{ marginTop: 16 }}>
        <div className="label">Уровень</div>
        <div style={{ display: "flex", gap: 10, margin: "8px 0 16px" }}>
          {(["base", "specialist"] as Level[]).map((l) => (
            <button key={l} className={`btn ${level === l ? "" : "btn-ghost"}`} onClick={() => setLevel(l)}>
              {l === "base" ? "Базовый" : "Специалист"}
            </button>
          ))}
        </div>
        <div className="label">Режим</div>
        <div style={{ display: "flex", gap: 10, margin: "8px 0 16px" }}>
          {(["exam", "adaptive"] as Mode[]).map((m) => (
            <button key={m} className={`btn ${mode === m ? "" : "btn-ghost"}`} onClick={() => setMode(m)}>
              {m === "exam" ? "Экзамен-симуляция" : "Тренировка слабых тем"}
            </button>
          ))}
        </div>
        {error && <div className="error">{error}</div>}
        <button className="btn" onClick={start} style={{ marginTop: 8 }}>Начать</button>
      </div>

      {overview && overview.competency.length > 0 && (
        <div className="card" style={{ marginTop: 16 }}>
          <h3>Профиль по темам</h3>
          {overview.competency.map((c) => (
            <div key={`${c.level}-${c.topic_id}`} style={{ display: "flex", gap: 10, alignItems: "center", margin: "6px 0" }}>
              <span style={{ width: 160 }}>{c.topic_id} ({c.level})</span>
              <div style={{ flex: 1, height: 8, background: "#eef2f8", borderRadius: 4 }}>
                <div style={{ width: `${Math.round(c.accuracy * 100)}%`, height: "100%", background: "#2f6fed", borderRadius: 4 }} />
              </div>
              <span>{Math.round(c.accuracy * 100)}%</span>
            </div>
          ))}
        </div>
      )}

      {overview && overview.sessions.length > 0 && (
        <div className="card" style={{ marginTop: 16 }}>
          <h3>История</h3>
          {overview.sessions.map((s) => (
            <div key={s.id} style={{ display: "flex", justifyContent: "space-between", padding: "8px 0", borderBottom: "1px solid #eef2f8" }}>
              <span>{new Date(s.created_at).toLocaleString("ru")} · {s.level} · {s.mode}</span>
              <span>
                {s.status === "finished"
                  ? `${s.score_percent}% ${s.passed ? "✓ сдан" : "✗ не сдан"}`
                  : s.status}
                {s.status === "finished" && <a href={`/test/${s.id}/results`} style={{ marginLeft: 10 }}>результаты</a>}
                {(s.status === "ready" || s.status === "in_progress" || s.status === "generating") &&
                  <a href={`/test/${s.id}`} style={{ marginLeft: 10 }}>продолжить</a>}
              </span>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
