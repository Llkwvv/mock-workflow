"""Tests for RAG rule indexing and semantic retrieval."""

import pytest

from backend.rag.rule_indexer import RuleIndexer, _rule_to_text
from backend.rules.store import FieldRule, RuleStore
from backend.schemas.field import FieldSemantic, SqlType


def test_rule_to_text():
    rule = FieldRule(
        name="email",
        type=SqlType.varchar,
        length=255,
        comment="User email address",
        semantic=FieldSemantic.email,
        enum_values=["a@b.com", "c@d.com"],
        confidence=0.95,
        source="llm",
    )
    text = _rule_to_text(rule)
    assert "email" in text
    assert "VARCHAR" in text
    assert "User email address" in text
    assert "email" in text  # semantic
    assert "a@b.com" in text  # enum values
    assert "0.95" in text


def test_index_and_search(tmp_path, monkeypatch):
    # Build a tiny rule store
    store = RuleStore(tmp_path / "rules.json")
    store.upsert_fields([
        FieldRule(name="email", type=SqlType.varchar, semantic=FieldSemantic.email, confidence=0.95).to_field_spec(),
        FieldRule(name="phone", type=SqlType.varchar, semantic=FieldSemantic.phone_number, confidence=0.92).to_field_spec(),
        FieldRule(name="name", type=SqlType.varchar, semantic=FieldSemantic.id, confidence=0.88).to_field_spec(),
    ])

    # Mock the vector store to avoid heavy embedding in tests
    class FakeStore:
        def __init__(self):
            self._data = {}

        def upsert(self, collection, ids, documents, metadatas=None):
            self._data[collection] = list(zip(ids, documents, metadatas or [{}] * len(ids)))

        def query(self, collection, query_texts, n_results=5, where=None):
            # Fake semantic search: match on metadata semantic or document content
            results = []
            for q in query_texts:
                q_lower = q.lower()
                for rid, doc, meta in self._data.get(collection, []):
                    doc_lower = doc.lower()
                    meta_semantic = meta.get("semantic", "").lower()
                    if q_lower in doc_lower or q_lower in meta_semantic or meta_semantic in q_lower:
                        results.append({
                            "id": rid,
                            "document": doc,
                            "metadata": meta,
                            "distance": 0.1,
                        })
            return results[:n_results]

        def reset(self, collection):
            self._data.pop(collection, None)

    fake = FakeStore()
    indexer = RuleIndexer(rule_store=store, vector_store=fake)

    # Index rules
    count = indexer.index_rules()
    assert count == 3

    # Search for email-like query
    results = indexer.search_similar_rules("email", top_k=2)
    assert len(results) >= 1
    assert results[0]["metadata"]["semantic"] == "email"

    # Search for phone-like query
    results = indexer.search_similar_rules("phone", top_k=2)
    assert len(results) >= 1
    assert results[0]["metadata"]["semantic"] == "phone_number"


def test_index_rules_force_rebuild(tmp_path, monkeypatch):
    store = RuleStore(tmp_path / "rules.json")
    store.upsert_fields([
        FieldRule(name="id", type=SqlType.int, semantic=FieldSemantic.unknown, confidence=0.99).to_field_spec(),
    ])

    class FakeStore:
        def __init__(self):
            self._calls = []

        def upsert(self, collection, ids, documents, metadatas=None):
            self._calls.append(("upsert", ids))

        def reset(self, collection):
            self._calls.append(("reset", collection))

    fake = FakeStore()
    indexer = RuleIndexer(rule_store=store, vector_store=fake)
    indexer.index_rules(force_rebuild=True)
    assert ("reset", "rules") in fake._calls
