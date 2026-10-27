# Operator runbook: recurring governed repository security reviews

## Responsibility map

The table describes the evidence a real deployment needs. The local recipe
demonstrates target binding with fictional trusted JSON inputs; it does not
implement enterprise identity, legal approvals, a reviewer UI or an immutable
human-approval service.

| Decision | Accountable named human | Required evidence |
| --- | --- | --- |
| Repository inclusion | Scope owner and service owner | Authorised repository, pinned revision, current owner and permitted data route. |
| Organisation or workload threat context | Security architecture owner | Versioned shared controls, trust boundaries and review history. |
| High-risk or materially unique model | Named threat-model reviewer | Exact repository, pinned revision and accepted effective-context digest. |
| Model, reasoning and campaign charge | Customer security and FinOps owners | Approved model, effort, trigger, budget, concurrency and charge attribution. |
| Finding disposition | Named security reviewer | Signed finding identity, evidence, severity, confidence and exact revision. |
| Patch or draft pull request | Named repository and patch owners | Scoped proposed diff; separate provider-write approval before any draft publication. |
| Risk exception | Named risk owner | Finding identity, justification, expiry, compensating controls and revalidation date. |
| Merge and deployment | Repository/release owners | Separate explicit human approval; neither is implemented by this recipe. |
| Policy or owner change | Previously trusted policy owner | Exact full configuration digest, future expiry, identity change and authenticated audit receipt. |

## Trusted input collection

Build the repository inventory from customer-owned source-control administration, service catalogue/CMDB, code ownership, dependency manifests, deployment configuration and data classification. Treat every repository file, webhook payload and model output as untrusted until independently validated.

Capture at least: stable repository identity, full immutable revision, accountable service owner, language, framework, runtime topology, data class, internet exposure, authentication, dependencies, service criticality, security controls, relevant changed paths and material boundary exceptions. If ownership, exposure or data classification cannot be established, stop for human review rather than inventing metadata.

## Change triggers and refresh cadence

| Trusted signal | Action | Safe default |
| --- | --- | --- |
| Security-relevant source, dependency, deployment or authentication change | Recompute boundary/context hashes and schedule the exact approved revision. | Do not reuse evidence across a changed security boundary. |
| Ordinary non-security documentation change | Reuse authenticated prior evidence only while context, boundary and scanner/policy versions match. | Preserve known findings and recheck current review authority; escalate instruction-bearing and security-sensitive documentation. |
| Organisation baseline or archetype context changes | Find affected repositories and obtain required high-risk reacceptance. | Do not rescan unrelated archetypes. |
| Owner, scope, entitlement, data-route or spend approval changes | Suspend the affected repository or campaign. | Existing evidence never creates new execution authority. |
| Weekly revalidation boundary | Recheck eligible previously successful reviews. | Preserve hostile-content quarantine unless trusted material changes. |
| Exception expires or upstream critical vulnerability appears | Reopen human review and reprioritise affected services. | No silent extension or automatic acceptance. |

The base recipe performs explicitly requested reconciliation cycles. An optional
local supervisor adds an explicitly finite number of cycles, bounded local
JSONL-event coalescing, signed cursor recovery and fresh per-cycle approval
checks; it is not an unbounded scheduler, hosted webhook consumer or production
queue. See `local/README.md` for the distinct daemon-free service-container and
trusted-host restricted-worker topologies. Deploying a persistent scheduler,
webhook listener, enterprise database, service account, real provider
integration or production monitoring still requires separately approved
customer-owned implementation.

## Evidence retention and recovery

### Jobs, attempts and retry diagnostics

Read these fields together; a retry is not another repository job:

| Receipt field | Meaning |
| --- | --- |
| `admitted_jobs` | Repository jobs admitted by policy in this cycle. A cancellation can stop an admitted job before its first call. |
| `attempted_repositories` | Distinct repositories for which a scanner call actually began in this cycle. |
| `scanner_attempts_by_repository` | Current-cycle call counts for each attempted repository. Historical cached attempts are not added again. |
| `scanner_invocations` | Raw calls to this recipe cycle's new scanner. If reusing a lower-level `FleetPipeline` directly, this older counter is cumulative; compare against the measured prior value. |
| `retry_attempts` | Calls beyond the first call for a repository, not retries that were only scheduled. |
| `transient_retry_events` | Exact repository, failed attempt and a bounded host-defined reason code. A scheduled retry may still be cancelled before it starts. |
| `restricted_docker_receipts` | Successful, validated worker-isolation receipts, not attempts or all container launches. |

For the six-record tutorial, the first cycle must attempt the four specified
repositories and produce the exact documented decisions. Without a transient
failure it uses four attempts; one permitted recovery uses five attempts and
one recorded retry. The configured attempt ceiling, concurrency and synthetic
budget still apply. A restart or review-only cycle must perform zero new work.
Cancellation is a safe stop, not successful completion of the nominal example.

Do not accept a timeout or worker crash as a prompt-injection refusal. The
restricted fixture worker uses a dedicated exit and exact typed refusal
protocol. Only its explicit instruction-refusal result satisfies that tutorial
check; generic Docker exits, malformed refusals and exhausted retries fail it.
The soak separately reports executor calls, proven starts, rejected or
unresolved launches, successful isolation and unverified receipts.

On notebook failure, retain the structured error receipt: it distinguishes the
raw zero-based cell index from the one-based code-cell number and includes the
failed contract with safe counts. It does not dump the notebook namespace,
arbitrary exception text, source contents or credentials. Preserve the first
failed run, investigate its evidence and verify a corrected candidate from
fresh state; a later passing rerun alone does not explain an earlier failure.

### Exact approval records

Approval input contains active grants, not historical decisions. Scope binds
the repository, revision and current owner. High-risk context binds its exact
hash. Finding disposition, patch and exception grants must include
`target_sha256` and a future integer `expires_at`. The target is the digest of
repository ID, revision, idempotency key and finding ID; the idempotency key
includes effective context, scanner and policy versions. An optional
`context_sha256` constraint is checked, never silently ignored.

Configuration changes require `configuration_sha256`, computed from
`RecipeConfiguration.fingerprint`, and a future `expires_at`. The approving
actor must be a policy owner in the prior authenticated checkpoint. A newly
listed owner cannot authorise their own appointment. The checkpoint records
the trusted owner policy and the configuration-change audit binds both hashes.

Remove expired, stale or consumed handover grants from the active input file
when issuing a new decision; retain historical approvals in the organisation's
separate audit system. Malformed, duplicate or unknown constraints stop the
cycle instead of being ignored or rebound to current context. Checkpoints from
older versions that lack trusted owner provenance require explicit migration;
do not hand-edit a signing key or checkpoint to bypass the refusal.

### Private state

The local state root and every nested directory use mode `0700`; the signing key, authenticated checkpoint, campaign inputs, evidence and run receipts use mode `0600`. Back up signing material only in an approved enterprise secret manager. Losing the key or modifying state/evidence invalidates the checkpoint and prevents scanner dispatch.

Documentation-only classification is an illustrative trusted-host heuristic,
not proof that an arbitrary Markdown change is harmless. A live adapter must
independently obtain complete changed paths and refresh effective context for
architecture, dependencies, exposure, authentication and other material changes.

Do not copy `.local-state-key`, credentials, customer source, private transcripts, account identifiers or state receipts into publication bundles. Define customer-owned retention, encryption, legal hold, regional processing, access auditing, incident response and deletion before production.

## Minimum promotion gates

**Phase 1: two or three approved repositories.** Validate entitlement, scoped credentials, approved data route, explicitly approved model/effort, bounded spend, trustworthy isolation, exact owner mapping, human finding review and evidence integrity. Stop on unexpected spend, owner mismatch, incomplete coverage or a failed approval boundary.

**Phase 2: representative archetypes.** Add enough repositories to exercise different languages, internet exposure, data sensitivity and deployment patterns. Compare finding usefulness, duplicate rate, review time, stale-context frequency and operational cost against the existing manual workflow. Any five-to-ten-repository size is a proposal, not a preapproved commitment.

**Phase 3: bounded fleet rollout.** Increase concurrency and campaign size only after customer-owned quality, spend, exception, audit, incident and revalidation measures pass. Pause automatically when approvals expire, budgets approach their limit, isolation degrades or reviewer backlogs breach agreed thresholds.

## Initial customer workshop decisions

1. Which exact repositories and pinned revisions are authorised for the first proof?
2. Who owns repository scope, security architecture, finding disposition, risk exceptions, FinOps and release approval?
3. Which Codex Security surface is available under the customer's actual access and data-processing conditions?
4. Which model, reasoning effort, trigger and maximum campaign admission are approved?
5. Which services share an archetype, and which require a bespoke human-accepted threat model?
6. What output is allowed: owner-private review packet only, or a separately authorised draft pull request?
7. What measured accuracy, review effort, coverage, freshness and operating-cost thresholds must pass before expansion?

No repository access, product execution, automation, draft pull request, shared-document change, customer communication, merge, deployment or publication is performed by this runbook.
