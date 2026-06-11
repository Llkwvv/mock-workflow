"""Tests for sample profile indexing and similarity retrieval."""

from backend.rag.sample_indexer import SampleIndexer, _profile_to_text
from backend.schemas.field import ColumnProfile, SampleProfile, SqlType


def test_profile_to_text():
    profile = SampleProfile(
        file_path="/data/users.csv",
        columns=["id", "name", "email", "age"],
        row_count=100,
        column_profiles={
            "id": ColumnProfile(name="id", inferred_type=SqlType.int, confidence=0.95),
            "age": ColumnProfile(name="age", inferred_type=SqlType.int, confidence=0.9),
        },
    )
    text = _profile_to_text(profile)
    assert "100 rows" in text
    assert "id" in text
    assert "email" in text


def test_index_and_search(tmp_path):
    class FakeStore:
        def __init__(self):
            self._data = {}

        def upsert(self, collection, ids, documents, metadatas=None):
            self._data[collection] = list(zip(ids, documents, metadatas or [{}] * len(ids)))

        def query(self, collection, query_texts, n_results=5, where=None):
            results = []
            for q in query_texts:
                q_lower = q.lower()
                for rid, doc, meta in self._data.get(collection, []):
                    doc_lower = doc.lower()
                    if q_lower in doc_lower or any(col in doc_lower for col in q_lower.replace(",", " ").split()):
                        results.append({
                            "id": rid,
                            "document": doc,
                            "metadata": meta,
                            "distance": 0.15,
                        })
            return results[:n_results]

        def delete(self, collection, ids):
            if collection in self._data:
                self._data[collection] = [
                    item for item in self._data[collection]
                    if item[0] not in ids
                ]

    fake = FakeStore()
    indexer = SampleIndexer(vector_store=fake)

    profile = SampleProfile(
        file_path="/data/users.csv",
        columns=["id", "name", "email", "age"],
        row_count=100,
    )
    doc_id = indexer.index_profile(profile, task_id="task-001")
    assert doc_id == "sample:task-001"

    # Search with a structurally similar profile
    query_profile = SampleProfile(
        file_path="/data/customers.csv",
        columns=["user_id", "full_name", "contact_email", "years_old"],
        row_count=120,
    )
    results = indexer.search_similar_profiles(query_profile, top_k=2)
    assert len(results) >= 1
    assert results[0]["id"] == doc_id

    # Delete and verify cleanup
    indexer.delete_profile(doc_id)
    results_after = indexer.search_similar_profiles(query_profile, top_k=2)
    assert len(results_after) == 0
