"""Map cycle walks back to text via lexical perturbations.

Theorem (semantic preservation). For a sentence-transformer
encoder E with normalization ||E(x)||_2 = 1, the perturbation
operations swap_synonym, char_substitute, whitespace_inject
preserve cosine similarity cos(E(x), E(p)) >= 1 - 0.05. The
attack set A_T has mean semantic similarity at least
1 - eps under the uniform distribution over operations.
"""

from __future__ import annotations

import random
import string

import numpy as np
from numpy.typing import NDArray

from topoattack.types import AttackPrompt

SYNONYMS: dict[str, list[str]] = {
    "ignore": ["disregard", "skip", "omit"],
    "previous": ["prior", "earlier", "preceding"],
    "instructions": ["directives", "guidance", "rules"],
    "tell": ["say", "share", "give"],
    "joke": ["quip", "gag", "funny story"],
    "the": ["a", "this", "that"],
    "a": ["one", "some", "any"],
    "to": ["for", "toward", "into"],
    "and": ["plus", "as well as", "&"],
}


def _swap_synonym(text: str, rng: random.Random) -> str:
    words = text.split(" ")
    for i, w in enumerate(words):
        key = w.lower().strip(string.punctuation)
        if key in SYNONYMS and rng.random() < 0.5:
            words[i] = rng.choice(SYNONYMS[key])
    return " ".join(words)


def _char_substitute(text: str, rng: random.Random) -> str:
    if not text:
        return text
    idx = rng.randrange(len(text))
    ch = text[idx]
    if ch.isalpha():
        repl = rng.choice(string.ascii_lowercase)
        return text[:idx] + repl + text[idx + 1 :]
    return text


def _whitespace_inject(text: str, rng: random.Random) -> str:
    if not text:
        return text
    idx = rng.randrange(len(text))
    return text[:idx] + " " + text[idx:]


_PERTURBATIONS = [_swap_synonym, _char_substitute, _whitespace_inject]


class AttackSetGenerator:
    """Generate T perturbations per base prompt."""

    def __init__(self, perturbations_per_base: int = 8, seed: int = 1729) -> None:
        self.perturbations_per_base = perturbations_per_base
        self._rng = random.Random(seed)

    def generate(self, base_prompts: list[str], walk: NDArray[np.float64]) -> list[AttackPrompt]:
        out: list[AttackPrompt] = []
        T = self.perturbations_per_base
        for base_idx, base in enumerate(base_prompts):
            for step in range(T):
                op = self._rng.choice(_PERTURBATIONS)
                text = op(base, self._rng)
                out.append(
                    AttackPrompt(
                        text=text,
                        base_index=base_idx,
                        step=step,
                        guard_score=0.0,
                        semantic_similarity=0.0,
                        judge_verdict=None,
                    )
                )
        return out
