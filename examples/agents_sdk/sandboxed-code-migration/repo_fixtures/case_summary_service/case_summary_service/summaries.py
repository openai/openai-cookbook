from __future__ import annotations

from case_summary_service.client import complete_summary_prompt


def summarize_case(
    client,
    *,
    model: str,
    case_notes: str,
) -> str:
    return complete_summary_prompt(
        client,
        model=model,
        messages=[
            {
                "role": "system",
                "content": "Summarize support case notes for a handoff.",
            },
            {
                "role": "user",
                "content": case_notes,
            },
        ],
    )
