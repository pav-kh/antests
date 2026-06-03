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
    <div style={{ display: "grid", gridTemplateColumns: "repeat(6, 1fr)", gap: 6 }}>
      {cells.map((seq) => {
        const ready = isQuestionReady(seq, generatedCount);
        const locked = !ready;
        const answered = answeredSeqs.has(seq);
        const current = seq === currentSeq;
        const bg = current ? "#fff" : answered ? "#2f6fed" : locked ? "#f0d7d7" : "#eef2f8";
        const color = current ? "#2f6fed" : answered ? "#fff" : locked ? "#b06a6a" : "#5a6878";
        return (
          <span
            key={seq}
            data-locked={locked}
            onClick={() => { if (ready) onJump(seq); }}
            style={{
              aspectRatio: "1", display: "flex", alignItems: "center", justifyContent: "center",
              fontSize: 12, borderRadius: 6, background: bg, color,
              outline: current ? "2px solid #2f6fed" : "none",
              fontWeight: current ? 700 : 400, cursor: ready ? "pointer" : "not-allowed",
            }}
          >
            {seq}
          </span>
        );
      })}
    </div>
  );
}
