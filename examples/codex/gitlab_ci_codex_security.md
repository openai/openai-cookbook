# Detect and remediate vulnerabilities in GitLab CI with Codex Security

Use [`@openai/codex-security`](https://learn.chatgpt.com/docs/security/cli) to scan GitLab merge requests and the default branch, publish findings to GitLab Security, and optionally open draft merge requests with verified fixes.

Start with one protected API key and the downloadable pipeline. Add automated remediation only after the basic integration works. The scanner never receives repository-write credentials, and every generated fix requires human review.

## What you will build

The pipeline:

1. Scans eligible protected merge request diffs, the default branch, and optional scheduled deep reviews.
2. Publishes SARIF from a successful report job, then applies scanner policy in a separate gate.
3. Optionally validates and fixes one high- or critical-severity finding.
4. Opens a draft merge request after a focused regression test verifies the fix.
5. Tests the unprotected remediation branch without exposing protected credentials.

![GitLab CI/CD workflow with merge request, default branch, and scheduled Codex Security scan profiles](../../images/gitlab-codex-security-workflow.png)

## Prerequisites

Before you start, make sure you have:

- A GitLab project with a trusted runner that supports the Codex sandbox's user namespace.
- Node.js 22.13.0 or later, Python 3.10 or later, and access to the public `@openai/codex-security` package. Python 3.10 additionally requires `tomli`.
- An OpenAI API key from a project with Codex Security access.
- Full Git history for merge request diff scans.
- GitLab Ultimate 19.2 or later for generally available [SARIF ingestion](https://docs.gitlab.com/user/application_security/detect/sarif/).
- [Trusted Access for Cyber](https://chatgpt.com/cyber) if your account and repository require it for full-repository scans.

Optional remediation also requires an existing regression test and a job container that can run repository-controlled commands as a separate unprivileged user. Publishing draft merge requests additionally requires a scoped GitLab project access token.

## Step 1: Add the API key and pipeline

Create a [masked, hidden, and protected GitLab CI/CD variable](https://docs.gitlab.com/ci/variables/#define-a-cicd-variable-in-the-ui) named `CODEX_SECURITY_API_KEY`. Set its value to an OpenAI Platform API key with Codex Security access and enable **Protect variable**.

Scanning and SARIF publication require only one project variable: `CODEX_SECURITY_API_KEY`. You do not need a GitLab token or additional `OPENAI_API_KEY` or `CODEX_API_KEY` project variables for a scan-only integration.

[Download the complete `.gitlab-ci.yml`](./gitlab_ci_codex_security/.gitlab-ci.yml) and save it at the root of your GitLab repository. If you already have a pipeline, merge the included stages, hidden templates, and jobs into your existing configuration.

The example pins the tested CLI release through `CODEX_SECURITY_VERSION`. Retest authentication, SARIF ingestion, severity handling, and remediation before changing that version.

### Keep scan credentials on trusted refs

The pipeline scans only protected same-project merge requests and the protected default branch. For a merge request job to receive protected variables, both branches must be protected, its initiating user must have push or merge access to the target, and **Allow merge request pipelines to access protected variables and runners** must be enabled. See GitLab's [protected merge request resource requirements](https://docs.gitlab.com/ci/pipelines/merge_request_pipelines/#control-access-to-protected-variables-and-runners).

Protected refs do not by themselves make repository-controlled CI safe: a merge request can modify `.gitlab-ci.yml`. Review which branches and contributors can run secret-bearing jobs. If ordinary feature branches are unprotected, scan after merging to the protected default branch instead.

Larger deployments can enforce immutable jobs with a [pipeline execution policy](https://docs.gitlab.com/user/application_security/policies/pipeline_execution_policies/) and retrieve short-lived credentials from an [external secrets provider](https://docs.gitlab.com/ci/secrets/).

If an existing masked variable was created without hidden visibility, GitLab cannot convert it in place. Preserve its value securely and recreate the variable with masked, hidden, and protected settings.

## Step 2: Run your first scan and verify GitLab findings

Start with a small protected merge request or another deliberately limited scan before running a paid full-repository review. A two-file, `low`-effort validation scan took 334 seconds and reported an estimated cost of USD 2.76. A 63-file, `high`-effort scan took 656 seconds and reported USD 11.67. Your results will differ.

Create a same-project merge request between protected branches, or run the pipeline on the protected default branch. Open the `codex-security` job and confirm the selected target and effort. A completed scan retains these artifacts:

- `scan-manifest.json`
- `findings.json`
- `coverage.json`
- `report.md`
- `codex-security.json`
- `results.sarif`
- `scan-exit-code.txt`

Next, verify that GitLab accepted the SARIF report:

1. Open the pipeline **Security** tab and check for ingestion warnings.
2. Confirm finding identifiers, severities, file locations, and scanner names.
3. For a default-branch pipeline, open the project vulnerability report. For a merge-request pipeline, inspect its Security tab or merge-request security widget instead.
4. Download `results.sarif` from the job artifacts.

![GitLab vulnerability report populated with Codex Security SARIF findings](../../images/gitlab-vulnerability-report-pipeline-21.png)

GitLab populates project-wide vulnerability records after a successful default-branch scan; merge-request findings alone do not create project-wide vulnerability records. An uploaded SARIF artifact from a failed report job does not prove GitLab ingested its findings.

GitLab's [SARIF severity resolution](https://docs.gitlab.com/user/application_security/detect/sarif/#severity-resolution) otherwise maps `level: error` to high even for scanner-classified critical findings. The pipeline matches SARIF results to `findings.json` and sets `result.rank` to `95` for critical findings, `80` for high, `55` for medium, `25` for low, and `5` for informational. Preserve finding identifiers and locations when adapting the report.

## Step 3: Understand the pipeline components

The complete configuration is downloadable, while the sections below explain the small components you are most likely to customize.

### Select a scan profile

The pipeline routes each supported GitLab event to the smallest scan that answers its security question:

| Profile | Trigger | Target | Effort |
| --- | --- | --- | --- |
| Merge request | Protected same-project merge request | Committed diff | `low` |
| Default branch | Protected default-branch push or manual run | Full repository, `standard` | `high` |
| Deep review | Scheduled pipeline | Full repository, `deep` | `xhigh` |

These are starting points, not universal recommendations. A complete merge request scan covers the selected diff, not the whole repository. Keep periodic broader scans for repository-wide coverage.

If your project already defines stages, add `security_scan`, `security_remediation`, `security_publish`, and `security_gate` to its existing stage list. If it defines [`workflow: rules`](https://docs.gitlab.com/ci/yaml/workflow/), allow the relevant merge request, default-branch, and scheduled pipelines.

```yaml
variables:
  CODEX_SECURITY_VERSION: "0.1.11"
  CODEX_SECURITY_MAX_CHANGED_FILES: "8"

stages:
  - security_scan
  - security_remediation
  - security_publish
  - security_gate

.codex-security-rules:
  rules:
    - if: '$CI_PIPELINE_SOURCE == "schedule"'
      variables:
        CODEX_SECURITY_TARGET: "repository"
        CODEX_SECURITY_MODE: "deep"
        CODEX_SECURITY_EFFORT: "xhigh"
    - if: '$CI_PIPELINE_SOURCE == "merge_request_event" && $CI_MERGE_REQUEST_SOURCE_PROJECT_ID == $CI_PROJECT_ID && $CI_MERGE_REQUEST_SOURCE_BRANCH_PROTECTED == "true" && $CI_MERGE_REQUEST_TARGET_BRANCH_PROTECTED == "true"'
      variables:
        CODEX_SECURITY_TARGET: "diff"
        CODEX_SECURITY_MODE: "standard"
        CODEX_SECURITY_EFFORT: "low"
    - if: '$CI_COMMIT_REF_PROTECTED == "true" && $CI_COMMIT_BRANCH == $CI_DEFAULT_BRANCH && ($CI_PIPELINE_SOURCE == "push" || $CI_PIPELINE_SOURCE == "web")'
      variables:
        CODEX_SECURITY_TARGET: "repository"
        CODEX_SECURITY_MODE: "standard"
        CODEX_SECURITY_EFFORT: "high"
```

### Install the CLI outside the checkout

The runtime template installs the pinned CLI under `/tmp` and invokes its absolute path, preventing repository-controlled executables from replacing it. `--ignore-scripts` disables dependency lifecycle scripts. Git, Python, ripgrep, certificates, and `util-linux` provide the CLI and sandbox prerequisites.

The example omits runner tags so projects can select any eligible trusted runner. Add your organization's dedicated security-runner tag when required.

```yaml
.codex-security-runtime:
  image: node:26-bookworm-slim
  variables:
    GIT_DEPTH: "0"
  before_script:
    - |
      set -eu

      CLI_DIR="/tmp/codex-security-cli"

      apt-get update -qq > /dev/null
      apt-get install -y -qq --no-install-recommends \
        ca-certificates git python3 ripgrep util-linux

      npm install \
        --prefix "$CLI_DIR" \
        --ignore-scripts \
        --no-audit \
        --no-fund \
        --loglevel=error \
        "@openai/codex-security@$CODEX_SECURITY_VERSION"

      export CODEX_SECURITY_BIN="$CLI_DIR/node_modules/.bin/codex-security"
      "$CODEX_SECURITY_BIN" --version
```

### Pin the exact scan target

`GIT_DEPTH: "0"` provides enough history to calculate a merge base. For a merge request, the pipeline passes both the base revision and `CI_COMMIT_SHA`, ensuring it scans the committed change GitLab is reviewing.

The tested CLI also needs `CODEX_SECURITY_TARGET_SNAPSHOT_DIGEST` to bind a diff scan's manifest to its exact reviewed content. This is a compatibility workaround, not a public configuration setting. Retest it after upgrading the CLI and remove it once the diff seals correctly without the override.

Repository scans identify the checkout by revision and do not set the diff snapshot digest.

```bash
unset CODEX_SECURITY_TARGET_SNAPSHOT_DIGEST

case "$CODEX_SECURITY_TARGET" in
  diff)
    BASE_REVISION="$(git merge-base \
      "$CI_MERGE_REQUEST_DIFF_BASE_SHA" \
      "$CI_COMMIT_SHA")"

    DIFF_DIGEST="$(
      git diff --binary --full-index --no-ext-diff --no-textconv \
        "$BASE_REVISION" "$CI_COMMIT_SHA" \
        | python3 -c 'import hashlib, sys; print(hashlib.sha256(sys.stdin.buffer.read()).hexdigest())'
    )"
    export CODEX_SECURITY_TARGET_SNAPSHOT_DIGEST="codex-security-snapshot/v1:sha256:$DIFF_DIGEST"

    set -- --diff "$BASE_REVISION" --head "$CI_COMMIT_SHA"
    ;;
  repository)
    set -- --mode "$CODEX_SECURITY_MODE"
    ;;
  *)
    echo "Unsupported scan target: ${CODEX_SECURITY_TARGET:-unset}" >&2
    exit 2
    ;;
esac
```

### Validate configuration before a paid scan

The job checks `CODEX_SECURITY_API_KEY`, creates private state and result directories, and runs [`--dry-run`](https://learn.chatgpt.com/docs/security/cli/reference). With `--auth api-key`, CLI `0.1.11` requires a process-scoped `OPENAI_API_KEY` even for this preflight.

A dry run checks the target and configuration without starting a paid scan, but it does not verify account entitlement, available quota, or rate-limit capacity. Both invocations receive the credential only for their individual processes:

```bash
# API-key authentication requires a credential even in dry-run mode.
OPENAI_API_KEY="$CODEX_SECURITY_API_KEY" \
  "$CODEX_SECURITY_BIN" scan . "$@" --dry-run

set +e
OPENAI_API_KEY="$CODEX_SECURITY_API_KEY" \
CODEX_SECURITY_STATE_DIR="$STATE_DIR" \
  "$CODEX_SECURITY_BIN" scan . "$@" > "$JSON_FILE"
scan_exit="$?"
set -e

unset OPENAI_API_KEY CODEX_API_KEY CODEX_ACCESS_TOKEN CODEX_SECURITY_API_KEY
```

### Publish SARIF before enforcing scan policy

GitLab does not ingest SARIF findings from a failed report job, even when `allow_failure` is enabled. The report job must therefore verify the sealed scan, export non-empty SARIF, save the scanner's real exit status, and return success. A separate final gate restores that exit status after optional remediation and publication.

Exit `2` is accepted by the report job only when the manifest is completed, `coverage.json` explicitly reports `partial`, and SARIF export succeeds. Missing evidence, unrelated scanner errors, malformed results, and unsupported severities remain blocking.

The report job retains the complete artifact directory for seven days and registers SARIF through `artifacts:reports:sarif`:

```yaml
codex-security:
  artifacts:
    when: always
    access: maintainer
    expire_in: 7 days
    paths:
      - codex-security-artifacts/
    reports:
      sarif: codex-security-artifacts/results.sarif
```

[`artifacts:access: maintainer`](https://docs.gitlab.com/ci/yaml/#artifactsaccess) limits UI and API downloads to Maintainers and Owners. Configure job-token access, downstream pipelines, and project visibility separately because artifacts may contain source excerpts and vulnerability details.

During calibration, only the final gate allows a verified partial-coverage exit `2`. Remove this allowance when incomplete coverage must block:

```yaml
codex-security-gate:
  extends: .codex-security-rules
  stage: security_gate
  image: alpine:3.20
  dependencies:
    - codex-security
  # Remove this calibration-only allowance when partial coverage must block.
  allow_failure:
    exit_codes:
      - 2
  script:
    - |
      set -eu
      unset OPENAI_API_KEY CODEX_API_KEY CODEX_ACCESS_TOKEN CODEX_SECURITY_API_KEY

      scan_exit="$(cat codex-security-artifacts/scan-exit-code.txt)"
      echo "Codex Security scan exit code: $scan_exit"

      case "$scan_exit" in
        0|1|2) exit "$scan_exit" ;;
        *) echo "Invalid Codex Security scan exit code: $scan_exit" >&2; exit 2 ;;
      esac
```

## Step 4: Enable automated draft merge requests

Automatic remediation is optional and runs only on the protected default branch. It processes one high- or critical-severity finding from a completed scan with complete coverage. Merge request diff scans, medium- and low-severity findings, partial scans, failed verification, and unsafe patches never publish fixes.

### How automatic vulnerability remediation creates a merge request

When remediation and merge request publication are enabled, a protected default-branch pipeline progresses through these stages without a webhook:

| Step | GitLab job | What happens |
| --- | --- | --- |
| 1. Find a vulnerability | `codex-security` | Scans the protected default branch and publishes SARIF |
| 2. Select a trusted finding | `codex-security-remediate` | Requires complete coverage and selects one `high`- or `critical`-severity finding |
| 3. Reproduce and fix it | `codex-security-remediate` | Confirms the existing regression test fails, then validates and patches the finding |
| 4. Verify the fix | `codex-security-remediate` | Rejects unsafe changes and confirms the same regression test passes |
| 5. Open a draft merge request | `codex-security-draft-mr` | Uses a scoped project token to push a fix branch and create or reuse a draft merge request |
| 6. Test and review | `codex-security-remediation-mr-check` | Tests the unprotected fix branch without protected secrets; a human reviews and merges |

The workflow requires a completed scan of the current revision with complete coverage. Merge request diff scans do not create remediation merge requests. The pipeline rejects incomplete coverage, medium- or low-severity findings, failed verification, and unsafe changes.

An existing open draft is reused instead of creating a duplicate, and the pipeline never automatically merges code.

### Configure verified patch generation

Set these protected GitLab variables:

- `CODEX_SECURITY_ENABLE_REMEDIATION=true`.
- `CODEX_SECURITY_VERIFICATION_COMMAND` to an existing focused regression test, such as `npm test -- --runInBand tests/security-regression.test.ts`.
- Optionally, `CODEX_SECURITY_SETUP_COMMAND` when the project needs dependency installation before verification.

The regression test must fail with exit `1` before the fix and pass with exit `0` afterward. Test the security invariant, not a particular implementation. Exit `127`, for example, typically indicates a missing tool rather than a reproduced vulnerability.

The remediation job runs only for explicitly enabled protected default-branch pipelines:

```yaml
codex-security-remediate:
  extends: .codex-security-runtime
  stage: security_remediation
  environment:
    name: codex-security/remediate
  variables:
    CODEX_SECURITY_REMEDIATION_EFFORT: "high"
  rules:
    - if: '$CODEX_SECURITY_ENABLE_REMEDIATION == "true" && $CI_COMMIT_REF_PROTECTED == "true" && $CI_COMMIT_BRANCH == $CI_DEFAULT_BRANCH && ($CI_PIPELINE_SOURCE == "push" || $CI_PIPELINE_SOURCE == "schedule" || $CI_PIPELINE_SOURCE == "web")'
  needs:
    - job: codex-security
      artifacts: true
```

The [Security CLI reference](https://learn.chatgpt.com/docs/security/cli/reference) provides the two commands used to validate and patch the selected finding:

```bash
CODEX_API_KEY="$CODEX_SECURITY_API_KEY" \
  npx "@openai/codex-security@$CODEX_SECURITY_VERSION" validate finding.json --effort high

CODEX_API_KEY="$CODEX_SECURITY_API_KEY" \
  npx "@openai/codex-security@$CODEX_SECURITY_VERSION" patch finding.json --effort high
```

Unlike `scan`, `validate` and `patch` invoke Codex directly and require process-scoped `CODEX_API_KEY`. Do not add `--auth` to these subcommands. Their human-readable assessments complement the regression test; they are not machine-readable proof that the vulnerability was fixed.

Repository setup and test commands run as a separate unprivileged user without OpenAI, GitLab, registry, or deployment credentials. The separate user also prevents those commands from inspecting the credential-bearing parent process through `/proc`. Removing environment variables alone is insufficient.

The example's job shell runs as root inside an unprivileged container and drops repository-controlled commands to UID `65534`. Non-root runner deployments must move verification into a separate credential-free job instead.

The remediation job also verifies the current revision and complete scan coverage, rejects repository-write credentials and protected paths, and limits changed files. `CODEX_SECURITY_MAX_CHANGED_FILES` defaults to `8` and accepts values from `1` through `20`. One verified authorization fix required five implementation files and two focused tests, so a limit of five would incorrectly reject a complete fix.

Successful remediation stores `finding.json`, `fix.patch`, both validation reports, and before-and-after test logs in `codex-security-remediation/`. A clean scan with no eligible findings succeeds without producing a patch.

### Automatically create a draft merge request

Patch generation does not require GitLab write access. To also publish fixes, create a [project access token](https://docs.gitlab.com/user/project/settings/project_access_tokens/) with the Developer role and these [token scopes](https://docs.gitlab.com/security/tokens/access_token_scopes/):

- `write_repository` to push the fix branch over HTTPS.
- `api` to find existing merge requests and create a draft.

Save the token as the masked, hidden, protected variable `GITLAB_REMEDIATION_TOKEN`. Set its [environment scope](https://docs.gitlab.com/ci/environments/#limit-the-environment-scope-of-a-cicd-variable) to exactly `codex-security/publish`. Never expose this token to the scanner, remediation job, repository setup, or regression tests.

Finally, add the protected variable `CODEX_SECURITY_CREATE_MR=true`:

```yaml
codex-security-draft-mr:
  stage: security_publish
  image: python:3.13-slim
  environment:
    name: codex-security/publish
  rules:
    - if: '$CODEX_SECURITY_ENABLE_REMEDIATION == "true" && $CODEX_SECURITY_CREATE_MR == "true" && $CI_COMMIT_REF_PROTECTED == "true" && $CI_COMMIT_BRANCH == $CI_DEFAULT_BRANCH && ($CI_PIPELINE_SOURCE == "push" || $CI_PIPELINE_SOURCE == "schedule" || $CI_PIPELINE_SOURCE == "web")'
  needs:
    - job: codex-security-remediate
      artifacts: true
```

The job applies the verified patch, rechecks protected paths, pushes `codex-security/fix-<finding-hash>`, and creates `Draft: Fix Codex Security finding <finding-hash>` through the [GitLab merge requests API](https://docs.gitlab.com/api/merge_requests/#create-a-merge-request). It reuses an existing open draft for the same finding. If a closed merge request left its source branch behind, it appends `-$CI_PIPELINE_ID` to avoid a non-fast-forward collision.

Do not substitute `CI_JOB_TOKEN`: GitLab's [job token permissions](https://docs.gitlab.com/ci/jobs/ci_job_token/) do not include merge request creation. GitLab Runner can also inject a checkout-only `include.path` that rewrites repository URLs to use the job token and sets `credential.interactive=never`.

Before pushing, the publisher removes that include, clears inherited job credentials, and enables the protected `askpass` flow with `credential.interactive=true`. This isolates authentication to the scoped project token.

For self-hosted runners that cannot reach GitLab's advertised URL, optionally set protected `CODEX_SECURITY_GITLAB_INTERNAL_URL` to the origin reachable from the job container. Ordinary GitLab installations do not need this override.

### Test the remediation branch without secrets

Automatically created `codex-security/fix-*` branches remain unprotected. Their merge request pipelines must not receive protected OpenAI or publishing credentials and must not start another paid scan.

The dedicated regression job runs only for same-project remediation branches targeting the default branch:

```yaml
codex-security-remediation-mr-check:
  stage: security_gate
  image: node:26-bookworm-slim
  variables:
    CODEX_SECURITY_MR_TEST_COMMAND: "npm test"
  rules:
    - if: '$CI_PIPELINE_SOURCE == "merge_request_event" && $CI_MERGE_REQUEST_SOURCE_PROJECT_ID == $CI_PROJECT_ID && $CI_MERGE_REQUEST_SOURCE_BRANCH_NAME =~ /^codex-security\/fix-/ && $CI_MERGE_REQUEST_SOURCE_BRANCH_PROTECTED != "true" && $CI_MERGE_REQUEST_TARGET_BRANCH_NAME == $CI_DEFAULT_BRANCH'
```

Configure `CODEX_SECURITY_MR_TEST_COMMAND`, and optionally `CODEX_SECURITY_MR_SETUP_COMMAND`, as non-secret values available to unprotected pipelines. The example defaults to `npm test`. If dependency installation needs private registry access, use a separate least-privilege read-only mechanism approved for unprotected jobs.

To validate the complete workflow:

1. Add a vulnerable example with an existing regression test that fails on the protected default branch.
2. Enable remediation without `CODEX_SECURITY_CREATE_MR` and inspect `fix.patch`, validation reports, and before-and-after test logs.
3. Add the environment-scoped GitLab token, enable `CODEX_SECURITY_CREATE_MR`, and rerun the protected pipeline.
4. Confirm one draft merge request is created and its unprotected pipeline runs only credential-free checks.
5. Rerun the default-branch pipeline to verify the existing draft is reused, then review and merge the fix manually.

## Step 5: Configure optional variables

The pipeline already defines safe defaults where applicable. Start with the required API key and add other project variables only when enabling the corresponding feature:

| Variable | When to configure | Default | Purpose and scope |
| --- | --- | --- | --- |
| `CODEX_SECURITY_API_KEY` | Required for every scan | None | Protected, masked, hidden OpenAI API key with Codex Security access |
| `CODEX_SECURITY_VERSION` | Optional | `0.1.11` | Pinned CLI version already defined in the pipeline; change only after retesting |
| `CODEX_SECURITY_ENABLE_REMEDIATION` | Required to generate patches | Disabled | Protected opt-in for default-branch remediation |
| `CODEX_SECURITY_VERIFICATION_COMMAND` | Required for remediation | None | Protected regression command that fails before the fix and passes afterward |
| `CODEX_SECURITY_SETUP_COMMAND` | Optional for remediation | Unset | Protected dependency setup command, such as `npm ci` |
| `CODEX_SECURITY_REMEDIATION_EFFORT` | Optional for remediation | `high` | Reasoning effort for finding validation and patch generation |
| `CODEX_SECURITY_MAX_CHANGED_FILES` | Optional for remediation | `8` | Changed source and test file limit; accepts `1` through `20` |
| `CODEX_SECURITY_CREATE_MR` | Required to publish drafts | Disabled | Protected opt-in for draft merge request creation |
| `GITLAB_REMEDIATION_TOKEN` | Required to publish drafts | None | Protected Developer token with `api` and `write_repository`; scope to `codex-security/publish` |
| `CODEX_SECURITY_GITLAB_INTERNAL_URL` | Optional for self-hosted publishing | Unset | Protected GitLab origin reachable from the runner |
| `CODEX_SECURITY_MR_TEST_COMMAND` | Optional for remediation branch checks | `npm test` | Non-secret test command available to unprotected remediation branches |
| `CODEX_SECURITY_MR_SETUP_COMMAND` | Optional for remediation branch checks | Unset | Non-secret setup command available to unprotected remediation branches |

Keep remediation controls and secrets protected. The two `CODEX_SECURITY_MR_*` command variables contain no credentials and must remain available to unprotected remediation branches.

GitLab supplies `CI_*` variables automatically. The pipeline manages `GIT_DEPTH`, `CODEX_SECURITY_TARGET`, `CODEX_SECURITY_MODE`, `CODEX_SECURITY_EFFORT`, `CODEX_SECURITY_BIN`, `CODEX_SECURITY_STATE_DIR`, and `CODEX_SECURITY_TARGET_SNAPSHOT_DIGEST`; do not create project variables for these internal values.

## Step 6: Apply coverage, severity, and cost policy

Interpret scanner exit codes before deciding whether a pipeline should block:

| Exit code | Meaning | Suggested treatment |
| --- | --- | --- |
| `0` | Complete coverage and configured severity policy passed | Pass |
| `1` | Completed scan found an issue at or above the configured threshold | Block when severity policy is enabled |
| `2` | Runtime, configuration, export, input, or incomplete-coverage outcome | Inspect artifacts; advisory only during calibration |
| `130` | Interrupted | Retry or investigate cancellation |
| `143` | Terminated | Check timeout, cancellation, or runner shutdown |

Exit `2` can include real findings with partial coverage. The report job publishes these only after validating a completed manifest, explicitly partial coverage, and successful SARIF export. Any unrelated exit `2` or missing evidence fails closed.

Roll out policy gradually:

1. Validate credentials, sandbox behavior, scan artifacts, and SARIF ingestion.
2. Calibrate representative diff and repository scans while the final gate temporarily allows verified partial-coverage exit `2`.
3. Add `--fail-on-severity` when finding quality is understood, and remove the gate's allowance when incomplete coverage must block.

Because enforcement runs last, a severity-policy finding can still appear in GitLab and produce a verified draft fix before the pipeline fails with exit `1`.

### Optimize scan cost without losing coverage

Start by removing duplicate pipelines and scans that cannot answer a useful security question. Use focused committed diffs for merge request feedback, `--path` for independently owned services, and standard mode for routine repository scans. Reserve deep scans for scheduled or specifically high-risk reviews.

Compare effort and model changes independently on the same revision. Record duration, estimated cost, finding quality, and coverage before changing defaults. Consider `--max-cost` for an estimated-cost guardrail, but do not treat it as a hard billing cap.

The earlier sample scans reported USD 2.76 for a two-file diff and USD 11.67 for a 63-file full scan. These observations are not cost predictions for other repositories. Keep periodic full scans even when most routine checks use smaller targets.

The [Security CLI option reference](https://learn.chatgpt.com/docs/security/cli/reference) documents relevant controls including `--diff BASE --head HEAD`, `--path`, `--mode`, `--effort`, `--model`, `--knowledge-base`, `--max-cost`, and `--fail-on-severity`. Do not combine `--path` with `--diff`; deep mode supports repository and path scans, not diff scans.

## Step 7: Troubleshoot the integration

Start by checking whether canonical scan artifacts exist. Then inspect coverage, the scanner exit code, and the GitLab report job:

| Symptom | Check |
| --- | --- |
| Unknown merge base or unexpected diff | Fetch full history and verify the base and head revisions |
| `bwrap: No permissions to create a new namespace` | Verify the trusted runner's user-namespace and sandbox policy |
| Exit `2` with artifacts present | Inspect scan completion, coverage, deferred work, and open questions |
| Exit `2` without canonical artifacts | Inspect credentials, runtime, output directory, and sandbox setup |
| Dry run reports missing credentials | Pass process-scoped `OPENAI_API_KEY` to both the dry run and scan |
| Validation or patching cannot authenticate | Pass process-scoped `CODEX_API_KEY`; do not add unsupported `--auth` |
| GitLab does not show findings | Confirm the report job succeeded, then inspect GitLab tier, SARIF, and ingestion warnings |
| Remediation or publishing does not run | Check protected default-branch rules, opt-in variables, verification, token scope, and API access |
| A complete fix exceeds the file limit | Increase `CODEX_SECURITY_MAX_CHANGED_FILES` within the reviewed `1`-to-`20` range |
| Git push uses the job token | Remove the runner's checkout-only `include.path` and permit the scoped-token `askpass` flow |
| Publishing cannot reach GitLab | Set optional `CODEX_SECURITY_GITLAB_INTERNAL_URL` only when the runner needs a different origin |
| Remediation branch requests protected secrets | Run only the dedicated credential-free regression job on the unprotected branch |

### Fix user-namespace failures on Docker executors

Runner configuration is environment-specific and does not belong in the portable pipeline. If Docker's default seccomp profile blocks the user namespace required by Codex, prefer a tailored profile that permits the necessary operation.

The following last-resort configuration worked for the Docker executor used to validate this example:

```toml
[runners.docker]
  security_opt = ["seccomp=unconfined"]
  privileged = false
```

`seccomp=unconfined` disables Docker's default seccomp protection. Use it only on a dedicated trusted runner restricted to protected refs, keep privileged mode disabled, and add a trusted runner tag if needed. Restart only the affected runner and verify `unshare -Ur true` before retrying.

## Next steps

Begin with a report-only integration, confirm GitLab ingests findings, and measure representative scans. Then enable one verified remediation at a time, add draft merge requests only after credential isolation is confirmed, and introduce blocking policy once the team understands coverage and finding quality.

Assign owners for finding review, draft merge requests, incomplete scans, token rotation, and exceptions. When the CLI, runner, GitLab version, or model changes, rerun a representative scan and verified fix before broad rollout.
