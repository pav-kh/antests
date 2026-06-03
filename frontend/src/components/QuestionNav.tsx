"use client";
import { isQuestionReady } from "@/lib/examState";

export function QuestionNav({
  total, generatedCount, currentSeq, answeredSeqs, onJump,
}: {
  total: number;
  generatedCount: number;
  currentSeq: number;
  answeredSeqs: Set<number>;
  onJump: (seq: number) => void;
}) {
  const cells = Array.from({ length: total }, (_, i) => i + 1);
  return (
    <div role="group" aria-label="Навигация по вопросам"
      style={{ display: "grid", gridTemplateColumns: "repeat(6, 1fr)", gap: 6 }}>
      {cells.map((seq) => {
        const ready = isQuestionReady(seq, generatedCount);
        const locked = !ready;
        const answered = answeredSeqs.has(seq);
        const current = seq === currentSeq;
        const bg = current ? "#fff" : answered ? "#2f6fed" : locked ? "#f0d7d7" : "#eef2f8";
        const color = current ? "#2f6fed" : answered ? "#fff" : locked ? "#b06a6a" : "#5a6878";
        const label =
          `Вопрос ${seq}` +
          (locked ? ", ещё не готов" : answered ? ", отвечен" : "") +
          (current ? ", текущий" : "");
        return (
          <button
            key={seq}
            type="button"
            data-locked={locked}
            disabled={locked}
            aria-label={label}
            aria-current={current ? "true" : undefined}
            onClick={() => { if (ready) onJump(seq); }}
            style={{
              aspectRatio: "1", display: "flex", alignItems: "center", justifyContent: "center",
              fontSize: 12, borderRadius: 6, background: bg, color, border: "none",
              outline: current ? "2px solid #2f6fed" : "none",
              fontWeight: current ? 700 : 400, cursor: ready ? "pointer" : "not-allowed",
            }}
          >
            {seq}
          </button>
        );
      })}
    </div>
  );
}
