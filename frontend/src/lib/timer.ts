export function formatRemaining(totalSeconds: number): string {
  const s = Math.max(0, Math.floor(totalSeconds));
  const hh = Math.floor(s / 3600);
  const mm = Math.floor((s % 3600) / 60);
  const ss = s % 60;
  const pad = (n: number) => String(n).padStart(2, "0");
  return `${pad(hh)}:${pad(mm)}:${pad(ss)}`;
}

export function remainingSeconds(
  startedAtIso: string,
  limitSec: number,
  nowMs: number
): number {
  const startMs = new Date(startedAtIso).getTime();
  const elapsed = Math.floor((nowMs - startMs) / 1000);
  return Math.max(0, limitSec - elapsed);
}

export function isExpired(
  startedAtIso: string | null,
  limitSec: number,
  nowMs: number
): boolean {
  if (startedAtIso === null) return false;
  return remainingSeconds(startedAtIso, limitSec, nowMs) <= 0;
}
