"""Frequency-weighted sampling for categorical / enum-like fields.

Given the distinct values observed in a sample together with their occurrence
counts, generate new values by sampling according to the empirical frequency
distribution.  This makes generated data reuse real values in roughly the same
proportions as the source data (e.g. a column that is 90% "黑榜" stays ~90%
"黑榜").
"""

from __future__ import annotations

import random
from typing import Callable


def build_frequency_sampler(
    value_frequency: dict[str, int] | None,
    fallback_values: list[str] | None = None,
    keep_empty: bool = False,
) -> Callable[[], str] | None:
    """Build a closure that returns a value sampled by empirical frequency.

    Args:
        value_frequency: Mapping of distinct value -> occurrence count.
        fallback_values: Used (with uniform weights) when ``value_frequency``
            is empty but distinct values are still available.
        keep_empty: When True, blank ("") values are kept so they are
            reproduced in roughly the same proportion as the source data.

    Returns:
        A zero-arg callable returning a sampled string, or ``None`` if there is
        nothing to sample from.
    """
    freq = {
        k: v
        for k, v in (value_frequency or {}).items()
        if v > 0 and (keep_empty or k != "")
    }

    if not freq and fallback_values:
        freq = {v: 1 for v in fallback_values if keep_empty or v != ""}

    if not freq:
        return None

    population = list(freq.keys())
    weights = list(freq.values())

    def sample() -> str:
        return random.choices(population, weights=weights, k=1)[0]

    return sample
