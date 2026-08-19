# OpenAI Cookbook editorial checklist

Use this checklist for articles and notebook Markdown cells in `openai-cookbook`. Apply only the rules relevant to the content under review.

## Audience and purpose

- Write for developers who want to understand and run an OpenAI API example.
- State the task or outcome early. Keep background material only when it helps the reader use the example correctly.
- Assume general programming knowledge, but explain Cookbook-specific setup, choices, and tradeoffs.
- Avoid promotional language, vague praise, and claims that the example does not demonstrate.

## Technical accuracy

- Match API, model, method, parameter, field, file, and environment-variable names exactly.
- Keep prose consistent with the code, sample inputs, outputs, diagrams, and nearby cells.
- Check counts, ordered steps, cross-references, defaults, constraints, and stated results.
- Do not infer a correction when the intended fact is unclear. Preserve the source and flag it for review.
- Use authoritative sources to verify uncertain product behavior.
- Do not imply that an optional step is required or that a required step is optional.

## Runnable examples

- List prerequisites and dependencies that readers need before running the example.
- Document required environment variables. Never hard-code API keys, tokens, credentials, or other secrets.
- Keep setup instructions in the same order that readers perform them.
- Introduce code with the goal or reason for the step; do not narrate every line.
- Use realistic inputs and clearly label placeholders.
- Show expected output only when it helps readers verify success, and keep it consistent with the code.
- Keep external-service calls and other opt-in behavior clearly labeled.

## Notebook integrity

- Edit Markdown cells only during an editorial pass.
- Preserve code cells, outputs, execution counts, attachments, cell IDs, cell order, and metadata.
- Keep notebook JSON valid and avoid whole-file reserialization for a small prose edit.
- Keep each Markdown cell focused. Split or merge cells only when the structure is genuinely confusing and the request permits it.
- Use Markdown headings in a logical hierarchy without skipping levels unnecessarily.

## Prose

- Lead with the point. Prefer concrete nouns and strong verbs.
- Use direct instructions and address the reader as “you” when helpful.
- Prefer active voice, but keep passive voice when the actor is unknown or unimportant.
- Remove throat-clearing, repeated conclusions, filler, and ornamental transitions.
- Keep paragraphs short enough to scan and use lists for genuinely parallel items.
- Use numbered lists for ordered procedures and bullets for unordered groups.
- Keep sibling headings and list items parallel.
- Use sentence-style capitalization for headings and do not end headings with periods.
- Preserve useful warmth and explanation; do not flatten the content into terse fragments.

## Terminology and formatting

- Use exact product terminology and consistent capitalization.
- Format commands, options, environment variables, paths, filenames, code identifiers, and literal values with backticks.
- Match the capitalization and spelling used by the language or API.
- Expand uncommon abbreviations on first use unless the surrounding audience clearly knows them.
- Use inclusive, precise language and neutral role terms.
- Do not replace a technically precise term merely to vary wording.

## Links and assets

- Prefer descriptive link text over “here” or a pasted URL.
- Verify local links, anchors, image paths, and referenced notebook or article paths.
- Use stable, authoritative external links when available.
- Give images meaningful alt text unless they are purely decorative.
- Keep diagrams, screenshots, captions, and prose consistent.

## Publication metadata

- Add or update `registry.yaml` for new, moved, renamed, or removed published content.
- Confirm registry paths, dates, tags, and titles match the content.
- Add or update `authors.yaml` when introducing or changing author attribution.
- Check that filenames follow the repository's naming conventions and clearly describe the content.

## Final review

- Read each edited passage in context, not only as an isolated diff hunk.
- Confirm no factual meaning, literal value, condition, negation, or uncertainty changed unintentionally.
- Confirm all repository-defined P0 issues are fixed.
- Run the notebook structural validator for changed notebooks and inspect the final diff for unintended changes.
