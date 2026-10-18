import { Search, FileText, Check } from "lucide-react";

const labelFor = (tc) => {
  if (tc.name === "read_pages" || tc.name === "read") {
    const a = tc.args || {};
    return `Read ${a.source_id || "source"}, pp. ${a.first ?? "?"}–${a.last ?? "?"}`;
  }
  return `Searched “${tc.args?.query || ""}”`;
};

export const ToolCallIndicator = ({ steps }) => {
  if (!steps?.length) return null;
  return (
    <ol data-testid="tool-call-step-indicator" className="mb-4 space-y-1">
      {steps.map((s, i) => {
        const Icon = s.name === "read_pages" || s.name === "read" ? FileText : Search;
        return (
          <li key={i} className="flex items-center gap-2.5 text-[13.5px] rise" style={{ color: s.done ? "var(--ink-3)" : "var(--ink-2)" }}>
            <span className="inline-flex w-4 h-4 items-center justify-center flex-shrink-0">
              {s.done ? <Check className="w-3.5 h-3.5" strokeWidth={2.25} style={{ color: "var(--accent)" }} /> : <span className="spinner" />}
            </span>
            <Icon className="w-3.5 h-3.5 flex-shrink-0" strokeWidth={1.75} />
            <span className="truncate tnum">{s.done ? labelFor(s) : labelFor(s).replace(/^Searched/, "Searching").replace(/^Read/, "Reading")}</span>
          </li>
        );
      })}
    </ol>
  );
};
