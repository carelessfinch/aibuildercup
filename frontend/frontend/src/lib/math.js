// MathJax 3 is loaded from a pinned CDN build; chat answers use TeX delimiters.
export const MATHJAX_SRC = "https://cdn.jsdelivr.net/npm/mathjax@3.2.2/es5/tex-chtml.js";

export const MATHJAX_CONFIG = {
  tex: {
    inlineMath: [["$", "$"], ["\\(", "\\)"]],
    displayMath: [["$$", "$$"], ["\\[", "\\]"]],
    processEscapes: true, // "\$" stays a literal dollar sign
  },
  options: { skipHtmlTags: ["script", "noscript", "style", "textarea", "pre", "code"] },
};

// Display math first so "$$…$$" is not read as two inline spans.
// Escaped "\$" never opens or closes a span.
export const MATH_SPAN = /((?<!\\)\$\$[\s\S]+?(?<!\\)\$\$|\\\[[\s\S]+?\\\]|\\\([\s\S]+?\\\)|(?<!\\)\$[^$\n]+?(?<!\\)\$)/g;

export const hasMath = (text) => typeof text === "string" && new RegExp(MATH_SPAN.source).test(text);
