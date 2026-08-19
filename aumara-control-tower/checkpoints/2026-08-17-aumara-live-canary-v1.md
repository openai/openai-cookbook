# AUMARA live guest-journey canary v1

## Objective

Add one manual-only live canary for Beds24 property `324882` with a mandatory
central DynamoDB claim before every guest-message POST.

## Status

Complete in branch `agent/aumara-guest-journey-live-canary`.

## Scope

- Allowed: AUMARA property `324882`, six physical units, property-level GETs,
  recent-message readback, verified actual check-in timestamps, DynamoDB
  conditional claims, manual workflow dispatch, aggregate-only metrics, tests
  and documentation.
- Excluded: property `324903`, schedules, automatic retries, Gmail, WhatsApp,
  checkout pressure, rating/review requests, table creation, TTL setup, IAM
  changes, secret creation, workflow execution and PR merge.

## Evidence

- Base `main` merge commit: `05c37614f6f1cc5f91bbf66ccc458ce36149fadc`.
- Reused the live sender, shadow GET-only requester, booking/message readers,
  policy runtime and hard blocks merged by PR #46.
- AUMARA canary inventory supplied for this execution: four SL plus two Chalet
  Super under property `324882`; no `roomId` filter.

## Changes

- Removed the local `/tmp` claim backend and made DynamoDB table
  `aumara-guest-journey-claims` mandatory.
- Added atomic key `324882:{booking_ref.lower()}:{event_type}`, UTC
  `created_at`, seven-day `ttl`, and conditional conflict skip behavior.
- Added AUMARA-only live reads and required actual check-in evidence before a
  decision can reach the claim boundary.
- Added a confirmation-gated, `workflow_dispatch`-only workflow and importable
  `python -m` entrypoint.
- Added focused DynamoDB, six-unit scope, no-room-filter, EL CID rejection,
  check-in evidence and workflow tests.

## Tests

- `cd aumara-control-tower/tests && python -m unittest discover -v` — PASS,
  61/61.
- `python aumara-control-tower/scripts/validate_policy_registry.py` — PASS,
  17 policies across 3 registries.
- `python -m aumara_control_tower.scripts.beds24_guest_journey_live --help` —
  PASS from repository root.
- Python compile and workflow YAML parse — PASS.
- External network calls and live sends during validation — 0.

## Stop condition

Reached when a mergeable draft PR exists from the recovery branch with the
manual workflow unexecuted and no credentials or infrastructure changes.

## Recovery point

Branch `agent/aumara-guest-journey-live-canary` based on `05c3761`. The next
safe action after review is to verify the pre-existing DynamoDB table, TTL, IAM
scope, repository variable and secrets before any manual dispatch.
