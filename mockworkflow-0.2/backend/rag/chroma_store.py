"""Chroma-based vector store for RAG.

Supports two collections:
  - "rules"   : existing mock rules (for semantic rule retrieval)
  - "samples" : historical sample profiles (for similar-sample recall)

Persistence path: project_root / "chroma_db" (local file-based, no server needed).
"""
from pathlib import Path
from typing import Any, Sequence

import chromadb
from chromadb.config import Settings as ChromaSettings

from backend.rag.embedding import EmbeddingService, get_embedding_service

DEFAULT_COLLECTIONS = ("rules", "samples")


class ChromaVectorStore:
    """Lightweight wrapper around ChromaDB PersistentClient.

    All vectors are stored locally in a SQLite-backed directory so the stack
    stays single-instance and zero-network-dependency after the first run.
    """

    def __init__(
        self,
        persist_dir: str | Path,
        embedding_service: EmbeddingService | None = None,
        collections: Sequence[str] | None = None,
    ):
        self._persist_dir = Path(persist_dir)
        self._persist_dir.mkdir(parents=True, exist_ok=True)
        self._client = chromadb.PersistentClient(
            path=str(self._persist_dir),
            settings=ChromaSettings(anonymized_telemetry=False),
        )
        self._embedding = embedding_service or get_embedding_service()
        self._collections: dict[str, Any] = {}
        for name in collections or DEFAULT_COLLECTIONS:
            self._collections[name] = self._client.get_or_create_collection(
                name=name,
                metadata={"hnsw:space": "cosine"},
            )

    # -- public API --

    def collection(self, name: str):
        if name not in self._collections:
            self._collections[name] = self._client.get_or_create_collection(
                name=name,
                metadata={"hnsw:space": "cosine"},
            )
        return self._collections[name]

    def add(
        self,
        collection_name: str,
        ids: Sequence[str],
        documents: Sequence[str],
        metadatas: Sequence[dict[str, Any]] | None = None,
    ) -> None:
        """Add documents to a collection. Vectors are computed on the fly."""
        coll = self.collection(collection_name)
        embeddings = self._embedding.encode(documents).tolist()
        coll.add(
            ids=list(ids),
            documents=list(documents),
            embeddings=embeddings,
            metadatas=list(metadatas) if metadatas else None,
        )

    def upsert(
        self,
        collection_name: str,
        ids: Sequence[str],
        documents: Sequence[str],
        metadatas: Sequence[dict[str, Any]] | None = None,
    ) -> None:
        """Upsert (insert or overwrite) documents into a collection."""
        coll = self.collection(collection_name)
        embeddings = self._embedding.encode(documents).tolist()
        coll.upsert(
            ids=list(ids),
            documents=list(documents),
            embeddings=embeddings,
            metadatas=list(metadatas) if metadatas else None,
        )

    def query(
        self,
        collection_name: str,
        query_texts: Sequence[str],
        n_results: int = 5,
        where: dict[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        """Semantic search by text. Returns a list of result dicts.

        Each result dict has:
            id, document, metadata, distance
        """
        coll = self.collection(collection_name)
        query_embeddings = self._embedding.encode(query_texts).tolist()
        results = coll.query(
            query_embeddings=query_embeddings,
            n_results=n_results,
            where=where,
            include=["documents", "metadatas", "distances"],
        )
        # Flatten the nested lists returned by Chroma
        output = []
        for i, ids in enumerate(results["ids"]):
            for j, doc_id in enumerate(ids):
                output.append({
                    "id": doc_id,
                    "document": results["documents"][i][j],
                    "metadata": results["metadatas"][i][j] if results["metadatas"] else {},
                    "distance": results["distances"][i][j],
                })
        return output

    def delete(self, collection_name: str, ids: Sequence[str]) -> None:
        self.collection(collection_name).delete(ids=list(ids))

    def count(self, collection_name: str) -> int:
        return self.collection(collection_name).count()

    def peek(self, collection_name: str, n: int = 5) -> list[dict[str, Any]]:
        """Return the first n items in a collection (useful for debugging)."""
        coll = self.collection(collection_name)
        res = coll.peek(limit=n)
        return [
            {"id": _id, "document": doc, "metadata": meta or {}}
            for _id, doc, meta in zip(res["ids"], res["documents"], res.get("metadatas") or [{}] * len(res["ids"]))
        ]

    def reset(self, collection_name: str) -> None:
        """Drop and recreate a collection (dangerous – mainly for tests)."""
        self._client.delete_collection(name=collection_name)
        self._collections.pop(collection_name, None)
        self.collection(collection_name)
