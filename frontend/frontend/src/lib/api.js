import { INDEXED_SOURCES } from "./sources";
import { authorizationHeader, handleUnauthorized } from "./auth";

const RAW_URL = (process.env.REACT_APP_RAG_API_URL || "").trim();

export const API_BASE = RAW_URL.replace(/\/+$/, "");
// When no real RAG base URL is configured we run a self-contained demo so the
// full experience (streaming, tool calls, citations) still works end-to-end.
export const DEMO_MODE = API_BASE.length === 0;

export function headers(extra = {}) {
  return {
    "Content-Type": "application/json",
    ...authorizationHeader(),
    ...extra,
  };
}

async function parseError(res) {
  if (res.status === 401) handleUnauthorized();
  try {
    const body = await res.json();
    return body.detail || `Request failed (${res.status})`;
  } catch {
    return `Request failed (${res.status})`;
  }
}

/* ---------------- Real API ---------------- */

// rag-api returns {sources: [{id, short, title, year, pages, kind}]}; the UI
// uses the INDEXED_SOURCES shape ({source_id, authors, ...}).
export function normalizeSources(body) {
  const list = Array.isArray(body) ? body : body?.sources || [];
  return list.map((s) => ({
    source_id: s.source_id || s.id,
    kind: s.kind,
    title: s.title || s.short || s.source_id || s.id,
    authors: s.authors || (s.short || "").replace(/\s*\(\d{4}\)\s*$/, ""),
    year: s.year,
    pages: Number(s.pages) || 0,
  }));
}

async function realGetSources() {
  const res = await fetch(`${API_BASE}/v1/sources`, { headers: headers() });
  if (!res.ok) throw new Error(await parseError(res));
  return normalizeSources(await res.json());
}

async function realSearch(body) {
  const res = await fetch(`${API_BASE}/v1/search`, {
    method: "POST",
    headers: headers(),
    body: JSON.stringify(body),
  });
  if (!res.ok) throw new Error(await parseError(res));
  return res.json();
}

async function realGetPages(sourceId, first, last) {
  const res = await fetch(`${API_BASE}/v1/sources/${sourceId}/pages?first=${first}&last=${last}`, {
    headers: headers(),
  });
  if (!res.ok) throw new Error(await parseError(res));
  return res.json();
}

async function realGetSession(sessionId) {
  const res = await fetch(`${API_BASE}/v1/sessions/${sessionId}`, {
    headers: headers(),
  });
  if (!res.ok) throw new Error(await parseError(res));
  return res.json();
}

async function realDeleteSession(sessionId) {
  const res = await fetch(`${API_BASE}/v1/sessions/${sessionId}`, {
    method: "DELETE",
    headers: headers(),
  });
  if (!res.ok && res.status !== 404) throw new Error(await parseError(res));
  return true;
}

// Parse an SSE response into typed events; shared by chat and validation runs.
// sse-starlette (research-api) frames with "\r\n"; rag-api uses "\n".
export async function consumeSse(res, on) {
  const reader = res.body.pipeThrough(new TextDecoderStream()).getReader();
  let buf = "";
  const dispatch = (block) => {
    const lines = block.split("\n");
    const event = lines.find((line) => line.startsWith("event:"))?.slice(6).trim();
    const dataLine = lines
      .filter((line) => line.startsWith("data:"))
      .map((line) => line.slice(5).trim())
      .join("\n");
    let data = null;
    try { data = JSON.parse(dataLine); } catch { data = null; }
    if (event) on(event, data);
  };
  for (;;) {
    const { value, done } = await reader.read();
    if (done) break;
    // A "\r" may end one chunk and its "\n" start the next; keep it until then.
    buf = (buf + value).replace(/\r\n|\r(?!$)/g, "\n");
    let i;
    while ((i = buf.indexOf("\n\n")) >= 0) {
      dispatch(buf.slice(0, i));
      buf = buf.slice(i + 2);
    }
  }
  buf = buf.replace(/\r/g, "\n").trim();
  if (buf) dispatch(buf);
}

// Streams chat SSE events; calls on(event, data) for each.
async function realChatStream(body, on, signal) {
  const res = await fetch(`${API_BASE}/v1/chat/stream`, {
    method: "POST",
    headers: headers(),
    body: JSON.stringify(body),
    signal,
  });
  if (!res.ok) throw new Error(await parseError(res));
  await consumeSse(res, on);
}

/* ---------------- Demo API ---------------- */

const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
const demoSessions = {}; // sessionId -> { agent, messages }

function demoCitation(src, p0, p1, section) {
  return `${src.authors.split(",")[0]} et al. (${src.year}). ${src.title}. p. ${p0}, PDF p. ${p1}.`;
}

function buildDemoAnswer(message, agent) {
  const liev = INDEXED_SOURCES[0];
  const kush = INDEXED_SOURCES[6];
  const coburn = INDEXED_SOURCES[8];
  if (agent === "professor_reviewer") {
    const c1 = demoCitation(kush, 212, 249, "Ch. 6 > PIC-MCC");
    const c2 = demoCitation(liev, 334, 371, "Ch. 10 > Global Models");
    return {
      answer:
        `VERDICT: REVISE\n\n` +
        `**Summary.** Your ICP etch setup is physically reasonable but the collision model and boundary conditions need adjustment before the results can be trusted.\n\n` +
        `- **Pressure regime** — At 10 mTorr the mean free path exceeds your mesh cell size; a PIC-MCC treatment is required rather than a fluid approximation [${c1}].\n` +
        `- **Electron temperature** — Your fixed Te = 4 eV contradicts particle balance, where Te is set by the ionization/loss ratio, not the input power [${c2}].\n` +
        `- **Surface chemistry** — The fluorocarbon passivation flux is missing; this governs SiO2 selectivity.\n\n` +
        `**Requested changes:** switch to kinetic transport below 20 mTorr, let Te float from particle balance, and add the F/C surface model.`,
      citations: [
        { citation: c1, source_id: kush.source_id, pdf_pages: [249, 253], section: "Ch. 6 > PIC-MCC", snippet: "Below ~20 mTorr the electron energy distribution is non-Maxwellian and a kinetic PIC-MCC treatment captures the high-energy tail driving ionization..." },
        { citation: c2, source_id: liev.source_id, pdf_pages: [371, 374], section: "Ch. 10 > Global Models", snippet: "In a global model the electron temperature is fixed by the particle balance between ionization and wall loss and is nearly independent of absorbed power..." },
      ],
      tool_calls: [
        { name: "search_literature", args: { query: "ICP etch Te particle balance low pressure", top_k: 5 } },
        { name: "read_pages", args: { source_id: kush.source_id, first: 249, last: 253 } },
      ],
    };
  }
  const c1 = demoCitation(liev, 334, 371, "Ch. 10 > Global Discharge Models");
  const c2 = demoCitation(coburn, 44, 51, "Ion-assisted surface reactions");
  return {
    answer:
      `In a low-pressure global model, the **electron temperature (Te)** is set almost entirely by *particle balance* — the equilibrium between ionization and diffusive loss to the walls — rather than by the absorbed power [${c1}].\n\n` +
      `- Raising the power increases plasma **density**, not Te, because more power simply creates more electron–ion pairs at the same ionization rate.\n` +
      `- Te therefore depends mainly on the product of gas pressure and chamber size (the *pL* parameter), which fixes how readily charged particles are lost.\n\n` +
      `For etching, this means **ion flux scales with power** while **ion energy** is controlled separately by the bias — the decoupling that makes ICP reactors so useful for anisotropic etching [${c2}].`,
    citations: [
      { citation: c1, source_id: liev.source_id, pdf_pages: [371, 374], section: "Ch. 10 > Global Discharge Models", snippet: "In a global model the electron temperature is fixed by the particle balance between ionization and wall loss and is nearly independent of absorbed power. Power controls the plasma density..." },
      { citation: c2, source_id: coburn.source_id, pdf_pages: [51, 54], section: "Ion-assisted surface reactions", snippet: "Ion bombardment dramatically enhances the reaction rate of neutral fluorine with silicon, demonstrating the synergy at the heart of reactive ion etching..." },
    ],
    tool_calls: [
      { name: "search_literature", args: { query: "electron temperature power independence global model", top_k: 5 } },
    ],
  };
}

async function demoChatStream(body, on, signal) {
  const sessionId = body.session_id || `demo-${Math.random().toString(36).slice(2, 10)}`;
  const agent = body.agent || "literature_assistant";
  const model = agent === "professor_reviewer" ? "gemini-3.8-flash" : "gemini-3.8-flash";
  const result = buildDemoAnswer(body.message, agent);

  on("session", { session_id: sessionId, agent, model });
  await sleep(500);
  if (signal?.aborted) return;

  for (const tc of result.tool_calls) {
    on("tool_call", tc);
    await sleep(900);
    if (signal?.aborted) return;
    const cites = result.citations.filter((c) => c.source_id === (tc.args.source_id || c.source_id)).slice(0, 2);
    on("tool_result", { name: tc.name, status: "success", citations: cites });
    await sleep(450);
    if (signal?.aborted) return;
  }

  const tokens = result.answer.match(/\S+\s*|\n/g) || [result.answer];
  for (const t of tokens) {
    if (signal?.aborted) return;
    on("text", { delta: t });
    await sleep(22);
  }
  on("done", {
    session_id: sessionId,
    answer: result.answer,
    citations: result.citations,
    tool_calls: result.tool_calls,
    elapsed_s: 6.2,
  });
  demoSessions[sessionId] = demoSessions[sessionId] || { agent, messages: [] };
  demoSessions[sessionId].messages.push({ role: "user", content: body.message });
  demoSessions[sessionId].messages.push({ role: "assistant", content: result.answer, citations: result.citations });
}

async function demoSearch(body) {
  await sleep(500);
  const pool = body.source_ids?.length
    ? INDEXED_SOURCES.filter((s) => body.source_ids.includes(s.source_id))
    : INDEXED_SOURCES;
  const results = pool.slice(0, body.top_k || 5).map((s, i) => ({
    citation: demoCitation(s, 330 + i * 7, 367 + i * 7),
    source_id: s.source_id,
    kind: s.kind,
    section: `Chapter ${i + 1}`,
    pdf_pages: [367 + i * 7, 367 + i * 7],
    printed_pages: [`${330 + i * 7}`],
    score: Math.max(0.01, 0.09 - i * 0.012),
    text: `Passage matching "${body.query}": ${s.title} discusses the governing mechanisms relevant to this query, with experimental and modelling evidence across the referenced pages.`,
  }));
  return { status: "success", mode: "hybrid", query: body.query, results };
}

async function demoGetPages(sourceId, first, last) {
  await sleep(350);
  const src = INDEXED_SOURCES.find((s) => s.source_id === sourceId) || INDEXED_SOURCES[0];
  const pages = [];
  for (let p = first; p <= Math.min(last, first + 3); p++) {
    pages.push({
      pdf_page: p,
      text: `[Page ${p} — ${src.title}]\n\nThis page develops the argument with the governing equations and boundary conditions. The electron energy distribution, ionization balance and wall-loss terms are derived, followed by the scaling relations used throughout the chapter. Figures on this page illustrate the dependence on pressure and power for the regimes discussed in the surrounding text.`,
    });
  }
  return { source_id: sourceId, pages };
}

async function demoGetSession(sessionId) {
  await sleep(200);
  const s = demoSessions[sessionId];
  if (!s) { const e = new Error("Session not found"); e.status = 404; throw e; }
  return { session_id: sessionId, agent: s.agent, messages: s.messages };
}

async function demoDeleteSession(sessionId) {
  delete demoSessions[sessionId];
  return true;
}

/* ---------------- Public interface ---------------- */

export const api = {
  demo: DEMO_MODE,
  getSources: async () => {
    // The static list is demo data; never show it in place of the real index.
    if (DEMO_MODE) return INDEXED_SOURCES;
    return realGetSources();
  },
  search: (body) => (DEMO_MODE ? demoSearch(body) : realSearch(body)),
  getPages: (id, first, last) => (DEMO_MODE ? demoGetPages(id, first, last) : realGetPages(id, first, last)),
  getSession: (id) => (DEMO_MODE ? demoGetSession(id) : realGetSession(id)),
  deleteSession: (id) => (DEMO_MODE ? demoDeleteSession(id) : realDeleteSession(id)),
  chatStream: (body, on, signal) => (DEMO_MODE ? demoChatStream(body, on, signal) : realChatStream(body, on, signal)),
};
