"""Pattern-template generation for structured text fields.

Many columns hold structured identifiers such as case numbers
(``(2025)苏1203执303号``), document numbers, or codes that mix fixed literal
parts with variable digit runs.  Rather than reproduce the exact sample values
(too repetitive) or invent free text (meaningless), we learn the *skeleton* of
the values and regenerate them by keeping the literal parts and randomising the
digit runs.

The approach is deliberately simple and robust:

1. Decide whether a column looks "structured": its values contain digits AND
   non-digit structural characters, with reasonably high cardinality.
2. To generate a value, pick a random real sample as a stencil and replace each
   maximal run of digits with a random run of the same length (optionally bounded
   by the digits observed at that position across samples).

This keeps the recognisable format (``(YYYY)苏NNNN执NNN号``) while producing new,
non-duplicated values.
"""

from __future__ import annotations

import random
import re
from typing import Callable

_DIGIT_RUN = re.compile(r"\d+")


def _has_digit(value: str) -> bool:
    return any(ch.isdigit() for ch in value)


def _has_non_digit_structure(value: str) -> bool:
    # At least one non-digit, non-CJK character (punctuation / latin) OR a CJK
    # character acting as a separator between digit runs.
    return any((not ch.isdigit()) for ch in value)


def looks_structured(values: list[str]) -> bool:
    """Heuristic: do these values look like structured identifiers?"""
    clean = [v for v in values if v != ""]
    if len(clean) < 2:
        return False
    # Every value must contain digits and some non-digit structure.
    if not all(_has_digit(v) and _has_non_digit_structure(v) for v in clean):
        return False
    # Must contain at least one multi-character digit run somewhere (codes/years),
    # which distinguishes "案号" style strings from plain short text.
    if not any(len(m.group()) >= 2 for v in clean for m in _DIGIT_RUN.finditer(v)):
        return False
    return True


def build_template_generator(values: list[str]) -> Callable[[], str] | None:
    """Build a generator that fabricates structured values from a stencil.

    The recognisable *format* of a sample value is preserved, but every digit
    run is replaced with freshly fabricated digits so that no real identifier is
    reproduced.  Digit runs whose observed values all look like years
    (1990-2099) are constrained to a plausible recent-year range so the output
    still reads as realistic.

    Returns ``None`` when the values do not look structured.
    """
    clean = [v for v in dict.fromkeys(values) if v != ""]
    if not looks_structured(clean):
        return None

    # Determine which positional digit runs behave like a year.
    positional_runs: dict[int, list[str]] = {}
    for value in clean:
        for idx, match in enumerate(_DIGIT_RUN.finditer(value)):
            positional_runs.setdefault(idx, []).append(match.group())

    year_positions: set[int] = set()
    for idx, runs in positional_runs.items():
        if all(len(r) == 4 and r.isdigit() and 1990 <= int(r) <= 2099 for r in runs):
            year_positions.add(idx)

    def _random_run(length: int) -> str:
        if length == 1:
            return str(random.randint(0, 9))
        first = str(random.randint(1, 9))
        rest = "".join(str(random.randint(0, 9)) for _ in range(length - 1))
        return first + rest

    def generate() -> str:
        stencil = random.choice(clean)
        counter = {"i": 0}

        def _replace(match: re.Match) -> str:
            i = counter["i"]
            counter["i"] += 1
            if i in year_positions:
                # Plausible but fabricated year.
                return str(random.randint(2008, 2025))
            return _random_run(len(match.group()))

        return _DIGIT_RUN.sub(_replace, stencil)

    return generate
