# Continuous Beds24 guest-note writer

## Objective

Replace the manual Gmail `Beds24 note pending` queue for supported safe EL CID
guest requests with a scheduled, idempotent Beds24 `infoItems` writer.

## Status

Deployed to `main`; the first live workflow run completed successfully.

## Scope

- Direct guest messages: bed, pet, parking, early check-in, late check-in and
  late check-out.
- Cot requests only when the separate room, infant-age and occupancy policy is
  proven.
- Recent combined bed and non-smoking requests from booking payloads.
- No guest messages, payments, prices, dates, rooms, status or inventory writes.

## Evidence

- Beds24 API V2 documents that an `infoItems` child without an `id` creates a
  new item.
- Every live worker performs an exact GET read-back and stores only sanitized
  evidence.
- The production workflow is single-concurrency and runs the workers
  sequentially.
- Live run `30726680043` wrote and exactly read back two direct-request notes,
  found four existing bed/non-smoking notes without duplicating them, and
  completed with no manual-review cases.

## Changes

- Added one hourly production workflow using the existing refresh credential.
- Converted the bed/non-smoking and cot writers from one-time reconciliations
  to bounded continuous workers.
- Added a verified direct-message policy, bounded writes and exact read-back.

## Tests

- Unit tests cover zero-candidate runs, duplicate suppression, write caps,
  unsupported/ambiguous requests, preserved existing notes and failed
  read-back.
- GitHub Actions runs the full note-worker test set without credentials on the
  pull request.

## Stop condition

Any missing policy guard, ambiguous candidate, batch overflow, POST error or
read-back mismatch stops the affected worker safely. Other independent workers
still run and the job reports failure after evidence upload.

## Recovery point

Disable `.github/workflows/aumara-beds24-continuous-notes.yml`. Existing notes
remain ordinary Beds24 info items; the workflow has no delete path.
