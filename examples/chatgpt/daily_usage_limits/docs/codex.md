# I test the approach with Codex

Use a Codex automation for a supervised, time-limited pilot with a small group. Explore the release schedule and confirm its value before moving ongoing operation to organization-managed infrastructure.

Codex invokes a fixed controller command and explains the result. The controller calculates each limit from the configured policy. Complete [the policy and enrollment review](../README.md#prepare-a-reviewed-enrollment) before a live trial.

The local automation depends on the desktop app and its host being available. For ongoing workspace credit management, use a managed virtual machine or cloud service operated by your organization. This walkthrough prepares the pilot; step 3 covers setting up its optional schedule. See [scheduled-task documentation](https://learn.chatgpt.com/docs/automations?surface=app).

## 1. I rehearse without a key

Open this repository as a project in the desktop app. Use its existing local folder so each run sees the same private state. From the example directory, run:

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

The first `run` previews the targets. The next applies them to the simulator. The repeat should report `duplicate_slot` for both users, with no extra release. This demonstrates command execution and durable local state; it does not demonstrate an actual scheduled trigger. If the first apply is more than 15 minutes after the snapshot, or crosses an interval boundary, capture and review a fresh snapshot before applying.

## 2. I test the task prompt manually

Paste this prompt into the project task, replacing `ABSOLUTE_EXAMPLE_DIRECTORY` with the absolute path to `examples/chatgpt/daily_usage_limits`:

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

## 3. I review a small pilot and its test schedule

1. Use a separate private pilot directory and complete the README's live snapshot, review, approval, and preview. Have the runtime's approved secret store supply `CHATGPT_ADMIN_API_KEY`; verify that it is available in this execution context without printing it.
2. Authorize a bounded first live change and its restoration. Set `liveWrites: true` and run the reviewed command with `--apply`. Inspect independent API readback, repeat the same command to verify duplicate handling, and follow the [restoration procedure](../README.md#stop-restore-and-renew). A successful receipt confirms the API setting, not exact enforcement of a daily allowance.
3. For a time-limited Codex pilot, enroll a small selected group in a new private directory. Decide the owner, cadence, pilot end date, and route for attention alerts. Run the live command manually and inspect its receipt. There must be only one writer for these users.
4. When authorized, ask the desktop app to create a **paused** scheduled task in the existing local project. Use the proven command with the live pilot's paths, without `--synthetic`. If it is intended to apply changes, include `--apply` explicitly and retain the configuration gate. Tell the task to report failures or required action, remain quiet when unchanged, and stop at the pilot end date or confirmed period end, whichever comes first. Review the saved prompt, project folder, cadence, permissions, and paused state before enabling it.
5. Enable the reviewed task, then verify a real scheduled run and its saved receipt. Do not substitute a manual “Run now” result for proof of a timed trigger. Review initial runs and separately verify that the chosen attention route reaches its operator.

The release interval belongs to the policy. A task that checks hourly can still release daily or weekly. Do not enable a second local or AWS scheduler to improve reliability; repeated delivery is supported, but competing owners make recovery and manual edits harder to reason about.

## 4. I stop and verify cleanup

Pause the scheduled task in the app and confirm its saved paused status. Set the pilot's `liveWrites` to `false`, wait for any active run to finish, and inspect receipts. Follow the README's reviewed restore procedure while the confirmed period is current. After readback matches the original settings and source, remove the pilot's scheduled task if it is no longer needed. Preserve the private journal and revoke a dedicated key according to your credential policy.

For the synthetic rehearsal, the equivalent restore check is:

```bash
node src/cli.mjs restore --config .private/codex-rehearsal/config.json --enrollment .private/codex-rehearsal/enrollment.json --state .private/codex-rehearsal/state --synthetic
node src/cli.mjs restore --config .private/codex-rehearsal/config.json --enrollment .private/codex-rehearsal/enrollment.json --state .private/codex-rehearsal/state --synthetic --apply
node src/cli.mjs inspect --state .private/codex-rehearsal/state
```

Expect a restore preview, then `restored` receipts for the fictional users. The closed enrollment cannot resume releasing budget; a new reviewed pilot uses a new directory.

## 5. I move to managed infrastructure

Choose a managed virtual machine or cloud environment operated by your organization. The [host scheduler guide](local.md) provides macOS and Linux examples; the [AWS guide](aws.md) provides a cloud deployment example. Another managed environment can use the same controller with its own scheduling, credential storage, persistent records, and monitoring.

Complete the pilot's stop and restore steps above, retaining its records. On the managed infrastructure, use the chosen policy settings to create a fresh enrollment and preview the intended limits. Verify a scheduled run and delivery of failure alerts before expanding the group. Keep the Codex pilot schedule disabled after the transition.
