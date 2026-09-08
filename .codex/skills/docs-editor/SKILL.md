---
name: docs-editor
description: Review and edit OpenAI Cookbook notebooks, Markdown, and MDX for technical accuracy, clarity, grammar, consistency, runnable examples, and repository publication requirements. Use for editorial reviews, pre-merge documentation checks, or notebook Markdown-cell sweeps in openai-cookbook.
---

# OpenAI Cookbook docs editor

## Objective

Review Cookbook content conservatively. Improve correctness and readability without changing the author's intent, inventing facts, or creating unrelated churn.

## Workflow

### 1. Define the scope

- Prefer explicit paths or the files changed in the pull request.
- For pull requests, review changed `.md` and `.mdx` files plus Markdown cells in changed `.ipynb` files.
- Review `registry.yaml` and `authors.yaml` when content is added, moved, removed, or attributed to a new author.
- Stay within the requested content. Do not turn a focused review into a repository-wide rewrite.

### 2. Protect notebook integrity

- When the request is editorial, edit only notebook Markdown cells.
- Preserve code cells, outputs, execution counts, attachments, cell order, cell IDs, and notebook and cell metadata.
- Avoid reserializing an entire notebook for a small prose change. Inspect the diff for unintended JSON churn.
- Do not execute notebook code unless the user requests it or code changes are in scope. Markdown-only edits require structural validation, not calls to external services.
- Never add hard-coded secrets. Document required environment variables such as `OPENAI_API_KEY`.

### 3. Review the content

Load `resources/style-guide.md` and check:

- Technical claims, API names, model names, identifiers, commands, paths, and URLs.
- Agreement between prose, code, sample inputs, and expected outputs.
- Prerequisites, dependencies, environment variables, and steps needed to run an example.
- File and notebook names, headings, lists, numbering, cross-references, and links.
- Grammar, spelling, punctuation, terminology, capitalization, and concise wording.
- Publication metadata in `registry.yaml` and author metadata in `authors.yaml` when applicable.

Verify uncertain technical claims from an authoritative source or flag them for review. Do not guess.

### 4. Prioritize findings

Use the repository's review bar:

- **P0**: Broken notebook JSON; hard-coded secrets; materially false or unsafe guidance; or any repository-defined P0 issue, including naming violations, typos, broken links, inconsistent formatting, placeholder identifiers, undocumented environment variables, or out-of-sync publication metadata.
- **P1**: Misleading instructions, prose that contradicts code or output, missing prerequisites, or a required link that does not work.
- **P2**: Clear improvements to grammar, consistency, organization, or readability that do not affect correctness.
- **P3**: Optional polish with little effect on comprehension.

### 5. Make safe edits

- Fix obvious typos, grammar, punctuation, broken local references, and clear prose/code mismatches.
- Keep changes minimal, local, and reversible.
- Preserve exact literals, code identifiers, commands, values, counts, conditions, modality, negation, and uncertainty markers.
- Tighten prose only when meaning stays unchanged. Prefer concrete nouns, strong verbs, short introductions, and direct instructions.
- Flag any change that depends on product knowledge or could alter meaning instead of guessing.
- Do not make file-wide formatting or stylistic changes solely for uniformity.

### 6. Validate the result

For any changed notebook, run the repository validator:

```bash
env -u VIRTUAL_ENV uv run --with nbformat python .github/scripts/check_notebooks.py
```

Then:

- Run `git diff --check`.
- Inspect the diff and confirm that notebook changes are limited to intended Markdown cells.
- Run an available YAML linter if `registry.yaml` or `authors.yaml` changed.
- Run the relevant example or test only when executable content changed and its dependencies are available.

### 7. Report the review

Provide:

- A short summary of the scope and edits.
- Auto-fixed items.
- Remaining findings grouped by priority with file and cell or line references.
- The validation commands run and their results.

If no issues remain, say so explicitly.
