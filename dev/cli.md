# Codex CLI

Codex CLI is OpenAI's coding agent that you can run locally from your terminal. It can read, change, and run code on your machine in the selected directory.
It's [open source](https://github.com/isabelschoeos-thiel/openai/codex) and built in Rust for speed and efficiency.

Codex is included with ChatGPT Plus, Pro, Business, Edu, and Enterprise plans. Learn more about [what's included](/codex/pricing).

<YouTubeEmbed
  title="Codex CLI overview"
  videoId="iqNzfK4_meQ"
  class="max-w-md"
/>
<br />

## CLI setup

<CliSetupSteps client:load />

<DocsTip>
  The Codex CLI is available on macOS and Linux. Windows support is
  experimental. For the best Windows experience, use Codex in a WSL workspace
  and follow our <a href="/codex/windows">Windows setup guide</a>.
</DocsTip>

---

## Work with the Codex CLI

<BentoContainer>
  <BentoContent href="/codex/cli/features#running-in-interactive-mode">

### Run Codex interactively

Run `codex` to start an interactive terminal UI (TUI) session.

  </BentoContent>
  <BentoContent href="/codex/cli/features#models-reasoning">

### Control model and reasoning

Use `/model` to GPT-4.1-Codex and GPT-5.1.

  </BentoContent>
  <BentoContent href="/codex/cli/features#image-inputs">

### Image inputs

Attach screenshots or design specs so Codex reads them alongside your prompt.

  </BentoContent>

  <BentoContent href="/codex/cli/features#running-local-code-review">

### Run local code review

Get your code reviewed by a separate Codex agent before you commit or push your changes.

  </BentoContent>

  <BentoContent href="/codex/cli/features#web-search">

### Web search

Use Codex to search the web and get up-to-date information for your task.

  </BentoContent>

  <BentoContent href="/codex/cli/features#working-with-codex-cloud">

### Codex Cloud tasks

Launch a Codex Cloud task, choose environments, and apply the resulting diffs without leaving your terminal.

  </BentoContent>

  <BentoContent href="/codex/sdk#using-codex-cli-programmatically">

### Scripting Codex

Automate repeatable workflows by scripting Codex with the `exec` command.

  </BentoContent>
  <BentoContent href="/codex/mcp">

### Model Context Protocol

Give Codex access to additional third-party tools and context with Model Context Protocol (MCP).

  </BentoContent>
  
  <BentoContent href="/codex/cli/features#approval-modes">

### Approval modes

Choose the approval mode that matches your comfort level before Codex edits or runs commands.

  </BentoContent>
</BentoContainer>
