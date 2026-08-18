# AUMARA continuous notes write-and-verify hardening

## Objective

Harden the existing continuous Beds24 guest-note workflow so live writes run
only from a manual dispatch with explicit operator confirmation and preflight
read-only authentication checks.

## Status

Complete in branch `codex/write-and-verify`.

## Scope

- Allowed: `.github/workflows/aumara-beds24-continuous-notes.yml`, one compact
  checkpoint, focused validation of the existing note-worker tests and workflow
  YAML.
- Excluded: note-worker Python logic, policies, registry/authors metadata,
  credential values, workflow execution, scheduled live writes, and any other
  Beds24 or messaging behavior.

## Evidence

- Inspected `docs/AI_EXECUTION_POLICY.md` and `docs/CHECKPOINT_PROTOCOL.md`
  before implementation.
- Reused the existing live-write guards already enforced by
  `aumara-control-tower/scripts/beds24_guest_note_sync.py`,
  `aumara-control-tower/scripts/beds24_cot_note_sync.py`, and
  `aumara-control-tower/scripts/beds24_bed_nonsmoking_note_sync.py`.
- Inspected the current target workflow at
  `.github/workflows/aumara-beds24-continuous-notes.yml`.
- Compared established manual/live gating patterns in
  `.github/workflows/beds24-aumara-fixed-pin-seed.yml`,
  `.github/workflows/beds24-aumara-access-message-send.yml`, and
  `.github/workflows/aumara-guest-journey-live.yml`.
- Reused the existing read-only auth helper
  `aumara-control-tower/scripts/beds24_auth_check.py`.

## Changes

- Removed the scheduled trigger from
  `.github/workflows/aumara-beds24-continuous-notes.yml`.
- Added `workflow_dispatch` input `confirm_live_writes` with exact `YES`
  confirmation semantics.
- Restricted `write-and-verify` to manual dispatch only and derived
  `AUMARA_LIVE_BOOKING_WRITES_CONFIRMED` from the dispatch input instead of a
  hard-coded `true`.
- Added Python setup, read-only Beds24 auth preflight, El Cid property-access
  preflight, auth evidence upload, and explicit final outcome logging.

## Tests

- `python -m unittest aumara-control-tower/tests/test_beds24_guest_note_sync.py aumara-control-tower/tests/test_beds24_cot_note_sync.py aumara-control-tower/tests/test_beds24_bed_nonsmoking_note_sync.py aumara-control-tower/tests/test_guest_request_dry_run.py -v` — PASS, 40/40.
- `python - <<'PY' ... yaml.safe_load(...) ... PY` on `.github/workflows/aumara-beds24-continuous-notes.yml` — PASS.

## Stop condition

Reached when the existing continuous-notes workflow fails closed for live
Beds24 writes unless a human manually dispatches it and types `YES`, and the
targeted validations pass.

## Recovery point

Branch `codex/write-and-verify` from commit `90e538d0469ed20d5f0f9e3ac36a61c15b071649`.
Next safe action: review the workflow diff, then manually dispatch the workflow
with `confirm_live_writes=YES` only when live Beds24 writes are intentionally
authorized.
