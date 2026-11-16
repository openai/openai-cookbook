"""Deterministic matching shared by assistant action graders."""

from __future__ import annotations

import re
from collections.abc import Callable, Mapping, Sequence
from typing import Any


def normalize_argument_text(value: object) -> str:
    """Compare caller-provided strings without case or punctuation artifacts."""
    normalized = re.sub(r"[^\w\s]", " ", str(value).casefold().strip())
    return re.sub(r"\s+", " ", normalized).strip()


def expected_arguments_match(expected: Mapping[str, Any], actual: Mapping[str, Any]) -> bool:
    """Match required argument subsets recursively without confusing booleans and numbers."""

    def matches(wanted: Any, observed: Any) -> bool:
        if isinstance(wanted, Mapping):
            return isinstance(observed, Mapping) and expected_arguments_match(wanted, observed)
        if isinstance(wanted, list):
            return (
                isinstance(observed, list)
                and len(wanted) <= len(observed)
                and all(matches(left, right) for left, right in zip(wanted, observed, strict=False))
            )
        if isinstance(wanted, bool) or isinstance(observed, bool):
            return wanted is observed
        if isinstance(wanted, int | float) and isinstance(observed, int | float):
            return wanted == observed
        return normalize_argument_text(wanted) == normalize_argument_text(observed)

    return all(key in actual and matches(value, actual[key]) for key, value in expected.items())


def unique_expected_matches[Expected, Observed](
    expected: Sequence[Expected],
    observed: Sequence[Observed],
    matches: Callable[[Expected, Observed], bool],
) -> list[tuple[int, int]]:
    """Find the maximum one-to-one assignment between expected and observed actions."""
    assigned: dict[int, int] = {}

    def assign(expected_index: int, visited: set[int]) -> bool:
        for observed_index, item in enumerate(observed):
            if observed_index in visited or not matches(expected[expected_index], item):
                continue
            visited.add(observed_index)
            prior = assigned.get(observed_index)
            if prior is None or assign(prior, visited):
                assigned[observed_index] = expected_index
                return True
        return False

    for index in range(len(expected)):
        assign(index, set())
    return sorted((expected_index, observed_index) for observed_index, expected_index in assigned.items())
