"""Gets the private litrag index onto local disk and loads it once per container.

The index (passages, page text, vectors) is derived from copyrighted books and papers, so it never goes in
the image or the public repo. It sits in a private bucket and is copied to the container's disk at startup.
"""
import logging
import os
import time
from pathlib import Path

log = logging.getLogger(__name__)


def download_gcs_prefix(uri: str, dest: Path) -> int:
    """Copies every object under gs://bucket/prefix/ into dest, keeping relative paths. Returns the file count."""
    from google.cloud import storage

    bucket_name, _, prefix = uri.removeprefix("gs://").partition("/")
    prefix = prefix.rstrip("/") + "/" if prefix else ""
    client = storage.Client()
    n = 0
    for blob in client.list_blobs(bucket_name, prefix=prefix):
        rel = blob.name[len(prefix):]
        if not rel or rel.endswith("/"):
            continue
        target = dest / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        blob.download_to_filename(str(target))
        n += 1
    if n == 0:
        raise RuntimeError(f"no files found under {uri}; check the bucket path and that the service account can read it")
    return n


def prepare_index(index_uri: str, local_dir: str) -> Path:
    """Makes the index available locally and points litrag at it (LITRAG_INDEX_DIR)."""
    if index_uri.startswith("gs://"):
        dest = Path(local_dir)
        if not (dest / "meta.json").exists():
            t0 = time.time()
            n = download_gcs_prefix(index_uri, dest)
            log.info("copied %d index files from %s in %.1f s", n, index_uri, time.time() - t0)
    else:
        dest = Path(index_uri or os.environ.get("LITRAG_INDEX_DIR", "index"))
    if not (dest / "meta.json").exists():
        raise RuntimeError(f"litrag index not found at {dest} (set LITRAG_INDEX_URI)")
    os.environ["LITRAG_INDEX_DIR"] = str(dest)
    return dest


def load_index(index_dir: Path):
    """Loads the index once and hands it to litrag's agent tools, so the first user request doesn't pay for it."""
    from litrag import tools
    from litrag.index import LiteratureIndex

    t0 = time.time()
    idx = LiteratureIndex(index_dir)
    tools.get_index = lambda: idx  # the tool functions look this up at call time
    log.info("litrag index loaded: %d passages, mode=%s, %.1f s%s", len(idx.chunks), idx.mode, time.time() - t0,
             f" (dense search off: {idx.dense_error})" if idx.dense_error else "")
    return idx
