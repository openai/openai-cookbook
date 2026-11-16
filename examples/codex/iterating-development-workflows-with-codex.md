# Iterating development workflows with Codex

## Introduction

While the vast capabilities Codex offers can be empowering, it can be difficult to know where to start integrating it into your workflows. This recipe shows a practical approach to incorporating Codex while making iterative improvements to continuously leverage its abilities more effectively.

The `AGENTS.md` file is optional but recognized by Codex. The other files in this recipe are recommended workflow conventions, not files Codex requires. Adapt the structure to fit your project.

Below is the completed structure based on the design of a simple to-do list application. Files in the `context/` directory are generated during each phase of development and contain phase-specific context records.

<details>
<summary><strong>Example Directory Structure</strong></summary>

``` text
.
├── .gitignore
├── AGENTS.md
├── GOALS.md
├── PLANS.md
├── PROMPTS.md
├── README.md
└── harness
    ├── build
    │   ├── phase-00-repository-foundation.md
    │   ├── phase-01-create-list.md
    │   ├── phase-02-update-complete-delete.md
    │   └── phase-03-demo-verification.md
    ├── build-log.md
    ├── code_review
    │   └── .gitkeep
    └── context
        └── README.md

4 directories, 13 files
```
</details>

## Create harness and build phase files

### Agents and plans

For new projects, the best place to start is by populating the [`AGENTS.md`](https://learn.chatgpt.com/docs/agent-configuration/agents-md) file. When present, Codex reads this file as persistent repository guidance before performing work. It is an optional convention for work that benefits from durable execution. In general, agents files should contain items like:

- The goal of the repository and a high-level summary
- Coding conventions
- Testing standards
- Relevant context files
- Project-specific behaviors
- Scopes and boundaries

The `/init` command in Codex can generate the file and will attempt to populate it based on the context it gathers from the directory contents.

> **💡 Tip: Tracking Institutional Knowledge**
>
> The agents file is a great place to store institutional knowledge from your team.

For plan execution, creating a [`PLANS.md`](https://developers.openai.com/cookbook/articles/codex_exec_plans#plansmd) file as a source of truth is considered a useful, optional convention. In addition to the purpose of the plan, this file should also contain a project roadmap. While these are not properties required by Codex, they can then be used to generate files for each individual build phase.

> **💡 Tip: Build File Sizes**
>
> For teams that prefer longer running tasks, the `PLANS.md` file can be larger
> and contain extensive details on material decisions and acceptance criteria.
>
> Creating smaller build files not only improves readability but supports
> human gating to manually review code quality and other outputs.

### Harness files

In addition to the agents and plans files, it is also possible to create individual files to specify the desired outcomes, success conditions and boundaries (`GOALS.md`) and for the instructions to initiate planned work (`PROMPTS.md`). These can be either manually written or derived from the agents and plans file using a prompt like the one below:

<details>
<summary><strong>Generate <code>GOALS.md</code> and <code>PROMPTS.md</code></strong></summary>


```text
Read the applicable `AGENTS.md` files for this repository, starting at the
repository root and including any instructions that apply to the current
directory. If `PLANS.md` exists, read it as well.

Using those sources, create or conservatively update only these files:

- `GOALS.md`
- `PROMPTS.md`

Before writing, briefly summarize:

1. The source files you found
2. The project outcomes and constraints you inferred
3. Any assumptions caused by missing or ambiguous information

Use the following ownership boundaries:

## `GOALS.md`

Document what the project is trying to achieve. Include:

- Project purpose
- Desired outcomes
- Success conditions
- Scope
- Non-goals
- Technical and operational constraints
- Security, reliability, and recovery expectations when supported by the sources
- Known unknowns or decisions that still require human input

Keep goals outcome-oriented. Do not copy implementation procedures, reusable
prompts, or progress updates into this file. Do not claim capabilities,
deadlines, guarantees, or requirements that are not supported by the source
material.

## `PROMPTS.md`

Provide reusable prompts for initiating and advancing the planned work. Include:

- A repository-orientation prompt
- A planning or phase-preparation prompt
- A prompt for executing one approved phase
- A verification and evidence-gathering prompt
- A review or remediation prompt
- A phase-completion and handoff prompt

Each prompt should:

- Tell Codex which repository files to read
- Reference the relevant goal or plan instead of duplicating it
- Define the immediate scope and explicit non-goals
- Require a read-only preflight before implementation
- Require an approval summary before repository writes
- Use red, green, refactor, and verification where appropriate
- Require observed test and validation evidence
- Keep commits, pushes, deployments, credentials, and external writes behind
  separate explicit approval
- Stop after the selected phase rather than beginning the next one automatically

If `PLANS.md` does not exist:

- Derive only high-level goals supported by `AGENTS.md`
- Do not invent a roadmap, phases, architecture, or product requirements
- Use clearly marked placeholders where planning input is required
- Make the prompts request an explicit plan or phase before implementation

Preserve existing repository terminology and filename capitalization. Keep both
documents concise and avoid repeating information already owned by
`AGENTS.md` or `PLANS.md`.

Do not modify application code, tests, dependencies, configuration, existing
planning files, or any other files.

After writing:

1. Review both files for contradictions and duplicated ownership
2. Confirm that every substantive claim is grounded in `AGENTS.md` or
   `PLANS.md`, or is clearly labeled as an assumption
3. Run `git diff --check`
4. Report the files changed, assumptions made, and any unresolved questions
```
</details>

### Build phase files

Once the files the harness will use for context have been generated, the next step is to break down the stages of each build into individual files to identify:

- The purpose of each step
- Any files needed for additional context
- Acceptance criteria
- Boundaries

For discoverability, it is recommended to keep these files in a manually created `harness/build/` folder in the root project directory, typically in the format `<phase-number>-<phase-title>.md`. The corresponding file, along with the prompt and goal from the harness context files can then be provided to Codex at the beginning of each phase. This helps prevent agent drift and creates a clear, human-gated development history that, when combined with version control, creates an easy-to-read audit trail for future use including debugging.

<details>
<summary><strong>Generate Build Phase Files</strong></summary>

```
Perform a read-only discovery pass of this repository.

Read the applicable repository instructions and planning sources, including:

- `AGENTS.md`
- `PLANS.md`, if present
- `GOALS.md`, if present
- `PROMPTS.md`, if present
- `harness/build-log.md`, if present
- Existing files under `harness/build/`
- Relevant application manifests, tests, and verification commands

Use the live repository as the source of truth. Do not rely on assumptions from
other projects.

Your task is to create the planned phase files under `harness/build/`.

## Before writing

Identify:

1. The source files you found
2. The repository’s purpose and current state
3. The planned phases and their dependencies
4. The exact build files you propose creating
5. Any missing, ambiguous, or contradictory requirements
6. The acceptance criteria for this planning task

If the source files do not establish a clear phase sequence, stop and propose a
phase breakdown for human review. Do not invent and write a roadmap without
approval.

Before creating files, present the proposed scope and exact paths and wait for
explicit confirmation.

## Build-file ownership

Each build file describes one bounded implementation phase. It is a plan, not
evidence that the work has already been completed.

Use the phase numbers, names, ordering, and terminology established by the
repository. Follow an existing build-file template when one is present.

Each phase file should contain:

- Phase number and descriptive title
- Status, initially `Not started`
- Source inputs
- Objective
- In-scope work
- Explicit non-goals
- Dependencies and prerequisites
- Expected files or components affected
- Decisions requiring human input
- Approval gate
- Red, green, refactor, and verification plan
- Focused and broader verification commands
- Security, privacy, reliability, observability, and recovery considerations
  when relevant to the phase
- Acceptance criteria
- Evidence that must be recorded before the phase can be considered complete
- Handoff or stop condition

## Planning requirements

For every phase:

1. Keep the scope small enough to implement and verify independently.
2. Preserve dependency order and do not move later work into earlier phases.
3. Define observable acceptance criteria rather than subjective completion
   statements.
4. Include the smallest meaningful failing test or check for the red step.
5. Describe the minimum implementation needed for the green step.
6. Allow refactoring only when it preserves the approved behavior and scope.
7. Name the actual verification commands when they can be established from the
   repository.
8. Mark unknown commands or requirements as unresolved instead of inventing
   them.
9. Identify credentials, external systems, infrastructure changes, deployments,
   commits, and pushes that require separate authorization.
10. Do not claim that tests, recovery procedures, or integrations have passed
    unless they have actually been run during a separately approved
    implementation phase.

## Scope restrictions

Create or update only the explicitly approved files under:

`harness/build/`

Do not create or modify:

- Application code
- Tests
- Dependencies
- Package manifests
- Infrastructure or deployment configuration
- `AGENTS.md`
- `PLANS.md`
- `GOALS.md`
- `PROMPTS.md`
- Context files
- Execution or build logs
- Code-review artifacts
- README files
- Git branches, commits, or remote state

Do not begin implementing any phase.

If a proposed build file already exists, inspect it and describe the intended
changes before modifying it. Preserve useful existing content and do not
overwrite recorded decisions or evidence.

## After writing

1. Confirm that only approved `harness/build/` files changed.
2. Check that every phase traces back to the repository’s source documents.
3. Check for duplicated, missing, or incorrectly ordered scope.
4. Confirm that every phase includes an approval gate, acceptance criteria, and
   verification plan.
5. Run `git diff --check`.
6. Report:
   - Files created or updated
   - Phase sequence
   - Validation performed
   - Assumptions and unresolved questions
   - The approval needed before beginning the first phase
```
</details>

## Context files

In addition to development framework files, capture the session-specific decisions made during each phase that materially affect the project.

Adding a prompt like the one below to `AGENTS.md` instructs Codex to capture relevant context for later reuse. Store phase context as `harness/context/phase-<NN>-<phase-slug>-context.md`.

<details>
<summary><strong>Capture Build Phase Context using <code>AGENTS.md</code></strong></summary>

``` text
## Phase context requirements

For each approved implementation phase, maintain one phase-specific context file:

`harness/context/phase-<NN>-<phase-slug>-context.md`

Create the context file only when the phase begins and after any required
approval. Read the applicable repository instructions, goal, prompt, build
file, prior context, and build-log evidence before recording
new context.

### Materiality test

Record information only when omitting it could reasonably:

- Change the approved scope or implementation approach
- Cause a future phase to repeat discovery or make a different decision
- Affect an interface, dependency, invariant, or ownership boundary
- Change acceptance criteria or the required verification
- Affect security, privacy, reliability, observability, rollback, or recovery
- Hide a blocker, unresolved assumption, accepted limitation, or required
  follow-up

If the information would not affect future work, verification, operations, or
decision-making, do not add it to the context file.

### Capture

Record material:

- User decisions and clarifications
- Scope changes and explicit non-goals
- Assumptions that influenced implementation
- Architectural or implementation decisions and their rationale
- Relevant component, interface, dependency, and ownership boundaries
- Existing behavior or invariants that must be preserved
- Security, privacy, operational, and recovery constraints
- Verification limitations or unavailable evidence
- Blockers and unresolved questions
- Findings that must inform a later phase
- Superseded decisions, including what replaced them and why

For each entry, include enough provenance to recover the reasoning. Reference
the relevant file, command, test result, issue, review finding, or user decision
when available.

### Do not capture

Do not use context files as transcripts, scratchpads, or progress logs. Exclude:

- Routine command output
- Step-by-step narration
- Temporary dead ends that had no lasting effect
- Facts already owned by another canonical file
- Full copies of plans, prompts, test output, or source code
- Routine progress or completion status
- Speculation presented as fact
- Credentials, tokens, secrets, or sensitive values

Link to canonical sources instead of duplicating their contents.

### Source-of-truth boundaries

- The phase build file owns approved scope, non-goals, acceptance criteria, and
  the planned verification.
- The phase context file owns material discoveries, decisions, constraints, and
  unresolved matters needed by future work.
- `harness/build-log.md` owns implementation progress and observed verification
  evidence.
- Code-review artifacts own review findings and sign-off status.

Do not copy information between these files unless a short summary is necessary
to explain a material decision.

### Update and handoff

Update the context file when a material decision or discovery occurs and review
it before closing the phase. Before handoff:

1. Remove non-material narration and duplicated information.
2. Confirm that material decisions include their rationale and provenance.
3. Mark assumptions and unresolved questions explicitly.
4. Confirm that evidence is linked rather than claimed without support.
5. Record downstream implications for later phases.
6. Do not mark the phase complete solely because the context file is complete.
```
</details>

## Build log

A file named `harness/build-log.md` acts as the source of truth for project progress. While human-readable, it is primarily intended for Codex consumption and can also be used to generate user-facing changelogs and other documentation.

A prompt like the following can be added to the agents file to ensure the build log is updated consistently after each phase is completed.

<details>
<summary><strong>Tracking Progress using <code>build-log.md</code></strong></summary>

``` text

# Build Log Instructions
At the end of each phase, prior to committing work, your task is to create or update only:

`harness/build-log.md`

The build log is the source of truth for observed implementation progress and
verification evidence. It must describe what actually happened, not what the
plan predicts will happen.

## Before writing

Summarize:

1. The selected phase
2. Its current recorded status
3. The sources and evidence you inspected
4. The log entries or status changes you propose
5. Any conflicting, missing, or unverified information

Wait for explicit confirmation before creating or updating the build log when
repository instructions require approval for documentation writes.

## Initialize the log

If `harness/build-log.md` does not exist, create it with:

1. A short statement of purpose
2. A phase summary table
3. An append-only activity section

Build the phase summary table from the approved files under `harness/build/`.
Initialize phases as `Not started` unless repository evidence supports another
status.

Use only these statuses unless the repository defines its own:

- `Not started`
- `In progress`
- `Blocked`
- `Complete`

Do not infer completion from the existence of code, a passing focused test, or
a prior conversation.

## Phase summary

Maintain a concise summary table containing:

| Phase | Status | Branch | Started | Completed | Evidence | Blockers |
|---|---|---|---|---|---|---|

The table is a current summary. Detailed history belongs in append-only activity
entries.

Only mark a phase `Complete` when:

- Its approved acceptance criteria are satisfied
- Required tests and verification have actually run and passed
- Required review findings are resolved or explicitly accepted
- Operational, security, recovery, and cleanup requirements are satisfied when
  applicable
- Remaining limitations are recorded
- Repository-specific completion requirements are met

If any required condition lacks evidence, keep the phase `In progress` or
`Blocked`.

## Append-only activity entries

Append an entry whenever a material phase event occurs, including:

- Phase authorization
- Work beginning
- A red test or check producing the expected failure
- The focused check passing after implementation
- A material refactor or an explicit decision not to refactor
- Broader verification
- A material scope change
- A blocker
- A review finding or remediation
- Acceptance or rejection of a limitation
- Phase completion

Use this structure:

## <timestamp> — Phase <NN>: <event>

- **Status:** `<previous status>` → `<new status>`
- **Branch:** `<observed branch>`
- **Authorized scope:** Brief summary or link to the phase build file
- **Changes:** Material files, components, or behavior changed
- **Red:** Exact check and observed expected failure, or `Not applicable` with
  justification
- **Green:** Exact focused check and observed result
- **Refactor:** Material refactor and repeated checks, or the reason no
  refactor was needed
- **Verification:** Exact commands or procedures actually run and their results
- **Review:** Findings, remediation, and sign-off state when required
- **Operational evidence:** Relevant security, observability, rollback,
  recovery, or cleanup evidence
- **Limitations:** Untested areas, accepted risks, or incomplete evidence
- **Blockers:** Current blockers or `None`
- **Next action:** The next approved action; do not authorize it implicitly
- **Evidence references:** Paths to context files, review artifacts, logs,
  commits, or other durable evidence

Use an unambiguous timestamp including the timezone.

## Evidence requirements

- Record exact commands and concise pass/fail results.
- Distinguish observed evidence from reported or historical evidence.
- Never claim that a test, integration, recovery procedure, or external check
  passed unless it was actually run and the result was observed.
- Never convert planned commands from a build file into passing evidence.
- Record skipped and unavailable checks explicitly, including the reason.
- Link to large outputs or artifacts instead of copying them into the log.
- Do not include credentials, tokens, secrets, sensitive values, or unnecessary
  personal information.
- Do not copy full context files, build plans, code diffs, or command output
  into the build log.
- If evidence conflicts, preserve both observations and mark the phase
  `Blocked` until the conflict is resolved.

## History and corrections

Treat activity entries as append-only.

Do not silently rewrite prior evidence or remove failed attempts. If an earlier
entry is incorrect:

1. Append a correction
2. Identify the entry being corrected
3. Explain what changed
4. Update the summary table to reflect the current supported state

Routine typo fixes that do not change meaning may be corrected in place.

## Source-of-truth boundaries

- `PLANS.md` owns the planned phase sequence.
- `harness/build/<phase>.md` owns phase scope, non-goals, acceptance criteria,
  and planned verification.
- `harness/context/` owns material discoveries, decisions, constraints, and
  unresolved questions.
- `harness/build-log.md` owns observed progress and verification evidence.
- Review artifacts own detailed findings and sign-off.

Reference those sources instead of duplicating them.

## Scope restrictions

Do not:

- Implement or modify application code
- Modify tests or configuration
- Create phase context
- Change build files or the execution plan
- Change Git branches
- Commit or push
- Start the next phase
- Mark a phase complete without sufficient evidence

If the evidence indicates that another file needs an update, report it as a
follow-up rather than modifying it.

## After writing

1. Confirm that the logging task changed only `harness/build-log.md` and
   preserved any pre-existing phase implementation, test, or other worktree
   changes.
2. Confirm that every status transition has supporting evidence.
3. Confirm that planned work is not represented as completed work.
4. Confirm that failures, skipped checks, and limitations remain visible.
5. Run `git diff --check`.
6. Report:
   - The phase and status recorded
   - The entries appended
   - The evidence used
   - Remaining blockers or limitations
   - Any separate approval required for the next action
```
</details>

## Automate with skills

Given the size of each prompt and the number of files involved, it should seem obvious that such a manual process would become unwieldy, error-prone and unpredictable. To make such work reusable and more consistent, Codex provides [skills](https://learn.chatgpt.com/docs/build-skills) as a way of creating workflows that can be reused for projects of any scale.

Use the [Skill Creator skill](https://github.com/openai/skills/blob/main/skills/.system/skill-creator/SKILL.md) with the prompt below to create a reusable harness-authoring skill.

<details>
<summary><strong>Create the <code>$harness-author</code> Skill</strong></summary>

``` text
Use `$skill-creator` to create a reusable Codex skill named `harness-author`.

The skill should help Codex create, review, and improve a right-sized
repository engineering harness without beginning implementation unless the
user explicitly requests and separately approves it.

## Destination

Before writing, determine where the skill should be installed.

Default to:

`${CODEX_HOME:-$HOME/.codex}/skills/harness-author`

If the destination is ambiguous or an existing `harness-author` skill is
present, report the exact path and ask whether to update it or choose another
name. Do not overwrite an existing skill without explicit approval.

## Read-only discovery

Before creating the skill:

1. Read the applicable repository `AGENTS.md` files.
2. Inspect existing harness examples and conventions in the current repository.
3. Read `PLANS.md`, `GOALS.md`, and `PROMPTS.md` when present.
4. Inspect existing `harness/` files without modifying them.
5. Identify concrete requests that should and should not trigger the skill.
6. Determine which behavior belongs in `SKILL.md`, reference files, scripts,
   and tests.
7. Read the `$skill-creator` instructions and required references completely.

Do not infer that one repository’s harness structure is mandatory for every
project.

## Before writing

Present:

- The proposed skill path
- The triggering description
- The files and resources to be created
- The behavioral scope
- Explicit non-goals
- The validator and test plan
- The acceptance criteria

Wait for confirmation before creating or modifying the skill.

## Triggering behavior

The skill should trigger when a user asks Codex to:

- Create or review a repository engineering harness
- Create durable repository instructions
- Convert goals or plans into phased build files
- Define acceptance criteria and approval gates
- Create or streamline execution and build logs
- Establish test-driven phase plans
- Separate planning, implementation, context, and evidence
- Improve an existing harness after observing workflow failures

The description should also make clear that requests containing terms such as
“harness-only,” “planning-only,” “just the build files,” or “only these files”
must not authorize application implementation.

## Core behavior

The skill must instruct Codex to:

1. Read applicable repository instructions and inspect the live repository
   before designing the harness.
2. Identify the authoritative source for goals, plans, implementation
   contracts, phase status, context, review findings, and verification evidence.
3. Classify the repository shape and change risk.
4. Recommend the smallest useful harness for that repository.
5. Preserve existing architecture, naming, ownership, and operational
   safeguards.
6. Freeze the exact user-approved artifact list before writing.
7. Present scope, affected files, tests, acceptance criteria, risks, and
   approval gates before repository changes.
8. Keep planning and implementation as separately authorized activities.
9. Use red, green, refactor, and verification checkpoints in implementation
   plans when appropriate.
10. Define observable acceptance criteria and evidence requirements.
11. Record unknowns as unresolved rather than inventing requirements or proof.
12. Avoid duplicating facts across multiple harness files.
13. Preserve existing application files.
14. Require separate approval for credentials, external systems,
    infrastructure, branch changes, commits, pushes, and deployments.

## Artifact ownership

Teach the skill to distinguish these possible artifacts:

- `AGENTS.md`: durable repository instructions and working agreements
- `PLANS.md`: roadmap and planned phase sequence
- `GOALS.md`: outcomes, success conditions, scope, and non-goals
- `PROMPTS.md`: reusable workflow entry points
- `harness/build/<phase>.md`: approved scope and plan for one phase
- `harness/context/<phase>.md`: material discoveries, decisions, constraints,
  and unresolved questions for one phase
- `harness/build-log.md`: observed progress and verification evidence
- `harness/code_review/`: detailed review findings when required

These are optional conventions, not files Codex requires automatically. The
skill must extend existing repository conventions instead of creating every
artifact by default.

## Planning-only boundary

When the user requests only planning or harness artifacts:

- Create only the explicitly approved files.
- Do not create application code.
- Do not create tests for the application.
- Do not add dependencies or manifests.
- Do not create Docker, infrastructure, or deployment files.
- Do not create README files or review artifacts unless explicitly approved.
- Do not create phase context files before the corresponding phase begins
  unless the user explicitly requests them.
- Do not change Git state, commit, push, or access external systems.
- Describe future implementation and tests inside the plans only.
- Stop after validating and reporting the harness artifacts.

## Right-sizing

The skill should adapt its recommendations:

- For a minimal project, prefer existing documentation, tests, and a concise
  acceptance checklist.
- For an application, add phased planning and recovery guidance only when
  useful.
- For multiple services, capture ownership, contracts, dependency boundaries,
  degraded behavior, and integration verification.
- For a monorepo, combine root guidance with only the applicable package-level
  instructions.
- For high-risk changes, include security, authorization, rollback, recovery,
  failure modes, and independent verification regardless of repository size.

Do not impose enterprise process, mandatory reviewers, or extra documents when
the repository and risk do not justify them.

## Skill structure

Use `$skill-creator`’s initialization script rather than manually creating the
skill skeleton.

Create only resources that materially support the workflow. The likely
structure is:

harness-author/
├── SKILL.md
├── agents/
│   └── openai.yaml
├── references/
│   ├── project-profiles-and-templates.md
│   ├── source-of-truth-and-templates.md
│   ├── tdd-and-verification.md
│   └── reliability-and-tradeoffs.md
└── scripts/
    ├── validate_harness.py
    └── test_validate_harness.py

Do not create a README, changelog, installation guide, or other auxiliary
documentation.

Keep `SKILL.md` concise and procedural. Move detailed templates, matrices, and
examples into the directly linked reference files. Avoid duplicating content
between `SKILL.md` and its references.

Generate `agents/openai.yaml` using the `$skill-creator` tooling. Read the
required `openai.yaml` reference before generating:

- `display_name`
- `short_description`
- `default_prompt`

Do not add optional branding fields unless the user supplies them.

## Deterministic validator

Create a standard-library validator that can inspect a repository and validate
a proposed harness without modifying files or printing source contents.

It should support:

- Repository and optional target paths
- Project-shape and risk assessment
- A `harness-only` intent
- Repeated proposed-path arguments
- Repeated explicitly allowed-path arguments
- JSON output
- Strict mode for blocking findings

It should reject:

- Absolute paths
- Path traversal
- Proposed application scaffolding during harness-only requests
- Files outside the approved artifact set
- Context, review, or implementation artifacts that were not explicitly
  approved
- Missing approval, acceptance, or verification sections when required
- Claims of completed verification without evidence

Keep the validator advisory for repositories that do not use this harness
structure. It must not make network calls, access credentials, change Git
state, or modify repository files.

## Tests

Write and run tests for at least these cases:

1. A valid minimal harness-only request
2. An explicitly approved custom Markdown artifact
3. Rejection of application code during a planning-only request
4. Rejection of dependencies, manifests, Docker, and infrastructure files
5. Rejection of unapproved context and review artifacts
6. Safe normalization of relative paths
7. Rejection of absolute paths and traversal
8. Preservation of exact filename capitalization
9. A small repository that should not receive an oversized harness
10. A high-risk project that requires security and recovery coverage
11. JSON output and strict-mode behavior
12. An existing repository whose conventions should be preserved

Run added scripts and tests directly and report their observed results.

## Validation

After implementation:

1. Run the validator’s test suite.
2. Run `$skill-creator`’s `quick_validate.py` on the completed skill.
3. Confirm the YAML frontmatter contains only `name` and `description`.
4. Confirm the skill name uses lowercase hyphenated form.
5. Confirm `agents/openai.yaml` agrees with `SKILL.md`.
6. Inspect the final file list for unnecessary files.
7. Inspect the diff for accidental changes outside the approved destination.

If forward-testing would be useful, propose realistic test prompts and request
approval before launching subagents or modifying external repositories.

## Acceptance criteria

The skill is complete only when:

- It triggers for repository-harness authoring and review requests.
- It right-sizes the harness to the repository and risk.
- It preserves local repository conventions and sources of truth.
- A harness-only request cannot silently create implementation artifacts.
- Phase context remains session-created unless separately approved.
- Plans include meaningful acceptance and verification requirements.
- The validator and its tests pass.
- The skill passes `quick_validate.py`.
- No files outside the approved skill destination were changed.
- All limitations and untested behavior are reported.

Finish by reporting:

- Skill location
- Files created or changed
- Triggering description
- Validator behavior
- Tests and validation results
- Forward-testing not performed
- Remaining assumptions or limitations
```
</details>

> **💡 Tip: Identifying Repeatable Work**
>
> A skill can be created for almost anything, but good skills are generally intended for frequent use. Some examples of potential skills you might run into in your day-to-day workflows might include:
>
> - Committing code changes, pushing to remote and creating a pull request
> - Watching for the latest change to merge in remote, then preparing the next feature branch
> - Identifying the current phase from the build log, loading the goal and prompt for the phase, summarizing purpose and acceptance criteria, then waiting for a human gate.

### Skill tuning

Skills may not behave exactly as expected upon creation. For example, when asked to create harness context and build-phase files, the `$harness-author` skill proposed the following, omitting `PLANS.md` and `harness/build-log.md`:

``` text
...
 I propose creating the following files:

  - harness/build/00_repository_foundation.md
  - harness/build/01_sqlite_core.md
  - harness/build/02_add_and_list_cli.md
  - harness/build/03_interactive_completion.md
  - harness/build/04_hardening_and_verification.md
  - harness/build/05_documentation_and_handoff.md
  - harness/context/README.md
  - harness/context/00_repository_foundation_context.md
  ...
  ```

  In cases like this, correct the proposed scope before approving any changes:

  ``` text
  Revise the proposed harness-only scope before writing.

Include these missing artifacts:

- PLANS.md: the ordered phase execution plan.
- harness/build-log.md: observed implementation progress and verification evidence.

Do not create a phase-specific context file until that phase begins and has
received the required approval. Include harness/context/README.md only if it
is explicitly approved as an exception to the standard harness-only allowlist.

Check the proposed artifact list for both missing required files and
unapproved additional files. Present the revised exact file list, explain
the ownership of each artifact, and wait for approval before writing.
```

After applying the correction, Codex proposes the expected harness files.

``` text
 I propose creating the following files:

  - PLANS.md
  - harness/build-log.md
  - harness/build/00_repository_foundation.md
  - harness/build/01_sqlite_core.md
  - harness/build/02_add_and_list_cli.md
  - harness/build/03_interactive_completion.md
  - harness/build/04_hardening_and_verification.md
  - harness/build/05_documentation_and_handoff.md
  ...
  ```

## Retrospective

Now that the entire structure has been created to start development, it's important to remember that this is only a starting point. Once the project has been completed according to the criteria specified in the agents file and the changes checked into version control, it's time to look back, using Codex, to understand what was learned during the process and optimize for future improvement.

Here's a prompt that can be used with Codex to produce a retrospective.

<details>
<summary><strong>Generate a Retrospective</strong></summary>

``` text
Use `$skill-creator` to conduct an evidence-backed postmortem of the completed
development workflow.

The goals are to:

1. Understand what worked and what created friction
2. Improve the existing harness-authoring skill
3. Identify missing reusable skills without creating overlapping skill sprawl
4. Improve repository instructions, harness artifacts, validators, and process
5. Convert verified workflow failures into regression tests or enforceable
   safeguards where appropriate

Do not modify any repository, harness, or skill files during the initial
postmortem.

## Read-only discovery

Read the applicable sources, including:

- Global and repository `AGENTS.md` files
- `PLANS.md`, `GOALS.md`, and `PROMPTS.md`, when present
- `harness/build-log.md`
- Applicable files under `harness/build/`
- Applicable files under `harness/context/`
- Code-review and postmortem artifacts
- Relevant implementation diffs
- Test and verification results
- Current Git branch and working-tree state
- User corrections, approval decisions, and accepted limitations
- The installed `harness-author` skill
- Other skills invoked during the workflow
- Their scripts, references, metadata, and tests
- Existing skills that could already own an identified procedure

Use current files and observed evidence as the source of truth. Do not treat
plans, intended behavior, prior conversations, or unverified reports as proof
of what occurred.

Do not access credentials, production systems, external services, or remote Git
state unless separately authorized.

## Reconstruct the intended workflow

Document:

- The intended sequence of phases
- The ownership of each harness artifact
- The expected approval gates
- The planned red, green, refactor, and verification checkpoints
- The expected review and handoff process
- Which skills should have triggered and what each was expected to own
- The expected boundaries around context, evidence, commits, pushes,
  deployments, credentials, and external writes

Distinguish required repository behavior from optional workflow conventions.

## Reconstruct what actually happened

Using observed evidence, identify:

- Work completed
- Commands and checks actually run
- Approval gates honored, missed, or ambiguous
- Scope changes
- Repeated discovery or duplicated work
- Incorrect assumptions
- Agent drift or overbuilding
- Missing or excessive context
- Misleading status or unsupported completion claims
- Manual interventions
- Review findings and remediation
- Failed, skipped, or unavailable verification
- Recovery or rollback issues
- User corrections
- Work that succeeded because of the harness or a skill
- Work that succeeded despite gaps in the process

Do not manufacture a root cause when evidence supports only a symptom or
correlation.

## Analyze each material event

For every material success, failure, or friction point, record:

| Field | Meaning |
|---|---|
| Event | What happened |
| Expected behavior | What should have happened |
| Observed evidence | What proves the event occurred |
| Impact | Effect on scope, quality, safety, time, or confidence |
| Contributing conditions | Evidence-supported factors |
| Current safeguard | Existing instruction, skill, test, or approval gate |
| Safeguard result | Worked, failed, missing, ambiguous, or bypassed |
| Generalizability | One-off, repository-specific, or reusable |
| Recommended owner | Where an improvement should live |
| Proposed validation | How the improvement would be tested |

Use a blameless framing. Focus on workflow design, missing information,
ambiguous ownership, and insufficient validation rather than assigning personal
fault.

## Apply a materiality test

Include an event only when it materially affected or could reasonably affect:

- Approved scope
- Implementation correctness
- Verification confidence
- Security or privacy
- Reliability, observability, rollback, or recovery
- Human approval or review
- Future phase decisions
- Repeated effort
- The ability to reproduce or audit the work

Do not fill the postmortem with harmless typos, routine command failures, or
temporary exploration that had no lasting impact.

## Classify improvement ownership

Assign every recommendation to exactly one primary owner.

### Repository instructions

Use `AGENTS.md` when the lesson is a durable, repository-specific convention,
constraint, command, or approval rule.

### Project harness

Use a goal, plan, build file, context file, execution tracker, build log, or
review artifact when the lesson applies only to this project or phase.

### Existing skill instructions

Update an existing skill when the lesson changes a reusable procedure,
triggering condition, safety boundary, or decision rule.

### Existing skill reference

Update a reference when the lesson adds detailed guidance, examples, matrices,
or variants that do not belong in the core `SKILL.md`.

### Existing skill script or validator

Use deterministic code when the condition can be checked mechanically and a
miss would be costly or repeatedly error-prone.

### Regression test

Add a regression test when the failure is reproducible and the expected
behavior can be asserted reliably.

### New skill

Recommend a new skill only when all of the following are true:

- The task has a distinct user intent and triggering vocabulary
- It represents a reusable multi-step procedure
- It will recur across repositories or phases
- It has a clear owner and bounded responsibility
- Existing skills cannot own it cleanly
- Creating it reduces complexity rather than redistributing duplication
- Its success can be validated independently

Do not recommend a new skill for a single rule, one repository’s convention,
a one-time incident, or functionality already owned by another skill.

### No process change

Choose no change when the event was non-material, adequately handled, or too
specific to justify permanent workflow complexity.

## Evaluate existing skill quality

For each skill used, assess:

- Did its description trigger for the right requests?
- Did it fail to trigger when it should have?
- Did it trigger too broadly?
- Did `SKILL.md` contain only essential procedural guidance?
- Were detailed instructions routed to the correct references?
- Were applicable references actually loaded?
- Did scripts enforce fragile or safety-critical behavior?
- Were script failures handled safely?
- Were approval boundaries explicit?
- Did the skill preserve repository-specific conventions?
- Did it create files or process that the repository did not need?
- Did it confuse plans with observed evidence?
- Did it overfit to a previous project?
- Did its UI metadata remain consistent with its behavior?
- Are new regression tests needed?

Prefer tightening an existing skill over creating another skill when ownership
is already clear.

## Identify process improvements

Evaluate the end-to-end process separately from individual skills:

- Repository orientation
- Source-of-truth ownership
- Harness generation
- Phase selection
- Context capture
- Approval packets
- Red, green, refactor, and verification
- Evidence recording
- Independent review
- Remediation
- Phase completion
- Commit and push approval
- Post-merge branch preparation
- Cross-phase handoff
- Postmortem timing

For every proposed process change, state:

- The problem it solves
- Its intended owner
- Whether it is advisory or mechanically enforced
- Its cost or added process burden
- The smallest useful change
- How to validate that it improved the workflow

Avoid adding process solely to make the harness look comprehensive.

## Produce the read-only postmortem

Return:

### Executive summary

A concise assessment of the workflow’s effectiveness and the most important
improvement opportunity.

### What worked

Evidence-backed practices and safeguards worth preserving.

### What created friction

Material problems, their impact, and their evidence.

### Existing skill improvements

For each proposed change:

- Skill name and path
- Trigger, instruction, reference, script, metadata, or test affected
- Evidence supporting the change
- Proposed behavior
- Risk of overfitting
- Validation required

### New skill candidates

For each candidate:

- Proposed lowercase hyphenated name
- Distinct triggering requests
- Responsibility and explicit non-goals
- Why an existing skill cannot own it
- Likely files or resources
- Concrete example requests
- Validation and forward-testing plan
- Priority: now, later, or reject

Include rejected skill candidates and explain which existing owner should
absorb the behavior.

### Harness and repository improvements

Changes that belong in `AGENTS.md`, planning files, context rules, logs,
validators, or review requirements.

### Prioritized improvement backlog

Group recommendations as:

- P0: Unsafe or materially incorrect workflow behavior
- P1: Repeated failures, approval gaps, or misleading evidence
- P2: Meaningful efficiency or clarity improvements
- P3: Optional polish

For each item, include effort, expected value, owner, and validation.

### Unresolved questions

Evidence gaps or decisions that require human input.

## Approval gate

After presenting the postmortem, stop.

Do not:

- Modify an existing skill
- Create a new skill
- Change repository instructions
- Change harness files
- Add scripts or tests
- Launch forward-testing
- Create commits or push changes

Request separate approval for:

1. Repository or harness changes
2. Changes to each existing skill
3. Creation of each new skill
4. Forward-testing
5. Commits or pushes

## Implement approved improvements

Only after explicit approval, use `$skill-creator` for skill changes.

For each approved skill change:

1. Confirm the exact skill path and affected files.
2. Add a failing regression test when the behavior is mechanically testable.
3. Make the smallest change that addresses the evidence-backed failure.
4. Keep `SKILL.md` concise and move detailed material into directly linked
   references.
5. Update scripts only when deterministic enforcement is justified.
6. Run the relevant script tests.
7. Run `$skill-creator`’s `quick_validate.py`.
8. Regenerate `agents/openai.yaml` only when its interface metadata is stale.
9. Inspect the final diff for unrelated changes.
10. Report observed results and remaining limitations.

For each approved new skill:

1. Confirm its distinct trigger and ownership boundary.
2. Confirm the installation destination.
3. Initialize it using `$skill-creator`’s `init_skill.py`.
4. Create only necessary resources.
5. Add and run relevant tests.
6. Run `quick_validate.py`.
7. Verify that it does not duplicate or conflict with existing skills.

## Forward-testing

When forward-testing is approved:

- Use fresh, independent contexts
- Provide realistic requests and raw artifacts
- Do not reveal the expected answer or suspected defect
- Test both positive and negative triggering cases
- Check for scope expansion and unsafe writes
- Remove or isolate generated test artifacts between runs
- Compare observed behavior with explicit acceptance criteria
- Feed verified failures back into instructions, validators, or regression tests

Do not declare the workflow improved solely because the skill passes structural
validation. Require evidence from realistic use.

## Completion criteria

The postmortem cycle is complete only when:

- Material events are supported by evidence
- Improvements have a clear owner
- Existing skills are preferred over unnecessary new skills
- Approved changes have regression coverage where practical
- Skill and script validation passes
- Forward-testing results are recorded when performed
- Repository-specific lessons remain in the repository
- Reusable lessons are encoded in the appropriate skill
- Remaining limitations and rejected recommendations are documented
- No unapproved files, external systems, commits, or pushes were changed
```
</details>

## Conclusion

An improved directory structure is omitted here because it is impossible to predict the outcome of each phase or project. The initial setup should capture only the context that materially affects decisions, verification, and future work. As you become more comfortable with the process, you can create longer-running tasks that benefit from previous development cycles and produce more consistent, reliable results within approved boundaries.
