from __future__ import annotations

from typing import Any


def complete_support_prompt(
    client: Any,
    *,
    model: str,
    messages: list[dict[str, str]],
) -> str:
    completion = client.chat.completions.create(
        model=model,
        messages=messages,
        temperature=0,
    )
    if not completion.choices:
        raise ValueError("No choices returned from the API")
    return completion.choices[0].message.content
