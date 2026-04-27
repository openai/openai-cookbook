# Migration request: Chat Completions to Responses

Migrate this package from the legacy Chat Completions call shape to the
Responses API call shape.

## Current structure

- `customer_support_bot/client.py` contains the OpenAI client wrapper.
- `customer_support_bot/replies.py` builds the support reply prompt and calls the wrapper.
- `tests/` contains offline fakes for the legacy Chat Completions shape.

## Target shape

- In `customer_support_bot/client.py`, call `client.responses.create(...)`
  instead of `client.chat.completions.create(...)`.
- Keep the same `model` argument.
- Replace the wrapper's `messages` argument with an `input_items` argument.
- In `customer_support_bot/replies.py`, pass the two-message system/user
  conversation as `input_items`.
- Forward `input_items` as the Responses API `input` argument.
- Keep `temperature=0`.
- Return `response.output_text` instead of `completion.choices[0].message.content`.
- Preserve the `draft_reply(client, *, model, case_id, customer_message)` function signature.
- Update client-wrapper and reply tests to fake the Responses API instead of
  Chat Completions.
- Tests must remain offline; do not import or instantiate the real OpenAI client.

## Required validation pipeline

- Before editing, run baseline tests: `python -m unittest discover -s tests -t .`.
- After editing, run the compile/check command: `python -m compileall -q customer_support_bot tests`.
- After the compile/check command passes, run final tests: `python -m unittest discover -s tests -t .`.
- Validate with `python -m unittest discover -s tests -t .`.
