"""PDF -> cleaned per-page text, with printed page labels (books) and section titles (PDF outline)."""
import math
import re
from collections import Counter

import pypdfium2 as pdfium

from .textutil import fix_ligatures

# Publisher cover pages that list unrelated articles (AIP, IOP).
COVER_MARKERS = (
    ("View Online", "Export Citation", "Articles You May Be Interested In"),
    ("To cite this article", "You may also like"),
)
BACK_MATTER = {"CONTENTS", "INDEX", "REFERENCES", "BIBLIOGRAPHY", "PREFACE", "PREFACE TO THE FIRST EDITION",
               "PREFACE TO THE SECOND EDITION", "ACKNOWLEDGMENTS"}
REFERENCE_HEADINGS = re.compile(r"^(references|references and notes|bibliography)$", re.I)
_SOFT_HYPHEN = re.compile(r"(\w+)￾\s*(\w+)")
_HYPHENATED = re.compile(r"\b(\w+)-(\w+)\b")
_WORD = re.compile(r"\w+")
_PRIVATE_USE = re.compile("[\ue000-\uf8ff]")
_PAGE_NUM_LINE = re.compile(r"^(?:(\d{1,4})\s+[A-Z][A-Z0-9 ,.:;&'()/-]{2,80}|[A-Z0-9][A-Z0-9 ,.:;&'()/-]{2,80}?\s+(\d{1,4})|(\d{1,4}))$")


_SAFE_SYMBOLS = str.maketrans({"\u00fe": "+"})  # "þ" is how MathPi "+" extracts (AIP, Wiley)


def fix_symbols(text, scheme=None):
    """Undo common symbol-font mis-mappings. scheme="wiley_mathpi" applies the full map for
    Wiley books such as Lieberman & Lichtenberg, where every "=" in the text is really "/"."""
    if scheme == "wiley_mathpi":
        text = text.replace("=", "/").replace("\u00bc", "=").replace("\u00f0", "(").replace("\u00de", ")")
        text = text.replace("\u00bd", "[").replace("@", "\u2202")
        text = re.sub(r"(?<=[a-z])\x02(?=[a-z])", "\ufffe", text)  # line-break hyphen inside a word
        text = re.sub(r"(?<=\d) [\x01\x04\x05] (?=\d)", " \u00d7 ", text)  # 1.6 x 10
        text = re.sub(r" \x01 (?=[A-Z])", " \u00d7 ", text)  # E x B
        text = re.sub(r"\x01(?=\d)", "\u2212", text)  # exponent sign: 10^-19, m^-3
        text = re.sub(r" [\x02\x03] ", " \u2212 ", text)  # binary minus
        text = re.sub(r"(?<=\d):(?=\d)", ".", text)  # 1:602 -> 1.602, (4:4:12) -> (4.4.12)
        text = re.sub(r"(?<=\w) \. (?=\w)", " > ", text)
        text = re.sub(r"(?<=\w) , (?=\w)", " < ", text)
        text = re.sub(r"(?<=\w) \? (?=\w)", " \u22a5 ", text)  # k ? B0 -> k perpendicular B0
        text = re.sub(r"\b(?:ffi){2,}\w*", "\u221a", text)  # square-root bar artefacts
        text = text.translate(str.maketrans({"\x02": "\u2212", "\x04": "\u226b", "\x05": "\u00d7", "\x06": "\u00b7", "\x03": "\u00b7"}))
        text = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f]", " ", text)
    return text.translate(_SAFE_SYMBOLS).replace(" \u00bc ", " = ")


def _norm_line(line):
    return re.sub(r"\s+", " ", re.sub(r"\d", "#", line.strip()))


def _read_pdf(path):
    pdf = pdfium.PdfDocument(path)
    try:
        texts = []
        for i in range(len(pdf)):
            page = pdf[i]
            tp = page.get_textpage()
            texts.append(tp.get_text_range())
            tp.close()
            page.close()
        toc = []
        for bm in pdf.get_toc():
            dest = bm.get_dest()
            index = dest.get_index() if dest else None
            if index is not None:
                toc.append((bm.level, bm.get_title(), index))
    finally:
        pdf.close()
    return texts, toc


def _fix_soft_hyphens(texts):
    """pdfium marks end-of-line hyphens with U+FFFE; keep the hyphen only if the doc uses the hyphenated form."""
    full = "\n".join(texts)
    words = Counter(w.lower() for w in _WORD.findall(full.replace("￾", " ")))
    hyph = Counter(f"{a}-{b}".lower() for a, b in _HYPHENATED.findall(full))

    def repl(m):
        a, b = m.group(1), m.group(2)
        if hyph[f"{a}-{b}".lower()] and not words[(a + b).lower()]:
            return f"{a}-{b}"
        return a + b

    return [_SOFT_HYPHEN.sub(repl, t).replace("￾", "-") for t in texts]


def _sections(toc, n_pages):
    """Breadcrumb ("Chapter > Section") per 0-based page index from the PDF outline."""
    if not toc:
        return [None] * n_pages
    roots = [t for t in toc if t[0] == min(x[0] for x in toc)]
    drop_root = len(roots) == 1  # a paper's outline root is just its title
    out, stack, j = [], {}, 0
    toc = sorted(toc, key=lambda t: t[2])
    for p in range(n_pages):
        while j < len(toc) and toc[j][2] <= p:
            level, title, _ = toc[j]
            stack = {lv: tt for lv, tt in stack.items() if lv < level}
            stack[level] = " ".join(title.split())
            j += 1
        crumbs = [stack[lv] for lv in sorted(stack) if not (drop_root and lv == roots[0][0])]
        out.append(" > ".join(crumbs[-3:]) or None)
    return out


def _page_labels(lines_per_page):
    """Printed page numbers for books: detect numbers in running heads/feet, smooth the PDF-to-print offset."""
    n = len(lines_per_page)
    detected = [None] * n
    prev = None
    for i, lines in enumerate(lines_per_page):
        cands = []
        for line in lines[:3] + lines[-3:]:
            m = _PAGE_NUM_LINE.match(line.strip())
            if m:
                num = int(next(g for g in m.groups() if g))
                if 0 < num <= i + 1:
                    cands.append(i + 1 - num)
        if cands:
            detected[i] = min(cands, key=lambda o: abs(o - prev)) if prev is not None else Counter(cands).most_common(1)[0][0]
            prev = detected[i]
    if sum(d is not None for d in detected) < max(5, 0.2 * n):
        return [None] * n
    mode = Counter(d for d in detected if d is not None).most_common(1)[0][0]
    detected = [d if d is not None and abs(d - mode) <= 3 else None for d in detected]
    labels = []
    for i in range(n):
        window = [d for d in detected[max(0, i - 10): i + 11] if d is not None]
        if not window:
            labels.append(None)
            continue
        off = Counter(window).most_common(1)[0][0]
        labels.append(str(i + 1 - off) if i + 1 - off >= 1 else None)
    return labels


def _strip_running_lines(lines_per_page, is_book):
    """Drop headers/footers: lines near the top/bottom whose digit-normalised form repeats across pages."""
    n = len(lines_per_page)
    edge = lambda ls: ls[:6] + ls[-6:]
    counts = Counter()
    for ls in lines_per_page:
        counts.update({_norm_line(l) for l in edge(ls)})
    threshold = 3 if is_book else max(3, math.ceil(0.4 * n))
    out = []
    for ls in lines_per_page:
        top, bottom = set(range(min(6, len(ls)))), set(range(max(0, len(ls) - 6), len(ls)))
        keep = []
        for k, line in enumerate(ls):
            norm = _norm_line(line)
            at_edge = k in top or k in bottom
            if at_edge and (counts[norm] >= threshold or re.fullmatch(r"[#ivxlc]{1,6}", norm)):
                continue
            if is_book and at_edge and _PAGE_NUM_LINE.match(line.strip()) and line.strip().upper() == line.strip():
                continue  # running head with page number, e.g. "118 PLASMA DYNAMICS"
            keep.append(line)
        out.append(keep)
    return out


def _join_lines(lines):
    """Join PDF lines into running text; keep a newline after short lines that end a sentence."""
    if not lines:
        return ""
    lengths = sorted(len(l) for l in lines)
    typical = lengths[len(lengths) // 2] or 1
    parts = []
    for line in lines:
        line = line.strip()
        if not line:
            continue
        parts.append(line)
        parts.append("\n" if line.endswith((".", ":", "?")) and len(line) < 0.7 * typical else " ")
    text = "".join(parts)
    text = re.sub(r"[ \t ]+", " ", text)
    return re.sub(r" ?\n ?", "\n", text).strip()


def extract_pdf(path, kind="paper", symbol_map=None):
    """Return [{page (1-based PDF page), label (printed page or None), section, text}] for content pages."""
    texts, toc = _read_pdf(path)
    texts = [fix_symbols(_PRIVATE_USE.sub("", fix_ligatures(t.replace("\r\n", "\n").replace("\r", "\n"))), symbol_map) for t in texts]
    texts = _fix_soft_hyphens(texts)
    lines = [[l for l in t.split("\n") if l.strip()] for t in texts]
    is_book = kind == "textbook"
    labels = _page_labels(lines) if is_book else [None] * len(lines)
    if kind == "vendor_model":  # COMSOL docs print the PDF page number in the running head
        labels = [str(i + 1) for i in range(len(lines))]
    first_labeled = next((i for i, lb in enumerate(labels) if lb), 0) if is_book else 0
    sections = _sections(toc, len(lines)) if (toc or not is_book) else _book_sections(lines, first_labeled)
    lines = _strip_running_lines(lines, is_book)
    index_start = len(lines)
    if is_book:  # the subject index at the back only adds noise
        for i in range(int(0.9 * len(lines)), len(lines)):
            if any(l.strip() == "INDEX" for l in lines[i][:3]):
                index_start = i
                break

    pages, in_refs = [], False
    for i, ls in enumerate(lines):
        if is_book and (i < first_labeled or i >= index_start):
            continue  # title pages, preface and contents; index
        raw = " ".join(texts[i].split())
        if i < 2 and any(all(m in raw for m in markers) for markers in COVER_MARKERS):
            continue
        if kind == "paper" and i >= len(lines) // 2:
            for k, l in enumerate(ls):
                if REFERENCE_HEADINGS.match(l.strip()):
                    ls, in_refs = ls[:k], True
                    break
            else:
                if in_refs:
                    continue
        text = _join_lines(ls)
        if len(text) < 40:
            continue
        if is_book and sections[i] and sections[i].split(" > ")[0].strip().upper() in BACK_MATTER:
            continue
        pages.append({"page": i + 1, "label": labels[i], "section": sections[i], "text": text})
    return pages


_BOOK_CHAPTER_HEAD = re.compile(r"^(\d{1,2}|[A-Z])\. ([A-Z][A-Z ,.:;&'()/-]{2,80}?) (\d{1,4})$")
_SECTION_LINE = re.compile(r"^(\d{1,2}\.(?:\d{1,2})?)\s+([A-Z][^=]{2,75})$")


def _looks_like_heading(title):
    title = title.strip()
    if title.endswith((",", ";", ".", ":")) or len(title.split()) > 10:
        return False
    if title.isupper():
        return True
    long_words = [w for w in title.split() if len(w) > 3]
    return bool(long_words) and sum(w[0].isupper() for w in long_words) / len(long_words) >= 0.6


_MAX_SECTION_CARRY = 6  # pages a numbered section may run on without another heading


def _book_sections(lines_per_page, start=0):
    """Breadcrumbs for a scanned book without a PDF outline: chapter from running heads such as
    "3. NONUNIFORM MAGNETOSTATIC FIELDS 79", section from numbered heading lines in the body."""
    n = len(lines_per_page)
    heads = [None] * n
    for i, ls in enumerate(lines_per_page):
        for line in ls[:2] + ls[-2:]:
            m = _BOOK_CHAPTER_HEAD.match(line.strip())
            if m:
                heads[i] = f"{m.group(1)}. {_title(m.group(2))}"
                break
    upcoming, nxt = None, [None] * n
    for i in range(n - 1, -1, -1):
        upcoming = heads[i] or upcoming
        nxt[i] = upcoming
    chapter = section = None
    section_page = 0
    out = []
    for i, ls in enumerate(lines_per_page):
        if i < start:
            out.append(None)
            continue
        if section and section != "Problems" and i - section_page > _MAX_SECTION_CARRY:
            section = None  # the next heading was probably lost in the scan; fall back to the chapter
        first = ls[0].strip() if ls else ""
        opener = (heads[i] is None and len(first) >= 8 and first.upper() == first
                  and not re.search(r"\d", first) and not _PAGE_NUM_LINE.match(first))
        if heads[i] and heads[i] != chapter:
            chapter, section = heads[i], None
        elif opener and nxt[i] and nxt[i] != chapter:
            chapter, section = nxt[i], None  # chapter-opening page has no running head
        page_section = section
        chapter_num = chapter.split(".", 1)[0] if chapter else None
        for k, line in enumerate(ls):
            line = line.strip()
            m = _SECTION_LINE.match(line)
            if line.lower() == "problems" or (
                    chapter_num and line.startswith(f"{chapter_num}.1 ") and len(line) > 40
                    and not (m and _looks_like_heading(m.group(2)))):
                section = "Problems"  # heading, or the first exercise ("10.1 Consider a ...")
            elif m and _looks_like_heading(m.group(2)) and not _BOOK_CHAPTER_HEAD.match(line):
                title = re.sub(r"\s*[-~_'.]{3,}.*$", "", m.group(2)).strip()
                title = re.sub(r"(?<=[A-Za-z]),(?=[A-Za-z])", "", title).rstrip(",;")  # OCR "INTRODUCTI,ON"
                if len(title) < 3:
                    continue
                if chapter and title.lower() == chapter.split(". ", 1)[-1].lower():
                    continue  # the chapter title repeated as a line, not a section
                number = m.group(1).rstrip(".") if m.group(1).count(".") > 1 or not m.group(1).endswith(".") else m.group(1)
                section = f"{number} {_title(title) if title.isupper() else title}"
            else:
                continue
            section_page = i
            if k < len(ls) // 2:
                page_section = section
        out.append(" > ".join(c for c in (chapter, page_section) if c) or None)
    return out


# --- Books supplied as plain text (one page per blank-line-separated block, running head on the last line) ---
_EVEN_HEAD = re.compile(r"^(\d{1,3}) (?=.*[A-Z]{3})([A-Z][A-Z0-9 ,.:;&'()/\-]{2,90})$")
_ODD_HEAD = re.compile(r"^(?=.*[A-Z]{3})([A-Z0-9][A-Z0-9 ,.:;&'()/\-]{2,90}?) (\d{1,3})$")
_ROMAN_HEAD = re.compile(r"^(?:([ivxlc]{1,7})(?: ([A-Z][A-Z ,.:;&'()/-]{2,90}))?|([A-Z][A-Z ,.:;&'()/-]{2,90}) ([ivxlc]{1,7}))$")
_ISBN_FOOTER = re.compile(r"^ISBN [\dX-]+ Copyright")
_SMALL_WORDS = {"and", "of", "in", "the", "for", "to", "a", "an", "on", "with", "by", "at", "or"}
_KEEP_UPPER = {"DC", "RF", "ICP", "CCP", "ECR", "TCP", "MHD", "II", "III", "IV", "EEDF", "IEDF", "MOS", "CVD", "PECVD", "PIII", "UV"}


def _title(head):
    words = head.split()
    out = []
    for k, w in enumerate(words):
        core = w.strip("(),")
        first = k == 0 or (k == 1 and re.fullmatch(r"[\d.]+", words[0]))
        if core in _KEEP_UPPER or any(ch.isdigit() for ch in core):
            out.append(w)
        elif not first and w.lower() in _SMALL_WORDS:
            out.append(w.lower())
        else:
            out.append(w.capitalize() if not w.startswith("(") else "(" + w[1:].capitalize())
    return " ".join(out)
_ROMAN = {"i": 1, "v": 5, "x": 10, "l": 50, "c": 100}


def _roman_to_int(r):
    total = 0
    for a, b in zip(r, r[1:] + " "):
        v = _ROMAN[a]
        total += -v if b != " " and _ROMAN[b] > v else v
    return total


def extract_text_blocks(path, kind="textbook", pdf_page_offset=0, roman_page_offset=0, symbol_map=None):
    """Pages from a plain-text book export where pages are separated by blank lines and each page ends
    with its running head ("118 PLASMA DYNAMICS" / "4.5 WAVES IN MAGNETIZED PLASMAS 117").
    PDF page = printed page + pdf_page_offset (roman front matter: + roman_page_offset)."""
    raw = open(path, encoding="utf-8").read()
    blocks = [b for b in re.split(r"\n[ \t]*\n", fix_ligatures(raw))]
    pages = []  # dicts with block lines and anchor info
    seen_arabic = False
    for b in blocks:
        lines = [l.rstrip() for l in b.strip("\n").split("\n") if l.strip() and not _ISBN_FOOTER.match(l.strip())]
        if not lines:
            continue
        last = lines[-1].strip()
        info = {"lines": lines, "num": None, "roman": None, "chapter": None, "section": None}
        m_even, m_odd, m_rom = _EVEN_HEAD.match(last), _ODD_HEAD.match(last), _ROMAN_HEAD.match(last)
        if m_even:
            info.update(num=int(m_even.group(1)), chapter=m_even.group(2).strip())
        elif m_odd:
            info.update(num=int(m_odd.group(2)), section=m_odd.group(1).strip())
        elif re.fullmatch(r"\d{1,3}", last):
            info.update(num=int(last))
        elif m_rom and not seen_arabic:
            info.update(roman=_roman_to_int(m_rom.group(1) or m_rom.group(4)), chapter=m_rom.group(2) or m_rom.group(3))
        seen_arabic = seen_arabic or info["num"] is not None
        if info["num"] is not None or info["roman"] is not None:
            info["lines"] = lines[:-1]
        pages.append(info)

    # Keep only arabic numbers that continue the sequence (equation lines can look like "1 + ...").
    prev = None
    for p in pages:
        if p["num"] is None:
            continue
        if prev is not None and not (0 < p["num"] - prev <= 4):
            p.update(num=None, chapter=None, section=None)
            continue
        prev = p["num"]

    # Assign PDF page numbers. Anchored pages come from their printed number. Unanchored blocks between two
    # anchors first fill the missing page numbers (chapter openers), and any extra blocks are pieces of the
    # next anchored page (a page split by blank lines inside equations).
    pdf_pages = [None] * len(pages)
    for i, p in enumerate(pages):
        if p["num"] is not None:
            pdf_pages[i] = p["num"] + pdf_page_offset
        elif p["roman"] is not None:
            pdf_pages[i] = p["roman"] + roman_page_offset
    anchors = [i for i, v in enumerate(pdf_pages) if v is not None]
    if anchors:
        for k, i in enumerate(range(anchors[0] - 1, -1, -1), 1):
            pdf_pages[i] = max(1, pdf_pages[anchors[0]] - k)
        for a, b in zip(anchors, anchors[1:]):
            gap = pdf_pages[b] - pdf_pages[a] - 1
            for j, i in enumerate(range(a + 1, b)):
                pdf_pages[i] = pdf_pages[a] + 1 + j if j < gap else pdf_pages[b]
        for k, i in enumerate(range(anchors[-1] + 1, len(pages)), 1):
            pdf_pages[i] = pdf_pages[anchors[-1]] + k
    else:
        pdf_pages = list(range(1, len(pages) + 1))

    # Breadcrumbs from running heads: even pages carry the chapter title, odd pages the section title.
    chapter = section = None
    next_chapter = [None] * len(pages)
    upcoming = None
    for i in range(len(pages) - 1, -1, -1):
        upcoming = pages[i]["chapter"] or upcoming
        next_chapter[i] = upcoming
    out = []
    for i, p in enumerate(pages):
        if p["chapter"]:
            if p["chapter"] != chapter:
                section = None
            chapter = p["chapter"]
        elif p["num"] is None and next_chapter[i] and next_chapter[i] != chapter:
            chapter, section = next_chapter[i], None  # chapter-opening page has no running head
        if p["section"]:
            section = p["section"]
        label = str(p["num"]) if p["num"] is not None else None
        if label is None and pdf_pages[i] > pdf_page_offset:
            label = str(pdf_pages[i] - pdf_page_offset)
        crumbs = [_title(c) for c in (chapter, section) if c]
        text = _join_lines(p["lines"])
        if len(text) < 40 or (chapter or "").upper() in BACK_MATTER or (chapter is None and label is None):
            continue  # title pages, contents, preface, reference list and index only add noise
        out.append({"page": pdf_pages[i], "label": label, "section": " > ".join(crumbs) or None, "text": text})

    # Symbol fixes after head detection; soft hyphens need document-wide vocabulary.
    fixed = _fix_soft_hyphens([fix_symbols(p["text"], symbol_map) for p in out])
    for p, t in zip(out, fixed):
        p["text"] = re.sub(r"[ \t]+", " ", t).strip()
    merged = []
    for p in out:  # a page split across two blocks
        if merged and merged[-1]["page"] == p["page"]:
            merged[-1]["text"] += " " + p["text"]
        else:
            merged.append(p)
    return merged
