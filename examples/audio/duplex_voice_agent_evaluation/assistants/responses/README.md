# OpenAI-managed Responses delegation

Configures GPT Live with `session.delegation.type: "responses"`. GPT Live owns
backend conversation continuity and result injection; application
tool calls execute inside the assistant against isolated application-owned
state. Evaluators only observe tool events and final state.

Commands assume the harness directory. See [setup](../../README.md#3-set-up-and-run)
for setup and installed-wheel usage; live commands incur API usage.

Everything needed to customize this backend lives in this folder:
`prompts/backend.txt`, `tools/restaurant.py`, `tools/definitions.json`, and
`tools/restaurant_facts.json`. Frontend instructions live in
`../frontend/prompts/voice.txt`.

The bundled restaurant behavior follows the
[comparison-baseline contract](../README.md#bundled-comparison-baseline).
Keep baseline fixes aligned with the client assistant; document intentional variants.

```bash
uv run run-eval --scenario restaurant_booking_complete --assistant responses
```
