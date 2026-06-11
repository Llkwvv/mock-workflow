"""Tests for RAG embedding service (with mocked model to avoid heavy downloads)."""

import numpy as np
import pytest

from backend.rag.embedding import EmbeddingService, _resolve_model_path


class _FakeModel:
    """Stand-in for SentenceTransformer."""
    def __init__(self, dim: int = 384):
        self._dim = dim

    def get_sentence_embedding_dimension(self):
        return self._dim

    def encode(self, sentences, convert_to_numpy=True, normalize_embeddings=True, **kwargs):
        arr = np.random.randn(len(sentences), self._dim).astype(np.float32)
        if normalize_embeddings:
            arr = arr / np.linalg.norm(arr, axis=1, keepdims=True)
        return arr


@pytest.fixture
def embedding(monkeypatch):
    svc = EmbeddingService(model_name="fake-model")
    monkeypatch.setattr(svc, "_model", _FakeModel(dim=384))
    return svc


def test_resolve_model_path_local(tmp_path):
    local_dir = tmp_path / "mini-model"
    local_dir.mkdir()
    (local_dir / "config.json").write_text("{}")
    resolved = _resolve_model_path("org/mini-model", project_root=tmp_path)
    assert resolved == str(local_dir)


def test_resolve_model_path_fallback(tmp_path):
    resolved = _resolve_model_path("org/nonexistent", project_root=tmp_path)
    assert resolved == "org/nonexistent"


def test_encode_single(embedding):
    vec = embedding.encode_single("hello world")
    assert isinstance(vec, np.ndarray)
    assert vec.dtype == np.float32
    assert vec.ndim == 1
    assert vec.shape[0] == embedding.dimension


def test_encode_batch(embedding):
    texts = ["first sentence", "second sentence", "third sentence"]
    vecs = embedding.encode(texts)
    assert vecs.shape == (3, embedding.dimension)
    # Normalized vectors should have unit length
    norms = np.linalg.norm(vecs, axis=1)
    np.testing.assert_allclose(norms, 1.0, atol=1e-5)


def test_encode_empty(embedding):
    vecs = embedding.encode([])
    assert vecs.shape == (0, embedding.dimension)
