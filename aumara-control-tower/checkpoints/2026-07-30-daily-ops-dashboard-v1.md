# AUMARA Daily Ops Dashboard v1 checkpoint

## Objective

Add one read-only Daily Ops dashboard to the existing AUMARA Control Tower that
combines reviewed snapshots from the existing Gmail, Beds24, Epos Now and
Bitrix24 paths.

## Status

`locally verified on current main; ready for pull request`

## Scope

- Allowed:
  - `aumara-control-tower/` dashboard, snapshot builder, synthetic fixtures,
    focused tests and documentation.
  - one dedicated branch and one pull request.
- Excluded:
  - new monitoring or schedules;
  - a new database or production deployment;
  - Gmail sends or mailbox mutations;
  - Beds24 writes or booking mutations;
  - Epos Now writes;
  - Bitrix24 writes;
  - credential creation, rotation or disclosure;
  - changes to PR #15 or PR #16.

## Evidence

- Clean base: `main` commit
  `8e0affa23d079f1fc6286fb7a84dc212ab203ec4` (merged PR #18).
- PR #15 remains the separate read-only Beds24 guest-message ingestion work.
- PR #16 is merged and remains the separate policy-gated Beds24 cot-note
  writer work.
- `scripts/eposnow_reporting_export.py` is the existing read-only Epos Now
  export.
- The existing Control Tower server exposes `/health` and fail-closed webhook
  routes but no operational dashboard.
- Gmail is documented as the sole current live guest-reply path.
- A read-only Gmail check for 30 July confirmed that the service labels and
  verified SENT messages are accessible. It also confirmed that label counts
  are message-level and must be grouped/deduplicated before becoming metrics.
- The latest PR #15 pull-request run passed deterministic tests but skipped the
  credential-backed live proof, so Beds24 is not yet marked live by Dashboard
  v1.
- No merged Bitrix24 adapter is present on `main`; the dashboard must expose
  that source as unavailable rather than inventing data.

## Implemented changes

- Canonical `aumara-daily-ops-v1` snapshot builder with source-of-truth rules,
  freshness checks, event deduplication and explicit unavailable values.
- Authenticated read-only `/daily-ops` view and
  `/api/daily-ops/latest` endpoint in the existing server.
- Synthetic regression fixtures and focused Python/Node tests.
- Read-time freshness recalculation so an old snapshot cannot remain `ready`.
- Explicit `null` plus `partial` quality when a metric is missing inside an
  otherwise available source.

## Tests

Passed locally:

- `npm test` — 16/16.
- `python -m unittest tests/test_daily_ops_snapshot.py` — 8/8.
- `python -m unittest discover -s scripts/tests -p 'test_*.py'` — 22/22.
- `python .github/scripts/validate_ai_execution_governance.py`.
- `python -m py_compile aumara-control-tower/scripts/daily_ops_snapshot.py`.
- `git diff --check`.

## Stop condition

One reviewed branch and pull request containing a locally verified read-only
Dashboard v1. The PR must not deploy, schedule, send, mutate external systems or
claim unavailable sources are live.

## Recovery point

Branch `agent/daily-ops-dashboard-v1-current`, created from
`8e0affa23d079f1fc6286fb7a84dc212ab203ec4`.
