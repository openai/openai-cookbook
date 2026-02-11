# Image Generation + Editing Evals

This folder contains a lightweight vision eval harness plus example runners for
image generation and image editing. The code mirrors the structure of
`examples/evals/realtime_evals/` so you can adapt it quickly.

**Directory layout**

- `vision_harness/`: minimal shared library (types, runners, graders, evaluate loop)
- `generation_harness/`: text-to-image evals (UI mockups + marketing flyer)
- `editing_harness/`: image-edit evals (virtual try-on + logo edit)
- `shared/`: reporting and optional rendering helpers

## Quickstart

Python 3.9+ required.

```bash
pip install -r requirements.txt
export OPENAI_API_KEY="your_api_key"
```

Run a harness:

- Generation: `python generation_harness/run_imagegen_evals.py`
- Editing: `python editing_harness/run_imagegen_evals.py`

## What the harness does

1. Builds a small set of `TestCase` objects (prompt + criteria).
2. Runs the image model for each case.
3. Grades each output with an LLM judge using a strict JSON schema.
4. Writes results and artifacts to `results/<run_id>/`.

The harness is intentionally small so you can copy/paste parts into your own
production eval setup.

## Example cases

Generation cases:
- `ui_checkout_mockup`: mobile checkout screen with strict text + layout rules
- `coffee_flyer_generation`: marketing flyer with exact copy constraints

Editing cases:
- `vto_jacket_tryon`: virtual try-on with reference person + garment
- `logo_year_edit`: precision logo text edit

## Required assets (editing harness)

The editing harness expects these files in `images/`:

- `images/base_woman.png`
- `images/jacket.png`
- `images/logo_generation_1.png`

## Results layout

Each harness writes into its own `results/` folder:

- `results/<run_id>/results.json`: per-example outputs and grades
- `results/<run_id>/results.csv`: tabular results
- `results/<run_id>/summary.json`: aggregated metrics
- `results/<run_id>/artifacts/*.png`: generated or edited images

Tip: keep `results/` out of git (delete after runs or add to `.gitignore`).

## Common CLI flags

Both harnesses accept a shared core set of flags:

- `--results-dir`, `--run-name`
- `--model` (image model under test), `--judge-model` (LLM judge)
- `--num-images` (images per case)
- `--cases` (comma-separated list of case ids)

Generation harness adds `--image-size` and `--run-ocr` (text extraction check).

## Suggested workflows

- Quick smoke test:
  - `python generation_harness/run_imagegen_evals.py --cases ui_checkout_mockup`
  - `python editing_harness/run_imagegen_evals.py --cases vto_jacket_tryon`
- Compare model variants: run once per model name and compare `summary.json`.
- Use `--run-ocr` on the flyer case to validate exact text rendering.

## Adapting for your use case

- Replace prompts/criteria in the harness scripts.
- Update JSON schemas to match your rubric (and parse them into `Score` values).
- Add new cases by creating new `TestCase` objects and graders.
- Swap the output store to change where artifacts are written.

## Notes

- This harness uses the OpenAI Images API and a judge model. Costs scale with
  the number of images and judge calls.
- Judge outputs are best treated as signals, not ground truth. Keep a small
  human review loop for high-stakes decisions.
