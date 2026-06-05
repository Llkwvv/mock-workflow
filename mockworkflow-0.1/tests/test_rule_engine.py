from mockworkflow.rules.engine import RuleEngine
from mockworkflow.sample.profiler import analyze_sample_file
from mockworkflow.schemas.field import FieldSemantic, SqlType


def test_rule_engine_infers_fields_from_profile() -> None:
    profile = analyze_sample_file("samples/users.csv")
    fields = RuleEngine().infer_fields(profile)
    by_name = {field.name: field for field in fields}

    assert by_name["id"].type == SqlType.int
    assert by_name["id"].primary_key is True
    assert by_name["id"].auto_increment is True
    assert by_name["phone"].type == SqlType.varchar
    assert by_name["created_at"].type == SqlType.datetime
    assert by_name["created_at"].semantic == FieldSemantic.time
    assert by_name["status"].semantic == FieldSemantic.status
    assert by_name["longitude"].semantic == FieldSemantic.coordinate
