from __future__ import annotations

from customer_support_bot.client import complete_support_prompt


def draft_reply(
    client,
    *,
    model: str,
    case_id: str,
    customer_message: str,
) -> str:
    return complete_support_prompt(
        client,
        model=model,
        messages=[
            {
                "role": "system",
                "content": "You draft concise, empathetic support replies.",
            },
            {
                "role": "user",
                "content": f"Case {case_id}: {customer_message}",
            },
        ],
    )
