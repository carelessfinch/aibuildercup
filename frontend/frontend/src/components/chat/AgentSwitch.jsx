import { BookOpen, ClipboardCheck } from "lucide-react";
import { AGENTS } from "@/lib/sources";

const ICONS = { literature_assistant: BookOpen, professor_reviewer: ClipboardCheck };
const TEST_IDS = { literature_assistant: "agent-picker-literature", professor_reviewer: "agent-picker-reviewer" };

export const AgentSwitch = ({ value, onChange, disabled }) => (
  <div
    role="radiogroup"
    aria-label="Agent"
    className="inline-flex items-center p-0.5 rounded-md"
    style={{ background: "var(--paper-2)" }}
  >
    {Object.values(AGENTS).map((a) => {
      const Icon = ICONS[a.id];
      const active = a.id === value;
      return (
        <button
          key={a.id}
          type="button"
          role="radio"
          aria-checked={active}
          title={a.description}
          data-testid={TEST_IDS[a.id]}
          disabled={disabled}
          onClick={() => onChange(a.id)}
          className="inline-flex h-10 items-center gap-1.5 rounded-md px-3 text-[12.5px] font-medium disabled:opacity-50 md:h-8"
          style={{
            background: active ? "var(--paper)" : "transparent",
            color: active ? "var(--ink)" : "var(--ink-2)",
            boxShadow: active ? "var(--shadow-sm)" : "none",
            transition: "background-color 160ms var(--ease-out), color 160ms var(--ease-out), box-shadow 160ms var(--ease-out)",
          }}
        >
          <Icon className="w-3.5 h-3.5" strokeWidth={1.75} style={{ color: active ? "var(--accent)" : "var(--ink-3)" }} />
          {a.short}
        </button>
      );
    })}
  </div>
);
