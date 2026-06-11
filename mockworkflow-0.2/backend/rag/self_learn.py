"""RAG self-learning loop.

After a task completes successfully, its resolved field specs and sample profile
are fed back into the vector indices so that future tasks can benefit from
historical knowledge.
"""
from backend.rag.rule_indexer import get_rule_indexer
from backend.rag.sample_indexer import get_sample_indexer
from backend.rules.store import RuleStore
from backend.schemas.field import FieldSpec, SampleProfile


def learn_from_task(
    profile: SampleProfile,
    fields: list[FieldSpec],
    task_id: str | None = None,
    rule_store: RuleStore | None = None,
) -> dict[str, int]:
    """Feed a completed task back into the RAG knowledge base.

    This performs three actions:
      1. Upsert the resolved FieldSpecs into the JSON rule store.
      2. Re-index the rules into the Chroma vector store.
      3. Index the sample profile for future similarity search.

    Returns a summary dict with counts of what was learned.
    """
    from backend.config import get_settings
    settings = get_settings()

    if rule_store is None:
        rule_store = RuleStore(settings.rules_file)

    # 1. Persist rules
    upserted = rule_store.upsert_fields(
        fields,
        min_confidence=settings.rules_min_confidence,
        source="self_learn",
    )

    # 2. Refresh vector index (incremental – only re-index if rules changed)
    indexed = 0
    try:
        indexer = get_rule_indexer()
        indexed = indexer.index_rules()
    except Exception as exc:
        print(f"Warning: rule vector index refresh failed ({exc})")

    # 3. Index sample profile
    sample_indexed = False
    try:
        sample_indexer = get_sample_indexer()
        sample_indexer.index_profile(profile, task_id=task_id)
        sample_indexed = True
    except Exception as exc:
        print(f"Warning: sample profile indexing failed ({exc})")

    return {
        "rules_upserted": upserted,
        "rules_indexed": indexed,
        "sample_indexed": 1 if sample_indexed else 0,
    }
