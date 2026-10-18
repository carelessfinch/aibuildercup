import { useRef, useEffect } from "react";
import { ArrowUp, Square } from "lucide-react";
import { AGENTS } from "@/lib/sources";
import { AgentSwitch } from "./AgentSwitch";

export const Composer = ({ value, onChange, onSend, onStop, streaming, agentId, onAgentChange }) => {
  const ref = useRef(null);
  const agent = AGENTS[agentId];
  const canSend = !streaming && value.trim().length > 0;

  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    el.style.height = "auto";
    el.style.height = Math.min(el.scrollHeight, 220) + "px";
  }, [value]);

  const handleKey = (e) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      if (canSend) onSend();
    }
  };

  return (
    <div className="px-4 pb-5 pt-2 sm:px-6 md:px-8" style={{ background: "linear-gradient(to bottom, transparent, var(--paper) 28%)", paddingBottom: "max(1.25rem, calc(env(safe-area-inset-bottom) + 0.75rem))" }}>
      <div className="mx-auto" style={{ maxWidth: "72ch" }}>
        <div
          className="rounded-xl border"
          style={{
            background: "var(--paper)",
            borderColor: "var(--rule-2)",
            boxShadow: "var(--shadow-md)",
            transition: "border-color 160ms var(--ease-out), box-shadow 160ms var(--ease-out)",
          }}
          onFocusCapture={(e) => { e.currentTarget.style.borderColor = "var(--accent)"; }}
          onBlurCapture={(e) => { e.currentTarget.style.borderColor = "var(--rule-2)"; }}
        >
          <textarea
            ref={ref}
            data-testid="chat-message-input"
            rows={1}
            value={value}
            onChange={(e) => onChange(e.target.value)}
            onKeyDown={handleKey}
            placeholder={agent.placeholder}
            aria-label="Message"
            className="block w-full resize-none bg-transparent px-4 pt-3.5 pb-2 text-[15.5px] leading-relaxed focus:outline-none"
            style={{ color: "var(--ink)", minHeight: 48 }}
          />
          <div className="flex items-center justify-between px-2.5 pb-2.5 pt-1">
            <AgentSwitch value={agentId} onChange={onAgentChange} disabled={streaming} />
            {streaming ? (
              <button
                type="button"
                data-testid="stop-streaming-button"
                onClick={onStop}
                aria-label="Stop generating"
                className="inline-flex h-10 w-10 items-center justify-center rounded-full md:h-9 md:w-9"
                style={{ background: "var(--ink)", color: "var(--paper)" }}
              >
                <Square className="w-3 h-3" fill="currentColor" />
              </button>
            ) : (
              <button
                type="button"
                data-testid="send-message-button"
                onClick={onSend}
                disabled={!canSend}
                aria-label="Send message"
                className="inline-flex h-10 w-10 items-center justify-center rounded-full disabled:cursor-not-allowed md:h-9 md:w-9"
                style={{
                  background: canSend ? "var(--accent)" : "var(--paper-3)",
                  color: canSend ? "var(--paper)" : "var(--ink-4)",
                  transition: "background-color 160ms var(--ease-out), color 160ms var(--ease-out)",
                }}
              >
                <ArrowUp className="w-4 h-4" strokeWidth={2.25} />
              </button>
            )}
          </div>
        </div>
        <p className="mt-2 text-[12px]" style={{ color: "var(--ink-3)" }}>
          Enter to send, Shift+Enter for a new line. Verify citations before relying on them.
        </p>
      </div>
    </div>
  );
};
