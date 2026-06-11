"""Tests for ChromaVectorStore (with mocked embedding to avoid model download)."""

import numpy as np
import pytest

from backend.rag.chroma_store import ChromaVectorStore
from backend.rag.embedding import EmbeddingService


class _FakeModel:
    def __init__(self, dim: int = 384):
        self._dim = dim

    def get_sentence_embedding_dimension(self):
        return self._dim

    def encode(self, sentences, convert_to_numpy=True, normalize_embeddings=True, **kwargs):
        # Deterministic embedding based on word overlap so that
        # Chroma cosine search behaves predictably in tests.
        arr = np.zeros((len(sentences), self._dim), dtype=np.float32)
        for i, text in enumerate(sentences):
            words = text.lower().split()
            for w in words:
                idx = hash(w) % self._dim
                arr[i, idx] += 1.0
            if normalize_embeddings:
                norm = np.linalg.norm(arr[i])
                if norm > 0:
                    arr[i] = arr[i] / norm
        return arr


@pytest.fixture
def store(tmp_path, monkeypatch):
    emb = EmbeddingService(model_name="fake-model")
    monkeypatch.setattr(emb, "_model", _FakeModel(dim=384))
    return ChromaVectorStore(
        persist_dir=tmp_path / "chroma_test",
        embedding_service=emb,
        collections=("test_rules", "test_samples"),
    )


def test_add_and_count(store):
    store.add(
        "test_rules",
        ids=["r1", "r2"],
        documents=["email must contain @", "phone must be 11 digits"],
        metadatas=[{"category": "email"}, {"category": "phone"}],
    )
    assert store.count("test_rules") == 2


def test_query_by_text(store):
    store.add(
        "test_rules",
        ids=["r1", "r2", "r3"],
        documents=[
            "email must contain @",
            "phone must be 11 digits",
            "name should be Chinese characters",
        ],
        metadatas=[{"category": "email"}, {"category": "phone"}, {"category": "name"}],
    )
    results = store.query("test_rules", query_texts=["how to validate an email"], n_results=2)
    assert len(results) == 2
    # The top result should be the email rule
    assert "email" in results[0]["document"].lower()


def test_upsert_overwrites(store):
    store.add("test_rules", ids=["r1"], documents=["old text"])
    store.upsert("test_rules", ids=["r1"], documents=["new text"])
    results = store.query("test_rules", query_texts=["new text"], n_results=1)
    assert results[0]["document"] == "new text"


def test_delete(store):
    store.add("test_rules", ids=["r1", "r2"], documents=["a", "b"])
    store.delete("test_rules", ids=["r1"])
    assert store.count("test_rules") == 1


def test_peek(store):
    store.add("test_rules", ids=["r1", "r2"], documents=["a", "b"])
    peeked = store.peek("test_rules", n=2)
    assert len(peeked) == 2


def test_reset(store):
    store.add("test_rules", ids=["r1"], documents=["a"])
    store.reset("test_rules")
    assert store.count("test_rules") == 0
