import { MathJax } from "better-react-mathjax";
import { hasMath } from "@/lib/math";

// Short text (a transcript line, a rubric value) with TeX typeset in place.
// Only strings that contain TeX pay for MathJax.
export function MathText({ text, as: Tag = "span", className, style }) {
  const value = text == null ? "" : String(text);
  const content = <Tag className={className} style={style}>{value}</Tag>;
  return hasMath(value) ? <MathJax inline dynamic>{content}</MathJax> : content;
}
