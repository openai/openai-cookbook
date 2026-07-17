---
name: docs-editor
description: Review and edit technical documentation (Markdown/MDX) with Chicago Manual of Style + Microsoft Writing Style Guide alignment. Use when asked to review, edit, or QA docs for clarity, grammar, consistency, and style; to run Vale linting with a repo .vale.ini; to identify and prioritize doc issues and fixes; or to write or edit Ads docs using the repo's Ads-specific docs style guidance.
metadata:
  short-description: Review and edit docs
---

# Docs Editor

## Overview

Review technical documentation for style, clarity, and consistency. Run Vale when available, then perform a human review, fix easy issues, and report remaining issues by priority.

## Workflow

### 1) Gather inputs

- Prefer a specific file path. If none is provided, confirm scope.
- Accept a glob for MD/MDX when the user wants a sweep (for example: `--glob='*.{mdx,md}'`).
- Never invent or add new factual content.

### 2) Run repository Vale

- Check for `.vale.ini` in the project root. If it is missing, note that and proceed with manual review.
- Run `pnpm run setup` when Vale 3 or newer, or synchronized packages, are unavailable. This is the repository's supported bootstrap path.
- Run `pnpm run vale -- <path...>` with explicit Markdown or MDX paths. Resolve globs to paths before invoking the command.
- Don't call global Vale directly for repository files. The wrapper enforces repository configuration, package checks, exclusions, and `--no-global` behavior.

### 2a) Astro partials via stdin

The repository wrapper accepts files, not stdin. If content lives in an `.astro` file and only a subset of copy should be linted, extract the relevant Markdown or MDX and pass it to Vale with the same repository flags:

```bash
printf '%s\n' "*This* is Markdown" | vale --no-global --no-wrap --ext=.mdx
```

### 3) Triage findings

- Parse Vale output and map each alert to a priority.
- Apply the repo rule: any spelling or grammar issues in `.mdx` are **P0/P1**.
- If Vale reports vocabulary/spelling errors, ask the user first whether any terms should be added to the appropriate `accept.txt` vocabulary list before editing content.
- Use this priority scale:
  - **P0**: Critical correctness or meaning issues; spelling/grammar in `.mdx`.
  - **P1**: Major clarity, ambiguity, or misleading statements.
  - **P2**: Consistency, tone, minor grammar, or style issues.
  - **P3**: Nits and optional improvements.

### 4) Manual review (Chicago + Microsoft style)

Focus on:

- Clarity and brevity (tighten wordiness, active voice).
- Consistent terminology and capitalization.
- Parallel structure in lists and headings.
- Consistent punctuation, spacing, and heading styles.
- Logical consistency: list counts, referenced items, numbering, examples, and cross-references.
- For detailed developer-doc rules, load `resources/style-guide.md` and apply the checklist.

### 4a) Developer content checks

Apply Microsoft Writing Style Guide guidance that targets developer documentation:

- **Audience + voice**: Assume baseline dev knowledge; skip basics and focus on product-specific goals. Keep the voice warm, crisp, and helpful.
- **Reference documentation**: Favor consistent structure and predictable headings. Ensure a concise description, syntax/signature, requirements/applies-to, examples, exceptions/permissions where applicable, and “See also” links. Don’t repeat the element name in the description.
- **Code examples**: Make examples task-based, concise, and practical; start simple, avoid contrived scenarios, list prerequisites, show expected output, and ensure secure, tested code. Don’t add exception handling unless intrinsic to the example.
- **Formatting developer text**: Use code style for programmatic elements; match capitalization used in code and language conventions. Use code style for commands, options, identifiers, and markup.
- **Instructions**: Use imperative verbs, complete sentences, and consistent step structure; cap the first word, end steps with periods, and keep procedures short. Use sentence-style capitalization for headings and UI labels.
- **UI labels in prose**: When referring to UI text, either describe the action without a label, or clearly set off the label; use quotes or bold sparingly and consistently.

### 4b) Ads docs checks

When writing or editing Ads docs:

- Write for marketing developers: assume technical fluency, but explain Ads concepts in plain, direct, practical language before implementation details.
- Start with the job to be done: setup measurement, create campaigns, sync audiences, query insights, or debug delivery.
- Use concrete, workflow-shaped examples with realistic advertiser scenarios, short steps, and small happy-path code snippets.
- Build mental models around outcomes: data flow, update timing, defaults, and how choices affect reporting, targeting, or optimization.
- Stay crisp and direct: short sections, short paragraphs, practical bullets, useful tables and snippets, no marketing fluff.
- For Ads API docs, use the API when possible to confirm behavior; ask the human for an API key if needed.
- Do not add Ads changelog entries under `/content/changelogs`. For API-impacting Ads changes, update `/ads/api-overview#changelog`.

### 4c) Tighten prose without changing meaning

- Put accuracy first, clarity second, and cadence third. Before rewriting, identify protected actors, actions, objects, values, counts, sequences, conditions, scope, modality, negation, literals, and uncertainty markers. Compare them with the revision before finishing. Revert any introduced drift. If the source is ambiguous, preserve the original wording and flag the ambiguity for review.
- Lead with the point. Prefer concrete nouns, strong verbs, and the plainest accurate wording.
- Apply a literal-action test to abstract phrasing only when the source supplies the answer: who or what acts, what changes, and what happens next? Never invent or broaden an actor to avoid passive voice. Keep process-focused passive voice when the actor is unknown, irrelevant, or intentionally omitted.
- Treat phrases such as “not just X but Y,” “leverage,” “unlock,” “seamless,” “at scale,” “drive alignment,” “move work forward,” and “operationalize” as review prompts, not banned words. Replace them only when plainer wording is more specific.
- Cut throat-clearing, filler, repeated conclusions, vague praise, and ornamental transitions. Read the result once for natural cadence without flattening useful warmth or nuance.
- Correct a count or logical mismatch only when the surrounding source establishes the intended value or logic. A list-count mismatch alone is not enough evidence to choose a correction. Otherwise, preserve the original wording and flag the mismatch for review.
- Preserve exact product terminology, UI labels, error messages, commands, paths, code identifiers, normative keywords, negation, and security conditions. Repository mechanics and Vale remain constraints.
- Keep this pass local to the requested or already-touched prose. Don't create formatting, structural, or file-wide churn solely for rhythm.

### 5) Fix what is safe

- Auto-fix obvious typos, punctuation, spacing, and clear grammar errors.
- Keep edits minimal and reversible.
- If a fix could change meaning or requires product knowledge, flag it instead of editing.
- After edits, re-run Vale on the same scope when available.

### 6) Report results

- Provide a short summary, then list issues by priority with file/line references.
- Clearly separate:
  - **Auto-fixed** items (already changed)
  - **Needs review** items (awaiting user decision)
- Ask for confirmation before making non-trivial rewrites or meaning-altering edits.

## Output expectations

- Default to concise, reviewer-style feedback.
- Highlight inconsistencies (for example: “list says three items but shows two”).
- If no issues are found, say so explicitly and mention whether Vale ran.
