# Editing Harness

**Best for:** high-precision checks where edits must be exact and non-target
content should remain unchanged.

This harness runs two example cases:

- `vto_jacket_tryon`: virtual try-on using reference person + garment
- `logo_year_edit`: precision logo text edit

## Run

```bash
python editing_harness/run_imagegen_evals.py
```

Run a single case (use `--cases`):

```bash
python editing_harness/run_imagegen_evals.py --cases vto_jacket_tryon
```

Run multiple cases (comma-separated, no spaces):

```bash
python editing_harness/run_imagegen_evals.py --cases vto_jacket_tryon,logo_year_edit
```

## Flags (when to use them)

- `--cases`: limit runs to specific case ids. Valid values:
  - `vto_jacket_tryon`
  - `logo_year_edit`
- `--model`: image model under test (defaults to `gpt-image-1.5`).
- `--judge-model`: LLM used to grade outputs (defaults to `gpt-5.2`).
- `--num-images`: number of edited images to generate per case (defaults to 1).

## Inputs

This harness expects the following reference images in `images/`:

- `images/base_woman.png`
- `images/jacket.png`
- `images/logo_generation_1.png`

## Outputs

Results are written under `editing_harness/results/<run_id>/`:

- `results.json` and `results.csv` with per-example scores
- `summary.json` with aggregated metrics
- `artifacts/` for edited images

## Adapting the harness

- Replace the input images and edit prompts in `run_imagegen_evals.py`.
- Update the schemas and verdict rules to fit your workflow.
