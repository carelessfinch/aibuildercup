"""Offline unit tests for GeminiEmbedder using a fake google-genai client.

No real API calls, no keys. All tests monkeypatch sys.modules so google-genai
is replaced by fakes, making the tests hermetic (they pass even without the
real google-genai package installed).
"""
import json
import sys
import types as _stdlib_types
from unittest import mock

import numpy as np
import pytest

# ---------------------------------------------------------------------------
# Fake google-genai module hierarchy
# ---------------------------------------------------------------------------


class FakeEmbedContentConfig:
    """Stands in for google.genai.types.EmbedContentConfig (a pydantic model)."""

    def __init__(self, **kwargs):
        self.__dict__.update(kwargs)


class FakeContentEmbedding:
    """Stands in for google.genai.types.ContentEmbedding."""

    def __init__(self, values):
        self.values = values


class FakeEmbedContentResponse:
    """Stands in for google.genai.types.EmbedContentResponse."""

    def __init__(self, embeddings):
        self.embeddings = embeddings


class FakeEmbedContentError(Exception):
    """Stands in for API errors (rate limits, transient failures)."""


class FakeModels:
    """Stands in for google.genai.Client().models."""

    def __init__(self, responses=None, fail_times=0):
        self.calls = []
        self._responses = list(responses or [])
        self._fail_times = fail_times
        self._call_count = 0

    def embed_content(self, *, model, contents, config):
        self.calls.append({"model": model, "contents": list(contents), "config": config})
        self._call_count += 1
        if self._fail_times > 0:
            self._fail_times -= 1
            raise FakeEmbedContentError("429 RESOURCE_EXHAUSTED: quota exceeded")
        if self._responses:
            return self._responses.pop(0)
        # Default: generate a unit vector for each text.
        embeddings = [FakeContentEmbedding(values=[1.0] + [0.0] * 767) for _ in contents]
        return FakeEmbedContentResponse(embeddings=embeddings)


class FakeClient:
    """Stands in for google.genai.Client."""

    def __init__(self, models=None):
        self.models = models or FakeModels()


def _make_fake_genai_modules(client):
    """Build fake google / google.genai / google.genai.types module dicts for sys.modules."""
    fake_types = _stdlib_types.ModuleType("google.genai.types")
    fake_types.EmbedContentConfig = FakeEmbedContentConfig
    fake_types.ContentEmbedding = FakeContentEmbedding
    fake_types.EmbedContentResponse = FakeEmbedContentResponse

    fake_genai = _stdlib_types.ModuleType("google.genai")
    fake_genai.Client = lambda: client
    fake_genai.types = fake_types

    fake_google = _stdlib_types.ModuleType("google")
    fake_google.genai = fake_genai

    return {
        "google": fake_google,
        "google.genai": fake_genai,
        "google.genai.types": fake_types,
    }


@pytest.fixture()
def fake_models():
    return FakeModels()


@pytest.fixture()
def embedder_cls(fake_models):
    """Import litrag.embed with the fake google-genai in place; yield GeminiEmbedder."""
    client = FakeClient(models=fake_models)
    fake_mods = _make_fake_genai_modules(client)
    # Force a fresh import of litrag.embed so the lazy imports inside methods
    # pick up the fakes. We must also ensure litrag itself is importable.
    with mock.patch.dict(sys.modules, fake_mods):
        # Clear any cached litrag modules so lazy imports re-execute.
        litrag_mods = {k: v for k, v in sys.modules.items() if k.startswith("litrag")}
        with mock.patch.dict(sys.modules, {k: None for k in litrag_mods}):
            yield client.models


def _make_embedder(fake_models_fixture, **kwargs):
    """Import and instantiate GeminiEmbedder with the fake client active."""
    client = FakeClient(models=fake_models_fixture)
    fake_mods = _make_fake_genai_modules(client)
    litrag_mods = {k: v for k, v in sys.modules.items() if k.startswith("litrag")}
    with mock.patch.dict(sys.modules, fake_mods):
        with mock.patch.dict(sys.modules, {k: None for k in litrag_mods}):
            from litrag.embed import GeminiEmbedder

            return GeminiEmbedder(**kwargs)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestGeminiEmbedderRequestShape:
    def test_embed_documents_sends_correct_model_and_task_type(self, fake_models):
        emb = _make_embedder(fake_models)
        emb.embed_documents(["hello", "world"])
        assert len(fake_models.calls) == 1
        call = fake_models.calls[0]
        assert call["model"] == "gemini-embedding-001"
        assert call["config"].task_type == "RETRIEVAL_DOCUMENT"
        assert call["config"].output_dimensionality == 768
        assert call["contents"] == ["hello", "world"]

    def test_embed_query_sends_retrieval_query_task_type(self, fake_models):
        emb = _make_embedder(fake_models)
        emb.embed_query("Bohm flux")
        assert len(fake_models.calls) == 1
        call = fake_models.calls[0]
        assert call["model"] == "gemini-embedding-001"
        assert call["config"].task_type == "RETRIEVAL_QUERY"

    def test_custom_model_name_is_passed_through(self, fake_models):
        emb = _make_embedder(fake_models, model="my-custom-embedding-v2")
        emb.embed_query("test")
        assert fake_models.calls[0]["model"] == "my-custom-embedding-v2"

    def test_env_var_overrides_default_model(self, fake_models, monkeypatch):
        monkeypatch.setenv("LITRAG_GEMINI_EMBED_MODEL", "env-model-v1")
        emb = _make_embedder(fake_models)
        assert emb.model == "env-model-v1"
        emb.embed_query("test")
        assert fake_models.calls[0]["model"] == "env-model-v1"


class TestGeminiEmbedderBatching:
    def test_batching_splits_correctly(self, fake_models):
        texts = [f"text_{i}" for i in range(120)]
        emb = _make_embedder(fake_models, batch_size=50)
        emb.embed_documents(texts)
        assert len(fake_models.calls) == 3
        assert fake_models.calls[0]["contents"] == texts[:50]
        assert fake_models.calls[1]["contents"] == texts[50:100]
        assert fake_models.calls[2]["contents"] == texts[100:120]

    def test_batch_size_larger_than_input_means_one_call(self, fake_models):
        emb = _make_embedder(fake_models, batch_size=100)
        emb.embed_documents(["a", "b", "c"])
        assert len(fake_models.calls) == 1
        assert fake_models.calls[0]["contents"] == ["a", "b", "c"]

    def test_output_has_same_length_as_input(self, fake_models):
        texts = [f"doc {i}" for i in range(7)]
        emb = _make_embedder(fake_models)
        result = emb.embed_documents(texts)
        assert result.shape == (7, 768)


class TestGeminiEmbedderErrorHandling:
    def test_retry_succeeds_after_transient_failure(self, fake_models, monkeypatch):
        monkeypatch.setattr("time.sleep", lambda s: None)
        # Fail once, then succeed.
        fake_models._fail_times = 1
        emb = _make_embedder(fake_models)
        result = emb.embed_documents(["hello"])
        assert result.shape == (1, 768)
        assert len(fake_models.calls) == 2  # 1 failure + 1 success

    def test_raises_after_max_retries(self, fake_models, monkeypatch):
        monkeypatch.setattr("time.sleep", lambda s: None)
        fake_models._fail_times = 10  # more than the 6-attempt cap
        emb = _make_embedder(fake_models)
        with pytest.raises(FakeEmbedContentError, match="quota exceeded"):
            emb.embed_documents(["hello"])
        assert len(fake_models.calls) == 6

    def test_mismatched_response_count_raises(self, fake_models, monkeypatch):
        monkeypatch.setattr("time.sleep", lambda s: None)
        # API returns 1 embedding for a batch of 3 texts.
        short_response = FakeEmbedContentResponse(
            embeddings=[FakeContentEmbedding(values=[1.0, 0.0])]
        )
        fake_models._responses = [short_response]
        emb = _make_embedder(fake_models)
        with pytest.raises(ValueError, match="response shape mismatch"):
            emb.embed_documents(["a", "b", "c"])

    def test_none_embeddings_in_response_raises_clearly(self, fake_models, monkeypatch):
        monkeypatch.setattr("time.sleep", lambda s: None)
        bad_response = FakeEmbedContentResponse(embeddings=None)
        fake_models._responses = [bad_response]
        emb = _make_embedder(fake_models)
        with pytest.raises(ValueError, match="returned no embeddings"):
            emb.embed_documents(["hello"])


class TestGeminiEmbedderEmptyInput:
    def test_embed_documents_empty_list_returns_empty_array(self, fake_models):
        emb = _make_embedder(fake_models)
        result = emb.embed_documents([])
        assert isinstance(result, np.ndarray)
        assert result.shape == (0, 768)

    def test_embed_query_single_string_returns_1d_array(self, fake_models):
        emb = _make_embedder(fake_models)
        result = emb.embed_query("test query")
        assert result.shape == (768,)


class TestGeminiEmbedderDimensions:
    def test_vectors_are_normalised(self, fake_models):
        # Return non-unit vectors from the fake API.
        response = FakeEmbedContentResponse(
            embeddings=[
                FakeContentEmbedding(values=[3.0, 4.0] + [0.0] * 766),
                FakeContentEmbedding(values=[0.0, 5.0] + [0.0] * 766),
            ]
        )
        fake_models._responses = [response]
        emb = _make_embedder(fake_models)
        result = emb.embed_documents(["a", "b"])
        norms = np.linalg.norm(result, axis=1)
        np.testing.assert_allclose(norms, [1.0, 1.0], atol=1e-6)

    def test_dimension_consistency_across_batches(self, fake_models):
        texts = [f"doc {i}" for i in range(105)]
        emb = _make_embedder(fake_models, batch_size=50)
        result = emb.embed_documents(texts)
        assert result.shape == (105, 768)
        # All rows should have the same dim.
        dims = {r.shape[0] for r in result}
        assert dims == {768}


class TestGeminiEmbedderSymmetry:
    def test_query_and_document_use_same_model(self, fake_models):
        emb = _make_embedder(fake_models, model="consistent-model")
        emb.embed_documents(["doc"])
        emb.embed_query("query")
        assert fake_models.calls[0]["model"] == "consistent-model"
        assert fake_models.calls[1]["model"] == "consistent-model"

    def test_query_and_document_use_different_task_types(self, fake_models):
        emb = _make_embedder(fake_models)
        emb.embed_documents(["doc"])
        emb.embed_query("query")
        assert fake_models.calls[0]["config"].task_type == "RETRIEVAL_DOCUMENT"
        assert fake_models.calls[1]["config"].task_type == "RETRIEVAL_QUERY"


class TestGeminiEmbedderModelRecording:
    def test_model_name_is_stored_on_instance(self, fake_models):
        emb = _make_embedder(fake_models, model="gemini-embedding-001")
        assert emb.model == "gemini-embedding-001"
        assert emb.backend == "gemini"
        assert emb.dim == 768


class TestEmbedIndexRecordsGemini:
    """Verify embed_index writes the correct backend/model to meta.json and embedding_keys.json."""

    @pytest.fixture()
    def tmp_index(self, tmp_path):
        """Create a minimal index directory with chunks + sources + meta."""
        index_dir = tmp_path / "index"
        index_dir.mkdir()
        sources = {"sources": [{"id": "test_src", "kind": "paper", "short": "Test (2026)", "title": "Test Paper", "file": "test.pdf"}]}
        chunks = [
            {"id": "c1", "source_id": "test_src", "text": "chunk one", "page_start": 1, "page_end": 1},
            {"id": "c2", "source_id": "test_src", "text": "chunk two", "page_start": 2, "page_end": 2},
        ]
        with open(index_dir / "sources.json", "w") as f:
            json.dump(sources, f)
        with open(index_dir / "chunks.jsonl", "w") as f:
            for c in chunks:
                f.write(json.dumps(c) + "\n")
        meta = {"version": 1, "n_chunks": 2, "sources": [{"id": "test_src", "status": "indexed"}], "embedding": None}
        with open(index_dir / "meta.json", "w") as f:
            json.dump(meta, f)
        return index_dir

    def test_embed_index_writes_gemini_backend_and_model(self, fake_models, tmp_index):
        litrag_mods = {k: v for k, v in sys.modules.items() if k.startswith("litrag")}
        client = FakeClient(models=fake_models)
        fake_mods = _make_fake_genai_modules(client)
        with mock.patch.dict(sys.modules, fake_mods):
            with mock.patch.dict(sys.modules, {k: None for k in litrag_mods}):
                from litrag.index import embed_index

                meta = embed_index(tmp_index, "gemini", "gemini-embedding-001")

        assert meta["embedding"]["backend"] == "gemini"
        assert meta["embedding"]["model"] == "gemini-embedding-001"
        assert meta["embedding"]["dim"] == 768
        # Verify embedding_keys.json also records the backend/model.
        keys = json.load(open(tmp_index / "embedding_keys.json"))
        assert keys["backend"] == "gemini"
        assert keys["model"] == "gemini-embedding-001"

    def test_embed_index_api_calls_use_retrieval_document(self, fake_models, tmp_index):
        litrag_mods = {k: v for k, v in sys.modules.items() if k.startswith("litrag")}
        client = FakeClient(models=fake_models)
        fake_mods = _make_fake_genai_modules(client)
        with mock.patch.dict(sys.modules, fake_mods):
            with mock.patch.dict(sys.modules, {k: None for k in litrag_mods}):
                from litrag.index import embed_index

                embed_index(tmp_index, "gemini", "gemini-embedding-001")

        for call in fake_models.calls:
            assert call["config"].task_type == "RETRIEVAL_DOCUMENT"
