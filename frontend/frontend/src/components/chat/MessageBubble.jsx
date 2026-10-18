import { AGENTS } from "@/lib/sources";
import { MessageContent } from "./MessageContent";
import { ToolCallIndicator } from "./ToolCallIndicator";

const VERDICT = {
  PASS: { color: "var(--pass)", bg: "var(--pass-soft)", label: "Pass" },
  REVISE: { color: "var(--revise)", bg: "var(--revise-soft)", label: "Revise" },
  ESCALATE: { color: "var(--escalate)", bg: "var(--escalate-soft)", label: "Escalate" },
};

function extractVerdict(text) {
  const m = text.match(/^\s*VERDICT:\s*(PASS|REVISE|ESCALATE)\b/i);
  if (!m) return { verdict: null, body: text };
  return { verdict: m[1].toUpperCase(), body: text.replace(/^\s*VERDICT:\s*(PASS|REVISE|ESCALATE)\s*\n*/i, "") };
}

export const MessageBubble = ({ message, onOpenSource }) => {
  if (message.role === "user") {
    return (
      <div className="flex justify-end">
        <div className="max-w-[82%] min-w-0 rounded-lg px-4 py-2.5" style={{ background: "var(--paper-2)" }}>
          <p className="text-[15.5px] leading-relaxed whitespace-pre-wrap" style={{ color: "var(--ink)" }}>{message.content}</p>
        </div>
      </div>
    );
  }

  const agent = AGENTS[message.agent] || AGENTS.literature_assistant;
  const { verdict, body } = extractVerdict(message.content || "");
  const v = verdict ? VERDICT[verdict] : null;

  return (
    <article>
      <header className="flex items-baseline gap-2 mb-2.5">
        <span className="text-[12.5px] font-semibold" style={{ color: "var(--ink-2)" }}>{agent.name}</span>
        {message.model && <span className="text-[12px]" style={{ color: "var(--ink-4)" }}>{message.model}</span>}
      </header>

      <ToolCallIndicator steps={message.toolSteps} />

      {verdict && (
        <p
          data-testid="reviewer-verdict-badge"
          className="inline-flex items-baseline gap-2 mb-4 px-3 py-1.5 rounded-md text-[14px] font-semibold"
          style={{ color: v.color, background: v.bg }}
        >
          <span className="font-normal" style={{ color: "var(--ink-2)" }}>Verdict</span>
          {v.label.toUpperCase()}
        </p>
      )}

      {body ? (
        <MessageContent text={body} citations={message.citations} onOpenSource={onOpenSource} streaming={message.streaming} />
      ) : message.streaming ? (
        <p className="flex items-center gap-2.5 text-[13.5px]" style={{ color: "var(--ink-3)" }}>
          <span className="spinner" /> Working…
        </p>
      ) : null}

      {!message.streaming && message.citations?.length > 0 && (
        <footer className="mt-5 pt-3 border-t" style={{ borderColor: "var(--rule)" }}>
          <p className="text-[12.5px] mb-1.5" style={{ color: "var(--ink-3)" }}>
            {message.citations.length === 1 ? "1 passage cited" : `${message.citations.length} passages cited`}
          </p>
          <ul className="space-y-1">
            {message.citations.map((c, i) => (
              <li
                key={i}
                data-testid={`source-ref-${c.source_id}-${i}`}
                className="text-[13.5px] leading-snug break-words"
                style={{ color: "var(--ink-2)" }}
              >
                {c.citation}
              </li>
            ))}
          </ul>
        </footer>
      )}
    </article>
  );
};
