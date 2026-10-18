"""Build the literature index and search it (BM25 keyword search, plus dense vectors when available)."""
import datetime as dt
import json
import os
import shutil
from pathlib import Path

import numpy as np

from .bm25 import BM25
from .chunk import chunk_pages
from .embed import document_text, get_embedder
from .extract import extract_pdf, extract_text_blocks
from .textutil import expand_query, tokenize

PACKAGE_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_INDEX_DIR = Path(os.environ.get("LITRAG_INDEX_DIR", PACKAGE_ROOT / "index"))
DEFAULT_PDF_DIR = Path(os.environ.get("LITRAG_PDF_DIR", PACKAGE_ROOT / "corpus" / "pdf"))
DEFAULT_TEXT_DIR = Path(os.environ.get("LITRAG_TEXT_DIR", PACKAGE_ROOT / "corpus" / "text"))
DEFAULT_SOURCES = PACKAGE_ROOT / "sources.json"
RRF_K = 60


def _write_jsonl(path, rows):
    with open(path, "w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")


def _read_jsonl(path):
    with open(path, encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


def _load_pages(s, pdf_dir, text_dir):
    """Pages for one source: from its PDF if present, else from a plain-text export (text_file)."""
    pdf = pdf_dir / s["file"]
    if pdf.exists():
        return extract_pdf(pdf, s["kind"], s.get("symbol_map")), pdf.name
    if s.get("text_file") and (text_dir / s["text_file"]).exists():
        return extract_text_blocks(text_dir / s["text_file"], s["kind"], s.get("pdf_page_offset", 0),
                                   s.get("roman_page_offset", 0), s.get("symbol_map")), s["text_file"]
    return None, None


def build_index(pdf_dir=DEFAULT_PDF_DIR, index_dir=DEFAULT_INDEX_DIR, sources_path=DEFAULT_SOURCES, embed_backend=None,
                text_dir=DEFAULT_TEXT_DIR):
    """Extract every source listed in sources.json (PDF, or text export as fallback), chunk it, write the index."""
    pdf_dir, index_dir, text_dir = Path(pdf_dir), Path(index_dir), Path(text_dir)
    (index_dir / "pages").mkdir(parents=True, exist_ok=True)
    sources = json.load(open(sources_path, encoding="utf-8"))["sources"]
    all_chunks, summary = [], []
    for s in sources:
        pages, origin = _load_pages(s, pdf_dir, text_dir)
        if pages is None:
            summary.append({"id": s["id"], "status": "missing pdf"})
            print(f"  skip {s['id']}: {s['file']} not found")
            continue
        _write_jsonl(index_dir / "pages" / f"{s['id']}.jsonl", pages)
        chunks = chunk_pages(pages, s["id"])
        all_chunks += chunks
        summary.append({"id": s["id"], "status": "indexed", "from": origin, "pages": len(pages), "chunks": len(chunks),
                        "words": sum(c["n_words"] for c in chunks)})
        print(f"  {s['id']}: {len(pages)} pages -> {len(chunks)} chunks")
    _write_jsonl(index_dir / "chunks.jsonl", all_chunks)
    shutil.copyfile(sources_path, index_dir / "sources.json")
    meta = {"version": 1, "built_at": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
            "n_chunks": len(all_chunks), "sources": summary, "embedding": None}
    json.dump(meta, open(index_dir / "meta.json", "w"), indent=2)
    if embed_backend:
        meta = embed_index(index_dir, embed_backend)
    return meta


def embed_index(index_dir=DEFAULT_INDEX_DIR, backend="gemma", model=None):
    """Add dense vectors for every chunk (queries must later use the same backend/model).

    Vectors from the previous run are reused for passages whose text is unchanged, so adding a
    paper only embeds the new passages."""
    import hashlib

    index_dir = Path(index_dir)
    chunks = _read_jsonl(index_dir / "chunks.jsonl")
    sources = {s["id"]: s for s in json.load(open(index_dir / "sources.json"))["sources"]}
    embedder = get_embedder(backend, model)
    texts = [document_text(c, sources[c["source_id"]]) for c in chunks]
    keys = [hashlib.sha1(t.encode()).hexdigest() for t in texts]
    cached = {}
    keys_path, vec_path = index_dir / "embedding_keys.json", index_dir / "embeddings.npy"
    if keys_path.exists() and vec_path.exists():
        prev = json.load(open(keys_path))
        prev_vecs = np.load(vec_path)
        if (prev.get("backend"), prev.get("model")) == (embedder.backend, embedder.model) \
                and len(prev["keys"]) == len(prev_vecs):
            cached = dict(zip(prev["keys"], prev_vecs.astype(np.float32)))
    todo = [i for i, k in enumerate(keys) if k not in cached]
    print(f"  embedding {len(todo)} of {len(chunks)} chunks with {embedder.backend}:{embedder.model}"
          f" ({len(chunks) - len(todo)} unchanged)")
    fresh = embedder.embed_documents([texts[i] for i in todo]) if todo else None
    vectors = np.zeros((len(chunks), (fresh if fresh is not None else next(iter(cached.values()))).shape[-1]),
                       dtype=np.float32)
    for i, k in enumerate(keys):
        if k in cached:
            vectors[i] = cached[k]
    for j, i in enumerate(todo):
        vectors[i] = fresh[j]
    np.save(vec_path, vectors.astype(np.float16))
    json.dump({"backend": embedder.backend, "model": embedder.model, "keys": keys}, open(keys_path, "w"))
    meta = json.load(open(index_dir / "meta.json"))
    meta["embedding"] = {"backend": embedder.backend, "model": embedder.model, "dim": int(vectors.shape[1]),
                         "chunk_ids_sha": _ids_digest(chunks)}
    json.dump(meta, open(index_dir / "meta.json", "w"), indent=2)
    return meta


def _ids_digest(chunks):
    import hashlib

    return hashlib.sha1("|".join(c["id"] for c in chunks).encode()).hexdigest()[:12]


def format_citation(source, chunk):
    pages = (chunk["page_start"], chunk["page_end"])
    pdf_pages = f"PDF p. {pages[0]}" if pages[0] == pages[1] else f"PDF pp. {pages[0]}-{pages[1]}"
    printed = ""
    if source["kind"] == "textbook" and chunk.get("label_start"):
        a, b = chunk["label_start"], chunk.get("label_end") or chunk["label_start"]
        printed = f"p. {a}, " if a == b else f"pp. {a}-{b}, "
    venue = source.get("venue") or ""
    title = source["title"].rstrip(".")
    where = title if source["kind"] != "paper" else f"{title}, {venue}"
    return f"{source['short']}. {where}. {printed}{pdf_pages}."


class LiteratureIndex:
    def __init__(self, index_dir=DEFAULT_INDEX_DIR, dense=True):
        self.dir = Path(index_dir)
        self.chunks = _read_jsonl(self.dir / "chunks.jsonl")
        self.sources = {s["id"]: s for s in json.load(open(self.dir / "sources.json"))["sources"]}
        self.meta = json.load(open(self.dir / "meta.json"))
        self.bm25 = BM25([tokenize(self._search_text(c)) for c in self.chunks])
        self._source_arr = np.array([c["source_id"] for c in self.chunks])
        self._kind_arr = np.array([self.sources[c["source_id"]]["kind"] for c in self.chunks])
        self.vectors, self.embedder, self.dense_error = None, None, None
        emb = self.meta.get("embedding")
        if dense and emb and (self.dir / "embeddings.npy").exists():
            try:
                if emb.get("chunk_ids_sha") != _ids_digest(self.chunks):
                    raise RuntimeError("embeddings are stale; re-run `python -m litrag embed`")
                self.embedder = get_embedder(emb["backend"], emb["model"])
                self.vectors = np.load(self.dir / "embeddings.npy").astype(np.float32)
            except Exception as exc:  # no key / package: fall back to keyword search
                self.dense_error = f"{type(exc).__name__}: {exc}"
                self.vectors, self.embedder = None, None
        self._pages_cache = {}

    def _search_text(self, c):
        s = self.sources[c["source_id"]]
        return f"{s['short']} {s['title']} {c.get('section') or ''} {c['text']}"

    @property
    def mode(self):
        return "hybrid" if self.vectors is not None else "keyword"

    def search(self, query, top_k=5, source_ids=None, kinds=None, pool=50):
        mask = np.ones(len(self.chunks), dtype=bool)
        if source_ids:
            mask &= np.isin(self._source_arr, list(source_ids))
        if kinds:
            mask &= np.isin(self._kind_arr, list(kinds))
        ranked_lists = []
        bm = self.bm25.scores(expand_query(query))
        bm[~mask] = 0
        order = np.argsort(-bm)[:pool]
        ranked_lists.append([int(i) for i in order if bm[i] > 0])
        dense = None
        if self.vectors is not None:
            q = self.embedder.embed_query(query)
            dense = self.vectors @ q
            dense[~mask] = -np.inf
            ranked_lists.append([int(i) for i in np.argsort(-dense)[:pool] if np.isfinite(dense[i])])
        fused = {}
        for lst in ranked_lists:
            for rank, i in enumerate(lst):
                fused[i] = fused.get(i, 0.0) + 1.0 / (RRF_K + rank + 1)
        best = sorted(fused, key=lambda i: -fused[i])[:top_k]
        results = []
        for i in best:
            c = self.chunks[i]
            s = self.sources[c["source_id"]]
            results.append({
                "chunk_id": c["id"],
                "source_id": c["source_id"],
                "citation": format_citation(s, c),
                "doi": s.get("doi"),
                "kind": s["kind"],
                "section": c.get("section"),
                "pdf_pages": [c["page_start"], c["page_end"]],
                "printed_pages": [c.get("label_start"), c.get("label_end")] if s["kind"] == "textbook" else None,
                "score": round(fused[i], 5),
                "bm25": round(float(bm[i]), 3),
                "dense": None if dense is None else round(float(dense[i]), 4),
                "text": c["text"],
            })
        return results

    def pages(self, source_id):
        if source_id not in self._pages_cache:
            path = self.dir / "pages" / f"{source_id}.jsonl"
            self._pages_cache[source_id] = _read_jsonl(path) if path.exists() else []
        return self._pages_cache[source_id]
