"""CLI: python -m litrag {build,embed,search,sources,eval,ask} ..."""
import argparse
import json
import os
import sys
import textwrap
import time
from pathlib import Path

from .index import DEFAULT_INDEX_DIR, DEFAULT_PDF_DIR, PACKAGE_ROOT, LiteratureIndex, build_index, embed_index

ASK_PROMPT = """You are the literature assistant for a plasma-etch simulation research group.
Answer the question using only the numbered excerpts below. Cite every claim with [n].
If the excerpts do not contain the answer, say so plainly instead of guessing.
Equations in the excerpts were extracted from PDFs and may be garbled; do not copy garbled symbols.

Question: {question}

Excerpts:
{excerpts}
"""


def _print_results(results, width=110):
    for n, r in enumerate(results, 1):
        print(f"[{n}] {r['citation']}  (score {r['score']}, bm25 {r['bm25']}, dense {r['dense']})")
        if r.get("section"):
            print(f"    section: {r['section']}")
        print(textwrap.indent(textwrap.fill(r["text"][:600] + ("..." if len(r["text"]) > 600 else ""), width), "    "))
        print()


def cmd_build(a):
    meta = build_index(a.pdf_dir, a.index_dir, embed_backend=a.embed)
    print(json.dumps({k: meta[k] for k in ("n_chunks", "embedding")}, indent=2))


def cmd_embed(a):
    meta = embed_index(a.index_dir, a.backend, a.model)
    print(json.dumps(meta["embedding"], indent=2))


def cmd_search(a):
    idx = LiteratureIndex(a.index_dir)
    if idx.dense_error:
        print(f"(dense search off: {idx.dense_error})")
    t = time.perf_counter()
    res = idx.search(a.query, top_k=a.k, source_ids=a.source, kinds=a.kind)
    print(f"mode={idx.mode}  {1000 * (time.perf_counter() - t):.0f} ms\n")
    _print_results(res)


def cmd_sources(a):
    idx = LiteratureIndex(a.index_dir, dense=False)
    status = {s["id"]: s for s in idx.meta["sources"]}
    for sid, s in idx.sources.items():
        st = status.get(sid, {})
        print(f"{sid:18s} {s['kind']:12s} {st.get('status', '?'):12s} pages={st.get('pages', '-'):>4} chunks={st.get('chunks', '-'):>4}  {s['short']}")
    print(f"\nembedding: {idx.meta.get('embedding')}")


def cmd_eval(a):
    idx = LiteratureIndex(a.index_dir, dense=not a.keyword_only)
    rows = [json.loads(l) for l in open(a.questions, encoding="utf-8") if l.strip()]
    hits1 = hitsk = rr = 0
    skipped = 0
    for row in rows:
        if row["source"] not in {s["id"] for s in idx.meta["sources"] if s["status"] == "indexed"}:
            skipped += 1
            continue
        res = idx.search(row["q"], top_k=a.k)
        spans = row["pages"] if isinstance(row["pages"][0], list) else [row["pages"]]
        rank = next((n for n, r in enumerate(res, 1) if r["source_id"] == row["source"]
                     and any(r["pdf_pages"][0] <= hi and r["pdf_pages"][1] >= lo for lo, hi in spans)), None)
        hits1 += rank == 1
        hitsk += rank is not None
        rr += 1 / rank if rank else 0
        mark = f"rank {rank}" if rank else "MISS  "
        top = res[0]["citation"][:70] if res else "-"
        print(f"{mark:7s} | {row['q'][:70]:70s} | top: {top}")
    n = len(rows) - skipped
    print(f"\nmode={idx.mode}  questions={n} (skipped {skipped} for unindexed sources)")
    if n:
        print(f"hit@1={hits1 / n:.2f}  hit@{a.k}={hitsk / n:.2f}  MRR={rr / n:.2f}")


def cmd_ask(a):
    from google import genai

    idx = LiteratureIndex(a.index_dir)
    res = idx.search(a.question, top_k=a.k)
    excerpts = "\n\n".join(f"[{n}] {r['citation']}\n{r['text']}" for n, r in enumerate(res, 1))
    model = os.environ.get("LITRAG_GEMINI_MODEL", "gemini-flash-latest")
    reply = genai.Client().models.generate_content(model=model, contents=ASK_PROMPT.format(question=a.question, excerpts=excerpts))
    print(reply.text, "\n\nSources:")
    for n, r in enumerate(res, 1):
        print(f"[{n}] {r['citation']}")


def main(argv=None):
    p = argparse.ArgumentParser(prog="litrag", description=__doc__)
    p.add_argument("--index-dir", default=str(DEFAULT_INDEX_DIR))
    sub = p.add_subparsers(dest="cmd", required=True)

    b = sub.add_parser("build", help="extract + chunk all PDFs listed in sources.json")
    b.add_argument("--pdf-dir", default=str(DEFAULT_PDF_DIR))
    b.add_argument("--embed", choices=["gemma", "gemini"], help="also compute dense embeddings")
    b.set_defaults(fn=cmd_build)

    e = sub.add_parser("embed", help="add dense embeddings to an existing index")
    e.add_argument("--backend", choices=["gemma", "gemini"], default="gemma")
    e.add_argument("--model")
    e.set_defaults(fn=cmd_embed)

    s = sub.add_parser("search", help="search the index")
    s.add_argument("query")
    s.add_argument("-k", type=int, default=5)
    s.add_argument("--source", action="append", help="restrict to a source id (repeatable)")
    s.add_argument("--kind", action="append", choices=["textbook", "paper", "vendor_model"])
    s.set_defaults(fn=cmd_search)

    sub.add_parser("sources", help="list sources and index status").set_defaults(fn=cmd_sources)

    v = sub.add_parser("eval", help="retrieval hit-rate on eval/questions.jsonl")
    v.add_argument("--questions", default=str(PACKAGE_ROOT / "eval" / "questions.jsonl"))
    v.add_argument("-k", type=int, default=5)
    v.add_argument("--keyword-only", action="store_true")
    v.set_defaults(fn=cmd_eval)

    q = sub.add_parser("ask", help="retrieve + answer with Gemini, with citations")
    q.add_argument("question")
    q.add_argument("-k", type=int, default=6)
    q.set_defaults(fn=cmd_ask)

    a = p.parse_args(argv)
    a.fn(a)


if __name__ == "__main__":
    sys.exit(main())
