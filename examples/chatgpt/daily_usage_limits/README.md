# Release ChatGPT usage budgets daily, weekly, or on your own cadence

## The problem: the month's allocation can run out early

Your organization targets **2,000 credits per person per month**. Some users can spend that allocation early, leaving them with no capacity for the rest of the month.

![A person uses their full 2,000-credit monthly allocation in the first week and has no capacity left for the remaining weeks.](assets/monthly-budget-problem.svg)

## The solution: release the allocation in increments

Give admins the flexibility to apportion those **same 2,000 credits** in increments that make sense for their organization: daily, weekly, or on a custom schedule. Apply the approach to selected power users or all current workspace members.

For example, release **500 credits each week**. The monthly limit increases as each portion becomes available:

| Release date | New credits released | Monthly limit after release |
| --- | ---: | ---: |
| Day 1 | 500 | 500 |
| Day 8 | 500 | 1,000 |
| Day 15 | 500 | 1,500 |
| Day 22 | 500 | 2,000 |

![A 2,000-credit monthly allocation is released in four portions of 500 credits, on days 1, 8, 15, and 22.](assets/release-timeline.svg)

An organization could instead release **1,000 credits every two weeks**, or choose daily increments. Admins choose the amount and frequency; the monthly target stays at 2,000. Unused released credits remain available within the month.

Use the [interactive walkthrough](assets/release-explorer.html) to see the problem, then try different release schedules.

## Start with a pilot, then deploy for ongoing use

Use a Codex automation or a local run to test the approach with a small group, explore release schedules, and confirm the value for your organization.

For ongoing workspace credit management, we recommend running the controller on organization-managed infrastructure, such as a managed virtual machine or cloud service. Scheduled releases should run independently of an individual's computer, with monitoring and a team responsible for operation.

This guide provides an AWS deployment example. Your technical team can also adapt the controller to another managed environment that provides scheduled execution, secure credential storage, persistent records, and monitoring.

## Run the credential-free example

Prerequisites: Node.js 24 or later and npm. The local controller uses Node's standard library; no packages or credentials are needed for these commands. From the repository root:

```bash
cd examples/chatgpt/daily_usage_limits
npm test
npm run demo
```

The demo walks through the 2,000-credit monthly target with weekly releases for three fictional members. It previews the changes, applies them to a simulated workspace, advances to the next week, and restores the original settings. It also shows how the controller handles a repeated run and an interrupted update. See the [verification record](https://github.com/openai/openai-cookbook/blob/codex/daily-usage-limits/examples/chatgpt/daily_usage_limits/docs/verification.md) for the full test coverage.

## Choose a policy

| Pattern | Use it when | How the cap changes |
| --- | --- | --- |
| **Fixed budget release** (`fixed_release`) | You want a predictable release plan for selected people or a broad cohort. This is the recommended starting point. | Release a configured increment each elapsed interval, up to the monthly ceiling. No analytics history is required. |
| **Observed usage headroom** (`observed_headroom`) | You want a reviewed power-user cohort to receive headroom based on recent observed usage. | Use recent consumption to estimate the next cap, within the monthly ceiling. |

### Fixed budget release

```text
slot = floor((current UTC time − anchor) / interval)
target cap = min(ceiling, start cap + slot × increment)
```

For a start cap of 500 credits, a weekly increment of 500, and a 2,000-credit ceiling, the targets are 500, 1,000, 1,500, and 2,000. The controller sets that cumulative monthly limit through the [ChatGPT Admin API](https://chatgpt.com/public/admin/api-reference). A repeated run in the same week keeps the same target. If a scheduled run is missed, the next run sets the target for the current week.

Choose `intervalHours: 24` for daily releases, `168` for weekly, `336` for every two weeks, or another whole-hour interval from 1 through 744. Set the increment alongside the interval: for this example, 500 weekly or 1,000 every two weeks. The controller measures intervals in elapsed UTC hours. The scheduler can check more frequently than the release interval.

### Observed usage headroom

```text
estimated headroom = observed daily average × coverageHours / 24 × multiplier
target cap = min(ceiling, max(current finite cap, start cap,
                            round up(current period usage + estimated headroom)))
```

For example, a person has used 800 credits and currently has a 900-credit limit. Their recent observed average is 100 credits per day. With 24 hours of coverage and a 1.5 multiplier, the next target is 950 credits, within the 2,000-credit monthly ceiling. `multiplierBps: 15000` represents 1.5; `coverageHours` sets how much future usage the estimate covers.

This pattern uses reported daily usage to estimate the next increment. It requires history for each day in the selected lookback window. The [API contract](https://github.com/openai/openai-cookbook/blob/codex/daily-usage-limits/examples/chatgpt/daily_usage_limits/docs/api-contract.md) explains data freshness and how missing or corrected history is handled. Fixed budget releases use the schedule and amount you choose, without requiring usage history.

## Prepare a reviewed enrollment

An enrollment records the people included in the plan and their original settings. Save it, the configuration, and receipts in a private, access-controlled directory.

Confirm each person's current limit before including them. The [API contract](https://github.com/openai/openai-cookbook/blob/codex/daily-usage-limits/examples/chatgpt/daily_usage_limits/docs/api-contract.md) covers supported settings. To capture a fresh snapshot, use a new output filename and that filename in subsequent `--enrollment` arguments.

1. Create a local configuration template:

   ```bash
   node src/cli.mjs init --dir .private/pilot --pattern fixed_release --cohort selected --unit credit --interval-hours 168
   ```

2. Edit `.private/pilot/config.json`. The generated live template is deliberately incomplete. Confirm these choices before taking a snapshot:

   | Setting | What to review |
   | --- | --- |
   | `workspaceId`, `unit` | The intended workspace and its native `credit` or `usd` unit. Amounts are decimal strings. Credit caps use whole credits; USD caps use cents. Never convert between units. |
   | `cohort.mode`, `cohort.userIds` | `selected` uses an explicit approved user list. For all current members, use `all` with an empty user list. Review the resulting roster; later joiners are not automatically enrolled. |
   | `period` | Copy the current UTC start and end shown in Admin Console, confirm whether it is `calendar_month` or `billing_cycle`, and record the verification time and source in `verifiedAt` and `evidence`. Set `counterScopeConfirmed: true` only after confirming the counter covers that range. The API response alone does not establish period boundaries. |
   | `policy` | Pattern, UTC anchor, interval, starting cap, increment, and finite ceiling. For a mid-period start, review consumption already recorded: a starting cap at or below that usage can block additional eligible work. |
   | `allowInitialReduction` | Leave `false` unless the reviewed first target is allowed to lower a current cap, including an unlimited cap. Broad rollout often requires this choice; inspect the exact affected users first. |
   | `maxMembers`, `concurrency` | A reviewed batch limit of at most 500 members and at most five concurrent member operations. Split larger workspaces into selected cohorts with separate approvals and disjoint users. |
   | `liveWrites` | Leave `false` during setup and preview. |

3. Obtain a workspace-scoped ChatGPT Admin key through your approved credential process. Use Usage limits read and Users read for the snapshot; add Usage limits write only for an authorized live change. The headroom pattern also needs `enterprise.analytics.usage.read`. Supply the key as `CHATGPT_ADMIN_API_KEY` from a secure runtime secret store. Do not paste it into a prompt, source file, command, or receipt. A model API key does not replace an Admin key. See [Admin key setup and permissions](https://help.openai.com/en/articles/20001407-managing-admin-keys-in-admin-console/).

4. Read the cohort and current settings, then inspect the saved enrollment and its printed hash. This makes API reads, not cap changes:

   ```bash
   node src/cli.mjs snapshot --config .private/pilot/config.json --out .private/pilot/enrollment.json
   ```

5. After reviewing the workspace, member list, source settings, period, policy, and any reduction, approve that exact local snapshot. Replace `REVIEWED_SHA256` with the printed hash:

   ```bash
   node src/cli.mjs approve --enrollment .private/pilot/enrollment.json --hash REVIEWED_SHA256
   node src/cli.mjs run --config .private/pilot/config.json --enrollment .private/pilot/enrollment.json --state .private/pilot/state
   ```

   `approve` records the local review; it does not contact the Admin API. `run` without `--apply` previews targets. Review its before and after values before proceeding. The first apply must occur within 15 minutes of capture and in the same interval slot. If it expires before any operation was saved, capture and review a new snapshot. A saved, unapplied initial reduction also expires: use the [read-only cancellation procedure](https://github.com/openai/openai-cookbook/blob/codex/daily-usage-limits/examples/chatgpt/daily_usage_limits/docs/local.md#cancel-an-unapplied-initial-operation) before a new review. An already-committed change must be reconciled instead of cancelled. After a controller has applied changes, stop and restore before changing its policy or enrollment. Retain that state and use a new private pilot directory for the new review.

## Choose where the controller runs

![Test with a small group using Codex or a local run, then use organization-managed infrastructure for ongoing operation. The controller validates scope, records a fixed target, reads back changes, and saves a receipt.](assets/control-flow.svg)

| Purpose | Path | Walkthrough |
| --- | --- | --- |
| Test and demonstrate value | Codex automation or a local run with a small group | [Codex pilot](https://github.com/openai/openai-cookbook/blob/codex/daily-usage-limits/examples/chatgpt/daily_usage_limits/docs/codex.md) or [local rehearsal](https://github.com/openai/openai-cookbook/blob/codex/daily-usage-limits/examples/chatgpt/daily_usage_limits/docs/local.md) |
| Ongoing operation on a managed host | An organization-managed virtual machine or server with scheduled execution | [Host setup and scheduler examples](https://github.com/openai/openai-cookbook/blob/codex/daily-usage-limits/examples/chatgpt/daily_usage_limits/docs/local.md) |
| Ongoing operation in cloud infrastructure | AWS deployment example, using EventBridge Scheduler and Lambda | [AWS deployment walkthrough](https://github.com/openai/openai-cookbook/blob/codex/daily-usage-limits/examples/chatgpt/daily_usage_limits/docs/aws.md) |

Choose the managed environment your organization operates and supports. Assign one scheduler and an operating team to each cohort. The [Codex pilot guide](https://github.com/openai/openai-cookbook/blob/codex/daily-usage-limits/examples/chatgpt/daily_usage_limits/docs/codex.md#5-i-move-to-managed-infrastructure) explains the transition from a pilot; the [API contract](https://github.com/openai/openai-cookbook/blob/codex/daily-usage-limits/examples/chatgpt/daily_usage_limits/docs/api-contract.md) covers conflict handling and restoration.

Local CLI changes require `liveWrites: true` in the reviewed configuration and `--apply` at invocation. AWS changes also require its deployment write gate and an `apply` or `restore` event. The scheduler templates start disabled; follow the chosen walkthrough to enable them after review.

## Stop, restore, and renew

1. Pause the chosen scheduler and set `liveWrites: false`. Confirm no run is active. Keep the private state directory: it contains the original settings and any pending operation.
2. Inspect receipts with `node src/cli.mjs inspect --state .private/pilot/state`. Reconcile an ambiguous write against current API state before another change. Do not delete a lock or journal to force progress.
3. Preview restoration with `node src/cli.mjs restore --config .private/pilot/config.json --enrollment .private/pilot/enrollment.json --state .private/pilot/state`. After authorizing restoration, temporarily enable the live write gate and repeat with `--apply`. Restore only while the confirmed period is current and the observed state matches this controller's last change. A later manual edit requires review. Verify both the original cap and its original override/inherited source, then turn the write gate off again.
4. Remove only this pilot's scheduler and disposable infrastructure using the chosen walkthrough. Revoke its dedicated key when no longer needed. Retain private receipts according to your organization's policy.

At the confirmed period end, the controller stops and its temporary limits expire. Confirm the settings that will apply afterward. To continue the plan, record the next period and review a fresh cohort snapshot before restarting. Review a new enrollment whenever the workspace's billing unit changes.

For endpoint details, see the [ChatGPT Admin API reference](https://chatgpt.com/public/admin/api-reference).

For failures and recovery actions, use the [attention-receipt table](https://github.com/openai/openai-cookbook/blob/codex/daily-usage-limits/examples/chatgpt/daily_usage_limits/docs/local.md#4-i-handle-attention-receipts). Preserve the saved intent and original settings when troubleshooting.
