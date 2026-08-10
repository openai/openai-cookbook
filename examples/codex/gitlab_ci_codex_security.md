# Integrate Codex Security CLI with GitLab CI/CD and optimize scan cost

A platform team maintains a Next.js SaaS application in GitLab. The team wants security feedback on eligible merge requests between protected branches, broader coverage after changes reach the default branch, and the option to run deeper reviews for high-risk releases. At the same time, it does not want every commit to trigger the broadest and most expensive scan configuration.

In this cookbook, you will integrate the dedicated [`@openai/codex-security`](https://learn.chatgpt.com/docs/security/cli) package with GitLab CI/CD. You will start with three scan profiles, preserve the structured security evidence, publish SARIF to GitLab, and add controls for scope, model, reasoning effort, severity, and estimated cost.

The example was validated with a Docker-based runner and a Next.js SaaS demo application. The YAML does not hard-code a runner tag, so the same pipeline pattern can use any eligible trusted runner on GitLab.com, GitLab Self-Managed, or GitLab Dedicated. Add an organization-specific runner tag only when your project requires one, and adapt the image and security controls to your environment.

## What you will build

You will create a GitLab pipeline that:

1. Runs a committed-diff scan for eligible merge requests between protected branches.
2. Runs a full standard scan on the default branch.
3. Supports an optional scheduled deep scan.
4. Assigns effort by profile and documents optional model, knowledge-base, severity, and cost controls.
5. Preserves `scan-manifest.json`, `findings.json`, `coverage.json`, `report.md`, and structured JSON output.
6. Exports SARIF and publishes it through `artifacts:reports:sarif`.
7. Preserves available evidence before returning the scan or export status from the same job.

The finished workflow selects a scan profile from the GitLab pipeline event:

![GitLab CI/CD workflow with merge request, default branch, and scheduled Codex Security scan profiles](../../images/gitlab-codex-security-workflow.png)

## Prerequisites

You need:

- A GitLab project and trusted GitLab Runner that can create the user namespace required by the Codex sandbox.
- Node.js 22.13.0 or later, as required by the [Security CLI quickstart](https://learn.chatgpt.com/docs/security/cli).
- Python 3.10 or later for scans and exports; Python 3.10 also requires `tomli`.
- The public `@openai/codex-security` package.
- An OpenAI API key from a project with Codex Security access.
- [Trusted Access for Cyber](https://chatgpt.com/cyber) if your account and repository require it for full-repository scans.
- Full Git history when calculating merge request diffs.
- GitLab Ultimate 19.2 or later for generally available [SARIF ingestion](https://docs.gitlab.com/user/application_security/detect/sarif/).

## Step 1: Store the API key in GitLab

Make the Codex Security credential available only to trusted scan jobs without committing it to the repository.

Create a [masked, hidden, and protected GitLab CI/CD variable](https://docs.gitlab.com/ci/variables/#define-a-cicd-variable-in-the-ui):

- Key: `CODEX_SECURITY_API_KEY`
- Value: an OpenAI Platform API key with Codex Security access
- Protect variable: enabled

The value is not a GitLab token, runner token, npm token, ChatGPT session token, or a shell assignment.

The example maps the variable to `OPENAI_API_KEY` only for the scan process. Its job rule excludes fork merge requests and requires protected source and target branches. This does not make every same-project merge request trusted: code in a merge request can also change `.gitlab-ci.yml` and attempt to expose variables available to its pipeline. Masking and hiding reduce accidental disclosure in the UI and job logs, but they are not access controls for untrusted CI code.

For an eligible merge request job to receive the protected variable, both branches must belong to the same project and be protected, the user who starts the pipeline must have push or merge access to the target branch, and **Allow merge request pipelines to access protected variables and runners** must be enabled. GitLab documents these requirements under [protected merge request resources](https://docs.gitlab.com/ci/pipelines/merge_request_pipelines/#control-access-to-protected-variables-and-runners). If your workflow uses ordinary unprotected feature branches, run the secret-bearing scan after merge on the protected default branch instead. Larger deployments can enforce an immutable job through a [pipeline execution policy](https://docs.gitlab.com/user/application_security/policies/pipeline_execution_policies/) and retrieve a scoped, short-lived credential from an [external secrets provider](https://docs.gitlab.com/ci/secrets/). You are ready to continue when the protected `CODEX_SECURITY_API_KEY` is available only to approved scan jobs.

## Step 2: Choose initial scan profiles

Use GitLab [job rules](https://docs.gitlab.com/ci/jobs/job_rules/) to match each pipeline event to the smallest scan that answers its security question while retaining periodic broad coverage.

Start with profiles that map to distinct development decisions:

| Profile | Trigger | Target | Effort | Security question |
| --- | --- | --- | --- | --- |
| Merge request | Eligible protected same-project MR | Committed diff | `low` | What risk does this change introduce? |
| Default branch | Push to default branch | Full repository, `standard` | `high` | What risks exist in the integrated codebase? |
| Deep review | Scheduled pipeline | Full repository, `deep` | `xhigh` | What additional issues appear under deeper review? |

These effort levels are starting points, not universal recommendations. Measure representative repositories before setting organization-wide defaults. With these profiles in place, eligible protected merge requests receive focused feedback, the default branch receives a full standard scan, and scheduled pipelines run a deeper repository review. Complete coverage for a selected merge request diff applies only to that change, not to the entire repository. This keeps the tradeoff between feedback time, repository coverage, and cost explicit.

## Step 3: Add the GitLab pipeline

Install Codex Security in a trusted location, select the appropriate scan profile, preserve structured artifacts, export SARIF, and return the final scan or export status from the same job.

The example keeps only the variables required by the working pipeline. Optional model, policy, context, and cost controls are covered later in Step 8 and documented in the [Security CLI reference](https://learn.chatgpt.com/docs/security/cli/reference). It installs `@openai/codex-security` without a version specifier, so npm resolves the current `latest` release for each job. The job logs the installed version to make pipeline results traceable.

The job rules are self-contained so the example can be added to an existing pipeline without replacing its global `workflow`. If the project already uses [`workflow: rules`](https://docs.gitlab.com/ci/yaml/workflow/), make sure it permits eligible [merge request pipelines](https://docs.gitlab.com/ci/pipelines/merge_request_pipelines/), pushes to the default branch, and scheduled pipelines.

The pipeline is easier to adapt when each part has one clear responsibility.

### Route eligible pipeline events to scan profiles

The hidden `.codex-security-rules` job maps each supported GitLab event to the profiles selected in Step 2. A scheduled pipeline receives a deep repository scan, a push to the default branch receives a standard repository scan, and an eligible merge request between protected branches in the same project receives a focused diff scan. The protected variable and GitLab's protected-resource checks still determine whether the job receives the credential.

If the repository already defines stages, add `security_scan` to the existing list instead of replacing test, build, or deployment stages.

This part of the file defines the shared routing logic:

```text
stages:
  - security_scan

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
    - if: '$CI_PIPELINE_SOURCE == "push" && $CI_COMMIT_BRANCH == $CI_DEFAULT_BRANCH'
      variables:
        CODEX_SECURITY_TARGET: "repository"
        CODEX_SECURITY_MODE: "standard"
        CODEX_SECURITY_EFFORT: "high"
```

### Install the latest CLI outside the checkout

The scan job uses a Node.js image and installs the latest Security CLI release under `/tmp`. Installing it outside the checked-out repository and invoking its absolute path prevents repository-controlled executables from replacing the command. `--ignore-scripts` prevents dependency lifecycle scripts from running during installation. Git, Python, ripgrep, certificates, and `util-linux` provide the runtime and sandbox prerequisites used by the CLI.

The YAML intentionally omits `tags` so GitLab can select any eligible runner configured for the project. If your organization requires tagged runners, add its trusted security-runner tag to this job. The `unshare` check fails before a paid scan when the selected runner cannot start the Codex sandbox.

This job header and `before_script` prepare the trusted runtime:

```text
codex-security:
  extends: .codex-security-rules
  stage: security_scan
  image: node:26-bookworm-slim
  variables:
    GIT_DEPTH: "0"
  # Use this only during calibration. Remove it when exit 2 outcomes should
  # fail the pipeline.
  allow_failure:
    exit_codes:
      - 2
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
        "@openai/codex-security"

      export CODEX_SECURITY_BIN="$CLI_DIR/node_modules/.bin/codex-security"
      "$CODEX_SECURITY_BIN" --version
```

### Build an exact and reproducible scan target

`GIT_DEPTH: "0"` gives the job enough history to calculate the merge base for a merge request. For a diff scan, the script resolves the merge base and passes both the base and `CI_COMMIT_SHA` to the CLI. This ensures that the result describes the committed change GitLab is reviewing instead of an ambiguous working tree.

The pipeline tested for this cookbook also hashes the deterministic binary Git diff and exports `CODEX_SECURITY_TARGET_SNAPSHOT_DIGEST`. This compatibility step binds the scan manifest to the exact reviewed content so the observed `git_diff` result can be sealed. It is not a general configuration option in the public CLI reference. After the installed CLI changes, rerun a known diff scan without the variable and remove the workaround if the scan seals successfully. The variable is cleared before target selection and set only for diff scans, because a clean repository scan is identified by its Git revision instead.

Repository profiles do not calculate a diff. They pass the selected `standard` or `deep` mode directly to the CLI.

The target-selection block implements both paths:

```text
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

### Validate configuration before starting the scan

The job validates that `CODEX_SECURITY_API_KEY` is present, creates private job-specific state and result directories under `/tmp`, and then runs [`--dry-run`](https://learn.chatgpt.com/docs/security/cli/reference). The dry run checks the repository, target, output directory, and Codex configuration without loading credentials or starting Codex.

`CODEX_SECURITY_API_KEY` is mapped to `OPENAI_API_KEY` only for the paid scan process. The job removes all supported credential variables immediately after the scan so later artifact and export commands do not inherit them.

The first excerpt validates the secret and creates private, job-specific paths:

```text
      if test -z "${CODEX_SECURITY_API_KEY:-}"; then
        echo "Missing required GitLab CI/CD variable: CODEX_SECURITY_API_KEY" >&2
        exit 2
      fi

      STATE_DIR="/tmp/codex-security-state-$CI_JOB_ID"
      RESULTS_DIR="/tmp/codex-security-results-$CI_JOB_ID"
      JSON_FILE="/tmp/codex-security-$CI_JOB_ID.json"
      ARTIFACT_DIR="codex-security-artifacts"
      SARIF_FILE="$ARTIFACT_DIR/results.sarif"

      install -d -m 700 "$STATE_DIR" "$RESULTS_DIR" "$ARTIFACT_DIR/results"
```

The second excerpt runs the credential-free preflight and then the paid scan with a process-scoped credential:

```text
      "$CODEX_SECURITY_BIN" scan . "$@" --dry-run

      set +e
      OPENAI_API_KEY="$CODEX_SECURITY_API_KEY" \
      CODEX_SECURITY_STATE_DIR="$STATE_DIR" \
        "$CODEX_SECURITY_BIN" scan . "$@" > "$JSON_FILE"
      scan_exit="$?"
      set -e

      unset OPENAI_API_KEY CODEX_API_KEY CODEX_ACCESS_TOKEN CODEX_SECURITY_API_KEY
```

### Preserve evidence and export SARIF

The scan writes canonical artifacts to its private result directory and structured JSON to a separate file. The job copies available output into `codex-security-artifacts` even when the CLI returns a non-zero status. This is important because exit `1` or `2` can still accompany useful findings or coverage evidence.

When a scan manifest exists, `codex-security export` attempts to create SARIF from the completed, sealed result. GitLab retains the full artifact directory for seven days and ingests `results.sarif` through `artifacts:reports:sarif` when export succeeds. [`artifacts:access: maintainer`](https://docs.gitlab.com/ci/yaml/#artifactsaccess) restricts UI and API downloads to Maintainers and Owners because the retained evidence can contain source excerpts and vulnerability details. It does not block access through CI/CD job tokens or prevent artifacts from being forwarded to downstream pipelines, so configure project visibility and pipeline access separately. Because report artifacts are uploaded regardless of job success or failure, the same job can return the final scan or export status without an additional job.

This block preserves available evidence, attempts export, and publishes the artifact paths:

```text
      cp -R "$RESULTS_DIR"/. "$ARTIFACT_DIR/results/"
      test ! -s "$JSON_FILE" || cp "$JSON_FILE" "$ARTIFACT_DIR/codex-security.json"

      final_exit="$scan_exit"
      if test -s "$RESULTS_DIR/scan-manifest.json"; then
        set +e
        "$CODEX_SECURITY_BIN" export "$RESULTS_DIR" \
          --export-format sarif \
          --source-root "$CI_PROJECT_DIR" \
          --output "$SARIF_FILE"
        export_exit="$?"
        set -e

        if test "$export_exit" -ne 0 && test "$final_exit" -eq 0; then
          final_exit=2
        fi
      elif test "$final_exit" -eq 0; then
        echo "The scan completed without a sealed manifest." >&2
        final_exit=2
      fi

      exit "$final_exit"
  artifacts:
    when: always
    access: maintainer
    expire_in: 7 days
    paths:
      - codex-security-artifacts/
    reports:
      sarif: codex-security-artifacts/results.sarif
```

During initial calibration, `allow_failure` keeps exit `2` advisory while authentication, sandboxing, coverage, sealing, and SARIF export are being validated. An export failure changes a successful scan to exit `2` but never replaces an existing non-zero scan status. Remove the temporary rule when those technical outcomes should block the pipeline. Exit `1` remains blocking and is available for a later `--fail-on-severity` policy.

The complete file below combines these responsibilities. Copy it into the repository root as `.gitlab-ci.yml`, or merge its stage, hidden rules, and job into an existing pipeline.

```yaml
stages:
  - security_scan

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
    - if: '$CI_PIPELINE_SOURCE == "push" && $CI_COMMIT_BRANCH == $CI_DEFAULT_BRANCH'
      variables:
        CODEX_SECURITY_TARGET: "repository"
        CODEX_SECURITY_MODE: "standard"
        CODEX_SECURITY_EFFORT: "high"

codex-security:
  extends: .codex-security-rules
  stage: security_scan
  image: node:26-bookworm-slim
  variables:
    GIT_DEPTH: "0"
  # Use this only during calibration. Remove it when exit 2 outcomes should
  # fail the pipeline.
  allow_failure:
    exit_codes:
      - 2
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
        "@openai/codex-security"

      export CODEX_SECURITY_BIN="$CLI_DIR/node_modules/.bin/codex-security"
      "$CODEX_SECURITY_BIN" --version
  script:
    - |
      set -eu

      if test -z "${CODEX_SECURITY_API_KEY:-}"; then
        echo "Missing required GitLab CI/CD variable: CODEX_SECURITY_API_KEY" >&2
        exit 2
      fi

      STATE_DIR="/tmp/codex-security-state-$CI_JOB_ID"
      RESULTS_DIR="/tmp/codex-security-results-$CI_JOB_ID"
      JSON_FILE="/tmp/codex-security-$CI_JOB_ID.json"
      ARTIFACT_DIR="codex-security-artifacts"
      SARIF_FILE="$ARTIFACT_DIR/results.sarif"

      install -d -m 700 "$STATE_DIR" "$RESULTS_DIR" "$ARTIFACT_DIR/results"

      if ! unshare -Ur true; then
        echo 'The runner must allow the Codex sandbox user namespace.' >&2
        exit 2
      fi

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

      set -- "$@" \
        --auth api-key \
        --effort "$CODEX_SECURITY_EFFORT" \
        --output-dir "$RESULTS_DIR" \
        --json

      echo "Codex Security target: $CODEX_SECURITY_TARGET"
      echo "Codex Security mode: $CODEX_SECURITY_MODE"
      echo "Codex Security effort: $CODEX_SECURITY_EFFORT"

      # Validate the repository, target, output directory, and Codex
      # configuration without loading credentials or starting Codex.
      "$CODEX_SECURITY_BIN" scan . "$@" --dry-run

      set +e
      OPENAI_API_KEY="$CODEX_SECURITY_API_KEY" \
      CODEX_SECURITY_STATE_DIR="$STATE_DIR" \
        "$CODEX_SECURITY_BIN" scan . "$@" > "$JSON_FILE"
      scan_exit="$?"
      set -e

      unset OPENAI_API_KEY CODEX_API_KEY CODEX_ACCESS_TOKEN CODEX_SECURITY_API_KEY

      cp -R "$RESULTS_DIR"/. "$ARTIFACT_DIR/results/"
      test ! -s "$JSON_FILE" || cp "$JSON_FILE" "$ARTIFACT_DIR/codex-security.json"

      final_exit="$scan_exit"
      if test -s "$RESULTS_DIR/scan-manifest.json"; then
        set +e
        "$CODEX_SECURITY_BIN" export "$RESULTS_DIR" \
          --export-format sarif \
          --source-root "$CI_PROJECT_DIR" \
          --output "$SARIF_FILE"
        export_exit="$?"
        set -e

        if test "$export_exit" -ne 0 && test "$final_exit" -eq 0; then
          final_exit=2
        fi
      elif test "$final_exit" -eq 0; then
        echo "The scan completed without a sealed manifest." >&2
        final_exit=2
      fi

      exit "$final_exit"
  artifacts:
    when: always
    access: maintainer
    expire_in: 7 days
    paths:
      - codex-security-artifacts/
    reports:
      sarif: codex-security-artifacts/results.sarif
```

## Step 4: Run and verify the first pipeline

Confirm that GitLab selects the intended profile, the runner can start the Codex sandbox, the scan produces canonical artifacts, and the job returns the correct scan or export status.

Create an eligible merge request between protected branches in the same project and inspect the `codex-security` job log. Confirm that it reports the `diff` target and the configured effort. Then inspect the `codex-security-artifacts` artifact and verify that a completed scan contains:

- `scan-manifest.json`
- `findings.json`
- `coverage.json`
- `report.md`
- `codex-security.json`
- `results.sarif` when export succeeded

The pipeline checks that the required GitLab variable is present and runs [`--dry-run`](https://learn.chatgpt.com/docs/security/cli/reference) before starting a paid scan. The dry run does not load credentials, and `OPENAI_API_KEY` is scoped to the paid scan process. If the namespace preflight fails, no canonical scan artifacts are expected; fix the runner before retrying. For other preflight failures, fix the repository target, output directory, or CLI configuration. The integration is verified when the merge request pipeline completes a committed-diff scan, retains its structured evidence, publishes available SARIF, and returns the scan or export status directly. A green job without these artifacts is not sufficient evidence of a working security integration.

## Step 5: Optimize cost in the right order

Reduce unnecessary scan spend without removing the coverage needed for the pipeline's security decision.

Cost optimization should preserve the security question the pipeline needs to answer. Apply the controls in this order:

### 1. Remove unnecessary pipeline executions

Integrate the required conditions into the project's existing [`workflow: rules`](https://docs.gitlab.com/ci/yaml/workflow/) when duplicate branch and merge request pipelines are possible. Skip fork and unprotected merge requests that cannot receive the protected API key. In monorepos, use [`rules:changes`](https://docs.gitlab.com/ci/yaml/#ruleschanges) to avoid starting a service-specific scan when that service did not change.

This is often the cleanest cost reduction because it removes scans that provide no new decision value.

### 2. Choose the smallest valid target

Use a committed diff for merge request feedback. Use repeated `--path` arguments for independently owned monorepo services. Retain a periodic full scan because a diff scan does not establish repository-wide coverage.

### 3. Use standard mode for routine scans

Start with standard mode for full repository and path scans. Run deep mode on a schedule, manually, or for specifically identified high-risk components.

There is no documented `--fast` mode. Faster configurations come from target selection, effort, model selection, and cadence.

### 4. Tune reasoning effort with evidence

Run the same representative change set at two effort levels. Compare:

- Estimated cost and token usage.
- Runtime.
- Findings and severity.
- Coverage completeness.
- Deferred surfaces and open questions.
- Reviewer assessment of finding quality.

Lower effort only where the quality remains sufficient for the intended decision.

### 5. Evaluate model choice separately

`--model` is another quality, latency, and cost control. Compare supported models against the same repository revision, target, and effort. Consult current model pricing before drawing cost conclusions, and avoid changing model and effort in the same experiment.

### 6. Measure before changing organization-wide defaults

During calibration, add `--verbose`, retain the completion summary, and record:

- Repository revision, scan target, and mode.
- Model and effort.
- Changed files or selected paths.
- Estimated cost, token usage, and duration.
- Coverage completeness and deferred work.
- Finding count and reviewer disposition.

For custom orchestration, the [Codex Security TypeScript SDK](https://learn.chatgpt.com/docs/security/sdk) provides `maxCostUsd`, an `onCost` callback, and a final estimated cost. The CLI is sufficient for the GitLab integration in this cookbook, while the SDK is useful for central dashboards or cross-repository budget enforcement.

The optimization is complete when each profile has a target, cadence, effort level, and model choice that reflect its security purpose, while periodic full scans remain in place. Always measure cost alongside coverage and finding quality so that a cheaper configuration does not silently weaken the control.

## Step 6: Verify SARIF ingestion in GitLab

Step 3 already exports the sealed scan, retains `results.sarif`, and declares it as a GitLab report artifact. This step confirms that GitLab accepted the report and mapped its findings into the security workflow.

[GitLab Ultimate 19.2 or later](https://docs.gitlab.com/user/application_security/detect/sarif/) can display supported SARIF 2.1.0 findings in the pipeline Security tab, merge request security widget, project vulnerability report, and security dashboard. After the pipeline completes:

1. Open the pipeline Security tab and check for ingestion warnings.
2. Confirm that each finding has the expected scanner name, severity, file location, and identifier.
3. Open the project vulnerability report and verify that the findings are available for triage.
4. Download `results.sarif` from the job artifacts and retain it for debugging and audit evidence.

![GitLab vulnerability report populated with Codex Security SARIF findings](../../images/gitlab-vulnerability-report-pipeline-21.png)

*An earlier scan imported by pipeline `#21` populated the demo project's vulnerability report with 14 Codex Security findings: 2 high, 8 medium, and 4 low. This observed demo result is illustrative; finding counts vary by repository and scan profile.*

GitLab skips findings that do not contain `ruleId` or `physicalLocation`. If severity or report type is incorrect, inspect the SARIF mapping before changing the scan: preserve numeric severity information, stable identifiers, locations, and CWE tags. The integration is verified when GitLab displays the expected supported findings without ingestion errors and users can still download the retained SARIF artifact.

## Step 7: Apply coverage and severity policy

Distinguish a completed clean scan, a severity-policy failure, incomplete coverage, and an infrastructure or export problem before deciding whether the pipeline should block.

Interpret the [Security CLI exit codes](https://learn.chatgpt.com/docs/security/cli/reference) as follows:

| Exit code | Meaning | Suggested treatment |
| --- | --- | --- |
| `0` | Complete coverage and configured severity policy passed | Pass |
| `1` | Completed scan found an issue at or above the configured threshold | Block when severity policy is enabled |
| `2` | Input, runtime, export, configuration, or incomplete-coverage outcome | Inspect artifacts and logs; advisory only during calibration |
| `130` | Interrupted with Ctrl-C | Retry or investigate cancellation |
| `143` | Terminated with SIGTERM | Check timeout, cancellation, or runner shutdown |

Exit `2` does not always mean that no results exist. A scan can produce findings and sealed artifacts while reporting partial coverage. Inspect `coverage.json`, deferred surfaces, open questions, and the job log before deciding how to handle it.

Roll out the policy in three stages:

1. **Integration validation:** Confirm that the secret is configured, run `--dry-run`, validate runner behavior, and confirm artifact and SARIF publication.
2. **Advisory calibration:** Run representative diff and full scans, measure cost and quality, and allow exit `2` while investigating incomplete coverage.
3. **Policy enforcement:** Add `--fail-on-severity`, choose blocking coverage behavior, and document exceptions and ownership.

Do not introduce a blocking severity threshold before the team has reviewed representative findings, false-positive handling, scan duration, cost, and coverage behavior. Begin in report-only calibration mode, then add an explicit severity threshold and coverage policy once normal results are understood. Findings and coverage answer different questions: exit `1` represents a configured finding threshold, while exit `2` can represent incomplete evidence or a technical problem.

## Step 8: Tune the available Security CLI settings

The working pipeline already sets authentication, target selection, effort, output paths, and structured output. Most teams only need the following controls when adapting it for production. Use the complete [Security CLI option reference](https://learn.chatgpt.com/docs/security/cli/reference) for specialized runtime and output settings.

### Controls most GitLab teams need

| Setting | Use it for | Guidance |
| --- | --- | --- |
| `--diff BASE --head HEAD` | Eligible protected merge request scans | Pin both revisions to the committed change GitLab is reviewing |
| `--path PATH` | Independently owned monorepo services | Repeat for related paths and retain enough context for a complete review |
| `--mode standard` or `--mode deep` | Routine scans or scheduled high-risk reviews | Start with standard; reserve deep mode for repository or path scans |
| `--effort LEVEL` | Quality, latency, and cost calibration | Compare effort levels on the same revision and target |
| `--model MODEL` | Model-specific quality, latency, and cost evaluation | Change model separately from effort and consult current pricing |
| `--knowledge-base PATH` | Architecture, threat-model, or security-policy context | Include only relevant, maintained material because it expands context |
| `--max-cost USD` | Per-profile estimated-cost guardrail | Tune from observed runs; it is an estimate, not a hard billing cap |
| `--fail-on-severity LEVEL` | Blocking on `critical`, `high`, `medium`, or `low` findings | Enable only after representative findings and false positives are understood |

`--path` and `--diff` select different scan targets and should not be combined. Deep mode supports repository and path scans, not diff scans. Severity policy changes the pipeline decision but does not reduce scan cost.

Change one control at a time and compare runtime, estimated cost, coverage, findings, and reviewer usefulness. Keep `--dry-run` in CI, add `--verbose` during calibration, and restrict access to result directories because they can contain source excerpts and vulnerability details. Refer to the full option reference for custom Python interpreters, plugin overrides, output formats, and isolated Codex configuration.

## Step 9: Troubleshoot the integration

Identify whether a failed or inconclusive job comes from Git history, the runner sandbox, credentials, cost limits, coverage, export, or GitLab ingestion.

| Symptom | Check |
| --- | --- |
| Unknown base or unexpected MR diff | Fetch full history, verify both SHAs, and calculate the merge base explicitly |
| `bwrap: No permissions to create a new namespace` | Verify runner user-namespace and sandbox policy |
| Exit `2` with artifacts present | Inspect the completion summary, coverage details, deferred work, and open questions |
| Exit `2` without canonical artifacts | Inspect credentials, runtime, output directory, and sandbox setup |
| Scan exceeds the expected cost | Confirm profile, target, effort, model, change size, knowledge base, and duplicate pipelines |
| Cost limit is hit on most runs | Recalibrate the limit or narrow scope; do not treat partial results as clean coverage |
| SARIF export fails | Confirm a completed, sealed manifest exists |
| GitLab does not show findings | Confirm GitLab tier/version, valid SARIF 2.1.0, `artifacts:reports:sarif`, and report limits |

### Fix user-namespace failures on Docker executors

Runner configuration is environment-specific and therefore is not part of the portable `.gitlab-ci.yml`. For the Docker executor used to validate this example, the default seccomp profile blocked the user namespace required by the Codex Linux sandbox. The following last-resort runner setting allowed the namespace while keeping privileged mode disabled:

```toml
[runners.docker]
  security_opt = ["seccomp=unconfined"]
  privileged = false
```

`seccomp=unconfined` disables Docker's default seccomp profile, so do not treat it as a least-privilege configuration. First prefer a tailored seccomp profile that permits the required user-namespace operation. If `unconfined` is the only available workaround, apply it only to a dedicated trusted runner, keep privileged mode disabled, and prevent unrelated or untrusted jobs from using that runner. Restart only the affected runner and confirm that `unshare -Ur true` succeeds before retrying the scan.

Start with the presence or absence of canonical artifacts, then inspect coverage and the job's exit code. This separates jobs that never produced a scan from completed but inconclusive scans and avoids applying the wrong remediation to the same non-zero exit code.

## Conclusion

A useful GitLab integration connects four decisions:

- Scope and cadence determine what is scanned and how often cost is incurred.
- Mode, model, and effort balance analysis quality, latency, and estimated cost.
- Coverage, severity policy, and exit codes determine whether the result can support a security decision.
- SARIF places supported findings in GitLab's existing review and vulnerability-management workflow.

Begin with a correct, report-only integration. Measure representative scans. Then tune cost and introduce blocking policy using evidence rather than assumptions.

## Next steps for production rollout

Use the working pipeline as a baseline, then complete these steps in the target GitLab project:

1. Validate one eligible merge request between protected branches end to end. Confirm that the protected variable is available, the intended base and head revisions are selected, coverage is complete, `scan-manifest.json` is sealed, SARIF ingestion succeeds, and the artifact directory is complete. Resolve authentication, sandbox, target-sealing, coverage, and export-related exit `2` outcomes before enforcement; do not rely on `allow_failure` to hide incomplete results.
2. Calibrate all three profiles with representative changes. Run focused merge requests with `low` effort, a default-branch repository scan with `high` effort, and a scheduled deep scan with `xhigh` effort. Record duration, estimated cost, coverage, findings, and reviewer disposition.
3. Choose and enforce the production policy. Keep merge-request scans focused, reserve broader scans for the default branch or a schedule, and enable `--fail-on-severity` only after reviewers understand result quality and false positives. When the pipeline is stable, remove the temporary exit `2` allowance, apply the project's chosen trust controls to the job and API-key variable, and require the result in the merge policy.
4. Assign operational ownership. Name the team that reviews findings, define who investigates coverage or export failures, set response expectations for critical and high findings, and document the exception process and approvers.
5. Maintain the integration. Review the installed CLI version, supported models, pricing assumptions, GitLab SARIF support, runner image, and artifact retention regularly. When the resolved CLI version changes, rerun a known merge request and verify sealed artifacts, SARIF ingestion, exit-code behavior, runtime, and cost before broader rollout.

At that point, the integration has an owner, a tested operating model, measurable cost, and an explicit enforcement policy instead of being only a working CI example.
