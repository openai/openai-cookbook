# Repository Guidelines

## Project Structure & Module Organization

The cookbook is organized around runnable examples and reference articles for OpenAI APIs. Place notebooks and Python scripts under `examples/<topic>/`, grouping related assets inside topic subfolders (for example, `examples/agents_sdk/`). Narrative guides and long-form docs live in `articles/`, and shared diagrams or screenshots belong in `images/`. Update `registry.yaml` whenever you add content so it appears on cookbook.openai.com, and add new author metadata in `authors.yaml` if you want custom attribution. Keep large datasets outside the repo; instead, document how to fetch them in the notebook.

## Build, Test, and Development Commands

Use a virtual environment to isolate dependencies:

- `python -m venv .venv && source .venv/bin/activate`
- `pip install -r examples/<topic>/requirements.txt` (each sample lists only what it needs)
- `jupyter lab` or `jupyter notebook` to develop interactively
- `python .github/scripts/check_notebooks.py` to validate notebook structure before pushing

## Coding Style & Naming Conventions

Write Python to PEP 8 with four-space indentation, descriptive variable names, and concise docstrings that explain API usage choices. Name new notebooks with lowercase, dash-or-underscore-separated phrases that match their directory—for example `examples/gpt-5/prompt-optimization-cookbook.ipynb`. Keep markdown cells focused and prefer numbered steps for multi-part workflows. Store secrets in environment variables such as `OPENAI_API_KEY`; never hard-code keys inside notebooks.

## Testing Guidelines

Execute notebooks top-to-bottom after installing dependencies and clear lingering execution counts before committing. For Python modules or utilities, include self-check cells or lightweight `pytest` snippets and show how to run them (for example, `pytest examples/object_oriented_agentic_approach/tests`). When contributions depend on external services, mock responses or gate the cells behind clearly labeled opt-in flags.

## Commit & Pull Request Guidelines

Use concise, imperative commit messages that describe the change scope (e.g., "Add agent portfolio collaboration demo"). Every PR should provide a summary, motivation, and self-review, and must tick the registry and authors checklist from `.github/pull_request_template.md`. Link issues when applicable and attach screenshots or output snippets for UI-heavy content. Confirm CI notebook validation passes locally before requesting review.

## Metadata & Publication Workflow

New or relocated content must have an entry in `registry.yaml` with an accurate path, date, and tag set so the static site generator includes it. When collaborating, coordinate author slugs in `authors.yaml` to avoid duplicates, and run `python -m yaml lint registry.yaml` (or your preferred YAML linter) to catch syntax errors before submitting.

## Review Guidelines

These are considered priority 0 issues for this repo, in addition to the normal priority for possible issues.
- Verify file, function, and notebook names follow the repo's naming conventions and clearly describe their purpose.
- Scan prose and markdown for typos, broken links, and inconsistent formatting before approving.
- Check that code identifiers remain descriptive (no leftover placeholder names) and that repeated values are factored into constants when practical.
- Ensure notebooks or scripts document any required environment variables instead of hard-coding secrets or keys.
- Confirm metadata files (`registry.yaml`, `authors.yaml`) stay in sync with new or relocated content.
