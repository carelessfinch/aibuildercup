import { useEffect, useMemo, useRef, useState } from "react";

import { createRun, requestSignoff } from "./api";
import FourMForm from "./components/FourMForm";
import KpiTimer from "./components/KpiTimer";
import PlotGallery from "./components/PlotGallery";
import RunTimeline from "./components/RunTimeline";
import type { RunEvent, RunStatus } from "./types";

const SSE_EVENTS = [
  "timer",
  "run_received",
  "plan_created",
  "solver_started",
  "result_received",
  "plot_ready",
  "review_received",
  "awaiting_signoff",
  "signed_off",
  "run_failed"
];

export default function App() {
  const [runId, setRunId] = useState("");
  const [status, setStatus] = useState<RunStatus>("queued");
  const [events, setEvents] = useState<RunEvent[]>([]);
  const [plots, setPlots] = useState<string[]>([]);
  const [submittedAt, setSubmittedAt] = useState<string | null>(null);
  const [completedAt, setCompletedAt] = useState<string | null>(null);
  const [isEscalated, setIsEscalated] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [reviewer, setReviewer] = useState("human-reviewer");
  const streamRef = useRef<EventSource | null>(null);

  useEffect(() => {
    if (!runId) return;

    streamRef.current?.close();
    const stream = new EventSource(`/runs/${runId}/events`);
    streamRef.current = stream;

    const receive = (event: MessageEvent<string>) => {
      const parsed = JSON.parse(event.data) as RunEvent;
      setEvents((current) =>
        current.some((item) => item.sequence === parsed.sequence)
          ? current
          : [...current, parsed].sort((a, b) => a.sequence - b.sequence)
      );
      if (parsed.event_type === "awaiting_signoff") {
        const report = (parsed.data as { report?: { sign_off?: RunStatus } }).report;
        if (report?.sign_off === "escalated") {
          setStatus("escalated");
          setIsEscalated(true);
          setCompletedAt(parsed.created_at);
          stream.close();
        } else {
          setStatus("awaiting_signoff");
        }
      }
      if (parsed.event_type === "plot_ready") {
        const url = (parsed.data as { url?: string }).url;
        if (url) setPlots((current) => (current.includes(url) ? current : [...current, url]));
      }
      if (parsed.event_type === "review_received") {
        const review = (parsed.data as { review?: { verdict?: string } }).review;
        if (review?.verdict === "escalate") setIsEscalated(true);
      }
      if (parsed.event_type === "signed_off") {
        setStatus("signed_off");
        setCompletedAt(parsed.created_at);
        stream.close();
      }
      if (parsed.event_type === "run_failed") {
        setStatus("failed");
        stream.close();
      }
    };

    SSE_EVENTS.forEach((eventName) => stream.addEventListener(eventName, receive as EventListener));
    stream.onerror = () => setError("The live connection dropped. Reconnecting…");
    stream.onopen = () => setError(null);

    return () => stream.close();
  }, [runId]);

  useEffect(() => {
    if (!status || status === "queued" || status === "running") return;
    if (status === "awaiting_signoff") return;
    streamRef.current?.close();
  }, [status]);

  async function submit(payload: unknown) {
    setError(null);
    setEvents([]);
    setPlots([]);
    setIsEscalated(false);
    setCompletedAt(null);
    try {
      const created = await createRun(payload);
      setRunId(created.run_id);
      setStatus(created.status);
      setSubmittedAt(created.submitted_at);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "The run did not start.");
    }
  }

  async function signOff() {
    if (!runId) return;
    try {
      await requestSignoff(runId, reviewer);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Sign-off did not complete.");
    }
  }

  const latestReview = useMemo(() => {
    const reviewEvents = events.filter((event) => event.event_type === "review_received");
    const last = reviewEvents.at(-1);
    return last ? (last.data as { review?: { verdict?: string; round?: number } }).review : undefined;
  }, [events]);

  return (
    <div className="app">
      <header className="masthead">
        <div className="identity">
          <p className="system-name">CF₄/O₂ ICP · bias sweep</p>
          <h1>Set the experiment. Watch the proof.</h1>
          <p className="purpose">
            A research group assembles the model, checks the physics, and brings a signed result to you — without
            walking a solver GUI.
          </p>
        </div>
        <div className="health">
          <span className={`status-dot ${status}`} aria-hidden="true" />
          <span>{statusLabel(status)}</span>
        </div>
      </header>

      <main>
        <FourMForm onSubmit={submit} disabled={status === "running" || Boolean(runId && status !== "signed_off" && status !== "failed")} />

        <section className="run-space" aria-label="Live simulation run">
          {runId ? (
            <KpiTimer submittedAt={submittedAt} completedAt={completedAt} status={status} />
          ) : (
            <div className="timer invitation">
              <p>Waiting for the experiment brief</p>
              <strong>0:00:00.0</strong>
              <span>The clock starts when the form is submitted.</span>
            </div>
          )}

          {isEscalated && (
            <div className="banner escalation" role="alert">
              <strong>Escalated — not signed off</strong>
              <p>The review cap was reached. The objections and transcript go to a human.</p>
            </div>
          )}
          {error && (
            <div className="banner caution" role="alert">
              {error}
            </div>
          )}

          <RunTimeline events={events} latestReview={latestReview} />

          <div className="decision-row">
            <label htmlFor="reviewer">Sign-off owner</label>
            <input
              id="reviewer"
              value={reviewer}
              onChange={(event) => setReviewer(event.target.value)}
              autoComplete="name"
            />
            <button
              type="button"
              className="signoff"
              onClick={signOff}
              disabled={status !== "awaiting_signoff" || reviewer.trim().length === 0}
            >
              Sign off this result
            </button>
          </div>

          <PlotGallery urls={plots} />
        </section>
      </main>
      <footer>
        <p>Human sign-off is mandatory. The 120-minute manual baseline is a documented estimate.</p>
      </footer>
    </div>
  );
}

function statusLabel(status: RunStatus | "queued") {
  const labels: Record<string, string> = {
    queued: "Queued",
    running: "Research group working",
    awaiting_signoff: "Needs human sign-off",
    signed_off: "Signed off",
    escalated: "Escalated",
    failed: "Stopped"
  };
  return labels[status] ?? status;
}
