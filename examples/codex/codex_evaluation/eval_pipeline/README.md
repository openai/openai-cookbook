# Codex Evaluation Demo

This folder is a simplified, end-to-end example of the Codex evaluation pipeline. It mirrors the main CLI workflow (tasks → solver → grader → results), but removes Gerrit-specific details and uses plain git commits as the reference.

## Quick start

```bash
npm install
npm run solve -- --tasks data/tasks.yaml --working-directory /path/to/repo
python3 analysis/analyze.py --results-dir evals_output
```

## Tasks format

`data/tasks.yaml` expects a list of tasks with a git commit hash as the reference:

```yaml
tasks:
- name: "192755_embed-fonts-decomposed-pdf-with-additional-context"
  commit_hash: 192755
  patch_summary: >
    Add scrollbar width to desired size if enabled
  task_prompt: >
    Add scrollbar width to desired size if enabled in tbxctrls
  additional_context: >
    The patch adds scrollbar width via aSize.AdjustWidth. The patch is a simple change to svx/source/tbxctrls/linectrl.cxx
```

## What it does

- Creates a worktree at the base commit (`commit_hash^`).
- Uses the Codex SDK to apply the task prompt.
- Generates a diff and logs Codex output.
- Grades the diff against the original git diff from the reference commit.
- Writes JSON results that can be summarized with `analysis/analyze.py`.
