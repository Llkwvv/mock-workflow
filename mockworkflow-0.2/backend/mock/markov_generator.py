"""Character-level N-gram (Markov chain) text generator.

Used for free-text fields with high cardinality where neither frequency
sampling (too repetitive) nor template regeneration (not structured) is a good
fit -- e.g. organisation names like "泰州市高港区人民法院" or company names.

The model learns character transition probabilities of a given order from the
sample values and generates new strings that look structurally similar but are
not necessarily identical to any single sample.  Because real samples are often
small, generation includes guards: it constrains length to the observed range
and retries a few times to avoid emitting an exact copy of a sample.
"""

from __future__ import annotations

import random
from collections import defaultdict
from typing import Callable

_START = "\x02"  # text start marker
_END = "\x03"    # text end marker


class _MarkovModel:
    def __init__(self, order: int = 2):
        self.order = order
        self.transitions: dict[str, list[str]] = defaultdict(list)
        self.min_len = 1
        self.max_len = 50
        self.samples: set[str] = set()

    def fit(self, values: list[str]) -> None:
        clean = [v for v in values if v]
        if not clean:
            return
        self.samples = set(clean)
        lengths = [len(v) for v in clean]
        self.min_len = max(1, min(lengths))
        self.max_len = max(lengths)

        for value in clean:
            padded = _START * self.order + value + _END
            for i in range(len(padded) - self.order):
                key = padded[i : i + self.order]
                nxt = padded[i + self.order]
                self.transitions[key].append(nxt)

    def generate(self, max_attempts: int = 12) -> str | None:
        if not self.transitions:
            return None

        for _ in range(max_attempts):
            key = _START * self.order
            out: list[str] = []
            # Hard cap to avoid runaway generation.
            for _ in range(self.max_len + self.order + 5):
                choices = self.transitions.get(key)
                if not choices:
                    break
                nxt = random.choice(choices)
                if nxt == _END:
                    break
                out.append(nxt)
                key = (key + nxt)[-self.order :]

            result = "".join(out)
            if self.min_len <= len(result) <= self.max_len:
                return result

        # Last resort: return the closest-to-valid attempt or a real sample.
        return None


def build_markov_generator(
    values: list[str],
    order: int = 2,
) -> Callable[[], str | None] | None:
    """Build a Markov text generator from sample values.

    Returns ``None`` if the values are unsuitable (too few / too short) for
    meaningful modelling.

    The returned generator yields a fabricated string that is guaranteed never
    to be an exact copy of any sample value; when it cannot produce such a
    string it returns ``None``.  It never reuses a real sample value, so
    generated test data cannot leak real data.
    """
    clean = [v for v in values if v]
    # Need a little material to learn from; otherwise the chain just echoes input.
    if len(clean) < 2:
        return None
    if max(len(v) for v in clean) < 2:
        return None

    model = _MarkovModel(order=order)
    model.fit(clean)
    sample_set = set(clean)

    def generate() -> str | None:
        for _ in range(8):
            result = model.generate()
            if result is None:
                break
            if result in sample_set:
                continue
            return result
        return None

    return generate
