"""Simple JSON-backed rule store for field inference results."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from mockagent.schemas.field import FieldSemantic, FieldSpec, SqlType


class FieldRule(BaseModel):
    name: str = Field(min_length=1)
    aliases: list[str] = Field(default_factory=list)
    type: SqlType
    length: int | None = Field(default=None, gt=0)
    precision: int | None = Field(default=None, gt=0)
    scale: int | None = Field(default=None, ge=0)
    nullable: bool = True
    primary_key: bool = False
    auto_increment: bool = False
    comment: str | None = None
    semantic: FieldSemantic = FieldSemantic.unknown
    enum_values: list[str] = Field(default_factory=list)
    value_pool: list[str] = Field(default_factory=list)
    confidence: float = Field(default=0.0, ge=0, le=1)
    source: str = Field(default="llm")
    updated_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def matches(self, column_name: str) -> bool:
        normalized = _normalize(column_name)
        if normalized == _normalize(self.name):
            return True
        return any(normalized == _normalize(alias) for alias in self.aliases)

    def to_field_spec(self) -> FieldSpec:
        return FieldSpec(
            name=self.name,
            type=self.type,
            length=self.length,
            precision=self.precision,
            scale=self.scale,
            nullable=self.nullable,
            primary_key=self.primary_key,
            auto_increment=self.auto_increment,
            comment=self.comment or self.name,
            semantic=self.semantic,
            enum_values=self.enum_values,
            value_pool=self.value_pool,
            uncertain=False,
            confidence=self.confidence,
        )

    @classmethod
    def from_field_spec(
        cls,
        field: FieldSpec,
        aliases: list[str] | None = None,
        source: str = "llm",
    ) -> "FieldRule":
        return cls(
            name=field.name,
            aliases=aliases or [],
            type=field.type,
            length=field.length,
            precision=field.precision,
            scale=field.scale,
            nullable=field.nullable,
            primary_key=field.primary_key,
            auto_increment=field.auto_increment,
            comment=field.comment,
            semantic=field.semantic,
            enum_values=field.enum_values,
            value_pool=field.value_pool,
            confidence=field.confidence or 0.0,
            source=source,
        )


class RuleStore:
    """JSON-backed rule store with exact/alias matching."""

    def __init__(self, file_path: str | Path):
        self.path = Path(file_path)

    def load_rules(self) -> list[FieldRule]:
        if not self.path.exists():
            return []

        raw = json.loads(self.path.read_text(encoding="utf-8"))
        rules_data = raw.get("rules", []) if isinstance(raw, dict) else raw
        if not isinstance(rules_data, list):
            return []

        rules: list[FieldRule] = []
        for item in rules_data:
            try:
                rules.append(FieldRule.model_validate(item))
            except Exception:
                continue
        return rules

    def find(self, column_name: str) -> FieldRule | None:
        for rule in self.load_rules():
            if rule.matches(column_name):
                return rule
        return None

    def resolve(self, column_name: str) -> FieldSpec | None:
        rule = self.find(column_name)
        return rule.to_field_spec() if rule else None

    def upsert_fields(
        self,
        fields: list[FieldSpec],
        min_confidence: float = 0.85,
        source: str = "llm",
    ) -> int:
        existing = self.load_rules()
        existing_by_name = {_normalize(rule.name): rule for rule in existing}
        updated = 0

        for field in fields:
            confidence = field.confidence or 0.0
            if confidence < min_confidence:
                continue
            rule = FieldRule.from_field_spec(field, source=source)
            existing_by_name[_normalize(rule.name)] = rule
            updated += 1

        self._save(list(existing_by_name.values()))
        return updated

    def upsert_value_pool(self, column_name: str, value_pool: list[str]) -> bool:
        """Persist a value pool for an existing rule. Returns True when saved."""
        if not value_pool:
            return False
        existing = self.load_rules()
        key = _normalize(column_name)
        for rule in existing:
            if _normalize(rule.name) == key or any(_normalize(alias) == key for alias in rule.aliases):
                rule.value_pool = list(value_pool)
                rule.updated_at = datetime.now(timezone.utc).isoformat()
                self._save(existing)
                return True
        return False

    def _save(self, rules: list[FieldRule]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "rules": [rule.model_dump(mode="json") for rule in sorted(rules, key=lambda r: r.name)],
        }
        self.path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _normalize(value: str) -> str:
    return "".join(value.strip().lower().split())
