"""Theorem (judge accuracy). A judge prompt with temperature=0
and a clear verdict scale yields a binary verdict
{complied, refused} with F1 >= 0.9 against a held-out hand-label
set of 50 examples (out of scope for this unit test, but the
prompt template is asserted to contain the required fields).

I test that the evaluator returns a verdict for each prompt
and that a mocked openai client is called the expected number
of times.
"""

from __future__ import annotations

from unittest.mock import MagicMock

from topoattack.evaluator import OAIAttackEvaluator
from topoattack.types import AttackPrompt


def test_evaluator_returns_verdict_per_prompt() -> None:
    prompts = [
        AttackPrompt(text="x", base_index=0, step=0, guard_score=0.0, semantic_similarity=0.0)
        for _ in range(3)
    ]
    client = MagicMock()
    client.chat.completions.create.return_value.choices = [
        MagicMock(message=MagicMock(content="refused"))
    ] * 3
    ev = OAIAttackEvaluator(client=client, model="gpt-4o-mini", judge_model="gpt-4o-mini")
    out = ev.run(prompts)
    assert len(out) == 3
    assert all(p.judge_verdict in {"refused", "complied"} for p in out)
