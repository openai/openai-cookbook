# Build a Repository Configuration for Codex

Codex can read repository instructions, project configuration, lifecycle hooks,
custom agents, command rules, and skills directly from your working tree. This
example assembles those pieces in one small repository and gives every file a
real job to do.

The complete sample lives in [`example-project/`](./example-project/). It uses
only Node.js and the Python standard library, so you can copy it and exercise
the configuration without installing application dependencies.

## What you will build

```text
example-project/
├── AGENTS.md
├── .agents/
│   └── skills/
│       └── test-changes/
│           ├── SKILL.md
│           └── scripts/
│               └── run-tests.sh
├── .codex/
│   ├── agents/
│   │   └── reviewer.toml
│   ├── hooks/
│   │   └── session_start.py
│   ├── rules/
│   │   └── default.rules
│   ├── config.toml
│   └── hooks.json
├── src/
│   └── sum.js
├── test/
│   └── sum.test.js
└── package.json
```

The files under `.codex/` are project-scoped. Codex activates project config,
hooks, and rules only after you trust the repository. Read them before granting
trust, especially when you did not create the repository yourself.

## Run the sample

Copy the sample to a temporary directory so you can change it freely:

```bash
cp -R examples/codex/codex_repository_configuration/example-project \
  /tmp/codex-configuration-example
cd /tmp/codex-configuration-example
git init
```

Run the application test directly:

```bash
npm test
```

Exercise the hook implementation with a minimal `SessionStart` JSON payload
containing the current working directory:

```bash
printf '{"cwd":"/tmp/codex-configuration-example"}\n' \
  | python3 .codex/hooks/session_start.py \
  | python3 -m json.tool
```

The output includes `hookSpecificOutput`, the `SessionStart` event name, and the
repository context that Codex should add to the new session.

After you inspect the configuration files, start Codex from the example root:

```bash
codex "Explain the repository instructions you loaded, then run the smallest relevant test."
```

## `AGENTS.md`: shared repository instructions

[`AGENTS.md`](./example-project/AGENTS.md) tells Codex how to work in the
repository before it starts a task. Commit rules that should apply to every
contributor, such as the test command, source layout, and boundaries around
generated files.

The example intentionally keeps these instructions short and verifiable:

```md
# Repository guide

- Run `npm test` after changing JavaScript.
- Keep public functions in `src/` and their tests in `test/`.
- Do not commit generated coverage or dependency directories.
```

For directory-specific rules, add another `AGENTS.md` or
`AGENTS.override.md` closer to the files it governs. Codex combines the files
from the repository root down to the current working directory.

## `.codex/config.toml`: project defaults

[`config.toml`](./example-project/.codex/config.toml) sets portable defaults for
a trusted project. This example keeps approval prompts enabled, limits writes
to the workspace, caps subagent fan-out, and registers the public OpenAI
documentation MCP server:

```toml
approval_policy = "on-request"
sandbox_mode = "workspace-write"

[agents]
max_threads = 4
max_depth = 1

[mcp_servers.openaiDeveloperDocs]
url = "https://developers.openai.com/mcp"
```

Do not put API keys or machine-specific credentials in a committed project
config. Keep secrets in environment variables or an approved credential store.

## `.codex/hooks.json`: lifecycle hook registration

[`hooks.json`](./example-project/.codex/hooks.json) registers deterministic
commands at Codex lifecycle events. The sample runs one Python script when a
session starts. It resolves the script from the Git root, so starting Codex in
a nested directory still finds the same file.

The hook is not trusted merely because it is committed. Codex asks you to review
new or changed non-managed hooks before running them.

## `.codex/hooks/session_start.py`: hook implementation

[`session_start.py`](./example-project/.codex/hooks/session_start.py) reads a
JSON event from standard input and returns JSON on standard output. The
`additionalContext` value becomes context for the new Codex session.

Codex does not auto-discover scripts in `.codex/hooks/`; the adjacent
`hooks.json` file is what invokes this script.

## `.codex/agents/reviewer.toml`: custom subagent

[`reviewer.toml`](./example-project/.codex/agents/reviewer.toml) defines a
read-only reviewer that focuses on behavioral regressions and test coverage.
The `name`, `description`, and `developer_instructions` fields are required.
Runtime settings that are not present inherit from the parent session.

Ask Codex to use it directly:

```text
Use the reviewer agent to inspect the current diff. Return only actionable findings.
```

## `.codex/rules/default.rules`: command policy

[`default.rules`](./example-project/.codex/rules/default.rules) allows a narrow
set of read-only Git commands to run outside the sandbox. The `match` and
`not_match` cases are inline checks that Codex evaluates when it loads the
rule.

Rules control command execution; they are not a replacement for repository
instructions. Keep workflow guidance in `AGENTS.md` and reserve `.rules` files
for command policy.

## `.agents/skills/test-changes/`: reusable workflow

[`SKILL.md`](./example-project/.agents/skills/test-changes/SKILL.md) packages a
repeatable workflow. Codex sees the skill's `name` and `description` during
discovery, then reads the full instructions only when the skill is selected.

The skill calls
[`scripts/run-tests.sh`](./example-project/.agents/skills/test-changes/scripts/run-tests.sh),
which anchors itself at the Git root and runs the dependency-free Node test.
Supporting scripts are not loaded or executed during skill discovery.

Invoke the skill explicitly:

```text
Use the test-changes skill to verify this branch.
```

## Project files and personal files

The sample uses only project files so it is safe to copy as a repository. Keep
personal defaults in your home directories instead:

| Purpose | Project location | Personal location |
| --- | --- | --- |
| Instructions | `AGENTS.md` | `~/.codex/AGENTS.md` |
| Base configuration | `.codex/config.toml` | `~/.codex/config.toml` |
| Profile configuration | Not project-scoped | `~/.codex/<profile>.config.toml` |
| Hooks | `.codex/hooks.json` | `~/.codex/hooks.json` |
| Custom agents | `.codex/agents/*.toml` | `~/.codex/agents/*.toml` |
| Command rules | `.codex/rules/*.rules` | `~/.codex/rules/*.rules` |
| Skills | `.agents/skills/<name>/` | `~/.agents/skills/<name>/` |

Keep `~/.codex/auth.json`, histories, sessions, memories, logs, and caches out of
repositories. They are credentials or Codex-managed state, not portable
configuration examples.

## Extend the example

Start with the smallest configuration that changes a real workflow. Then:

1. Add nested `AGENTS.md` files only where a directory needs different rules.
2. Add project config values only when they should apply to every contributor.
3. Keep hooks deterministic, fast, and easy to audit.
4. Give each custom agent one clear responsibility.
5. Package repeated multi-step work as a skill with narrow helper scripts.
6. Include `match` and `not_match` cases with every command rule.

For the complete contracts and current availability, see the Codex documentation
for [custom instructions](https://learn.chatgpt.com/docs/agent-configuration/agents-md),
[configuration](https://learn.chatgpt.com/docs/config-file/config-basic),
[hooks](https://learn.chatgpt.com/docs/hooks),
[custom agents](https://learn.chatgpt.com/docs/agent-configuration/subagents),
[rules](https://learn.chatgpt.com/docs/agent-configuration/rules), and
[skills](https://learn.chatgpt.com/docs/build-skills).
