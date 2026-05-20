# Migration request: Chat Completions to Responses

Migrate this case summary service from the legacy Chat Completions call shape to
the Responses API call shape.

## Current structure

- `case_summary_service/client.py` contains the OpenAI client wrapper.
- `case_summary_service/summaries.py` builds the summary prompt and calls the wrapper.
- `tests/` contains offline fakes for the legacy Chat Completions shape.

## Target shape

- In `case_summary_service/client.py`, call `client.responses.create(...)`
  instead of `client.chat.completions.create(...)`.
- Keep the same `model` argument.
- Replace the wrapper's `messages` argument with an `input_items` argument.
- In `case_summary_service/summaries.py`, pass the two-message system/user
  conversation as `input_items`.
- Forward `input_items` as the Responses API `input` argument.
- Keep `temperature=0`.
- Return `response.output_text` instead of `completion.choices[0].message.content`.
- Preserve the `summarize_case(client, *, model, case_notes)` function signature.
- Update client-wrapper and summary tests to fake the Responses API instead of
  Chat Completions.
- Tests must remain offline; do not import or instantiate the real OpenAI client.

## Required validation pipeline

- Before editing, run baseline tests: `python -m unittest discover -s tests -t .`.
- After editing, run the compile/check command: `python -m compileall -q case_summary_service tests`.
- After the compile/check command passes, run final tests: `python -m unittest discover -s tests -t .`.
- Validate with `python -m unittest discover -s tests -t .`.
