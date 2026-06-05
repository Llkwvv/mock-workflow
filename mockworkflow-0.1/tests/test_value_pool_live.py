"""Live integration test: verify value pool generation against the real LLM.

Run directly (not via pytest) so output is visible:
    .venv/bin/python tests/test_value_pool_live.py

Uses settings from .env. Not part of the default pytest suite.
"""

from mockworkflow.config import get_settings
from mockworkflow.llm.value_pool import ensure_value_pools
from mockworkflow.schemas.field import FieldSemantic, FieldSpec, SampleProfile, SqlType


def main() -> None:
    settings = get_settings()
    # force-enable pool generation in this script even if .env didn't set it
    settings = settings.model_copy(update={
        "llm_enabled": True,
        "llm_value_pool_enabled": True,
        "llm_value_pool_size": 10,
        "llm_timeout": 90,
        "rules_autosave": False,  # don't pollute default_rules.json
    })

    print(f"Using model={settings.llm_model}, base_url={settings.llm_base_url}, timeout={settings.llm_timeout}s")

    fields = [
        FieldSpec(name="车型", type=SqlType.varchar, length=50, semantic=FieldSemantic.vehicle_model),
        FieldSpec(name="所属公司", type=SqlType.varchar, length=255, semantic=FieldSemantic.unknown),
    ]
    profile = SampleProfile(
        file_path="inline",
        columns=["车型", "所属公司"],
        samples={
            "车型": ["凯美瑞", "轩逸", "新桑塔纳"],
            "所属公司": ["泰州天顺出租汽车有限公司", "泰州国通出租汽车有限公司"],
        },
    )

    generated = ensure_value_pools(fields, profile, settings=settings)
    print(f"\nvalue_pools_generated = {generated}\n")

    for f in fields:
        print(f"--- {f.name} (pool size={len(f.value_pool)}) ---")
        for v in f.value_pool:
            print(f"  {v}")
        print()


if __name__ == "__main__":
    main()
