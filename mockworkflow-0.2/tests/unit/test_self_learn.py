"""Tests for RAG self-learning loop."""

from backend.rag.self_learn import learn_from_task
from backend.schemas.field import FieldSemantic, FieldSpec, SampleProfile, SqlType


def test_learn_from_task(tmp_path, monkeypatch):
    # Track what gets called
    calls = []

    class FakeRuleStore:
        def __init__(self, path):
            pass

        def upsert_fields(self, fields, min_confidence=0.85, source="self_learn"):
            calls.append(("upsert", len(fields)))
            return len(fields)

    class FakeRuleIndexer:
        def index_rules(self, force_rebuild=False):
            calls.append(("index_rules",))
            return 5

    class FakeSampleIndexer:
        def index_profile(self, profile, task_id=None):
            calls.append(("index_profile", task_id))

    monkeypatch.setattr("backend.rag.self_learn.RuleStore", FakeRuleStore)
    monkeypatch.setattr("backend.rag.self_learn.get_rule_indexer", lambda: FakeRuleIndexer())
    monkeypatch.setattr("backend.rag.self_learn.get_sample_indexer", lambda: FakeSampleIndexer())

    profile = SampleProfile(
        file_path="/data/test.csv",
        columns=["id", "name"],
        row_count=10,
    )
    fields = [
        FieldSpec(name="id", type=SqlType.int, semantic=FieldSemantic.id, confidence=0.95),
        FieldSpec(name="name", type=SqlType.varchar, semantic=FieldSemantic.person_name, confidence=0.88),
    ]

    result = learn_from_task(profile, fields, task_id="task-42")
    assert result["rules_upserted"] == 2
    assert result["rules_indexed"] == 5
    assert result["sample_indexed"] == 1

    assert ("upsert", 2) in calls
    assert ("index_rules",) in calls
    assert ("index_profile", "task-42") in calls
