"""Rule semantic indexing for RAG.

Indexes existing FieldRules from the JSON rule store into the Chroma
"rules" collection so that semantic retrieval can augment generation.
"""
from pathlib import Path
from typing import Any

from backend.rag.chroma_store import ChromaVectorStore
from backend.rag.embedding import EmbeddingService
from backend.rules.store import RuleStore, FieldRule


RULE_COLLECTION = "rules"


def _rule_to_text(rule: FieldRule) -> str:
    """Convert a FieldRule into a dense natural-language description.

    The text is what gets embedded; it should contain every salient
    signal (name, semantic, type, enum, pool) so that vector search
    can match on any of them.
    """
    parts = [f"Field name: {rule.name}"]
    if rule.aliases:
        parts.append(f"Aliases: {', '.join(rule.aliases)}")
    parts.append(f"SQL type: {rule.type}")
    if rule.length:
        parts.append(f"Length: {rule.length}")
    if rule.comment:
        parts.append(f"Description: {rule.comment}")
    if rule.semantic and rule.semantic != "unknown":
        parts.append(f"Semantic: {rule.semantic}")
    if rule.enum_values:
        parts.append(f"Enum values: {', '.join(rule.enum_values[:20])}")
    if rule.value_pool:
        parts.append(f"Sample values: {', '.join(rule.value_pool[:10])}")
    parts.append(f"Confidence: {rule.confidence}")
    return "; ".join(parts)


class RuleIndexer:
    """Manages the lifecycle of the rules vector index."""

    def __init__(
        self,
        rule_store: RuleStore | None = None,
        vector_store: ChromaVectorStore | None = None,
    ):
        if rule_store is None:
            from backend.config import get_settings
            rule_store = RuleStore(get_settings().rules_file)
        self._rule_store = rule_store
        self._vector_store = vector_store

    def _store(self) -> ChromaVectorStore:
        if self._vector_store is None:
            from backend.app.state import get_vector_store
            self._vector_store = get_vector_store()
        return self._vector_store

    # -- public API --

    def index_rules(self, force_rebuild: bool = False) -> int:
        """Load all rules from the JSON store and upsert them into Chroma.

        Returns the number of rules indexed.
        """
        rules = self._rule_store.load_rules()
        if not rules:
            return 0

        if force_rebuild:
            self._store().reset(RULE_COLLECTION)

        ids = []
        documents = []
        metadatas = []
        for rule in rules:
            rule_id = f"rule:{_normalize(rule.name)}"
            ids.append(rule_id)
            documents.append(_rule_to_text(rule))
            metadatas.append({
                "name": rule.name,
                "type": str(rule.type),
                "semantic": str(rule.semantic),
                "confidence": rule.confidence,
                "source": rule.source,
            })

        self._store().upsert(RULE_COLLECTION, ids=ids, documents=documents, metadatas=metadatas)
        return len(rules)

    def search_similar_rules(
        self,
        query: str,
        top_k: int = 5,
        min_confidence: float | None = None,
    ) -> list[dict[str, Any]]:
        """Semantic search over the rule index.

        Returns a list of result dicts with keys:
            id, document, metadata, distance
        """
        where = None
        if min_confidence is not None:
            # Chroma's Python client accepts simple numeric where filters
            where = {"confidence": {"$gte": min_confidence}}

        results = self._store().query(
            RULE_COLLECTION,
            query_texts=[query],
            n_results=top_k,
            where=where,
        )
        return results


def _normalize(value: str) -> str:
    return "".join(value.strip().lower().split())


# Convenience singleton
_rule_indexer: RuleIndexer | None = None


def get_rule_indexer() -> RuleIndexer:
    global _rule_indexer
    if _rule_indexer is None:
        _rule_indexer = RuleIndexer()
    return _rule_indexer
