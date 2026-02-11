# Generation Harness

**Best for:** fast iteration on prompt-following, layout, and text-rendering
quality for text-to-image workflows.

This harness runs two example cases:

- `ui_checkout_mockup`: mobile checkout UI mockup
- `coffee_flyer_generation`: marketing flyer with strict copy constraints

## Run

```bash
python generation_harness/run_imagegen_evals.py
```

Quick smoke test for a single case (use `--cases`):

```bash
python generation_harness/run_imagegen_evals.py --cases ui_checkout_mockup
```

Run multiple cases (comma-separated, no spaces):

```bash
python generation_harness/run_imagegen_evals.py --cases ui_checkout_mockup,coffee_flyer_generation
```

Optional OCR-style text check for the coffee flyer:

```bash
python generation_harness/run_imagegen_evals.py --run-ocr
```

## Flags (when to use them)

- `--cases`: limit runs to specific case ids. Valid values:
  - `ui_checkout_mockup`
  - `coffee_flyer_generation`
- `--model`: image model under test (defaults to `gpt-image-1.5`).
- `--judge-model`: LLM used to grade outputs (defaults to `gpt-5.2`).
- `--num-images`: number of images to generate per case (defaults to 1).
- `--image-size`: size for generated images (defaults to `1024x1024`).
- `--run-ocr`: only relevant for `coffee_flyer_generation` (checks exact text).

## Outputs

Results are written under `generation_harness/results/<run_id>/`:

- `results.json` and `results.csv` with per-example scores
- `summary.json` with aggregated metrics
- `artifacts/` for generated images

## Adapting the harness

- Update the prompts/criteria in `run_imagegen_evals.py`.
- Tune JSON schemas + parsers to match your evaluation rubric.
- Add more cases by creating new `TestCase` entries and graders.
