# Guest-service journey v1

## Objective

Add one dual-property, zero-send guest-care policy runtime for post-check-in
and first-morning communication.

## Status

Complete in the implementation patch. The Beds24 shadow feed is read-only;
live delivery remains blocked.

## Scope

- Allowed: policy registry, proposal-only runtime, hourly Beds24 GET-only
  shadow feed, PII-free summaries, fixtures, focused tests, dry-run CI and
  documentation.
- Excluded: guest sends, Beds24 mutations, WhatsApp/Gmail writes, live delivery
  schedules, credential values and deployment changes. The hourly GET-only
  shadow schedule and repository-level read-only MCP adapter are included.

## Evidence

- Approved internal guest-service evidence was reviewed without copying access,
  infrastructure or private operational values into the public repository.
- Existing property policy boundaries and the checkout-reminder hard block are
  preserved.
- The runtime fails closed until an approved reservation source and durable
  delivery claim are supplied by the live integration.

## Changes

- Added verified care-message policies for AUMARA and EL CID in five languages.
- Added deterministic Europe/Madrid time, status, departure-day, incident and
  stable lifecycle dedupe gates.
- Added a zero-network CLI report and regression tests.
- Added a scheduled dual-property Beds24 shadow mapper that reuses the existing
  authentication boundary and writes only aggregate, PII-free evidence.
- Added a stdio MCP adapter with two explicitly allowlisted read-only tools and
  a canonical Copilot MCP configuration using an Agents-scoped secret reference.
- Verified that El Cid is queried by property with no room filter, covering all
  registered El Cid rooms rather than only the Studio.
- Extended registry schema support for French, German and Dutch templates.

## Tests

- `python aumara-control-tower/scripts/validate_policy_registry.py`
- `python -m unittest` for policy registry, existing guest reply, guest journey
  and Beds24 shadow mapper suites.
- Proposal CLI with all three zero-send guards.

Results:

- Registry validation: PASS — 17 policies across 3 registries.
- Unit tests: PASS — 40/40.
- Dry-run: PASS — 2 proposals, 1 manual review, 1 hard block.
- External calls in policy dry-run, guest sends, booking mutations and durable
  claims: 0.

## Stop condition

Reached when the patch validates, the shadow adapter is GET-only and every
guest-facing or booking-mutation counter remains zero.

## Recovery point

Apply this patch to a new branch from current `main`. The next safe action is a
draft pull request; live delivery is a separate explicitly authorized task.
