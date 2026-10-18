import { Fragment } from "react";
import { MathJax } from "better-react-mathjax";
import { segmentWithCitations, parseBlocks } from "@/lib/format";
import { MATH_SPAN, hasMath } from "@/lib/math";
import { CitationChip } from "./CitationChip";

// Renders inline markdown (**bold**, `code`) and citation chips within a text run.
function InlineRun({ text, citations, onOpenSource }) {
  const segments = segmentWithCitations(text, citations);
  return (
    <>
      {segments.map((seg, i) => {
        if (seg.type === "citation") {
          return <CitationChip key={i} citation={seg.citation} index={i} />;
        }
        return <InlineMarkdown key={i} text={seg.value} />;
      })}
    </>
  );
}

// TeX spans pass through untouched (so "a*b" in a formula is not italics);
// MathJax typesets them after render.
function InlineMarkdown({ text }) {
  return (
    <>
      {text.split(MATH_SPAN).map((part, i) =>
        i % 2 === 1 ? <Fragment key={i}>{part}</Fragment> : <PlainMarkdown key={i} text={part} />
      )}
    </>
  );
}

function PlainMarkdown({ text }) {
  const parts = text.split(/(\*\*[^*]+\*\*|\*[^*\s][^*]*\*|`[^`]+`)/g);
  return (
    <>
      {parts.map((p, i) => {
        if (/^\*\*[^*]+\*\*$/.test(p)) return <strong key={i}>{p.slice(2, -2)}</strong>;
        if (/^\*[^*]+\*$/.test(p)) return <em key={i}>{p.slice(1, -1)}</em>;
        if (/^`[^`]+`$/.test(p)) return <code key={i}>{p.slice(1, -1)}</code>;
        return <Fragment key={i}>{p}</Fragment>;
      })}
    </>
  );
}

export const MessageContent = ({ text, citations = [], onOpenSource, streaming }) => {
  const blocks = parseBlocks(text);
  const body = (
    <div className={`prose-chat ${streaming ? "caret-stream" : ""}`}>
      {blocks.map((b, i) => {
        if (b.type === "h") {
          // "#" → h2 … "####"+ → h5; the page title owns h1.
          const Tag = `h${Math.min(b.level + 1, 5)}`;
          return <Tag key={i}><InlineRun text={b.text} citations={citations} onOpenSource={onOpenSource} /></Tag>;
        }
        if (b.type === "hr") return <hr key={i} />;
        if (b.type === "ul" || b.type === "ol") {
          const List = b.type;
          return (
            <List key={i}>
              {b.items.map((it, j) => (
                <li key={j}><InlineRun text={it} citations={citations} onOpenSource={onOpenSource} /></li>
              ))}
            </List>
          );
        }
        return (
          <p key={i}><InlineRun text={b.text} citations={citations} onOpenSource={onOpenSource} /></p>
        );
      })}
    </div>
  );
  // Only messages with TeX pay for typesetting; dynamic re-typesets while streaming.
  return hasMath(text) ? <MathJax dynamic>{body}</MathJax> : body;
};
