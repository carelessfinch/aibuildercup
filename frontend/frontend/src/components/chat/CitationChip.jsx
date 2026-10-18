import { shortCitation } from "@/lib/format";

// Citations are plain text: the source reader is not reachable from answers.
// The full reference shows as a native tooltip.
export const CitationChip = ({ citation, index }) => {
  const id = citation?.source_id || index;
  return (
    <span data-testid={`citation-chip-${id}`} className="cite-plain" title={citation?.citation || undefined}>
      ({shortCitation(citation)})
    </span>
  );
};
