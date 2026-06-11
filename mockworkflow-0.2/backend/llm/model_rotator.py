"""Model rotation and fallback logic extracted from ms-claude proxy.

Usage in OpenAIFieldParser:
    from backend.llm.model_rotator import ModelRotator
    from backend.llm.model_pool import get_model_pool

    rotator = ModelRotator(get_model_pool())

    # Inside parse_fields(), when request fails:
    rotator.record_failure(model_name, str(error))
    next_model = rotator.select_model(excluded={model_name})
    # retry with next_model

    # When request succeeds:
    rotator.record_success(model_name)
"""

from __future__ import annotations

import json
import logging
import os
import time
from collections import defaultdict, deque
from dataclasses import dataclass, field
from pathlib import Path
from threading import Lock
from typing import Any

from backend.llm.model_pool import ModelInfo, ModelPool

logger = logging.getLogger(__name__)


@dataclass
class RotatorConfig:
    """Configuration for model rotation."""

    max_retries: int = 3
    failure_threshold: int = 5
    failure_window_seconds: int = 3600
    persist_last_success: bool = True
    last_success_file: Path = field(
        default_factory=lambda: Path.home() / ".config" / "mockworkflow" / "last_success_model.json"
    )


class FailureTracker:
    """Tracks model failures and checks if a model has exceeded failure threshold."""

    def __init__(self, config: RotatorConfig):
        self.config = config
        self._lock = Lock()
        self._failures: dict[str, deque[float]] = defaultdict(
            lambda: deque(maxlen=100)
        )
        self._stats: dict[str, dict[str, int]] = defaultdict(
            lambda: defaultdict(int)
        )

    def record_failure(self, model_name: str, error_message: str) -> None:
        """Record a failure for a model."""
        with self._lock:
            self._failures[model_name].append(time.time())
            self._stats[model_name]["total_failures"] += 1
            logger.warning("Recorded failure for %s: %s", model_name, error_message[:200])

    def record_success(self, model_name: str) -> None:
        """Record a successful request for a model."""
        with self._lock:
            self._stats[model_name]["success"] += 1

    def is_over_threshold(self, model_name: str) -> bool:
        """Check if a model has exceeded the failure threshold within the time window."""
        with self._lock:
            cutoff = time.time() - self.config.failure_window_seconds
            recent = [t for t in self._failures.get(model_name, []) if t > cutoff]
            return len(recent) >= self.config.failure_threshold

    def get_stats(self, model_name: str) -> dict[str, Any]:
        """Get failure statistics for a model."""
        with self._lock:
            cutoff = time.time() - self.config.failure_window_seconds
            recent = [t for t in self._failures.get(model_name, []) if t > cutoff]
            stats = dict(self._stats.get(model_name, {}))
            stats["recent_failures"] = len(recent)
            return stats


class ModelRotator:
    """Manages model selection with fallback, blacklist, and failure tracking.

    Ported from ms-claude's ProxyService._select_model_excluding logic.
    """

    def __init__(
        self,
        model_pool: ModelPool,
        config: RotatorConfig | None = None,
        blacklist: set[str] | None = None,
        group_aliases: dict[str, str] | None = None,
    ):
        self.model_pool = model_pool
        self.config = config or RotatorConfig()
        self.failure_tracker = FailureTracker(self.config)

        # Blacklist – 明确不可用（连接失败、认证错误、配额耗尽等）
        self._blacklist: set[str] = set(blacklist) if blacklist else set()

        # Degraded – 返回了响应但没有 choices（格式异常、参数不支持、负载问题等）。
        # 区别于 blacklist：降级模型冷却时间更短，可能自动恢复。
        self._degraded: set[str] = set()
        self._degraded_cooldown_seconds: int = 300  # 5 分钟冷却
        self._degraded_since: dict[str, float] = {}

        # Skip-auto – 不参与自动轮换，但用户明确指定（forced / requested）时仍可用。
        # 与 blacklist 的区别：黑名单是完全禁用；skip-auto 只是不参与自动选择。
        self._skip_auto: set[str] = set()

        # Model groups: group_name -> set of model names
        self._model_groups: dict[str, set[str]] = {}
        self._model_group_aliases: dict[str, str] = dict(group_aliases) if group_aliases else {}

        # Forced model (e.g. from env var or user command)
        self._forced_model: str = ""

        # Last successful model
        self._last_successful_model: str | None = None
        self._load_last_successful_model()

    # ------------------------------------------------------------------
    # Persistence
    # ------------------------------------------------------------------
    def _load_last_successful_model(self) -> None:
        """Load last successful model from disk."""
        if not self.config.persist_last_success:
            return
        try:
            path = self.config.last_success_file
            if path.exists():
                with open(path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                self._last_successful_model = data.get("last_successful_model")
                if self._last_successful_model:
                    logger.info("Loaded last successful model: %s", self._last_successful_model)
        except Exception as exc:
            logger.warning("Failed to load last successful model: %s", exc)

    def _save_last_successful_model(self) -> None:
        """Save last successful model to disk."""
        if not self.config.persist_last_success or not self._last_successful_model:
            return
        try:
            path = self.config.last_success_file
            path.parent.mkdir(parents=True, exist_ok=True)
            with open(path, "w", encoding="utf-8") as f:
                json.dump({"last_successful_model": self._last_successful_model}, f)
        except Exception as exc:
            logger.warning("Failed to save last successful model: %s", exc)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------
    def set_forced_model(self, model_name: str) -> None:
        """Force a specific model (highest priority). Pass empty string to clear."""
        self._forced_model = model_name
        if model_name:
            logger.info("Forced model set to: %s", model_name)
        else:
            logger.info("Forced model cleared, back to auto-selection")

    def add_blacklist(self, model_name: str, reason: str = "") -> None:
        """Add a model to the blacklist."""
        self._blacklist.add(model_name)
        logger.info("Model %s blacklisted: %s", model_name, reason or "no reason")

    def remove_blacklist(self, model_name: str) -> None:
        """Remove a model from the blacklist."""
        self._blacklist.discard(model_name)

    def skip_auto(self, model_name: str) -> None:
        """Exclude a model from automatic rotation.

        The model can still be used when explicitly requested
        (forced model or payload model), but will never be picked
        automatically.
        """
        self._skip_auto.add(model_name)
        logger.info("Model %s excluded from auto rotation", model_name)

    def restore_auto(self, model_name: str) -> None:
        """Restore a model to automatic rotation."""
        self._skip_auto.discard(model_name)

    def is_skip_auto(self, model_name: str) -> bool:
        """Check if a model is excluded from automatic rotation."""
        return model_name in self._skip_auto

    def set_model_groups(self, groups: dict[str, list[str]]) -> None:
        """Set model groups. Each group is a list of model names."""
        self._model_groups = {name: set(models) for name, models in groups.items()}
        logger.info("Loaded %d model groups", len(self._model_groups))

    def set_group_aliases(self, aliases: dict[str, str]) -> None:
        """Set model group aliases. alias -> group_name."""
        self._model_group_aliases = dict(aliases)

    def record_failure(self, model_name: str, error_message: str) -> None:
        """Record that a model failed."""
        self.failure_tracker.record_failure(model_name, error_message)

    def record_success(self, model_name: str) -> None:
        """Record that a model succeeded."""
        self._last_successful_model = model_name
        self._save_last_successful_model()
        self.failure_tracker.record_success(model_name)

    # ------------------------------------------------------------------
    # Core selection logic
    # ------------------------------------------------------------------
    def select_model(
        self,
        requested_model: str | None = None,
        excluded: set[str] | None = None,
    ) -> str | None:
        """Select the best available model.

        Priority order:
        1. Forced model (if set and usable)
        2. Group match (if requested_model maps to a group)
        3. Last successful model (if usable)
        4. Requested model (if usable)
        5. Any available model by priority

        Args:
            requested_model: Model name requested by payload.
            excluded: Model names to skip this attempt.

        Returns:
            Selected model name, or None if no model is available.
        """
        excluded = excluded or set()
        models = self._get_enabled_models()
        if not models:
            logger.error("No enabled models in pool")
            return None

        # 1. Forced model (highest priority) – skip_auto 不生效，用户明确指定
        if self._forced_model and self._forced_model not in excluded:
            if self._is_usable(self._forced_model, excluded, auto_select=False):
                logger.info("Using forced model: %s", self._forced_model)
                return self._forced_model
            logger.warning(
                "Forced model '%s' is not available, falling back",
                self._forced_model,
            )

        # 2. Resolve group from requested model – 组内自动选择，跳过 skip_auto
        group_name = self._resolve_group(requested_model) if requested_model else None
        if group_name:
            model_name = self._select_from_group(group_name, excluded, auto_select=True)
            if model_name:
                return model_name
            logger.warning("All models in group '%s' failed, falling back", group_name)

        # 3. Last successful model – 自动选择，跳过 skip_auto
        if (
            self._last_successful_model
            and self._last_successful_model not in excluded
            and self._is_usable(self._last_successful_model, excluded, auto_select=True)
        ):
            return self._last_successful_model

        # 4. Requested model itself – skip_auto 不生效，用户明确请求
        if requested_model and requested_model not in excluded:
            if self._is_usable(requested_model, excluded, auto_select=False):
                return requested_model

        # 5. Any available model by priority – 自动选择，跳过 skip_auto
        for model in sorted(models, key=lambda m: m.priority, reverse=True):
            if self._is_usable(model.name, excluded, auto_select=True):
                return model.name

        logger.error("No available model after trying all options")
        return None

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------
    def _get_enabled_models(self) -> list[ModelInfo]:
        """Get enabled models from pool."""
        return self.model_pool.get_enabled_models()

    def _is_usable(self, model_name: str, excluded: set[str], auto_select: bool = False) -> bool:
        """Check if a model is usable.

        Args:
            auto_select: When True, also reject models in _skip_auto
                         (they won't be picked automatically but can still
                         be used when explicitly requested).
        """
        if model_name in self._blacklist:
            logger.debug("Model %s is blacklisted, skipping", model_name)
            return False
        if model_name in excluded:
            return False
        if auto_select and model_name in self._skip_auto:
            logger.debug("Model %s is skip-auto, skipping in auto selection", model_name)
            return False
        enabled = {m.name for m in self._get_enabled_models()}
        if model_name not in enabled:
            logger.debug("Model %s is not enabled, skipping", model_name)
            return False
        if self.failure_tracker.is_over_threshold(model_name):
            logger.debug("Model %s exceeded failure threshold, skipping", model_name)
            return False
        return True

    def _resolve_group(self, model_name: str | None) -> str | None:
        """Resolve a model name to a group name."""
        if not model_name:
            return None
        if model_name in self._model_groups:
            return model_name
        if model_name in self._model_group_aliases:
            return self._model_group_aliases[model_name]
        return None

    def _select_from_group(self, group_name: str, excluded: set[str], auto_select: bool = False) -> str | None:
        """Select a model from a specific group."""
        group_models = self._model_groups.get(group_name, set())
        if not group_models:
            logger.warning("Group '%s' is empty", group_name)
            return None

        # Prefer last successful if in group
        if (
            self._last_successful_model
            and self._last_successful_model not in excluded
            and self._last_successful_model in group_models
            and self._is_usable(self._last_successful_model, excluded, auto_select)
        ):
            logger.debug(
                "Using last successful model in group '%s': %s",
                group_name,
                self._last_successful_model,
            )
            return self._last_successful_model

        # Pick highest priority model in group
        for model in sorted(self._get_enabled_models(), key=lambda m: m.priority, reverse=True):
            if model.name in group_models and self._is_usable(model.name, excluded, auto_select):
                logger.debug("Selected model from group '%s': %s", group_name, model.name)
                return model.name

        return None
