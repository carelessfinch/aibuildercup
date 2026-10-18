import { useState } from "react";
import { Search } from "lucide-react";
import { toast } from "sonner";
import { Dialog, DialogContent, DialogTitle, DialogDescription } from "@/components/ui/dialog";
import { api } from "@/lib/api";

// The source reader is hidden from search results; flip to re-enable.
const SHOW_OPEN_PAGES = false;

export const LiteratureSearchModal = ({ open, onClose, selectedSources, onOpenSource, onInsert }) => {
  const [query, setQuery] = useState("");
  const [results, setResults] = useState(null);
  const [loading, setLoading] = useState(false);

  const run = async () => {
    if (!query.trim()) return;
    setLoading(true);
    try {
      const body = { query: query.trim(), top_k: 6, source_ids: selectedSources.length ? selectedSources : null, kind: null };
      const r = await api.search(body);
      setResults(r.results || []);
    } catch (e) {
      toast.error(e.message || "Search failed");
    } finally {
      setLoading(false);
    }
  };

  return (
    <Dialog open={open} onOpenChange={(o) => !o && onClose()}>
      <DialogContent
        className="left-0 top-0 h-dvh w-screen max-w-none translate-x-0 translate-y-0 rounded-none border-0 p-0 gap-0 overflow-hidden sm:left-1/2 sm:top-1/2 sm:h-auto sm:w-full sm:max-w-2xl sm:-translate-x-1/2 sm:-translate-y-1/2 sm:rounded-xl [&>button]:right-4 [&>button]:top-4 [&>button]:h-10 [&>button]:w-10 [&>button]:opacity-100 [&>button]:text-[var(--ink-3)] [&>button:hover]:text-[var(--ink)]"
        style={{ background: "var(--paper)", borderColor: "var(--rule-2)", boxShadow: "var(--shadow-lg)" }}
      >
        <DialogTitle className="sr-only">Search literature</DialogTitle>
        <DialogDescription className="sr-only">Search passages across the indexed plasma physics books and papers</DialogDescription>

        <div className="flex items-center gap-3 pl-5 pr-14 py-3.5 border-b" style={{ borderColor: "var(--rule)" }}>
          <Search className="w-4 h-4 flex-shrink-0" strokeWidth={1.75} style={{ color: "var(--ink-3)" }} />
          <input
            autoFocus
            data-testid="literature-search-input"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && run()}
            placeholder={selectedSources.length ? `Search within ${selectedSources.length} selected sources…` : "Search passages across all indexed works…"}
            aria-label="Search query"
            className="flex-1 bg-transparent text-[16px] focus:outline-none"
            style={{ color: "var(--ink)" }}
          />
          <button
            type="button"
            data-testid="run-literature-search"
            onClick={run}
            disabled={loading || !query.trim()}
            className="h-8 px-3.5 rounded-md text-[13px] font-semibold disabled:opacity-40"
            style={{ background: "var(--accent)", color: "var(--paper)" }}
          >
            {loading ? "Searching…" : "Search"}
          </button>
        </div>

        <div className="max-h-[calc(100dvh-72px)] overflow-y-auto px-4 sm:max-h-[62vh] sm:px-5">
          {results === null && !loading && (
            <p className="py-10 text-[14px]" style={{ color: "var(--ink-3)" }}>
              Returns the best-matching passages with their page numbers. Insert a passage into your message to ask about it.
            </p>
          )}
          {results?.length === 0 && !loading && (
            <p className="py-10 text-[14px]" style={{ color: "var(--ink-3)" }}>No passages matched “{query}”. Try different terms.</p>
          )}
          {results?.map((r, i) => (
            <article key={i} data-testid={`search-result-${i}`} className={`py-5 ${i > 0 ? "border-t" : ""}`} style={{ borderColor: "var(--rule)" }}>
              <div className="flex items-baseline justify-between gap-4 mb-2">
                <p className="text-[12.5px] font-semibold truncate" style={{ color: "var(--accent)" }}>{r.section}</p>
                <p className="text-[12px] tnum flex-shrink-0" style={{ color: "var(--ink-3)" }}>relevance {r.score?.toFixed(2)}</p>
              </div>
              <p className="font-serif-read text-[15px] leading-[1.65]" style={{ color: "var(--ink)" }}>{r.text}</p>
              <p className="mt-2 text-[12.5px]" style={{ color: "var(--ink-3)" }}>{r.citation}</p>
              <div className="flex items-center gap-5 mt-3">
                {SHOW_OPEN_PAGES && (
                  <button
                    type="button"
                    onClick={() => onOpenSource({ source_id: r.source_id, pdf_pages: r.pdf_pages, section: r.section, citation: r.citation, snippet: r.text })}
                    className="text-btn"
                  >
                    Open pages
                  </button>
                )}
                <button type="button" onClick={() => { onInsert(r.text); onClose(); }} className="text-btn quiet">
                  Insert into message
                </button>
              </div>
            </article>
          ))}
        </div>
      </DialogContent>
    </Dialog>
  );
};
