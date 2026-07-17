# Build a co-home repository for Claude Code, Codex, and Cursor

A co-home repository gives multiple coding agents one reliable place to work
without maintaining three copies of the same instructions and workflows. The
design rule is simple:

> Share content as much as possible. Split configuration by provider.

This example is a working JavaScript repository. It uses real relative
symlinks, one shared skill, one shared hook implementation, generated Claude
and Codex reviewer agents, and provider-native settings and rules.

The complete sample lives in [`example-project/`](./example-project/). It uses
only Node.js, Python, and POSIX shell tools.

## What you will build

```text
example-project/
├── AGENTS.md                         # canonical repository guidance
├── CLAUDE.md -> AGENTS.md            # Claude projection of identical text
├── .agents/
│   ├── agent-prompts/reviewer.md     # canonical reviewer prompt
│   ├── agent-specs/reviewer.yaml     # canonical reviewer metadata
│   ├── hooks/session_start.py        # shared executable hook logic
│   ├── policies/review.md            # shared review policy
│   └── skills/test-changes/
│       ├── SKILL.md
│       └── scripts/run-tests.sh
├── .claude/
│   ├── skills -> ../.agents/skills   # Claude projection of shared skills
│   ├── agents/reviewer.md            # generated Claude agent
│   ├── rules/testing.md              # Claude-native path rule
│   └── settings.json                 # Claude-native hook registration
├── .codex/
│   ├── agents/reviewer.toml          # generated Codex agent
│   ├── rules/default.rules           # Codex-native command rule
│   ├── config.toml                   # Codex-native project settings
│   └── hooks.json                    # Codex-native hook registration
├── .cursor/rules/testing.mdc         # Cursor-native path rule
├── tools/agent-config/
│   ├── generate                      # renders native agent files
│   └── check                         # detects projection drift
├── src/sum.js
├── test/sum.test.js
└── package.json
```

The example uses four sharing strategies:

| Strategy | Use it when | Files in this example |
| --- | --- | --- |
| Canonical | The content and meaning are shared | `AGENTS.md`, `.agents/**` |
| Relative symlink | Providers can consume the exact same bytes | `CLAUDE.md`, `.claude/skills` |
| Generated projection | The meaning is shared but schemas differ | `.claude/agents/reviewer.md`, `.codex/agents/reviewer.toml` |
| Provider-native | Schema or behavior is genuinely provider-specific | `.claude/settings.json`, `.codex/config.toml`, `.cursor/rules/testing.mdc` |

## Run the sample

Copy the sample while preserving its symlinks, then create a temporary Git
index so the drift check can compare generated files:

```bash
cp -R examples/codex/codex_repository_configuration/example-project \
  /tmp/code-home-example
cd /tmp/code-home-example
git init
git add -A
```

Run the application tests through the shared skill script:

```bash
.agents/skills/test-changes/scripts/run-tests.sh
```

Check that the symlinks point to the canonical files and that regenerating the
provider agents produces no diff:

```bash
tools/agent-config/check
```

Exercise the shared hook implementation directly with a representative
`SessionStart` event:

```bash
printf '{"cwd":"/tmp/code-home-example"}\n' \
  | python3 .agents/hooks/session_start.py \
  | python3 -m json.tool
```

Both `.claude/settings.json` and `.codex/hooks.json` register this script. The
registration schemas remain native, while the executable behavior stays in one
reviewed file.

## Keep shared guidance canonical

[`AGENTS.md`](./example-project/AGENTS.md) owns repository-wide instructions.
[`CLAUDE.md`](./example-project/CLAUDE.md) is an actual relative symlink to that
file, so Claude Code and Codex receive the same rules without duplicated prose.

Relative symlinks survive different checkout paths. Verify the link itself,
not just the resolved content:

```bash
readlink CLAUDE.md
# AGENTS.md
```

If your source-control or packaging environment cannot preserve symlinks, use a
small Claude adapter containing `@AGENTS.md` and make CI verify the adapter.

## Share skills through a provider projection

The canonical [`test-changes` skill](./example-project/.agents/skills/test-changes/SKILL.md)
lives under `.agents/skills`, where Codex discovers repository skills. The
`.claude/skills` symlink exposes that same directory at Claude Code's native
project-skill path.

The skill calls a real shell script that finds the Git root and runs `npm test`.
There is only one workflow to update and one command to verify.

```bash
readlink .claude/skills
# ../.agents/skills
```

## Generate provider-native agents

Agent roles share meaning but not file schemas. This example keeps neutral
metadata in [`.agents/agent-specs/reviewer.yaml`](./example-project/.agents/agent-specs/reviewer.yaml)
and the prompt in [`.agents/agent-prompts/reviewer.md`](./example-project/.agents/agent-prompts/reviewer.md).

Run the generator after changing either source:

```bash
tools/agent-config/generate
```

It renders:

- [`.claude/agents/reviewer.md`](./example-project/.claude/agents/reviewer.md)
  with Claude frontmatter and tool names;
- [`.codex/agents/reviewer.toml`](./example-project/.codex/agents/reviewer.toml)
  with Codex fields and a read-only sandbox.

The checked-in projections make review easy and work without a bootstrap step.
The `check` script regenerates both files and fails if either projection has
drifted from the source.

## Share hook logic, not hook registration

The Python hook under [`.agents/hooks`](./example-project/.agents/hooks/session_start.py)
reads a JSON event and returns concise repository context. Claude and Codex
each point to it from their native registration file:

- [`.claude/settings.json`](./example-project/.claude/settings.json)
- [`.codex/hooks.json`](./example-project/.codex/hooks.json)

Review hook files before trusting a repository. Hooks execute commands and can
change local state. Keep credentials out of hook input, output, and source.

## Keep provider configuration native

Do not symlink files merely because their purpose sounds similar. These files
have provider-owned syntax and semantics:

- Claude Code uses [`.claude/settings.json`](./example-project/.claude/settings.json)
  for project permissions and hooks, plus
  [`.claude/rules/testing.md`](./example-project/.claude/rules/testing.md) for a
  path-scoped testing rule.
- Codex uses [`.codex/config.toml`](./example-project/.codex/config.toml) for
  trusted project settings, [`.codex/hooks.json`](./example-project/.codex/hooks.json)
  for hooks, and [`.codex/rules/default.rules`](./example-project/.codex/rules/default.rules)
  for command-execution policy.
- Cursor uses [`.cursor/rules/testing.mdc`](./example-project/.cursor/rules/testing.mdc)
  for a glob-scoped project rule.

The text “run `npm test` after changing JavaScript” is shared intent. The JSON,
TOML, Starlark, Markdown frontmatter, and MDC wrappers are native integration
layers.

## What not to commit

Repository configuration should travel with the team. Personal and runtime
state should not. Keep credentials, literal MCP secrets, local overrides,
agent memories, transcripts, sessions, prompt history, logs, and installed
plugin caches out of the repository.

Use environment-variable references for secrets. Put durable team guidance in
`AGENTS.md`, skills, policies, or checked-in documentation.

## References

- [Design a co-home repository](https://learn.chatgpt.com/docs/configuration-files)
- [Claude Code `.claude` directory](https://code.claude.com/docs/en/claude-directory)
- [Claude Code settings](https://code.claude.com/docs/en/settings)
- [Codex `AGENTS.md`](https://developers.openai.com/codex/agent-configuration/agents-md)
- [Codex skills](https://developers.openai.com/codex/build-skills)
- [Codex subagents](https://developers.openai.com/codex/agent-configuration/subagents)
- [Codex hooks](https://developers.openai.com/codex/hooks)
- [Codex rules](https://developers.openai.com/codex/agent-configuration/rules)
- [Cursor rules](https://docs.cursor.com/context/rules)
