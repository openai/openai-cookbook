# Copilot Instructions for openai-cookbook

This repository contains runnable examples, notebooks, and reference articles for OpenAI APIs. Keep changes focused, minimal, and aligned with the existing cookbook structure.

## Repository structure

- Place notebooks and Python scripts under `examples/<topic>/`.
- Group related assets inside topic-specific subfolders and keep filenames descriptive and lowercase with dashes or underscores.
- Keep content discoverable by updating `registry.yaml` for new or relocated entries.
- Keep author metadata current in `authors.yaml` when adding or moving content.

## Coding and documentation expectations

- Write Python to PEP 8 with four-space indentation, descriptive names, and concise docstrings.
- Prefer clear examples over clever abstractions; document required environment variables instead of hard-coding secrets or API keys.
- Avoid introducing network calls in tests; use fakes or mocks where appropriate.
- For notebook changes, run them top-to-bottom and clear execution counts before committing.

## Validation and workflow

- Use a virtual environment for local work and install only the dependencies required by the relevant example.
- Validate notebooks with:
  - `python .github/scripts/check_notebooks.py`
- If a sample includes dependencies, use the example-specific `requirements.txt` rather than installing unrelated packages.

## Security and governance

- Never place secrets or private operational values in code, prompts, logs, commits, or pull request text.
- Do not change Gmail, Beds24, monitoring, deployment, access, payments, legal, tax, or external messaging without explicit task-specific authorization.
- Follow `docs/AI_EXECUTION_POLICY.md` and `docs/CHECKPOINT_PROTOCOL.md` for AI-assisted execution.

## Pull request expectations

- Use concise, imperative commit messages.
- Include a short summary, motivation, and validation details in pull requests.
- Ensure metadata files stay in sync with new or relocated content.
