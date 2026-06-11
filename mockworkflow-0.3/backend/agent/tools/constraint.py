"""Agent tool: infer cross-field constraints for mock data generation."""

from backend.mock.constraint_engine import infer_constraints
from backend.schemas.field import ConstraintSpec, FieldSpec


def infer_field_constraints(fields: list[FieldSpec]) -> list[ConstraintSpec]:
    """Analyze field specs and return inferred cross-field constraints.

    This is a thin wrapper over the core constraint engine; it can be
    extended later to call an LLM for semantic constraint discovery.
    """
    return infer_constraints(fields)
