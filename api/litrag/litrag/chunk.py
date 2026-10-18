"""Sentence-aware chunking that keeps track of the PDF pages and section each chunk came from."""
import re
from dataclasses import dataclass

_SENT_SPLIT = re.compile(r"(?<=[.!?])\s+(?=[A-Z0-9(\[\"“])")


@dataclass
class _Unit:
    page: int
    label: str
    section: str
    text: str
    n: int


def _units(pages, max_words):
    for p in pages:
        for para in p["text"].split("\n"):
            for sent in _SENT_SPLIT.split(para):
                words = sent.split()
                for i in range(0, len(words), max_words):  # garbled equations/tables can be one giant "sentence"
                    piece = words[i: i + max_words]
                    if piece:
                        yield _Unit(p["page"], p.get("label"), p.get("section"), " ".join(piece), len(piece))


def chunk_pages(pages, source_id, target_words=260, overlap_words=40, min_words=70, max_unit_words=90):
    """Greedy packing of sentences into ~target_words chunks with a sentence-level overlap.
    A new chunk starts at a section boundary once the current chunk has min_words."""
    groups, cur, n_cur = [], [], 0
    for u in _units(pages, max_unit_words):
        section_change = bool(cur) and u.section != cur[-1].section and n_cur >= min_words
        if cur and (n_cur + u.n > target_words or section_change):
            groups.append(cur)
            carry = []
            if not section_change:
                w = 0
                for prev in reversed(cur):
                    if w + prev.n > overlap_words:
                        break
                    carry.insert(0, prev)
                    w += prev.n
            cur, n_cur = carry, sum(c.n for c in carry)
        cur.append(u)
        n_cur += u.n
    if cur:
        if groups and n_cur < min_words and cur[0].section == groups[-1][-1].section:
            groups[-1] = groups[-1] + [u for u in cur if u not in groups[-1]]
        else:
            groups.append(cur)

    chunks = []
    for k, g in enumerate(groups):
        first, last = g[0], g[-1]
        chunks.append({
            "id": f"{source_id}:{k:04d}",
            "source_id": source_id,
            "page_start": first.page,
            "page_end": last.page,
            "label_start": first.label,
            "label_end": last.label,
            "section": next((u.section for u in g if u.section), None),
            "text": " ".join(u.text for u in g),
            "n_words": sum(u.n for u in g),
        })
    return chunks
