import { ArrowUpRight } from "lucide-react";
import { AGENTS, QUICK_PROMPTS } from "@/lib/sources";
import { useIndexedSources } from "@/hooks/useIndexedSources";

export const EmptyState = ({ agentId, onPrompt, onOpenSource, disabled }) => {
  const sources = useIndexedSources();
  const agent = AGENTS[agentId];
  return (
    <div className="mx-auto w-full max-w-[72ch] px-4 pb-10 pt-10 sm:px-6 md:px-8 md:pt-14 rise">
      <h1
        className="font-serif-read font-semibold text-[32px] sm:text-[38px] leading-[1.12] tracking-[-0.015em]"
        style={{ color: "var(--ink)", textWrap: "balance" }}
      >
        {agent.heading}
      </h1>
      <p className="mt-4 text-[16px] leading-relaxed" style={{ color: "var(--ink-2)", maxWidth: "62ch" }}>
        {agent.lede}
      </p>

      <ul className="mt-9 divide-y" style={{ borderColor: "var(--rule)" }}>
        {QUICK_PROMPTS[agentId].map((p, i) => (
          <li key={p} style={{ borderColor: "var(--rule)" }}>
            <button
              type="button"
              data-testid={`quick-prompt-chip-${i}`}
              disabled={disabled}
              onClick={() => onPrompt(p)}
              className="group flex w-full items-center justify-between gap-6 py-3 text-left text-[15px] disabled:opacity-50"
              style={{ color: "var(--ink)" }}
            >
              <span className="group-hover:underline underline-offset-4 decoration-1" style={{ textDecorationColor: "var(--rule-2)" }}>{p}</span>
              <ArrowUpRight className="w-4 h-4 flex-shrink-0 opacity-0 -translate-x-1 group-hover:opacity-100 group-hover:translate-x-0" style={{ color: "var(--accent)", transition: "opacity 160ms var(--ease-out), transform 160ms var(--ease-out)" }} />
            </button>
          </li>
        ))}
      </ul>

      {/* The per-source list is hidden: at 200+ works it buried the prompts. */}
      <p className="mt-12 text-[13px] font-semibold" style={{ color: "var(--ink-2)" }}>
        Indexed corpus — {sources.length} works, {sources.reduce((n, s) => n + s.pages, 0).toLocaleString()} pages
      </p>
    </div>
  );
};
