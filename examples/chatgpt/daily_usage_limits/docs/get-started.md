# Try a usage-budget plan with Codex

Download the starter kit and let Codex prepare a preview with fictional people. The preview uses a 2,000-credit monthly allocation released in 500-credit weekly portions. Then choose the amounts and schedule that fit your organization.

## 1. Download and open the starter kit

1. [Download the starter ZIP](https://raw.githubusercontent.com/openai/openai-cookbook/codex/daily-usage-limits/examples/chatgpt/daily_usage_limits/assets/chatgpt-usage-budget-starter.zip) and extract it. You should see a folder named `chatgpt-usage-budget-starter` containing `README.md`, `docs`, `src`, and `assets`.
2. Open **that folder** as a local project in Codex. Keep the files together.
3. Paste the request below into a new conversation in that project. Codex will check the available software before running the preview.

## 2. Ask Codex to prepare the preview

```text
Help me preview a ChatGPT usage-budget plan using this starter kit.

Read README.md and docs/get-started.md. If I opened the full Cookbook
repository instead, locate examples/chatgpt/daily_usage_limits first.

Check for an existing Node.js 24 or later runtime available to this Codex
environment. Verify its path and version. Use a bundled runtime when exposed
through a supported tool and permitted by the current execution controls.
Honor stated organization restrictions. Do not install or download software,
change device policy, elevate access, or bypass a blocked command. If no
runtime is available or host restrictions prevent the preview, explain the
actual obstacle, prepare the managed-host handoff below, and give me the
browser illustration's path.

With a permitted runtime, use src/cli.mjs in a new private rehearsal folder.
Do not overwrite existing configuration, enrollment, or state. Initialize
fixed_release for selected fictional users, credit units, and a 168-hour
interval, using --synthetic and --allow-initial-reduction. Capture the
fictional snapshot with --synthetic, inspect it, and record approval of its
actual hash only for this fictional rehearsal. Run the preview with
--synthetic and without --apply. Keep liveWrites false.

Show me each fictional person's current limit, proposed first limit, and
monthly ceiling. Explain a full four-release plan: 500, 1,000, 1,500, then 2,000.
After the preview, ask me about my monthly allocation, release amount and
frequency, and whether I want selected people or a reviewed workspace roster.
Keep any proposed changes as a preview for my review.

Do not retrieve credentials, contact a ChatGPT workspace, apply changes,
create an automation or service, deploy infrastructure, or upload files.
Do not modify the controller source. A live pilot is a separate decision.
```

Expect a preview showing the fictional users' current 2,000-credit limits and proposed first limits of 500. It creates local rehearsal files without changing a real workspace. A full four-release plan reaches 1,000, 1,500, and 2,000; unused released credits remain available within the month. A live plan must fit the confirmed usage period, including any mid-month start.

## If the required software is unavailable

You can still explore the release plan. In the extracted folder, open `assets/release-explorer.html` in your browser. It works without Node.js, an Admin key, or a connection to your workspace.

Ask Codex to prepare this handoff for your technology team, including the actual missing prerequisite or device restriction it found:

> Please provide an approved environment for a small ChatGPT usage-budget preview. This starter kit's controller needs Node.js 24 or later. Its fictional preview needs no credentials or package installation. An organization-managed virtual machine or cloud environment is suitable if this computer cannot run it. Before a live pilot, we will separately review the workspace, participants, monthly allocation, release schedule, credential storage, and the team responsible for operation.

Node.js 24 or later runs the controller included here. The ChatGPT Admin API can be used from other programming languages. Codex still needs a permitted runtime to execute this controller. The provided setup guides cover macOS, Linux, and AWS; this kit does not include a PowerShell controller or a packaged Windows application.

## When you are ready for a pilot

Use the [Codex pilot guide](codex.md#3-i-review-a-small-pilot-and-its-test-schedule) to review a small, time-limited trial. For ongoing workspace credit management, choose [an organization-managed host](local.md) or the [AWS deployment example](aws.md). Confirm the current usage period, review the exact participants and proposed changes, and verify restoration before enabling recurring changes.
