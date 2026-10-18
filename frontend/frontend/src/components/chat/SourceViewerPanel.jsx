import { useEffect, useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { X } from "lucide-react";
import { toast } from "sonner";
import { Dialog, DialogContent, DialogTitle, DialogDescription } from "@/components/ui/dialog";
import { api } from "@/lib/api";
import { useIndexedSources } from "@/hooks/useIndexedSources";

const useBelowLg = () => {
  const [belowLg, setBelowLg] = useState(() => window.matchMedia("(max-width: 1023px)").matches);
  useEffect(() => {
    const query = window.matchMedia("(max-width: 1023px)");
    const changed = () => setBelowLg(query.matches);
    query.addEventListener("change", changed);
    return () => query.removeEventListener("change", changed);
  }, []);
  return belowLg;
};

const SourceBody = ({ citation, src, onClose }) => {
  const [pages, setPages] = useState([]);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    if (!citation) return;
    const [first, last] = citation.pdf_pages || [1, 1];
    setLoading(true);
    setPages([]);
    api.getPages(citation.source_id, first, last)
      .then((r) => setPages(r.pages || []))
      .catch((e) => toast.error(e.message || "Could not load pages"))
      .finally(() => setLoading(false));
  }, [citation]);

  const copyBibtex = () => {
    const bib = `@book{${citation.source_id},\n  title={${src?.title || ""}},\n  author={${src?.authors || ""}},\n  year={${src?.year || ""}}\n}`;
    navigator.clipboard.writeText(bib);
    toast.success("BibTeX copied");
  };

  return (
    <div className="flex h-full min-h-0 flex-col">
      <header className="flex items-start justify-between gap-3 border-b px-4 pb-4 pt-5 md:px-6" style={{ borderColor: "var(--rule)", paddingTop: "max(1.25rem, env(safe-area-inset-top))" }}>
        <div className="min-w-0">
          <h2 className="font-serif-read text-[17px] font-semibold leading-snug tracking-[-0.01em] break-words" style={{ color: "var(--ink)", textWrap: "balance" }}>
            {src?.title || citation.source_id}
          </h2>
          <p className="mt-1 text-[13px] tnum break-words" style={{ color: "var(--ink-2)" }}>
            {src?.authors}{src?.year ? `, ${src.year}` : ""}
          </p>
          {citation.section && <p className="mt-0.5 text-[12.5px] break-words" style={{ color: "var(--ink-3)" }}>{citation.section}</p>}
          <div className="mt-3 flex flex-wrap items-center gap-3">
            <button type="button" onClick={copyBibtex} className="text-btn min-h-[36px]">Copy BibTeX</button>
            {citation.snippet && <button type="button" onClick={() => { navigator.clipboard.writeText(citation.snippet); toast.success("Passage copied"); }} className="text-btn min-h-[36px]">Copy passage</button>}
          </div>
        </div>
        <button type="button" data-testid="close-source-viewer" onClick={onClose} aria-label="Close source reader" className="icon-btn !h-10 !w-10 flex-shrink-0 md:!h-8 md:!w-8">
          <X className="h-4 w-4" />
        </button>
      </header>

      <div className="min-h-0 flex-1 overflow-y-auto px-4 py-5 md:px-6">
        {citation.snippet && (
          <blockquote className="mb-6 rounded-md px-4 py-3.5" style={{ background: "var(--accent-soft)" }}>
            <p className="mb-1.5 text-[12.5px] font-semibold" style={{ color: "var(--accent)" }}>Cited passage</p>
            <p className="font-serif-read text-[15px] italic leading-relaxed break-words" style={{ color: "var(--ink)" }}>{citation.snippet}</p>
          </blockquote>
        )}
        {loading && (
          <p className="flex items-center gap-2.5 py-4 text-[13.5px]" style={{ color: "var(--ink-3)" }}>
            <span className="spinner" /> Loading pages…
          </p>
        )}
        {pages.map((pg, i) => (
          <section key={i} className={i > 0 ? "mt-6 border-t pt-6" : ""} style={{ borderColor: "var(--rule)" }}>
            <p className="mb-2 text-[12px] font-semibold tnum" style={{ color: "var(--ink-3)" }}>Page {pg.pdf_page}</p>
            <p className="font-serif-read text-[15px] leading-[1.7] whitespace-pre-wrap break-words" style={{ color: "var(--ink)" }}>{pg.text}</p>
          </section>
        ))}
      </div>
    </div>
  );
};

export const SourceViewerPanel = ({ citation, onClose }) => {
  const belowLg = useBelowLg();
  const sources = useIndexedSources();
  const src = citation ? sources.find((s) => s.source_id === citation.source_id) : null;

  return (
    <>
      <AnimatePresence>
        {citation && !belowLg && (
          <motion.aside
            data-testid="source-viewer-panel"
            aria-label="Source reader"
            initial={{ x: 40, opacity: 0 }}
            animate={{ x: 0, opacity: 1 }}
            exit={{ x: 40, opacity: 0 }}
            transition={{ duration: 0.32, ease: [0.16, 1, 0.3, 1] }}
            className="hidden h-dvh w-[400px] flex-shrink-0 flex-col border-l lg:flex"
            style={{ background: "var(--paper)", borderColor: "var(--rule)" }}
          >
            <SourceBody citation={citation} src={src} onClose={onClose} />
          </motion.aside>
        )}
      </AnimatePresence>

      <Dialog open={Boolean(citation && belowLg)} onOpenChange={(open) => !open && onClose()}>
        <DialogContent
          data-testid="source-viewer-panel"
          className="h-dvh w-screen max-w-none translate-x-0 translate-y-0 left-0 top-0 rounded-none border-0 p-0 gap-0 overflow-hidden data-[state=open]:slide-in-from-right data-[state=closed]:slide-out-to-right [&>button]:hidden"
          style={{ background: "var(--paper)" }}
        >
          {citation && (
            <>
              <DialogTitle className="sr-only">Source reader</DialogTitle>
              <DialogDescription className="sr-only">Read the cited source pages</DialogDescription>
              <SourceBody citation={citation} src={src} onClose={onClose} />
            </>
          )}
        </DialogContent>
      </Dialog>
    </>
  );
};
