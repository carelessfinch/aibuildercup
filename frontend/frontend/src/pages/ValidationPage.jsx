import { useEffect, useMemo, useRef, useState } from "react";
import { FlaskConical, Clock, Play, CheckCircle2, AlertTriangle } from "lucide-react";
import { toast } from "sonner";
import { AppShell } from "@/components/chat/AppShell";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { researchApi, validateFourMForm } from "@/lib/research";
import { useAuth } from "@/components/AuthProvider";
import { VALIDATION } from "@/constants/testIds";
import { MathText } from "@/components/MathText";
import { MessageContent } from "@/components/chat/MessageContent";

const emptyForm = {
  presetId: "good_cf4o2_baseline",
  caseId: "plasma_cf4o2_icp_v1",
  question: "Validate electron density, ion flux and etch rate vs RF bias for the 100 W CF4/O2 ICP reference case.",
  diagnostics: "langmuir_probe, oes",
  wafer: "Si",
  stack: "",
  power: "100",
  pressure: "15",
  cf4: "40",
  o2: "10",
  argon: "0",
  biases: "0, 25, 50, 75, 100",
  operatorExperience: "senior",
  shift: "day",
  notes: "",
};

const TERMINAL_EVENTS = new Set(["awaiting_signoff", "escalated", "signed_off", "run_failed"]);
const RUN_STATUSES = new Set(["running", "awaiting_signoff", "escalated", "signed_off", "failed"]);

// Fault presets can omit fields (e.g. the missing-wafer case), so read defensively.
function formFromPreset(preset) {
  const input = preset.fourm_input || {};
  const recipe = input.method?.recipe || {};
  const flows = recipe.flow_sccm || {};
  return {
    presetId: preset.id,
    caseId: input.case_id || "",
    question: input.question || "",
    diagnostics: (input.machine?.diagnostics || []).join(", "),
    wafer: input.material?.wafer || "",
    stack: (input.material?.stack || []).join(", "),
    power: String(recipe.power_W ?? ""),
    pressure: String(recipe.pressure_mTorr ?? ""),
    cf4: String(flows.CF4 || 0),
    o2: String(flows.O2 || 0),
    argon: String(flows.Ar || 0),
    biases: (recipe.bias_sweep_V || []).join(", "),
    operatorExperience: input.man?.operator_experience || "",
    shift: input.man?.shift || "",
    notes: input.man?.notes || "",
  };
}

const PRESET_GROUPS = [
  ["Good cases", (p) => !p.id.startsWith("fault_")],
  ["Faults in the solver output", (p) => p.id.startsWith("fault_") && (!p.fault_site || p.fault_site === "plasma_result")],
  ["Faults in the 4M input", (p) => p.fault_site === "fourm_input"],
  ["Faults in the chemistry", (p) => p.fault_site === "chemistry"],
];

function groupPresets(presets) {
  return PRESET_GROUPS
    .map(([label, test]) => [label, presets.filter(test)])
    .filter(([, items]) => items.length);
}

function buildPayload(form, biases, usePreset) {
  const flows = {};
  if (Number(form.cf4) > 0) flows.CF4 = Number(form.cf4);
  if (Number(form.o2) > 0) flows.O2 = Number(form.o2);
  if (Number(form.argon) > 0) flows.Ar = Number(form.argon);
  const splitList = (value) => value.split(",").map((v) => v.trim()).filter(Boolean);
  const man = form.operatorExperience || form.shift || form.notes
    ? {
        operator_experience: form.operatorExperience || null,
        shift: form.shift || null,
        notes: form.notes || null,
      }
    : null;
  const fourmInput = {
    case_id: form.caseId.trim(),
    question: form.question.trim(),
    machine: { diagnostics: splitList(form.diagnostics) },
    material: { wafer: form.wafer.trim(), stack: splitList(form.stack) },
    method: {
      recipe: {
        power_W: Number(form.power),
        pressure_mTorr: Number(form.pressure),
        flow_sccm: flows,
        bias_sweep_V: biases,
      },
      metrology: splitList(form.diagnostics),
    },
    man,
    source: "form",
  };
  return usePreset ? { preset_id: form.presetId } : { fourm_input: fourmInput };
}

const verdictStyles = {
  approve: { background: "var(--pass-soft)", color: "var(--pass)" },
  revise: { background: "var(--revise-soft)", color: "var(--revise)" },
  escalate: { background: "var(--escalate-soft)", color: "var(--escalate)" },
};

function VerdictBadge({ verdict }) {
  const key = verdict?.toLowerCase();
  const style = verdictStyles[key] || verdictStyles.revise;
  return (
    <span className="inline-flex items-center rounded-full px-2.5 py-1 text-[11.5px] font-bold uppercase tracking-wide" style={style}>
      {key === "approve" ? "PASS" : key === "escalate" ? "ESCALATE" : "REVISE"}
    </span>
  );
}

function Field({ id, label, error, className, min, max, step, required, inputMode, ...props }) {
  return (
    <div className={className}>
      <Label htmlFor={id} className="text-[12.5px] font-medium" style={{ color: "var(--ink-2)" }}>
        {label}{required ? " *" : ""}
      </Label>
      <Input
        id={id}
        className="mt-1.5 h-10 rounded-md"
        min={min}
        max={max}
        step={step}
        required={required}
        inputMode={inputMode}
        aria-invalid={Boolean(error)}
        style={{ background: "var(--paper)", color: "var(--ink)", borderColor: error ? "var(--escalate)" : "var(--rule-2)" }}
        {...props}
      />
      {error && <p className="mt-1 text-[12px]" style={{ color: "var(--escalate)" }}>{error}</p>}
    </div>
  );
}

export default function ValidationPage({ theme, onToggleTheme }) {
  const { user } = useAuth();
  const [presets, setPresets] = useState([]);
  const [form, setForm] = useState(emptyForm);
  const [errors, setErrors] = useState({});
  const [presetDirty, setPresetDirty] = useState(false);
  const [run, setRun] = useState(null);
  const [events, setEvents] = useState([]);
  const [status, setStatus] = useState("idle");
  const [plots, setPlots] = useState([]);
  const [signing, setSigning] = useState(false);
  const [streamAttempt, setStreamAttempt] = useState(0);
  const streamRef = useRef(null);
  const plotUrlsRef = useRef([]);

  useEffect(() => {
    researchApi.getPresets().then((body) => {
      const list = Array.isArray(body) ? body : body.presets || [];
      setPresets(list);
    }).catch((e) => toast.error(e.message || "Could not load presets"));
  }, []);

  useEffect(() => () => streamRef.current?.abort(), []);

  useEffect(() => {
    if (!run || !["running", "awaiting_signoff", "escalated", "signed_off"].includes(status)) return;
    let cancelled = false;
    (async () => {
      for (const url of run.plots || []) {
        try {
          const objectUrl = await researchApi.fetchPlot(url);
          if (cancelled) { URL.revokeObjectURL(objectUrl); return; }
          plotUrlsRef.current.push(objectUrl);
          setPlots((prev) => prev.some((plot) => plot.sourceUrl === url)
            ? prev
            : [...prev, { sourceUrl: url, url: objectUrl, name: url.split("/").pop().replace(/\.svg$/, "").replace(/-/g, " ") }]);
        } catch { /* plots become available as they complete */ }
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [run, status]);

  useEffect(() => () => {
    plotUrlsRef.current.forEach((url) => URL.revokeObjectURL(url));
  }, []);

  // The server replays every event on each connection, so a reconnect starts
  // from an empty list. Cloud Run or a proxy can close a long stream before
  // the run ends; then the run is re-read and the stream reopened.
  const runId = run?.id;
  useEffect(() => {
    if (!runId || status !== "running") return;
    const controller = new AbortController();
    streamRef.current = controller;
    let finished = false;
    setEvents([]);
    // A terminal event moves status on, which aborts this stream before the
    // run (with its plot URLs) comes back, so the merge must not wait on it.
    const refreshRun = () => researchApi.getRun(runId)
      .then((current) => {
        setRun((prev) => (prev?.id === runId
          ? { ...prev, ...current, id: runId, plots: current.plots?.length ? current.plots : prev.plots }
          : prev));
        return current;
      });
    const handle = (eventType, data) => {
      const item = { ...data, event_type: data?.event_type || eventType };
      if (item.event_type === "timer") return;
      setEvents((prev) => [...prev, item]);
      if (TERMINAL_EVENTS.has(item.event_type)) finished = true;
      if (item.event_type === "awaiting_signoff") setStatus("awaiting_signoff");
      if (item.event_type === "escalated") setStatus("escalated");
      if (item.event_type === "signed_off") setStatus("signed_off");
      if (item.event_type === "run_failed") {
        setStatus("failed");
        toast.error(item.data?.error || item.message || "The validation run failed");
      }
      if (["awaiting_signoff", "escalated"].includes(item.event_type)) {
        refreshRun().catch(() => { /* the event stream already contains the visible final state */ });
      }
    };
    researchApi.streamEvents(runId, handle, controller.signal)
      .then(async () => {
        if (finished || controller.signal.aborted) return;
        const current = await refreshRun();
        if (controller.signal.aborted) return;
        if (RUN_STATUSES.has(current.status) && current.status !== "running") {
          setEvents((current.events || []).filter((e) => e.event_type !== "timer"));
          setStatus(current.status);
        } else {
          setTimeout(() => { if (!controller.signal.aborted) setStreamAttempt((n) => n + 1); }, 1500);
        }
      })
      .catch((e) => {
        if (e.name === "AbortError" || controller.signal.aborted) return;
        toast.error(e.message || "The validation run failed");
        setStatus("failed");
      })
      .finally(() => { if (streamRef.current === controller) streamRef.current = null; });
    return () => controller.abort();
  }, [runId, status, streamAttempt]);

  const finalEvent = [...events].reverse().find((e) => ["awaiting_signoff", "escalated"].includes(e.event_type));
  const report = finalEvent?.data?.report;
  const failure = [...events].reverse().find((e) => e.event_type === "run_failed");
  // Mock runs stream each review; ADK runs carry them only in the final report.
  const reviews = useMemo(() => {
    const byRound = new Map();
    events.forEach((e) => { if (e.data?.review?.round != null) byRound.set(e.data.review.round, e.data.review); });
    (report?.reviews || []).forEach((r) => { if (r?.round != null) byRound.set(r.round, r); });
    return [...byRound.values()].sort((a, b) => a.round - b.round);
  }, [events, report]);
  const finalReview = reviews.at(-1);
  const submittedAt = run?.submitted_at ? new Date(run.submitted_at).getTime() : null;
  const [elapsed, setElapsed] = useState(0);

  useEffect(() => {
    if (!submittedAt) return;
    if (!["running", "awaiting_signoff"].includes(status)) return;
    const tick = () => setElapsed(Math.max(0, Date.now() - submittedAt));
    tick();
    const timer = setInterval(tick, 1000);
    return () => clearInterval(timer);
  }, [submittedAt, status]);

  const update = (name) => (event) => {
    const value = event?.target ? event.target.value : event;
    setPresetDirty(true);
    setForm((prev) => ({ ...prev, [name]: value }));
  };

  const applyPreset = (presetId) => {
    const preset = presets.find((p) => p.id === presetId);
    setPresetDirty(false);
    if (preset) setForm(formFromPreset(preset));
    else setForm((prev) => ({ ...prev, presetId }));
  };

  const submit = async (event) => {
    event.preventDefault();
    const validation = validateFourMForm(form);
    setErrors(validation.errors);
    if (!validation.valid) return;
    streamRef.current?.abort();
    setEvents([]);
    setPlots([]);
    setStatus("running");
    try {
      const created = await researchApi.createRun(
        buildPayload(form, validation.biases, !presetDirty)
      );
      setRun({
        ...created,
        id: created.run_id || created.id,
        submitted_at: created.submitted_at || new Date().toISOString(),
        plots: created.plots || [],
      });
    } catch (e) {
      setStatus("failed");
      toast.error(e.message || "Could not start the run");
    }
  };

  const signOff = async () => {
    if (!run || status !== "awaiting_signoff") return;
    setSigning(true);
    try {
      const result = await researchApi.signOff(run.id);
      setStatus("signed_off");
      if (Number.isFinite(result?.elapsed_seconds)) setElapsed(result.elapsed_seconds * 1000);
      setEvents((prev) => [...prev, {
        sequence: prev.length + 1,
        event_type: "signed_off",
        actor: "Human",
        message: `Result signed off by ${user?.username || "human reviewer"}.`,
        data: { reviewer: user?.username },
        created_at: new Date().toISOString(),
      }]);
    } catch (e) {
      toast.error(e.message || "Sign-off failed");
    } finally {
      setSigning(false);
    }
  };

  const sidebarProps = { theme, onToggleTheme, noSessionFeatures: true };

  return (
    <AppShell
      title="Validate a simulation"
      sidebarProps={sidebarProps}
      showDemo={researchApi.demo}
    >
      <div className="flex-1 overflow-y-auto">
        <div className="mx-auto w-full max-w-[1400px] px-4 py-5 sm:px-6 md:px-8 md:py-8">
          <div className="grid min-w-0 gap-5 lg:grid-cols-[minmax(330px,420px)_minmax(0,1fr)] lg:gap-8">
            <form onSubmit={submit} noValidate={false} className="rounded-xl border p-4 md:p-5" style={{ background: "var(--paper)", borderColor: "var(--rule)", boxShadow: "var(--shadow-sm)" }}>
              <div className="flex items-center gap-2.5">
                <FlaskConical className="h-5 w-5" style={{ color: "var(--accent)" }} />
                <h1 className="font-serif-read text-[18px] font-semibold" style={{ color: "var(--ink)" }}>Simulation brief</h1>
              </div>

              <div className="mt-5">
                <Label htmlFor="validation-preset" className="text-[12.5px] font-medium" style={{ color: "var(--ink-2)" }}>Demo preset</Label>
                <select
                  id="validation-preset"
                  data-testid={VALIDATION.presetPicker}
                  value={form.presetId}
                  onChange={(e) => applyPreset(e.target.value)}
                  className="mt-1.5 h-10 w-full rounded-md border bg-transparent px-3 text-[14px]"
                  style={{ borderColor: "var(--rule-2)", color: "var(--ink)", background: "var(--paper)" }}
                >
                  {groupPresets(presets).map(([label, items]) => (
                    <optgroup key={label} label={label}>
                      {items.map((preset) => <option key={preset.id} value={preset.id}>{preset.title || preset.id}</option>)}
                    </optgroup>
                  ))}
                </select>
                <p className="mt-2 text-[12.5px] leading-relaxed" style={{ color: "var(--ink-3)" }}>
                  {presets.find((p) => p.id === form.presetId)?.description || "Selecting a preset fills all fields."}
                </p>
              </div>

              <div className="mt-5 grid grid-cols-1 gap-4 md:grid-cols-2">
                <Field id="validation-case-id" label="Case ID" required value={form.caseId} onChange={update("caseId")} data-testid="validation-case-id" />
                <Field id="validation-diagnostics" label="Machine diagnostics" value={form.diagnostics} onChange={update("diagnostics")} data-testid="validation-diagnostics" />
                <Field id="validation-wafer" label="Material wafer" required error={errors.wafer} value={form.wafer} onChange={update("wafer")} data-testid="validation-wafer" />
                <Field id="validation-stack" label="Material stack" value={form.stack} onChange={update("stack")} data-testid="validation-stack" />
                <Field id="validation-power" label="Power (W)" type="number" required inputMode="decimal" min={1} max={1000} step="any" error={errors.power} value={form.power} onChange={update("power")} data-testid="validation-power" />
                <Field id="validation-pressure" label="Pressure (mTorr)" type="number" required inputMode="decimal" min={1} max={500} step="any" error={errors.pressure} value={form.pressure} onChange={update("pressure")} data-testid="validation-pressure" />
                <Field id="validation-cf4" label="CF₄ (sccm)" type="number" inputMode="decimal" min={0} max={1000} step="any" error={errors.cf4} value={form.cf4} onChange={update("cf4")} data-testid="validation-cf4-flow" />
                <Field id="validation-o2" label="O₂ (sccm)" type="number" inputMode="decimal" min={0} max={1000} step="any" error={errors.o2} value={form.o2} onChange={update("o2")} data-testid="validation-o2-flow" />
                <Field id="validation-argon" label="Ar (sccm)" type="number" inputMode="decimal" min={0} max={1000} step="any" error={errors.argon} value={form.argon} onChange={update("argon")} data-testid="validation-argon-flow" />
                <Field id="validation-shift" label="Man shift" value={form.shift} onChange={update("shift")} data-testid="validation-shift" />
                <div className="md:col-span-2">
                  <Label htmlFor="validation-experience" className="text-[12.5px] font-medium" style={{ color: "var(--ink-2)" }}>Operator experience (optional)</Label>
                  <select id="validation-experience" data-testid="validation-operator-experience" value={form.operatorExperience} onChange={update("operatorExperience")} className="mt-1.5 h-10 w-full rounded-md border bg-transparent px-3 text-[14px]" style={{ borderColor: "var(--rule-2)", background: "var(--paper)", color: "var(--ink)" }}>
                    <option value="">Not supplied</option><option value="junior">Junior</option><option value="senior">Senior</option>
                  </select>
                </div>
                <div className="md:col-span-2">
                  <Label htmlFor="validation-biases" className="text-[12.5px] font-medium" style={{ color: "var(--ink-2)" }}>Bias sweep (V, comma-separated)</Label>
                  <Input id="validation-biases" data-testid="validation-biases" value={form.biases} onChange={update("biases")} required className="mt-1.5 h-10 rounded-md" aria-invalid={Boolean(errors.biases)} style={{ background: "var(--paper)", color: "var(--ink)", borderColor: errors.biases ? "var(--escalate)" : "var(--rule-2)" }} />
                  <p className="mt-1 text-[12px]" style={{ color: errors.biases ? "var(--escalate)" : "var(--ink-3)" }}>{errors.biases || "Up to 12 points; each from -200 to 200 V."}</p>
                </div>
                <div className="md:col-span-2">
                  <Label htmlFor="validation-question" className="text-[12.5px] font-medium" style={{ color: "var(--ink-2)" }}>Question *</Label>
                  <textarea id="validation-question" data-testid="validation-question" value={form.question} onChange={update("question")} required rows={3} className="mt-1.5 w-full resize-y rounded-md border px-3 py-2 text-[14px] focus:outline-none focus-visible:ring-2 focus-visible:ring-ring" style={{ background: "var(--paper)", color: "var(--ink)", borderColor: errors.question ? "var(--escalate)" : "var(--rule-2)" }} />
                  {errors.question && <p className="mt-1 text-[12px]" style={{ color: "var(--escalate)" }}>{errors.question}</p>}
                </div>
              </div>
            <Button type="submit" data-testid={VALIDATION.startRun} disabled={status === "running"} className="mt-5 h-11 w-full rounded-lg text-[14px] font-semibold" style={{ background: "var(--accent)", color: "var(--paper)" }}>
                <Play className="h-4 w-4" />{status === "running" ? "Run in progress…" : "Start validation run"}
              </Button>
            </form>

            <div className="min-w-0 space-y-5">
              <section aria-label="Elapsed time" className="rounded-xl border p-4 md:p-5" style={{ background: "var(--paper-2)", borderColor: "var(--rule)" }}>
                <div className="flex flex-wrap items-center justify-between gap-3">
                  <div className="flex items-center gap-2.5">
                    <Clock className="h-5 w-5" style={{ color: "var(--accent)" }} />
                    <div>
                      <p className="text-3xl font-semibold tnum leading-none" style={{ color: "var(--ink)" }}>
                        {String(Math.floor(elapsed / 60000)).padStart(2, "0")}:{String(Math.floor((elapsed % 60000) / 1000)).padStart(2, "0")}
                      </p>
                      <p className="mt-1 text-[12.5px]" style={{ color: "var(--ink-3)" }}>vs ~2 h manual baseline</p>
                    </div>
                  </div>
                  <span data-testid="validation-status" className="rounded-full px-3 py-1.5 text-[12px] font-semibold uppercase" style={{ background: status === "signed_off" ? "var(--pass-soft)" : status === "escalated" ? "var(--escalate-soft)" : "var(--accent-soft)", color: status === "signed_off" ? "var(--pass)" : status === "escalated" ? "var(--escalate)" : "var(--accent)" }}>{status.replace("_", " ")}</span>
                </div>
              </section>

              <section aria-label="Agent timeline" className="rounded-xl border overflow-hidden" style={{ background: "var(--paper)", borderColor: "var(--rule)" }}>
                <div className="flex min-h-[52px] items-center justify-between gap-3 border-b px-4 py-3" style={{ borderColor: "var(--rule)" }}>
                  <h2 className="font-serif-read text-[16px] font-semibold" style={{ color: "var(--ink)" }}>Research-group transcript</h2>
                  {finalReview && <VerdictBadge verdict={finalReview.verdict} />}
                </div>
                <ol data-testid={VALIDATION.timeline} className="max-h-[440px] overflow-y-auto px-4 py-4">
                  {!events.length && <li className="py-6 text-[13.5px]" style={{ color: "var(--ink-3)" }}>The Postdoc, PhD and Professor transcript begins after submission.</li>}
                  {events.map((item, index) => (
                    <li key={`${item.sequence}-${item.event_type}-${index}`} className="relative border-l pl-4 pb-4 last:pb-0" style={{ borderColor: "var(--rule)" }}>
                      <span className="absolute -left-[5px] top-1.5 h-2.5 w-2.5 rounded-full" style={{ background: item.actor === "Professor" ? "var(--accent)" : item.actor === "Human" ? "var(--pass)" : "var(--rule-2)" }} />
                      <div className="flex flex-wrap items-center gap-x-2 gap-y-1">
                        <span className="text-[12.5px] font-semibold" style={{ color: "var(--ink)" }}>{item.actor}</span>
                        <span className="text-[11.5px] tnum" style={{ color: "var(--ink-3)" }}>{new Date(item.created_at).toLocaleTimeString()}</span>
                      </div>
                      <MathText as="p" text={item.message} className="mt-1 text-[13.5px] leading-relaxed break-words whitespace-pre-wrap" style={{ color: "var(--ink-2)" }} />
                    </li>
                  ))}
                </ol>
              </section>

              {report?.summary && (
                <section data-testid="validation-report-summary" aria-label="Final report" className="rounded-xl border p-4" style={{ background: "var(--paper)", borderColor: "var(--rule)" }}>
                  <div className="flex items-center justify-between gap-3">
                    <h3 className="font-serif-read text-[16px] font-semibold" style={{ color: "var(--ink)" }}>Final report</h3>
                    {report.case_id && <span className="text-[12px] tnum" style={{ color: "var(--ink-3)" }}>{report.case_id}</span>}
                  </div>
                  <div className="mt-2 text-[14px]" style={{ color: "var(--ink-2)" }}><MessageContent text={report.summary} /></div>
                  {report.calibration && (
                    <p className="mt-2 text-[12.5px]" style={{ color: "var(--ink-3)" }}>
                      Calibration {report.calibration.converged ? "converged" : "did not converge"}
                      {Object.keys(report.calibration.tuned_parameters || {}).length > 0 && ` · tuned ${Object.entries(report.calibration.tuned_parameters).map(([k, v]) => `${k} = ${v}`).join(", ")}`}
                    </p>
                  )}
                </section>
              )}

              {reviews.map((review) => (
                <section key={review.round} data-testid={`validation-round-${review.round}`} aria-label={`Round ${review.round} review`} className="min-w-0 rounded-xl border overflow-hidden" style={{ background: "var(--paper)", borderColor: "var(--rule)" }}>
                  <div className="flex items-center justify-between gap-3 border-b px-4 py-3" style={{ borderColor: "var(--rule)" }}>
                    <h3 className="font-serif-read text-[16px] font-semibold" style={{ color: "var(--ink)" }}>Professor round {review.round}</h3>
                    <VerdictBadge verdict={review.verdict} />
                  </div>
                  <div className="overflow-x-auto">
                    <table className="w-full min-w-[480px] text-left text-[13px]">
                      <thead style={{ color: "var(--ink-3)" }}><tr className="border-b" style={{ borderColor: "var(--rule)" }}><th className="px-4 py-2 font-medium">Rubric</th><th className="px-4 py-2 font-medium">Result</th><th className="px-4 py-2 font-medium">Expected</th></tr></thead>
                      <tbody style={{ color: "var(--ink-2)" }}>
                        {(review.rubric_results || []).map((row, rowIndex) => (
                          <tr key={`${row.item_id}-${rowIndex}`} className="border-b last:border-0" style={{ borderColor: "var(--rule)" }}>
                            <td className="px-4 py-2.5 font-medium" style={{ color: "var(--ink)" }}>{String(row.item_id ?? "").replace(/_/g, " ")}</td>
                            <td className="px-4 py-2.5"><span className="rounded px-1.5 py-0.5" style={{ background: row.status === "pass" ? "var(--pass-soft)" : row.status === "fail" ? "var(--escalate-soft)" : "var(--revise-soft)", color: row.status === "pass" ? "var(--pass)" : row.status === "fail" ? "var(--escalate)" : "var(--revise)" }}><MathText text={row.value} /></span></td>
                            <td className="px-4 py-2.5"><MathText text={row.expected} /></td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                  {review.physics_checks?.length > 0 && (
                    <ul className="border-t px-4 py-3 text-[13px] space-y-1.5" style={{ borderColor: "var(--rule)", color: "var(--ink-2)" }}>
                      {review.physics_checks.map((check, i) => (
                        <li key={`${check.name}-${i}`}>
                          <span className="font-medium" style={{ color: check.status === "pass" ? "var(--pass)" : check.status === "fail" ? "var(--escalate)" : "var(--revise)" }}>{check.status}</span>{" "}
                          <span className="font-medium" style={{ color: "var(--ink)" }}>{check.name}</span>: <MathText text={check.detail} />
                        </li>
                      ))}
                    </ul>
                  )}
                  {review.feedback?.length > 0 && (
                    <ul className="border-t list-disc px-4 py-3 pl-9 text-[13px] space-y-1" style={{ borderColor: "var(--rule)", color: "var(--ink-2)" }}>
                      {review.feedback.map((note, i) => <li key={i}><MathText text={note} /></li>)}
                    </ul>
                  )}
                  <div className="flex flex-wrap gap-2 px-4 py-3">
                    {review.citations?.map((citation) => <span key={citation} className="max-w-full rounded-md px-2 py-1 text-[12px] break-words" style={{ background: "var(--accent-soft)", color: "var(--accent)" }}>{citation}</span>)}
                  </div>
                </section>
              ))}

              {plots.length > 0 && (
                <section aria-label="Physics plots" className="rounded-xl border p-4" style={{ background: "var(--paper)", borderColor: "var(--rule)" }}>
                  <h3 className="font-serif-read text-[16px] font-semibold" style={{ color: "var(--ink)" }}>Physics plots</h3>
                  <div className="mt-3 grid gap-4 sm:grid-cols-2">
                    {plots.map((plot) => <figure key={plot.url} className="overflow-hidden rounded-lg border" style={{ borderColor: "var(--rule)" }}><img src={plot.url} alt={plot.name} className="h-auto w-full" /><figcaption className="px-3 py-2 text-[12.5px] capitalize" style={{ color: "var(--ink-3)" }}>{plot.name}</figcaption></figure>)}
                  </div>
                </section>
              )}

              {status === "failed" && (
                <section data-testid="validation-failed" className="rounded-xl border p-4" style={{ background: "var(--escalate-soft)", borderColor: "var(--escalate)" }}>
                  <div className="flex items-start gap-3">
                    <AlertTriangle className="mt-0.5 h-5 w-5" style={{ color: "var(--escalate)" }} />
                    <div className="min-w-0">
                      <h3 className="text-[15px] font-bold uppercase" style={{ color: "var(--escalate)" }}>Run failed</h3>
                      <p className="mt-1 text-[13.5px] break-words" style={{ color: "var(--ink-2)" }}>{failure?.data?.error || failure?.message || "The validation run stopped before a final report was produced."}</p>
                    </div>
                  </div>
                </section>
              )}

              {(status === "escalated" || status === "signed_off") && (
                <section data-testid={VALIDATION.finalStatus} className="rounded-xl border p-4" style={{ background: status === "escalated" ? "var(--escalate-soft)" : "var(--pass-soft)", borderColor: status === "escalated" ? "var(--escalate)" : "var(--pass)" }}>
                  <div className="flex items-start gap-3">
                    {status === "escalated" ? <AlertTriangle className="mt-0.5 h-5 w-5" style={{ color: "var(--escalate)" }} /> : <CheckCircle2 className="mt-0.5 h-5 w-5" style={{ color: "var(--pass)" }} />}
                    <div className="min-w-0">
                      <h3 className="text-[15px] font-bold uppercase" style={{ color: status === "escalated" ? "var(--escalate)" : "var(--pass)" }}>
                        {status === "escalated" ? "ESCALATED — NOT SIGNED OFF" : "SIGNED OFF"}
                      </h3>
                      {report?.open_issues?.length > 0 && <ul className="mt-2 list-disc pl-5 text-[13.5px]" style={{ color: "var(--ink-2)" }}>{report.open_issues.map((issue, i) => <li key={i}><MathText text={issue} /></li>)}</ul>}
                    </div>
                  </div>
                </section>
              )}
            </div>
          </div>
        </div>
      </div>

      {status === "awaiting_signoff" && (
        <div data-testid="validation-signoff-sticky" className="sticky bottom-0 z-10 border-t px-4 py-3 md:px-8" style={{ background: "color-mix(in srgb, var(--paper) 92%, transparent)", backdropFilter: "blur(10px)", borderColor: "var(--rule)", paddingBottom: "max(0.75rem, env(safe-area-inset-bottom))" }}>
          <Button data-testid={VALIDATION.signOffButton} onClick={signOff} disabled={signing} className="h-11 w-full rounded-lg text-[14px] font-semibold sm:w-auto sm:min-w-[220px]" style={{ background: "var(--accent)", color: "var(--paper)" }}>
            {signing ? "Signing off…" : `Sign off as ${user?.username || "human reviewer"}`}
          </Button>
        </div>
      )}
    </AppShell>
  );
}
