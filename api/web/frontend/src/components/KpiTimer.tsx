import { useEffect, useState } from "react";

import type { RunStatus } from "../types";

const BASELINE_SECONDS = 120 * 60;
const TARGET_SECONDS = 20 * 60;

export default function KpiTimer({
  submittedAt,
  completedAt,
  status
}: {
  submittedAt: string | null;
  completedAt: string | null;
  status: RunStatus;
}) {
  const [now, setNow] = useState(() => Date.now());
  const running = Boolean(submittedAt && !completedAt && status !== "failed");

  useEffect(() => {
    if (!running) return;
    const interval = window.setInterval(() => setNow(Date.now()), 100);
    return () => window.clearInterval(interval);
  }, [running]);

  const start = submittedAt ? new Date(submittedAt).getTime() : now;
  const end = completedAt ? new Date(completedAt).getTime() : now;
  const elapsed = Math.max(0, (end - start) / 1000);
  const percent = Math.min(100, (elapsed / BASELINE_SECONDS) * 100);
  const targetPercent = (TARGET_SECONDS / BASELINE_SECONDS) * 100;

  return (
    <div className="timer" aria-live="polite">
      <div className="timer-heading">
        <p>Human time saved</p>
        <span>{status === "signed_off" ? "Stopped at sign-off" : "Counting from form submit"}</span>
      </div>
      <strong>{formatClock(elapsed)}</strong>
      <div
        className="baseline-meter"
        role="img"
        aria-label={`Elapsed ${formatClock(elapsed)} against a 120 minute manual baseline.`}
      >
        <div className="elapsed" style={{ width: `${percent}%` }} />
        <div className="target-mark" style={{ left: `${targetPercent}%` }} />
      </div>
      <div className="meter-caption">
        <span>20-minute target</span>
        <span>120-minute estimate</span>
      </div>
    </div>
  );
}

function formatClock(seconds: number): string {
  const hours = Math.floor(seconds / 3600);
  const minutes = Math.floor((seconds % 3600) / 60);
  const rest = seconds % 60;
  return `${hours}:${String(minutes).padStart(2, "0")}:${rest.toFixed(1).padStart(4, "0")}`;
}

