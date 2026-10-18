import { API_BASE, consumeSse, headers as apiHeaders } from "./api";
import { authorizationHeader, handleUnauthorized } from "./auth";

const RAW_RESEARCH_URL = (process.env.REACT_APP_RESEARCH_API_URL || "").trim();
export const RESEARCH_API_BASE = RAW_RESEARCH_URL.replace(/\/+$/, "");
export const RESEARCH_DEMO_MODE = RESEARCH_API_BASE.length === 0;

const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));
const runs = new Map();
let runCounter = 0;

const CITATIONS = {
  te: "Lieberman & Lichtenberg, Principles of Plasma Discharges, 2nd ed., pp. 336–361",
  bohm: "Lieberman & Lichtenberg, Principles of Plasma Discharges, 2nd ed., pp. 172–184",
  power: "Kimura & Noto, J. Appl. Phys. 100, 063303 (2006)",
  chemistry: "Kimura & Noto, J. Appl. Phys. 100, 063303 (2006), Table II",
};

function rubric(item, status, value, expected) {
  return { item_id: item, status, value, expected };
}

export const DEMO_PRESETS = [
  {
    id: "good_cf4o2_baseline",
    title: "CF₄/O₂ baseline",
    description: "100 W reference ICP; clean synthetic case with a five-point bias sweep.",
    fourm_input: {
      case_id: "plasma_cf4o2_icp_v1",
      question: "Validate electron density, ion flux and etch rate vs RF bias for the 100 W CF4/O2 ICP reference case.",
      machine: { diagnostics: ["langmuir_probe", "oes"] },
      material: { wafer: "Si", stack: [] },
      method: {
        recipe: {
          power_W: 100,
          pressure_mTorr: 15,
          flow_sccm: { CF4: 40, O2: 10 },
          bias_sweep_V: [0, 25, 50, 75, 100],
        },
        metrology: ["sem"],
      },
      man: { operator_experience: "senior", shift: "day" },
      source: "form",
    },
  },
  {
    id: "good_argon_baseline",
    title: "Argon baseline",
    description: "300 W argon ICP textbook case for electron density and ion flux.",
    fourm_input: {
      case_id: "plasma_ar_icp_v1",
      question: "Validate electron density and ion flux for the 300 W argon ICP textbook case.",
      machine: { diagnostics: ["langmuir_probe"] },
      material: { wafer: "Si", stack: [] },
      method: {
        recipe: { power_W: 300, pressure_mTorr: 10, flow_sccm: { Ar: 50 }, bias_sweep_V: [0, 25, 50] },
        metrology: ["langmuir_probe"],
      },
      man: { operator_experience: "senior", shift: "day" },
      source: "form",
    },
  },
  {
    id: "fault_te_impossible",
    title: "Fault: impossible Te",
    description: "Corrupted solver output reports 250 eV in a low-power ICP.",
    fourm_input: {
      ...DEMO_PRESET_FORM("fault_te"),
      question: "Validate electron temperature against the reference case.",
    },
  },
  {
    id: "fault_power_balance_violation",
    title: "Fault: power balance",
    description: "Solver diagnostic reports a 55% power-balance residual.",
    fourm_input: {
      ...DEMO_PRESET_FORM("fault_power"),
      question: "Validate electron density and etch rate versus bias.",
    },
  },
  {
    id: "fault_bohm_flux_inconsistent",
    title: "Fault: Bohm flux",
    description: "Ion flux is inconsistent with its own Te/ne Bohm estimate.",
    fourm_input: {
      ...DEMO_PRESET_FORM("fault_bohm"),
      question: "Validate ion flux for a synthetic argon ICP.",
    },
  },
];

function DEMO_PRESET_FORM(kind) {
  if (kind === "fault_power") {
    return {
      case_id: "plasma_cf4o2_icp_fault_power_balance",
      machine: { diagnostics: ["langmuir_probe", "oes"] },
      material: { wafer: "Si", stack: [] },
      method: {
        recipe: { power_W: 100, pressure_mTorr: 15, flow_sccm: { CF4: 40, O2: 10 }, bias_sweep_V: [0, 50, 100] },
        metrology: ["sem", "langmuir_probe"],
      },
      man: { operator_experience: "senior", shift: "day" },
      source: "form",
    };
  }
  return {
    case_id: kind === "fault_bohm" ? "plasma_ar_icp_fault_bohm" : "plasma_cf4o2_icp_fault_te",
    machine: { diagnostics: [kind === "fault_bohm" ? "langmuir_probe" : "langmuir_probe"] },
    material: { wafer: "Si", stack: [] },
    method: {
      recipe: kind === "fault_bohm"
        ? { power_W: 300, pressure_mTorr: 10, flow_sccm: { Ar: 50 }, bias_sweep_V: [0, 50] }
        : { power_W: 100, pressure_mTorr: 15, flow_sccm: { CF4: 40, O2: 10 }, bias_sweep_V: [0, 50, 100] },
      metrology: ["langmuir_probe"],
    },
    man: { operator_experience: "senior", shift: "day" },
    source: "form",
  };
}

function scriptFor(metadata) {
  const preset = DEMO_PRESETS.find((p) => p.fourm_input.case_id === metadata.case_id);
  const failed = Boolean(preset?.id.startsWith("fault_"));
  const events = [
    event(0, "run_received", "web", "4M metadata received; research group is being convened.", {}),
    event(1, "plan_created", "Postdoc", "Plan ready: one global-model sweep with calibration acceptance criteria.", {
      plan: {
        solver: "plasma_global_model",
        chemistry_ref: preset?.id.startsWith("good_argon") ? "ar_lieberman_icp" : "cf4o2_kimura2006_stub",
        operating_point: metadata.method.recipe,
        acceptance_criteria_proposal: [
          "Electron temperature remains in the published range.",
          "Power-balance residual stays below 5%.",
          "Ion flux is consistent with the Bohm edge criterion.",
        ],
      },
    }),
    event(2, "solver_started", "PhD", "Running the complete bias sweep as one solver job.", { backend: "local" }),
    event(3, "result_received", "PhD", "Plasma sweep complete; calibration table assembled.", {
      result: { points: 5, power_balance_residual_pct: failed && preset.id === "fault_power_balance_violation" ? 55 : 2.5 },
    }),
    event(4, "plot_ready", "Postdoc", "Plot prepared: electron-density-versus-bias.svg.", { url: `${metadata.case_id}/plots/electron_density.svg` }),
    event(5, "plot_ready", "Postdoc", "Plot prepared: ion-flux-versus-bias.svg.", { url: `${metadata.case_id}/plots/ion_flux.svg` }),
  ];

  const roundOne = {
    verdict: "revise",
    round: 1,
    rubric_results: [
      rubric("te_range", failed && preset.id === "fault_te_impossible" ? "fail" : "pass", failed && preset.id === "fault_te_impossible" ? "250 eV" : "2.4–2.7 eV", "1–10 eV"),
      rubric("power_balance", failed && preset.id === "fault_power_balance_violation" ? "fail" : "pass", failed && preset.id === "fault_power_balance_violation" ? "55%" : "2.5%", "< 5%"),
      rubric("bohm_flux", "warn", failed && preset.id === "fault_bohm_flux_inconsistent" ? "6 orders low" : "within 8%", "within 15%"),
    ],
    feedback: failed
      ? ["Repair the inconsistent solver output and resubmit without changing the input intent."]
      : ["Retune coupling efficiency and repeat the sweep before review."],
    citations: [CITATIONS.te, CITATIONS.power, CITATIONS.bohm],
  };
  events.push(event(6, "review_received", "Professor", "Round 1 verdict: REVISE. The flagged physics must be resolved.", { review: roundOne }));

  const finalVerdict = failed ? "escalate" : "approve";
  const finalRound = {
    verdict: finalVerdict,
    round: 2,
    rubric_results: failed
      ? roundOne.rubric_results.map((row) => (row.status === "warn" ? { ...row, status: "fail" } : row))
      : roundOne.rubric_results.map((row) => ({ ...row, status: "pass", value: row.status === "warn" ? "within 8%" : row.value })),
    feedback: failed ? ["ESCALATE: the injected fault survives a second review; human judgment is required."] : [],
    citations: [CITATIONS.te, CITATIONS.bohm, CITATIONS.chemistry],
  };
  events.push(event(7, "review_received", "Professor", failed
    ? "Round 2 verdict: ESCALATE. The issue is outside automated acceptance."
    : "Round 2 verdict: APPROVE. Human sign-off is still required.", { review: finalRound }));

  if (failed) {
    events.push(event(8, "escalated", "Professor", "ESCALATED — NOT SIGNED OFF.", {
      report: {
        sign_off: "escalated",
        open_issues: [
          preset.id === "fault_te_impossible" ? "Te = 250 eV is impossible for the stated low-power ICP." : undefined,
          preset.id === "fault_power_balance_violation" ? "Power-balance residual (55%) exceeds the 5% tolerance." : undefined,
          preset.id === "fault_bohm_flux_inconsistent" ? "Reported ion flux contradicts the Bohm flux estimate." : undefined,
        ].filter(Boolean),
      },
    }));
  } else {
    events.push(event(8, "awaiting_signoff", "Professor", "Recommendation approved; awaiting human sign-off.", {
      report: {
        sign_off: "pending",
        summary: "The sweep is physically consistent and calibrated within tolerance.",
        open_issues: [],
      },
    }));
  }
  return events;
}

function event(offset, event_type, actor, message, data) {
  return {
    sequence: offset + 1,
    event_type,
    actor,
    message,
    data: data || {},
    created_at: new Date(Date.now() + offset * 350).toISOString(),
  };
}

function demoRunCreated(input) {
  runCounter += 1;
  const caseId = input?.fourm_input?.case_id || input?.case_id || "demo-run";
  const preset = DEMO_PRESETS.find(
    (item) => item.id === input?.preset_id || item.fourm_input.case_id === caseId
  );
  const presetId = preset?.id;
  const metadata = input?.fourm_input || preset?.fourm_input || input || {};
  const run = {
    id: `demo-${runCounter}`,
    run_id: `demo-${runCounter}`,
    preset_id: presetId,
    status: "running",
    submitted_at: new Date().toISOString(),
    events: [],
    plots: [
      `${caseId}/plots/electron_density.svg`,
      `${caseId}/plots/ion_flux.svg`,
    ],
  };
  run.script = scriptFor(metadata);
  runs.set(run.id, run);
  return {
    run_id: run.id,
    status: run.status,
    submitted_at: run.submitted_at,
    events_url: `/runs/${run.id}/events`,
    plots_url_pattern: `/runs/${run.id}/plots/{name}`,
    plots: run.plots,
  };
}

function applyEvent(run, data) {
  run.events.push(data);
  if (data.event_type === "awaiting_signoff") run.status = "awaiting_signoff";
  if (data.event_type === "escalated") run.status = "escalated";
  if (data.event_type === "signed_off") run.status = "signed_off";
}

async function demoStream(id, on, signal) {
  const run = runs.get(id);
  if (!run) throw Object.assign(new Error("Run not found"), { status: 404 });
  const replay = run.status !== "running" && run.events.length > 0;
  const source = replay ? run.events : run.script;
  for (const data of source) {
    if (signal?.aborted) return;
    if (!replay) applyEvent(run, data);
    on(data.event_type, data);
    await sleep(replay ? 20 : 220);
  }
  if (!replay) run.status = run.script.some((e) => e.event_type === "escalated") ? "escalated" : "awaiting_signoff";
}

function parseError(res) {
  return async () => {
    if (res.status === 401) handleUnauthorized();
    try {
      const body = await res.json();
      return body.detail || `Request failed (${res.status})`;
    } catch {
      return `Request failed (${res.status})`;
    }
  };
}

async function authedFetch(path, options = {}) {
  const res = await fetch(`${RESEARCH_API_BASE}${path}`, {
    ...options,
    headers: { ...apiHeaders(), ...authorizationHeader(), ...(options.headers || {}) },
  });
  return res;
}

function normalizeRun(body) {
  return {
    ...body,
    id: body.run_id || body.id,
    events: body.events || [],
    plots: body.plots || [],
  };
}

export const researchApi = {
  demo: RESEARCH_DEMO_MODE,
  getPresets: async () => {
    if (RESEARCH_DEMO_MODE) return DEMO_PRESETS;
    const res = await authedFetch("/presets");
    if (!res.ok) throw new Error(await parseError(res)());
    const body = await res.json();
    const presets = body.presets || body;
    return presets.map((preset) => ({ ...preset, id: preset.id || preset.preset_id }));
  },
  createRun: async (body) => {
    if (RESEARCH_DEMO_MODE) return demoRunCreated(body);
    const res = await authedFetch("/runs", {
      method: "POST",
      body: JSON.stringify(body),
    });
    if (!res.ok) throw new Error(await parseError(res)());
    return res.json();
  },
  streamEvents: async (id, on, signal) => {
    if (RESEARCH_DEMO_MODE) return demoStream(id, on, signal);
    const res = await authedFetch(`/runs/${id}/events`, { signal });
    if (!res.ok) throw new Error(await parseError(res)());
    await consumeSse(res, (eventType, data) => {
      on(eventType, { ...data, event_type: data?.event_type || eventType });
    });
  },
  getRun: async (id) => {
    if (RESEARCH_DEMO_MODE) {
      const run = runs.get(id);
      if (!run) throw Object.assign(new Error("Run not found"), { status: 404 });
      return normalizeRun(run);
    }
    const res = await authedFetch(`/runs/${id}`);
    if (!res.ok) throw new Error(await parseError(res)());
    return normalizeRun(await res.json());
  },
  signOff: async (id) => {
    if (RESEARCH_DEMO_MODE) {
      const run = runs.get(id);
      if (!run || run.status !== "awaiting_signoff") throw new Error("This run cannot be signed off now.");
      const reviewer = JSON.parse(localStorage.getItem("plasma_demo_auth") || "{}")?.username || "human-reviewer";
      const signedEvent = event(run.events.length, "signed_off", "Human", `Result signed off by ${reviewer}.`, { reviewer });
      applyEvent(run, signedEvent);
      return { run_id: id, status: "signed_off", signed_off_by: reviewer };
    }
    // Deliberately sends no reviewer body: the backend derives identity from the token.
    const res = await authedFetch(`/runs/${id}/signoff`, { method: "POST", body: "{}" });
    if (!res.ok) throw new Error(await parseError(res)());
    return res.json();
  },
  fetchPlot: async (url) => {
    if (RESEARCH_DEMO_MODE) {
      const name = url.split("/").pop() || "plot";
      const points = Array.from({ length: 18 }, (_, i) => `${40 + i * 14},${100 - i * 4}`).join(" ");
      const svg = `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 300 160"><rect width="300" height="160" fill="white"/><text x="18" y="24" font-family="sans-serif" font-size="12" fill="#16211F">${name.replace(/-/g, " ")}</text><line x1="38" y1="130" x2="280" y2="130" stroke="#DDE3E2"/><line x1="38" y1="30" x2="38" y2="130" stroke="#DDE3E2"/><polyline points="${points}" fill="none" stroke="#0E6B6B" stroke-width="3"/></svg>`;
      return URL.createObjectURL(new Blob([svg], { type: "image/svg+xml" }));
    }
    const path = url.startsWith("/") ? url : `/${url}`;
    const res = await authedFetch(path);
    if (!res.ok) throw new Error(await parseError(res)());
    const blob = await res.blob();
    return URL.createObjectURL(blob);
  },
};

export function validateFourMForm(form) {
  const errors = {};
  const number = (value) => Number(value);
  if (!form.wafer.trim()) errors.wafer = "Wafer is required";
  if (!form.question.trim()) errors.question = "Question is required";
  if (!Number.isFinite(number(form.power)) || number(form.power) < 1 || number(form.power) > 1000) errors.power = "Power must be 1–1000 W";
  if (!Number.isFinite(number(form.pressure)) || number(form.pressure) < 1 || number(form.pressure) > 500) errors.pressure = "Pressure must be 1–500 mTorr";
  for (const gas of ["cf4", "o2", "argon"]) {
    const value = number(form[gas]);
    if (!Number.isFinite(value) || value < 0 || value > 1000) errors[gas] = "Flow must be 0–1000 sccm";
  }
  const biases = form.biases.split(",").map((v) => v.trim()).filter(Boolean).map(number);
  if (!biases.length) errors.biases = "At least one bias point is required";
  if (biases.length > 12) errors.biases = "Use at most 12 bias points";
  if (biases.some((v) => !Number.isFinite(v) || v < -200 || v > 200)) errors.biases = "Each bias must be -200–200 V";
  return { errors, valid: Object.keys(errors).length === 0, biases };
}
