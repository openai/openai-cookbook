# Publication sources and supported product contracts

This guide separates a reusable reference implementation from the official
OpenAI Cookbook publication process. Every link points to an official OpenAI
developer page, OpenAI-maintained documentation, or an OpenAI-owned public
GitHub repository. Product guidance was checked on 25 August 2026.

## Recommended deliverables: an implementation and its explanation

Publishable material should contain both:

1. A self-contained reference implementation that a reader can clone,
   configure with their own authorised repository inventory, run offline against
   fictional fixtures, and verify with automated tests.
2. A concise Cookbook notebook or article that explains the architecture, trust
   boundaries, configuration, expected outputs, approval gates, limitations,
   and the path from a synthetic demonstration to a separately approved pilot.

An architecture diagram alone does not prove repeatability. A repository alone
does not explain the decisions operators must make. The implementation and its
documented operating model are complementary deliverables.

Creating a local publication-ready package does not publish it, create a public
repository, open a pull request, grant product access, or approve paid model
usage. Those actions remain separate human decisions.

## Official OpenAI Cookbook contribution requirements

Authoritative sources:

- [OpenAI Cookbook](https://developers.openai.com/cookbook)
- [OpenAI Cookbook public repository](https://github.com/openai/openai-cookbook)
- [Repository layout, notebook, security, and review guidance](https://github.com/openai/openai-cookbook/blob/main/AGENTS.md)
- [Contribution policy](https://github.com/openai/openai-cookbook/blob/main/CONTRIBUTING.md)
- [Cookbook publication registry](https://github.com/openai/openai-cookbook/blob/main/registry.yaml)
- [Pull request review checklist](https://github.com/openai/openai-cookbook/blob/main/.github/pull_request_template.md)
- [Notebook structural validator](https://github.com/openai/openai-cookbook/blob/main/.github/scripts/check_notebooks.py)

The Cookbook repository places runnable examples under `examples/<topic>/`,
long-form articles under `articles/`, and shared images under `images/`.
Adding or moving published material requires a matching root-level
`registry.yaml` entry; `authors.yaml` is needed only when introducing optional
custom author metadata. A suitable contribution layout would be:

```text
examples/codex/governed_repository_security_reviews/
  governed_repository_security_reviews.ipynb
  README.md
  cookbook/security-review-pipeline/
    config.example.json
    inventory.example.json
    approvals.example.json
  src/
  fixtures/
  tests/
  contracts/codex-security-schemas/
    UPSTREAM-LICENSE-APACHE-2.0.txt
    PROVENANCE.json
    findings.schema.json
    coverage.schema.json
    scan-manifest.schema.json
```

An illustrative registry entry is:

```yaml
- title: Govern repository security reviews with versioned context
  path: examples/codex/governed_repository_security_reviews/governed_repository_security_reviews.ipynb
  slug: governed-repository-security-reviews
  description: Bind repository revisions and threat context to human approval, bounded work and repeat-safe review evidence in an offline security workflow.
  date: 2026-08-25
  authors:
    - rory-opanai
  tags:
    - codex
    - security
    - agents
    - automation
    - evals
    - human-in-the-loop
```

The proposed author slug was resolved from the authenticated GitHub account;
identity verification is not byline consent or a grant of publication rights.
Confirm the author, licence and release approvals before submission. Custom
`authors.yaml` metadata is optional when using the GitHub-profile fallback.

Run the notebook from top to bottom, remove saved execution outputs and counts,
document prerequisites and environment variables, and keep secrets out of
source control. The repository's structural check is:

```sh
python .github/scripts/check_notebooks.py
```

That upstream check inspects notebook files changed against `origin/main`; it
therefore runs inside an actual Cookbook checkout with `nbformat` installed.
A standalone package should additionally run its own notebook execution, unit,
integration, privacy, export, and isolated-checkout tests.

The upstream pull request template requires a summary, motivation, registry
entry, and self-review for relevance, uniqueness, spelling and grammar, clarity,
correctness, and completeness. Maintainers review community contributions on a
best-effort basis; acceptance and publication are not guaranteed.

The Cookbook default branch resolved to commit
`51c769595490f7513d4bd7c6e7700a7ab8dedbd4` during this review. Recheck the
repository instructions and contribution policy immediately before submission.

## Public, redistributable Codex Security evidence schemas

The official [Codex Security public repository](https://github.com/openai/codex-security)
contains the exact canonical findings, coverage, and scan-manifest JSON
schemas. Its [Apache 2.0 licence](https://github.com/openai/codex-security/blob/main/LICENSE)
permits redistribution subject to its conditions, including distributing the
licence and preserving applicable copyright and attribution notices.

The public default branch was independently resolved to commit
`59d026a0579af084b419cd7f33b8e1b867338ee8`. These immutable upstream sources
were fetched and hashed before inclusion in this provenance record:

| Public upstream artefact | SHA-256 | Bytes |
| --- | --- | ---: |
| [findings.schema.json](https://raw.githubusercontent.com/openai/codex-security/59d026a0579af084b419cd7f33b8e1b867338ee8/sdk/typescript/_bundled_plugin/schemas/findings.schema.json) | `a480337cc0fa4c48c44fc7be17c6c4348767815570775cda80f2aaf797b8e56c` | 19,167 |
| [coverage.schema.json](https://raw.githubusercontent.com/openai/codex-security/59d026a0579af084b419cd7f33b8e1b867338ee8/sdk/typescript/_bundled_plugin/schemas/coverage.schema.json) | `7964b132998ca4dcdd19c75f5d92483e1d44cb71462237709b968ec548c10652` | 4,670 |
| [scan-manifest.schema.json](https://raw.githubusercontent.com/openai/codex-security/59d026a0579af084b419cd7f33b8e1b867338ee8/sdk/typescript/_bundled_plugin/schemas/scan-manifest.schema.json) | `265a48629113f77cd65a3127f1f7e95d3c39ae60e868685837a6aa31d4133310` | 8,048 |
| [Apache 2.0 licence](https://raw.githubusercontent.com/openai/codex-security/59d026a0579af084b419cd7f33b8e1b867338ee8/LICENSE) | `d17f227e4df5da1600391338865ce0f3055211760a36688f816941d58232d8dc` | 10,926 |

All three schema documents contain zero `$ref` entries. They are therefore
self-contained at the pinned commit and do not require the neighbouring
`definitions/` or `tools/` directories for reference resolution.

The exported standalone reference repository stores these files at the exact
root-relative path `contracts/codex-security-schemas/`, alongside
`PROVENANCE.json` and `UPSTREAM-LICENSE-APACHE-2.0.txt`.

Prefer these pinned, attributed public files when a reference implementation
needs offline validation. A fresh clone must not require an employee-only
plugin cache, private machine state, hidden credentials, a customer repository,
or an automatically downloaded scanner. If an alternative simulator validates
only a deliberately reduced local contract, label that contract synthetic and
do not describe it as the full official product schema.

## Supported Codex Security interfaces

Authoritative sources:

- [Codex Security product overview](https://developers.openai.com/codex/security)
- [Official public CLI and TypeScript SDK repository](https://github.com/openai/codex-security)
- [Pinned official CLI and TypeScript SDK README](https://github.com/openai/codex-security/blob/59d026a0579af084b419cd7f33b8e1b867338ee8/sdk/typescript/README.md)
- [Pinned official SDK package manifest](https://github.com/openai/codex-security/blob/59d026a0579af084b419cd7f33b8e1b867338ee8/sdk/typescript/package.json)
- [Run bulk security scans](https://learn.chatgpt.com/docs/security/cli/bulk-scans)
- [Codex Security CLI reference](https://learn.chatgpt.com/docs/security/cli/reference)
- [Codex Security TypeScript SDK](https://learn.chatgpt.com/docs/security/sdk)
- [Codex Security security policy and trust boundaries](https://github.com/openai/codex-security/blob/main/SECURITY.md)
- [Official hardened Docker Compose configuration](https://github.com/openai/codex-security/blob/main/compose.yaml)

The published `@openai/codex-security` package provides both the
`codex-security` CLI and a server-side TypeScript SDK. The documented product
requires Node.js `^22.13.0`, `^24.0.0` or `^26.0.0`, and Python 3.10 or
later. Python 3.10 also requires `tomli`; this separate offline reference
requires Python 3.11 or newer on a supported POSIX host.

The package and source are public, but running genuine scans requires Codex
Security access, an approved authentication route, repository authorisation,
and any applicable data-handling or spending approvals. Some cybersecurity
requests or protected findings require Trusted Access for Cyber; signing in or
providing an API key does not itself grant that approval.

### Repository campaigns

The documented bulk interface accepts either interactive GitHub discovery or a
CSV inventory pinned to exact full Git commit hashes. CSV columns are `id`,
`repository`, and `revision`, with optional `scope`, `mode`, and `prompt`.
Interactive discovery is unsuitable for unattended execution; an approved CSV
is the repeatable campaign input.

After a human has approved the exact target inventory, model, effort,
credentials, spending owner, and output directory, a supported example is:

```sh
npx @openai/codex-security@0.1.20 bulk-scan repositories.csv \
  --output-dir "$SECURITY_REVIEW_OUTPUT_DIR" \
  --workers 4 \
  --max-attempts 2 \
  --knowledge-base ./security-context/organisation-baseline.md \
  --knowledge-base ./security-context/workload-archetypes \
  --model gpt-5.6-terra \
  --effort high
```

`SECURITY_REVIEW_OUTPUT_DIR` must identify a private directory outside every
repository being scanned. The example illustrates a documented command only;
the offline recipe must never invoke it without a separately approved live-run
mode.

Documented campaign behaviour:

- `--workers` bounds concurrent repository scans and defaults to four. It is
  distinct from the independent workers inside an individual deep scan.
- Repeated `--knowledge-base` options pass shared architecture, threat-model,
  and policy documents. Per-repository CSV prompts add repository-specific
  instructions; composing a hierarchical threat model remains application-owned.
- `--max-attempts` retries temporary checkout or scan errors. Completed scans
  with partial coverage are not retried and produce a non-successful campaign
  status requiring human review.
- Running the same campaign with its original CSV and output directory resumes
  unfinished work and skips completed repository scans. Changing pinned
  revisions, scopes, prompts, or other campaign inputs requires a new campaign.
- The documented bulk default is `gpt-5.6-sol` with `xhigh` effort. Production
  callers should choose an approved model and reasoning effort explicitly.
- `bulk-scan --max-cost USD` is documented, but the estimated threshold applies
  separately to each repository attempt and in-flight requests can overshoot.
  It is not a hard aggregate campaign cap; enforce customer-owned admission and
  reservation controls. `--max-time-hours` is not a documented bulk option.
- Campaign output includes `manifest.json`, `results.jsonl`, and per-attempt
  `scan-manifest.json`, `findings.json`, `coverage.json`, and `report.md`.
  Review coverage before treating an absence of findings as meaningful.

The single-repository `scan --patch --create-pr` command can open a **draft
GitHub pull request** through an independently authenticated `gh` session;
`--create-pr` requires `--patch` and separately approved repository, branch and
pull-request write authority. The saved-finding `patch --create-pr` path also
supports a draft pull request. Neither establishes bulk pull-request creation,
customer entitlement, automatic merge or deployment. The reference itself has
no provider-write adapter: its review packet remains the default, and named
humans retain patch approval, every provider write, merge and deployment.

### Recorded version and help checks

The exact public `0.1.20` release archive was SHA-256 checked and its
`--version`, `bulk-scan --help` and `scan --help` entrypoints were run with
Node.js 24.14.0 in separate non-root Docker containers. Each used no network,
a read-only root, dropped capabilities, no-new-privileges and no credentials
or repository mounts. All three invocations exited successfully and all three
containers were removed. No scan, paid call or provider write occurred.

The public recording and archive digests are in
`contracts/codex-security-cli/PROVENANCE.json`. The supplied
`scripts/check_codex_security_capabilities.py` validates recorded help only;
it never installs or executes the product and cannot prove a reader's current
installation or account entitlement. Run it from the example root:

```sh
python3 -B scripts/check_codex_security_capabilities.py \
  --version-file contracts/codex-security-cli/version.stdout.txt \
  --bulk-help-file contracts/codex-security-cli/bulk-help.stdout.txt \
  --scan-help-file contracts/codex-security-cli/scan-help.stdout.txt \
  --model gpt-5.6-terra --effort high
```

Published documentation and a released package can drift. The recorded
`0.1.20` help itself includes the per-attempt `--max-cost` option and describes
`scan --patch --create-pr` as creating a draft pull request. Revalidate a
different installed version before connecting a live adapter. The model name
is an explicit example selection, not proof of access or availability.

### TypeScript SDK

The documented SDK exposes `CodexSecurity`, `security.preflight(...)`,
`security.run(...)`, and `security.close()`. `knowledgeBasePaths` supplies
architecture or policy context. Deep scans support `mode: "deep"`, `workers`,
`subagents`, `stopAfterNoNew`, `maxDiscoveryRuns`, and `maxTimeHours`.

`maxCostUsd` limits estimated model spend, and `onCost` reports estimates.
In-flight requests can finish above the configured threshold. A bounded
campaign still needs an independently enforced admission budget, charge owner,
concurrency policy, cancellation path, and human exception process.

## Trust boundaries and human approvals

Codex Security runs with the operating-system permissions of its host process.
The official CLI reference documents the `codex_security_scan` filesystem
profile and `approvalPolicy: "never"`: scanning does not pause to request
interactive approval. Repository contents, Git worktrees, local scan state,
shared operating-system accounts, and model outputs are not independent
security boundaries.

Consequently, keep the trusted control plane responsible for inventory,
credential selection, authorisation, approved model egress, campaign budgets,
evidence integrity, and named human review. Execute untrusted repository code
or proposed tests in an independently restricted container with a separate
filesystem boundary, non-root identity, denied outbound network, minimal
mounts, dropped capabilities, and no inherited host credentials.

The official [sandboxed code-migration Cookbook example](https://developers.openai.com/cookbook/examples/agents_sdk/sandboxed-code-migration/sandboxed_code_migration_agent)
documents this architecture: the trusted host owns credentials, policy, tools,
and audit, while the sandbox receives only its scoped task workspace. The
[Codex workflow Cookbook](https://developers.openai.com/cookbook/examples/codex/iterating-development-workflows-with-codex)
separately illustrates approval gates and evidence-backed verification.

Application-owned human gates should cover repository scope, high-risk threat
context, live model and spending selection, finding disposition, patch review,
optional repository-provider writes, merge, deployment, exceptions, and policy
changes. A product's non-interactive execution policy is not equivalent to a
business approval.

## Scope of the integration example

This contribution teaches the repository-security control plane. It does not
include the separate automated-development walkthrough or implement Responses
API, hosted shell, webhook, CI-provider or deployment adapters. Those are
separate designs with their own current documentation and approval boundaries.

## Publication and verification boundaries

A publication-ready example should demonstrate:

- A clean clone that runs its synthetic example without an employee-only
  dependency, private credential, product entitlement, or live network call.
- Replaceable organisation controls, authorised inventory, named owners,
  repository revisions, human approvals, threat context, and campaign limits.
- Deterministic tests for changed-repository selection, durable idempotency,
  missing approvals, adversarial repository content, evidence tampering,
  partial coverage, failed scans, retry ceilings, and isolation failures.
- Container integration tests that verify the actual operating-system and
  network restrictions rather than inferring them from a Docker command.
- Clear separation between simulated repository counts and measured live
  throughput, between synthetic budget units and actual pricing, and between
  planned supported commands and observed product execution.
- A privacy scan and an allowlisted export containing no credentials, private
  customer names, local machine paths, account identifiers, generated cache
  files, saved scan results, or notebook execution output.

Do not describe any synthetic evaluation as a production deployment, a
guaranteed fleet scale, an available entitlement, an approved integration, a
completed customer result, a pricing commitment, or an automatic merge or
deployment. Publishing, opening a pull request, creating a remote repository,
making paid API calls, or scanning genuine repositories each requires a
separate explicit human decision.
