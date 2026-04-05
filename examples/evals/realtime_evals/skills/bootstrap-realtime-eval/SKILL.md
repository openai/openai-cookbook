---
name: bootstrap-realtime-eval
description: Bootstrap a new realtime eval folder inside this cookbook repo by choosing the right harness from examples/evals/realtime_evals, scaffolding prompt/tools/data files, generating a useful README, and validating it with smoke, full eval, and test runs. Use when a user wants to start a new crawl, walk, or run realtime eval in this repository.
---

# Bootstrap Realtime Eval

Use this skill when the user wants a new realtime eval scaffold under `examples/evals/realtime_evals/`.

This skill is repo-specific. Do not copy harness code into the generated folder. The generated eval should point at the shared harnesses already in:

- `examples/evals/realtime_evals/crawl_harness`
- `examples/evals/realtime_evals/walk_harness`
- `examples/evals/realtime_evals/run_harness`

## Inputs To Collect

Always ask the user for the minimum set needed to choose and scaffold the eval before you create files, run the scaffold script, or author starter data. Do not skip this just because you can infer a default.

Ask for:

- Eval name
- Goal or scenario
- Harness choice, or enough context to recommend one
- System prompt path or inline text
- Tools JSON path or tool descriptions
- Data path or source materials
- Desired graders

If the user does not know which harness they want, explain the options briefly and recommend one. See `references/harness-selection.md`.

When the user asks for synthetic audio but does not specify a harness, default to `crawl` text-to-TTS unless they need the generated audio to carry particular noise, telephony artifacts, speaker characteristics, or other replay-specific properties. Use `walk` for those cases.

Keep the questions concise and grouped into one short batch whenever possible.

If the user only provides `user_text` or a short task description, still ask the questions above first. If they answer only partially, then infer the remaining low-risk details, call out the assumptions, and make the scaffold easy to revise later.

## Workflow

1. Ask the user for the required inputs first.
   - Do this before making files or selecting a final harness.
   - If the user already supplied some of the inputs, ask only for the missing ones.
   - If you recommend a harness, wait for the user response before scaffolding.

2. Pick the harness.
   - `crawl`: single-turn text-to-TTS.
   - `walk`: replay saved audio or generate audio from text rows.
   - `run`: multi-turn simulation with tool mocks and judge criteria.
   - If the user wants synthetic audio but does not care about replay-specific audio characteristics, prefer `crawl` over `walk`.

3. Normalize the inputs.
   - If the user gives inline prompt or tool content, write it into the generated folder.
   - If the user gives CSV data, inspect it with pandas before wiring it in.
   - If the data is not yet harness-ready, scaffold the files and then have you author the starter dataset directly in those files.
   - If the user only gives `user_text`, infer `example_id` values and leave optional grading fields blank unless you have enough signal to fill them.
   - Ground the starter data in the use case, prompts, tools, and any other material the user provided.
   - Make the starter data realistic. Put yourself in the shoes of the end user in that use case and craft datapoints that a real user would plausibly say or do.

4. Be proactive when data is missing.
   - `crawl`: you should author 3 starter rows covering one happy path and a couple of nearby variants or edge cases.
   - `walk`: you should author 3 source CSV rows and prepare the audio-generation step so the user can create audio immediately.
   - `run`: you should author 2 starter simulations, not 1.
   - Do not rely on deterministic script-generated samples for use-case-specific starter data.
   - Show the generated starter samples to the user, ask for a quick greenlight or correction, then expand only after feedback when the task calls for more coverage.

5. Run the scaffold script:

```bash
python examples/evals/realtime_evals/skills/bootstrap-realtime-eval/scripts/bootstrap_realtime_eval.py --name "<eval_name>" --harness "<crawl|walk|run>"
```

Add flags for prompt, tools, data, graders, and run-specific fields as needed. Read the script help if you need the exact flag names.

6. Review the generated folder.
   - Confirm the README is accurate for the selected harness.
   - Confirm the system prompt, tools, and data files point at the generated folder.
   - If the user provided real data, make sure it is wired in instead of leaving starter placeholders.
   - If you authored inferred starter data, show the user the generated rows or simulations before scaling up.

7. Enrich the scaffold.
   - For `crawl` and `walk`, make the CSV realistic and ensure the expected tool columns are present.
   - For `walk`, if the dataset lacks `audio_path`, use the shared `walk_harness/generate_audio.py` flow described in the README.
   - For `run`, make sure `simulations.csv` and the starter `sim_*.json` file reflect the user’s scenario, tool mocks, and graders.

8. Validate before returning.
   - Run a smoke eval for the generated folder.
   - If the smoke eval succeeds, automatically run the full eval for the generated folder in the same turn.
   - If the smoke eval fails, stop and fix or report the blocker before attempting the full eval.
   - Run `pytest examples/evals/realtime_evals/tests -q`.
   - Inspect the generated README and at least one generated data file.

## Hard Rules

- Keep the generated folder inside `examples/evals/realtime_evals/`.
- Ask the user for the missing setup information before scaffolding. Do not jump straight to building a default eval when the request is to create a new eval.
- Do not duplicate the main harness scripts into the generated folder.
- Do not write generic placeholder starter data when the use case provides enough context to do better.
- Use the prompt, tools, and scenario details to make the initial datapoints feel like a real user interaction.
- The README must include:
  - why this harness was chosen
  - which files to edit first
  - smoke and full run commands
  - data contract notes
  - troubleshooting notes
- Prefer assistant-specific flags for run harness commands:
  - `--assistant-system-prompt-file`
  - `--assistant-tools-file`

## Completion Criteria

Treat the task as complete only when:

- the folder exists under `examples/evals/realtime_evals/<name>_realtime_eval/`
- `README.md`, `system_prompt.txt`, and `tools.json` exist
- harness-specific starter data exists, authored by you when the user did not provide it
- the smoke command has been run or is blocked for a clear reason
- if the smoke command succeeded, the full eval command has also been run or is blocked for a clear reason
- `pytest examples/evals/realtime_evals/tests -q` has been run

## Learnings

When this skill uncovers a reusable workflow or harness constraint that should guide future bootstrap work, add a short note here.

Keep learnings concise and action-oriented:

- **Problem -> Fix -> Why**

Only add items that are likely to help future realtime-eval scaffolding in this repo. Remove stale items when they no longer apply.

- **`gpt-realtime` temperature is unsupported** -> Do not add a `temperature` field or CLI flag when scaffolding `gpt-realtime` evals -> Avoids invalid config and keeps runs aligned with the realtime harness constraints.
- **Starter samples should come from the model, not the scaffold script** -> Use the script to create the folder structure and template files, then have you author the initial rows or simulations from the user’s use case -> Produces more relevant starter data and makes iteration easier with the user.
- **Synthetic audio can be overfit to the wrong harness** -> Default unspecified synthetic-audio requests to `crawl` text-to-TTS and reserve `walk` for replay-specific audio characteristics like noise or telephony artifacts -> Keeps the bootstrap path simpler unless audio realism is the actual target.
- **Smoke-only validation can leave scaffolds half-proven** -> After a successful smoke run, automatically run the full eval before declaring the bootstrap complete -> Catches dataset-wide or late-row failures that a one-example smoke test misses.
