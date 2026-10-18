// Splits assistant answer text into segments, turning any substring that exactly
// matches a known citation string into a clickable chip token. Also does light
// inline markdown (**bold**, `code`). Block structure (paragraphs, bullets) is
// handled by the renderer component.

function escapeRegExp(s) {
  return s.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
}

// Returns an array of { type: 'text'|'citation', value, citation? }
export function segmentWithCitations(text, citations = []) {
  if (!citations.length) return [{ type: "text", value: text }];
  // Citations wrapped in [ ... ] in the answer. Build an ordered pattern.
  const unique = [...new Set(citations.map((c) => c.citation).filter(Boolean))];
  if (!unique.length) return [{ type: "text", value: text }];
  const sorted = unique.sort((a, b) => b.length - a.length);
  const pattern = new RegExp(`\\[?(${sorted.map(escapeRegExp).join("|")})\\]?`, "g");

  const segments = [];
  let last = 0;
  let m;
  while ((m = pattern.exec(text)) !== null) {
    if (m.index > last) segments.push({ type: "text", value: text.slice(last, m.index) });
    const matched = m[1];
    const cit = citations.find((c) => c.citation === matched);
    segments.push({ type: "citation", value: matched, citation: cit });
    last = m.index + m[0].length;
  }
  if (last < text.length) segments.push({ type: "text", value: text.slice(last) });
  return segments;
}

// Parse answer into blocks for rendering: headings, rules, paragraphs and
// bullet / numbered lists.
export function parseBlocks(text) {
  const lines = text.split("\n");
  const blocks = [];
  let para = [];
  let list = [];
  let listType = "ul";

  const flushPara = () => {
    if (para.length) { blocks.push({ type: "p", text: para.join(" ") }); para = []; }
  };
  const flushList = () => {
    if (list.length) { blocks.push({ type: listType, items: [...list] }); list = []; }
  };
  const pushItem = (type, item) => {
    flushPara();
    if (list.length && listType !== type) flushList();
    listType = type;
    list.push(item);
  };

  for (const raw of lines) {
    const line = raw.trimEnd();
    const heading = line.match(/^\s{0,3}(#{1,6})\s+(.*?)\s*#*\s*$/);
    if (heading) {
      flushPara();
      flushList();
      blocks.push({ type: "h", level: heading[1].length, text: heading[2] });
    } else if (/^\s{0,3}([-*_])(\s*\1){2,}\s*$/.test(line)) {
      flushPara();
      flushList();
      blocks.push({ type: "hr" });
    } else if (/^\s*[-*+]\s+/.test(line)) {
      pushItem("ul", line.replace(/^\s*[-*+]\s+/, ""));
    } else if (/^\s*\d+[.)]\s+/.test(line)) {
      pushItem("ol", line.replace(/^\s*\d+[.)]\s+/, ""));
    } else if (line.trim() === "") {
      flushPara();
      flushList();
    } else {
      flushList();
      para.push(line);
    }
  }
  flushPara();
  flushList();
  return blocks;
}

export function shortCitation(cit) {
  if (!cit) return "source";
  const label = cit.citation || "";
  const m = label.match(/p\.\s*([\w-]+)/);
  const author = label.split("(")[0].trim().replace(/\.$/, "");
  return `${author}${m ? `, p. ${m[1]}` : ""}`.trim() || "source";
}
