"""Sample profile indexing for RAG.

Indexes historical sample profiles into the Chroma "samples" collection so that
new tasks can retrieve similar past samples and reuse their field resolutions
or generation settings as guidance.
"""
from pathlib import Path
from typing import Any, Optional

from backend.rag.chroma_store import ChromaVectorStore
from backend.schemas.field import SampleProfile, ColumnProfile

SAMPLE_COLLECTION = "samples"


def _profile_to_text(profile: SampleProfile) -> str:
    """Convert a SampleProfile into a dense natural-language description.

    Includes column names, inferred types, and any strong signals (distributions,
    high-confidence semantics) so that vector search can match structurally
    similar files even when column names differ.
    """
    parts = [f"Table with {profile.row_count} rows and {len(profile.columns)} columns."]
    parts.append(f"Columns: {', '.join(profile.columns)}")

    type_hints = []
    semantic_hints = []
    for col in profile.columns:
        cp = profile.column_profiles.get(col)
        if cp is None:
            continue
        if cp.inferred_type:
            type_hints.append(f"{col} is {cp.inferred_type}")
        if cp.confidence and cp.confidence > 0.7:
            # If we have a high-confidence semantic hint, surface it
            pass  # inferred_type already captures the type
    if type_hints:
        parts.append("Type hints: " + "; ".join(type_hints[:10]))

    return " ".join(parts)


class SampleIndexer:
    """Manages the lifecycle of the sample profile vector index."""

    def __init__(self, vector_store: ChromaVectorStore | None = None):
        self._vector_store = vector_store

    def _store(self) -> ChromaVectorStore:
        if self._vector_store is None:
            from backend.app.state import get_vector_store
            self._vector_store = get_vector_store()
        return self._vector_store

    # -- public API --

    def index_profile(self, profile: SampleProfile, task_id: str | None = None) -> str:
        """Index a single sample profile. Returns the document ID."""
        doc_id = f"sample:{task_id or Path(profile.file_path).stem}"
        document = _profile_to_text(profile)
        metadata = {
            "file_path": profile.file_path,
            "row_count": profile.row_count,
            "column_count": len(profile.columns),
            "columns": ",".join(profile.columns)[:500],  # Chroma metadata has limits
        }
        self._store().upsert(SAMPLE_COLLECTION, ids=[doc_id], documents=[document], metadatas=[metadata])
        return doc_id

    def search_similar_profiles(
        self,
        profile: SampleProfile,
        top_k: int = 3,
    ) -> list[dict[str, Any]]:
        """Find historically similar sample profiles.

        Returns a list of result dicts with keys:
            id, document, metadata, distance
        """
        query_text = _profile_to_text(profile)
        return self._store().query(
            SAMPLE_COLLECTION,
            query_texts=[query_text],
            n_results=top_k,
        )

    def search_similar_columns(
        self,
        column_name: str,
        top_k: int = 5,
        min_confidence: float = 0.5,
    ) -> list[dict[str, Any]]:
        """Find historically similar columns by name.

        Searches the samples collection for columns with similar names
        to the given column name using vector similarity. This allows
        matching columns like "cust_id" to "customer_id" when they
        have the same semantic meaning.

        Returns a list of result dicts with keys:
            id, document, metadata, confidence, distance
        """
        query_text = f"Column: {column_name}"
        results = self._store().query(
            SAMPLE_COLLECTION,
            query_texts=[query_text],
            n_results=top_k,
            include=["documents", "metadatas", "distances"],
        )

        # Filter results by confidence threshold and extract column-level info
        filtered = []
        for i, doc_id in enumerate(results["ids"][0] or []):
            distance = results["distances"][0][i] if results["distances"] else 1.0
            metadata = results["metadatas"][0][i] or {}
            # Convert distance (cosine distance) to similarity confidence
            confidence = 1.0 - distance if distance is not None else 0.0
            if confidence >= min_confidence:
                filtered.append({
                    "id": doc_id,
                    "document": results["documents"][0][i],
                    "metadata": metadata,
                    "confidence": confidence,
                    "distance": distance,
                })
        return filtered

    def delete_profile(self, doc_id: str) -> None:
        self._store().delete(SAMPLE_COLLECTION, ids=[doc_id])


# Convenience singleton
_sample_indexer: SampleIndexer | None = None


def get_sample_indexer() -> SampleIndexer:
    global _sample_indexer
    if _sample_indexer is None:
        _sample_indexer = SampleIndexer()
    return _sample_indexer
