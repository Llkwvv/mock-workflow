"""Load semantics.yaml and provide runtime semantic configuration."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

import yaml


@dataclass(frozen=True)
class SemanticConfig:
    name: str
    keywords_en: tuple[str, ...] = ()
    keywords_cn: tuple[str, ...] = ()
    keywords_pinyin: tuple[str, ...] = ()
    faker: str | None = None
    priority: int = 0
    strict_mode_reuse: bool = False


class SemanticRegistry:
    """Runtime registry loaded from semantics.yaml."""

    _instance: SemanticRegistry | None = None
    _configs: dict[str, SemanticConfig]
    _ordered: list[SemanticConfig]

    def __init__(self, configs: list[SemanticConfig]) -> None:
        self._configs = {cfg.name: cfg for cfg in configs}
        self._ordered = sorted(configs, key=lambda c: (-c.priority, c.name))

    @classmethod
    def load(cls, path: str | Path | None = None) -> SemanticRegistry:
        """Load or reload the registry from semantics.yaml."""
        from backend.schemas.field import FieldSemantic

        if path is None:
            here = Path(__file__).parent
            path = here / "semantics.yaml"
        with open(path, "r", encoding="utf-8") as fh:
            raw = yaml.safe_load(fh)
        configs: list[SemanticConfig] = []
        for name, data in raw.get("semantics", {}).items():
            cfg = SemanticConfig(
                name=name,
                keywords_en=tuple(data.get("keywords_en", [])),
                keywords_cn=tuple(data.get("keywords_cn", [])),
                keywords_pinyin=tuple(data.get("keywords_pinyin", [])),
                faker=data.get("faker") or None,
                priority=int(data.get("priority", 0)),
                strict_mode_reuse=bool(data.get("strict_mode_reuse", False)),
            )
            configs.append(cfg)
            # Register into FieldSemantic enum so pydantic accepts it
            FieldSemantic._register_dynamic(name)
        instance = cls(configs)
        cls._instance = instance
        return instance

    @classmethod
    def get(cls) -> SemanticRegistry:
        """Return the cached registry, loading it on first call."""
        if cls._instance is None:
            cls.load()
        return cls._instance

    @property
    def semantics(self) -> list[SemanticConfig]:
        return list(self._ordered)

    @property
    def names(self) -> list[str]:
        return [c.name for c in self._ordered]

    def get_config(self, name: str) -> SemanticConfig | None:
        return self._configs.get(name)

    def match(self, column_name: str) -> SemanticConfig | None:
        """Find the best matching semantic for a column name."""
        normalized = column_name.lower().strip()
        for cfg in self._ordered:
            # Pinyin abbreviation: exact match or suffix match (e.g. "rddw" ends with "dw")
            if normalized in cfg.keywords_pinyin:
                return cfg
            if any(normalized.endswith(kw) for kw in cfg.keywords_pinyin):
                return cfg
            # English keyword containment / suffix
            for kw in cfg.keywords_en:
                if kw.startswith("_"):
                    if normalized.endswith(kw):
                        return cfg
                else:
                    if kw in normalized:
                        return cfg
            # Chinese keyword containment
            for kw in cfg.keywords_cn:
                if kw in column_name:
                    return cfg
        return None

    def to_enum_dict(self) -> dict[str, str]:
        """Return a mapping suitable for building a StrEnum dynamically."""
        return {c.name: c.name for c in self._ordered}
