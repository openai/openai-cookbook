# Try a usage-budget pilot with Codex

Start with [the Codex setup request](get-started.md#let-codex-help). Open the extracted starter folder in Codex and run the demonstration with fictional people. Review the release plan, then choose the amounts and schedule for your organization.

The demonstration runs on Windows, macOS, and Linux. The commands below for saved enrollments and live pilots require a macOS or Linux runtime. On Windows, use Codex to explore the example and prepare your [managed environment setup](get-started.md#use-a-managed-environment).

If the folder is already open in Codex, paste:

```text
Run node src/demo.mjs in this starter folder using an available Node.js 24 or later
runtime. If this is the full Cookbook repository, use
examples/chatgpt/daily_usage_limits. Honor stated restrictions and current
execution controls. Show the fictional users' current limits, first release,
and monthly ceiling, then ask me about my budget and release schedule.
If the runtime is unavailable, prepare a managed-host setup request.
Keep workspace access, real changes, installation, and scheduling off.
```

The demo simulates an interrupted update and a conflicting admin edit, then shows recovery and restoration for the fictional users.

Codex invokes the controller and explains the result. The controller calculates each limit from the configured policy. Complete [the policy and enrollment review](operations.md#prepare-a-reviewed-enrollment) before a supervised, time-limited pilot with a small group.

Local automation requires the desktop app and its host to be available. Use organization-managed infrastructure for ongoing operation. Step 3 covers an optional [Codex scheduled task](https://learn.chatgpt.com/docs/automations?surface=app) for the pilot.

## 1. Run the fictional rehearsal

Run these commands to inspect each stage of the two-person fictional rehearsal. Use Node.js 24 or later under the current execution controls and the same local folder across runs. Run from the starter kit's root, or from `examples/chatgpt/daily_usage_limits` in the full repository:

```bash
node src/cli.mjs init --dir .private/codex-rehearsal --pattern fixed_release --cohort selected --unit credit --interval-hours 168 --synthetic --allow-initial-reduction
node src/cli.mjs snapshot --config .private/codex-rehearsal/config.json --out .private/codex-rehearsal/enrollment.json --synthetic
```

This rehearsal gives each person a 2,000-credit monthly target, released in 500-credit weekly portions. `--allow-initial-reduction` lets the first reviewed change move the fictional users from their original 2,000-credit limit to the first 500-credit portion. Inspect both members and their proposed limits in `enrollment.json`. Replace `REVIEWED_SHA256` below with the snapshot command's printed hash:

```bash
node src/cli.mjs approve --enrollment .private/codex-rehearsal/enrollment.json --hash REVIEWED_SHA256
node src/cli.mjs run --config .private/codex-rehearsal/config.json --enrollment .private/codex-rehearsal/enrollment.json --state .private/codex-rehearsal/state --synthetic
node src/cli.mjs run --config .private/codex-rehearsal/config.json --enrollment .private/codex-rehearsal/enrollment.json --state .private/codex-rehearsal/state --synthetic --apply
node src/cli.mjs run --config .private/codex-rehearsal/config.json --enrollment .private/codex-rehearsal/enrollment.json --state .private/codex-rehearsal/state --synthetic --apply
node src/cli.mjs inspect --state .private/codex-rehearsal/state
```

The first `run` previews the targets. The next applies them to the simulator. Expect the repeat to report `duplicate_slot` for both users and leave their caps unchanged. Verify scheduled execution separately in step 3. If the first apply is more than 15 minutes after the snapshot, or crosses an interval boundary, capture and review a fresh snapshot before applying.

## 2. Try the task prompt

Paste this prompt into the project task, replacing `ABSOLUTE_EXAMPLE_DIRECTORY` with the absolute path to the starter kit's root or `examples/chatgpt/daily_usage_limits` in the full repository:

```text
In ABSOLUTE_EXAMPLE_DIRECTORY, run exactly:
node src/cli.mjs run --config .private/codex-rehearsal/config.json --enrollment .private/codex-rehearsal/enrollment.json --state .private/codex-rehearsal/state --synthetic

Read the command's receipt. Report its mode, users processed, current slot,
proposed targets, and any attention codes. Treat this as a synthetic preview.
Do not alter the policy, cohort, period, approval, or state. Do not remove locks,
add --apply, retrieve credentials, create a schedule, or retry a different target.
If the period ended or a conflict occurred, stop and explain the required review.
```

Confirm that Codex ran the exact command, identified it as synthetic, and reported actual receipt fields. Keep secrets out of the prompt and task output.

<a id="3-i-review-a-small-pilot-and-its-test-schedule"></a>

## 3. Review a small pilot and its schedule

1. Use a separate private pilot directory and complete the [live snapshot, review, approval, and preview](operations.md#prepare-a-reviewed-enrollment). Have the runtime's approved secret store supply `CHATGPT_ADMIN_API_KEY`; verify that it is available in this execution context without printing it.
2. Authorize a bounded first live change and its restoration. Set `liveWrites: true` and run the reviewed command with `--apply`. Inspect independent API readback, repeat the same command to verify duplicate handling, and follow the [restoration procedure](operations.md#stop-restore-and-renew). A successful receipt confirms the API setting. Review its effect on eligible usage during the trial.
3. For a time-limited Codex pilot, enroll a small selected group in a new private directory. Decide the owner, cadence, pilot end date, and route for attention alerts. Run the live command manually and inspect its receipt. There must be only one writer for these users.
4. When authorized, ask the desktop app to create a **paused** scheduled task in the existing local project. Use the proven command with the live pilot's paths, without `--synthetic`. If it is intended to apply changes, include `--apply` explicitly and retain the configuration gate. Tell the task to report failures or required action, remain quiet when unchanged, and stop at the pilot end date or confirmed period end, whichever comes first. Review the saved prompt, project folder, cadence, permissions, and paused state before enabling it.
5. Enable the reviewed task, then verify a real scheduled run and its saved receipt. Use a receipt produced by the timed trigger for this check. Review initial runs and separately verify that the chosen attention route reaches its operator.

The policy sets the release interval. An hourly check can serve a daily or weekly release plan. Assign one scheduler to each cohort and coordinate manual edits with its operator.

## 4. Stop the pilot and verify cleanup

Pause the scheduled task in the app and confirm its saved paused status. Set the pilot's `liveWrites` to `false`, wait for any active run to finish, and inspect receipts. Follow the [reviewed restore procedure](operations.md#stop-restore-and-renew) while the confirmed period is current. After readback matches the original settings and source, remove the pilot's scheduled task if it is no longer needed. Preserve the private journal and revoke a dedicated key according to your credential policy.

For the synthetic rehearsal, the equivalent restore check is:

```bash
node src/cli.mjs restore --config .private/codex-rehearsal/config.json --enrollment .private/codex-rehearsal/enrollment.json --state .private/codex-rehearsal/state --synthetic
node src/cli.mjs restore --config .private/codex-rehearsal/config.json --enrollment .private/codex-rehearsal/enrollment.json --state .private/codex-rehearsal/state --synthetic --apply
node src/cli.mjs inspect --state .private/codex-rehearsal/state
```

Expect a restore preview, then `restored` receipts for the fictional users. Restoration closes the enrollment. Use a new directory and reviewed enrollment for another pilot.

## 5. Move to managed infrastructure

Choose a managed virtual machine or cloud environment operated by your organization. The [host scheduler guide](local.md) provides macOS and Linux examples; the [AWS guide](aws.md) provides a cloud deployment example. Another managed environment can use the same controller with its own scheduling, credential storage, persistent records, and monitoring.

Complete the pilot's stop and restore steps above, retaining its records. On the managed infrastructure, use the chosen policy settings to create a fresh enrollment and preview the intended limits. Verify a scheduled run and delivery of failure alerts before expanding the group. Keep the Codex pilot schedule disabled after the transition.
