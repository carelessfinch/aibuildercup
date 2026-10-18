"""Dense embedding backends. Both are Google models, to fit the competition's Gemini/Gemma rule.

gemma   - EmbeddingGemma 300M (int4/int8) run locally through MediaPipe's TextEmbedder. No API key.
          The model bundle is Google's public MediaPipe copy (downloaded on first use, ~184 MB).
          Needs `pip install mediapipe sentencepiece` and, on Debian/Ubuntu, `apt-get install libegl1 libgles2`.
gemini  - Gemini API / Vertex AI `gemini-embedding-001` via google-genai. Needs GEMINI_API_KEY (or
          GOOGLE_API_KEY), or GOOGLE_GENAI_USE_VERTEXAI=true + GOOGLE_CLOUD_PROJECT on Cloud Run.

Queries must be embedded with the same backend/model that embedded the index (recorded in meta.json).
"""
import os
import threading
import time
import urllib.request
import zipfile
from pathlib import Path

import numpy as np

DEFAULT_GEMINI_MODEL = "gemini-embedding-001"
GEMMA_TASK_URL = "https://storage.googleapis.com/mediapipe-models/text_embedder/embedding_gemma/int4int8/latest/embedding_gemma.task"
GEMMA_MAX_TOKENS = 500  # the MediaPipe graph accepts 512 including BOS/EOS
PACKAGE_ROOT = Path(__file__).resolve().parent.parent


def _normalise(vectors):
    v = np.asarray(vectors, dtype=np.float32)
    return v / np.maximum(np.linalg.norm(v, axis=1, keepdims=True), 1e-12)


def query_text(query):
    return f"task: search result | query: {query}"


def document_text(chunk, source):
    """What gets embedded for a chunk: EmbeddingGemma's document prompt with a short context header."""
    head = source["short"] + (f" | {chunk['section']}" if chunk.get("section") else "")
    return f"title: {head} | text: {chunk['text']}"


class GemmaEmbedder:
    backend = "gemma"

    def __init__(self, model=None):
        from mediapipe.tasks import python as mp_python
        from mediapipe.tasks.python import text as mp_text
        import sentencepiece as spm

        path = Path(model or os.environ.get("LITRAG_GEMMA_TASK", PACKAGE_ROOT / "models" / "embedding_gemma.task"))
        self.path = path
        if not path.exists():
            path.parent.mkdir(parents=True, exist_ok=True)
            print(f"  downloading EmbeddingGemma task bundle to {path}")
            urllib.request.urlretrieve(GEMMA_TASK_URL, path)
        self.model = "embeddinggemma-300m-int4int8-mediapipe"
        self.dim = 768
        self._sp = spm.SentencePieceProcessor(model_proto=zipfile.ZipFile(path).read("sentencepiece.model"))
        opts = mp_text.TextEmbedderOptions(base_options=mp_python.BaseOptions(model_asset_path=str(path)), l2_normalize=True)
        self._embedder = mp_text.TextEmbedder.create_from_options(opts)
        self._lock = threading.Lock()
        # Close before concurrent.futures shuts down its executors at exit (MediaPipe dispatches through one).
        threading._register_atexit(self.close)

    def close(self):
        if self._embedder is not None:
            try:
                self._embedder.close()
            except Exception:
                pass
            self._embedder = None

    def _truncate(self, text):
        ids = self._sp.encode(text)
        return text if len(ids) <= GEMMA_MAX_TOKENS else self._sp.decode(ids[:GEMMA_MAX_TOKENS])

    def _embed_one(self, text):
        with self._lock:
            e = self._embedder.embed(self._truncate(text)).embeddings[0]
        return np.asarray(e.embedding, dtype=np.float32)

    def embed_documents(self, texts, progress=True, workers=None):
        workers = workers or min(os.cpu_count() or 1, 8)
        if workers > 1 and len(texts) >= 200:  # one MediaPipe embedder per process
            import multiprocessing as mp

            shards = [list(map(int, s)) for s in np.array_split(np.arange(len(texts)), workers)]
            print(f"  embedding {len(texts)} texts in {workers} processes")
            with mp.get_context("spawn").Pool(workers) as pool:
                parts = pool.map(_embed_shard, [(str(self.path), [texts[i] for i in s]) for s in shards])
            return np.vstack(parts)
        out = []
        for i, t in enumerate(texts):
            out.append(self._embed_one(t))
            if progress and (i + 1) % 100 == 0:
                print(f"  embedded {i + 1}/{len(texts)}")
        return _normalise(out)

    def embed_query(self, query):
        return _normalise([self._embed_one(query_text(query))])[0]


def _embed_shard(args):
    path, texts = args
    emb = GemmaEmbedder(path)
    try:
        return emb.embed_documents(texts, progress=False, workers=1)
    finally:
        emb.close()


class GeminiEmbedder:
    backend = "gemini"

    def __init__(self, model=None, dim=768, batch_size=50):
        from google import genai

        self.client = genai.Client()
        self.model = model or os.environ.get("LITRAG_GEMINI_EMBED_MODEL", DEFAULT_GEMINI_MODEL)
        self.dim = dim
        self.batch_size = batch_size

    def _embed(self, texts, task_type):
        from google.genai import types

        config = types.EmbedContentConfig(task_type=task_type, output_dimensionality=self.dim)
        if not texts:
            return np.zeros((0, self.dim), dtype=np.float32)
        out = []
        for i in range(0, len(texts), self.batch_size):
            batch = texts[i: i + self.batch_size]
            resp = None
            for attempt in range(6):
                try:
                    resp = self.client.models.embed_content(model=self.model, contents=batch, config=config)
                    break
                except Exception as exc:  # rate limits and transient errors
                    if attempt == 5:
                        raise
                    print(f"  embed retry {attempt + 1}: {type(exc).__name__}: {str(exc)[:120]}")
                    time.sleep(2 ** attempt * 2)
            # Validation is outside the retry loop: a wrong response shape is not transient.
            if resp is None or not resp.embeddings:
                raise ValueError(
                    f"embed_content returned no embeddings for a batch of {len(batch)} texts"
                    f" (model={self.model!r})"
                )
            if len(resp.embeddings) != len(batch):
                raise ValueError(
                    f"embed_content returned {len(resp.embeddings)} embeddings for a batch"
                    f" of {len(batch)} texts (model={self.model!r}); response shape mismatch"
                )
            for e in resp.embeddings:
                if e.values is None or len(e.values) == 0:
                    raise ValueError(
                        f"embedding at output index {len(out)} has no values (model={self.model!r})"
                    )
                out.append(e.values)
        return _normalise(out)

    def embed_documents(self, texts, progress=True):
        return self._embed(texts, "RETRIEVAL_DOCUMENT")

    def embed_query(self, query):
        return self._embed([query], "RETRIEVAL_QUERY")[0]


def get_embedder(backend, model=None):
    if backend == "gemma":
        return GemmaEmbedder(model if model and model.endswith(".task") else None)
    if backend == "gemini":
        return GeminiEmbedder(model)
    raise ValueError(f"unknown embedding backend {backend!r} (use 'gemma' or 'gemini')")
