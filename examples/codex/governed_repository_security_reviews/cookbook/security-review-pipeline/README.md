# Govern repository security reviews with versioned context

This recipe binds an authorised repository revision and effective threat context
to bounded work, authenticated evidence and a named human decision. The trusted
control plane owns policy. Repository files, events and scanner output are data,
not permission to scan, accept a finding, open a pull request or deploy.

The default run uses six fictional repository records and deterministic marker
inspection. It performs no hosted model call, real Codex Security scan, customer
repository access, provider write or paid request. Docker is an explicit option
for testing real operating-system isolation of those same synthetic fixtures.

## Run the recipe

Use Python 3.11+ on Linux or macOS. No extra Python package or API key is needed.
Run from the complete reference or focused example root:

```sh
python3 -B scripts/run_security_review_cookbook.py --cycles 2
```

Expect four distinct authorised repositories on the first cycle and none on
the second. Raw attempts are nominally `[4, 0]`; a policy-bounded transient
retry may increase the first count and must have a corresponding typed retry
event. Two findings await human disposition, one clean
synthetic result becomes a review packet and one hostile fixture abstains. Two
other repositories wait for scope or high-risk context approval.

State is temporary and removed by default. To demonstrate a process restart,
select a new owner-private state directory outside the checkout:

```sh
REVIEW_STATE=$(mktemp -d "${TMPDIR:-/tmp}/security-review.XXXXXX")
python3 -B scripts/run_security_review_cookbook.py --state-dir "$REVIEW_STATE" --cycles 1
python3 -B scripts/run_security_review_cookbook.py --state-dir "$REVIEW_STATE" --cycles 1
```

The first process attempts four repository jobs; the second attempts exactly
zero scans or retries. Inspect the separate per-cycle job, attempt and retry
counts rather than treating every extra attempt as a new repository. You own cleanup
of an explicitly retained state directory. It contains local integrity keys and
must not be committed, copied into a tutorial, or treated as a production secret
store. Directories are `0700` and persisted state and evidence files are `0600`.

## The authority and evidence contract

1. **Inventory:** require a named owner, immutable revision and explicit trusted
   workload, exposure, data, dependency and control metadata.
2. **Scope:** bind human authorisation to repository identity, current owner and
   revision. Missing or revoked scope blocks fresh work and cached-result reuse.
3. **Context:** compose organisation controls, workload archetype and repository
   delta. High-risk or materially unique repositories also require accepted
   bespoke context. Hash the effective context and track boundary changes.
4. **Admission:** bound workers, scan admissions, retries and synthetic units.
   The idempotency key binds repository identity, revision, context hash,
   scanner version and policy version. A changed key cannot reuse stale work.
5. **Evidence:** validate the pinned public findings, coverage and manifest
   schemas; authenticate local evidence and state; deduplicate finding identity.
   Missing, partial or tampered evidence is not a clean security result.
6. **Review:** route findings and exceptions to named owners. The default output
   is a private review packet. A clean synthetic packet is not a production
   security approval, merge approval or deployment permission.

The JSON approval files are fictional trusted inputs. They do not implement
enterprise authentication, a reviewer UI or a production approval service.

## Threat-context choice

The hierarchy retains a per-repository delta even when the reusable model is
shared. Prefer a full repository-specific model for high risk or material
uniqueness. The optional generated 2,000-record inventory has ten archetypes and
57 high-risk records, producing 68 reviewer-managed model artefacts: one
baseline, ten archetypes and 57 bespoke models, plus 2,000 repository deltas.

Those are metadata counts, not measured review hours or model tokens. The older
`compare_strategies()` simulation uses its own per-repository assignment as an
oracle and illustrative context weights; it cannot establish real coverage,
cost, latency or savings. Use the separate declared scenario labels instead:

```sh
python3 -B scripts/evaluate_threat_context.py
```

That evaluation tests context retention and invalidation only. It does not
measure vulnerability recall. Updating one organisation baseline can invalidate
all dependent repository contexts and require many new reviews or scans.

## Product integration remains separate

Generated native plans are pinned to `@openai/codex-security@0.1.20`. They are
never executed. Repeated `--knowledge-base` inputs and row-specific prompts
carry shared and repository-specific context; the hierarchy and approval ledger
are application-owned, not native threat-model generation or access approval.

The pinned package supports `--max-cost USD` as a
per-repository-attempt estimated threshold and may overshoot. It is **not** a hard aggregate campaign cap.
A real control plane must independently bound admissions, reservations and
charge ownership. Synthetic budget units are not prices or invoiced spend.

The model and effort are explicit examples, with model approval set to false.
Help/argument validation does not verify model entitlement. The native single
repository patch path can propose a draft PR, but this recipe has no provider
write adapter; every provider write, patch acceptance, merge and deployment
requires independent human authority.

See [the versioned product sources](PUBLICATION_SOURCES.md) for public source,
archive and recorded-help provenance. No private plugin is required: the public
schema snapshot is bundled with its upstream licence and integrity hashes.

## Real container checks

With a locally approved Docker daemon and cached `python:3.12-alpine` image:

```sh
python3 -B scripts/run_security_review_cookbook.py --cycles 2 --docker
RUN_RECIPE_DOCKER=1 python3 -B -m unittest discover -s cookbook/security-review-pipeline/tests -q
```

A successful first cycle produces three genuine isolation receipts; the hostile
fixture abstains. Workers are non-root, network-denied and read-only, with
protected source/tests, dropped capabilities, no-new-privileges and no forwarded
credentials. Requested Docker execution never falls back to the host.

The bounded Compose service described in `local/README.md` is a different
topology: an outer service container with no Docker socket and no separate
nested worker. A trusted host can instead launch separately isolated workers.
Do not conflate the two receipts.

## Before a real pilot

Implement and approve repository acquisition, enterprise identity, scoped
credentials, data routing, scanner egress, spend controls, retention, monitoring
and operational ownership. Begin with a small representative corpus and
independently labelled findings; stop on scope, coverage, isolation or evidence
failures. Humans retain finding disposition, patch approval, optional provider
writes, merge/deploy, exceptions and policy changes.

See [the operating runbook](OPERATOR_RUNBOOK.md) for owner roles and promotion
conditions. This reference does not establish product entitlement, vulnerability
quality, supported fleet throughput or production readiness.
