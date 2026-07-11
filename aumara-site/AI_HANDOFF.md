# AUMARA WEB — AI handoff and source of truth

Updated: 2026-07-11
Owner / final approval: Ilya Doroshenko
Repository: `elcidspain/openai-cookbook`

## Current source of truth

- Preview file: `aumara-site/direct-v3-preview.html`
- Current production route: `aumara-site/direct-v2.html`
- GitHub Pages workflow uploads `./aumara-site` as the site root.
- Therefore the valid preview URL is:
  `https://elcidspain.github.io/openai-cookbook/direct-v3-preview.html`
- Legacy URL is redirected:
  `https://elcidspain.github.io/openai-cookbook/aumara-site/direct-v3-preview.html`

## Approved wording

English:

> Some places give you more.  
> AUMARA gives you back to yourself.

Spanish:

> Hay lugares que te dan más.  
> En AUMARA, vuelves a encontrarte contigo mismo.

Do not revert to `AUMARA te devuelve a ti`.

## Approved factual baseline

- 6 physical houses on site
- 5 currently bookable
- 3 Chalet
- 2 Superior Chalet
- Direct booking CTA: `https://beds24.com/booking2.php?propid=324882`
- Languages for this version: EN and ES
- Use real AUMARA media when available; do not replace it with generic AI imagery.
- Do not guess which exact numbered unit is unavailable when that fact is not verified.

## Roles

### Claude
- Review copy, hierarchy, mobile readability and visual rhythm.
- Propose changes against the current GitHub file, not against an isolated artifact.
- Return exact file-level edits or a complete replacement file.
- Do not publish, rename routes, alter booking URLs or change factual inventory without Ilya approval.

### ChatGPT / AI Ops
- Maintain GitHub source, deployment paths, redirects, media links and booking integration.
- Reconcile Claude proposals with the approved baseline.
- Verify URLs and preserve a reversible commit history.
- Do not switch production from v2 to v3 without Ilya approval.

## Change protocol

Every proposed change must include:

1. File path
2. Current wording / code
3. Proposed wording / code
4. Reason
5. Verification URL
6. Whether the change is preview-only or production

Never let two agents overwrite the same file independently. Claude proposes; AI Ops integrates; Ilya approves production.

## Current task for Claude

Review `aumara-site/direct-v3-preview.html` as it exists in GitHub now. Focus only on:

- first-screen hierarchy on iPhone
- EN/ES wording quality
- whether the slogan remains readable over the hero image
- CTA clarity
- which sections are essential before booking

Return a concise audit and exact replacement snippets. Do not create a separate prototype, do not change routes, and do not publish.
