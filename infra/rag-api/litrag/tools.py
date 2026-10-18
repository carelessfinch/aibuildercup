"""Agent-facing tools. Plain functions with docstrings, so Google ADK can wrap them directly:

    from google.adk.agents import Agent
    from litrag.tools import search_literature, read_source_pages, list_literature_sources
    professor = Agent(model="gemini-flash-latest", name="professor", instruction=...,
                      tools=[search_literature, read_source_pages, list_literature_sources])
"""
from functools import lru_cache

from .index import LiteratureIndex, format_citation

MAX_PAGES_PER_READ = 4


@lru_cache(maxsize=1)
def get_index():
    return LiteratureIndex()


def search_literature(query: str, top_k: int = 5, source_ids: list[str] | None = None, kind: str | None = None) -> dict:
    """Searches the group's plasma physics and plasma etching literature (textbooks, papers, and the COMSOL
    CF4/O2 ICP reference model) and returns the most relevant passages with citations.

    Use it to look up physics (global models, sheaths, Bohm flux, rate constants, transport), etch mechanisms,
    model setup details, typical parameter ranges, or to check whether a simulation result is physically
    plausible. Phrase the query as a specific question or as key terms, e.g. "electron temperature in a
    low-pressure ICP global model" or "CF4/O2 ICP RF bias etch rate versus bias voltage".

    Args:
        query: What to look for, in natural language or keywords.
        top_k: Number of passages to return (1-10).
        source_ids: Optional list of source ids to restrict the search to (see list_literature_sources).
        kind: Optional filter: "textbook", "paper" or "vendor_model".

    Returns:
        A dict with "status", "mode" ("keyword" or "hybrid") and "results": each result has "citation",
        "source_id", "pdf_pages", "printed_pages", "section" and the passage "text". Always cite the
        "citation" string when you use a passage.
    """
    idx = get_index()
    top_k = max(1, min(int(top_k), 10))
    try:
        results = idx.search(query, top_k=top_k, source_ids=source_ids, kinds=[kind] if kind else None)
    except Exception as exc:
        return {"status": "error", "error_message": f"{type(exc).__name__}: {exc}"}
    keep = ("citation", "source_id", "kind", "section", "pdf_pages", "printed_pages", "score", "text")
    return {"status": "success", "mode": idx.mode, "query": query, "results": [{k: r[k] for k in keep} for r in results]}


def read_source_pages(source_id: str, first_pdf_page: int, last_pdf_page: int | None = None) -> dict:
    """Reads the full extracted text of specific pages of one source, e.g. to see the equation, table or
    paragraph around a passage that search_literature returned. Reads at most 4 pages per call.

    Args:
        source_id: The source id, e.g. "lieberman2005" or "comsol_icp_cf4o2".
        first_pdf_page: First PDF page number (as in a result's "pdf_pages").
        last_pdf_page: Last PDF page number (inclusive). Defaults to first_pdf_page.

    Returns:
        A dict with "status", "citation" and "pages": a list of {"pdf_page", "printed_page", "section", "text"}.
    """
    idx = get_index()
    if source_id not in idx.sources:
        return {"status": "error", "error_message": f"unknown source_id {source_id!r}; known: {sorted(idx.sources)}"}
    last = last_pdf_page or first_pdf_page
    last = min(last, first_pdf_page + MAX_PAGES_PER_READ - 1)
    pages = [p for p in idx.pages(source_id) if first_pdf_page <= p["page"] <= last]
    if not pages:
        return {"status": "error", "error_message": f"no extracted text for {source_id} PDF pages {first_pdf_page}-{last}"}
    src = idx.sources[source_id]
    fake_chunk = {"page_start": pages[0]["page"], "page_end": pages[-1]["page"],
                  "label_start": pages[0].get("label"), "label_end": pages[-1].get("label")}
    return {
        "status": "success",
        "citation": format_citation(src, fake_chunk),
        "pages": [{"pdf_page": p["page"], "printed_page": p.get("label"), "section": p.get("section"), "text": p["text"]} for p in pages],
    }


def list_literature_sources() -> dict:
    """Lists the documents in the literature index (id, kind, short citation, title, year, topics, and
    whether each one is indexed), so you can restrict search_literature to particular sources.

    Returns:
        A dict with "status" and "sources".
    """
    idx = get_index()
    indexed = {s["id"]: s for s in idx.meta.get("sources", [])}
    rows = []
    for sid, s in idx.sources.items():
        info = indexed.get(sid, {})
        rows.append({"id": sid, "kind": s["kind"], "short": s["short"], "title": s["title"], "year": s.get("year"),
                     "topics": s.get("topics", []), "indexed": info.get("status") == "indexed", "pages": info.get("pages")})
    return {"status": "success", "mode": idx.mode, "sources": rows}
