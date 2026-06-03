"use client";
import { useEffect, useState } from "react";
import { formatRemaining, remainingSeconds } from "@/lib/timer";

export function Timer({
  startedAt, limitSec, onExpire,
}: {
  startedAt: string | null;
  limitSec: number;
  onExpire: () => void;
}) {
  const [now, setNow] = useState<number>(() => Date.now());
  useEffect(() => {
    const t = setInterval(() => setNow(Date.now()), 1000);
    return () => clearInterval(t);
  }, []);

  if (startedAt === null) {
    return <div className="label">Таймер запустится после подготовки теста</div>;
  }
  const left = remainingSeconds(startedAt, limitSec, now);
  if (left <= 0) onExpire();
  return (
    <div style={{
      background: "#fff", border: "1px solid #e0e6ee", borderRadius: 8,
      padding: "8px 16px", fontWeight: 700, color: "#1f3a5f",
      fontVariantNumeric: "tabular-nums",
    }}>
      {formatRemaining(left)}
    </div>
  );
}
