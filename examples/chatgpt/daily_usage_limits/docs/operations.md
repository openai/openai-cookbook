# Configure and operate the usage-budget controller

Use this guide after choosing a budget, release schedule, and initial group. The controller is the program that calculates and applies each person's limit. Run the commands on macOS or Linux with Node.js 24 or later, from the downloaded starter folder or `examples/chatgpt/daily_usage_limits` in the repository. Windows admins can use a managed Linux host or the [AWS CloudShell setup path](aws.md#choose-your-setup-environment).

Start with [the browser example or Codex setup](get-started.md) if you have not run the fictional demonstration yet.

## Choose a policy

| Pattern | Use it when | How the cap changes |
| --- | --- | --- |
| **Fixed budget release** (`fixed_release`) | Start here for a predictable release plan for selected people or a broad cohort. | Release a configured increment each elapsed interval, up to the monthly ceiling, using the schedule and amount you choose. |
| **Individual starting limits** (`individual_staircase`) | Introduce scheduled limits during a month when people have already used different amounts. | Give each person initial headroom above their recorded usage, then add the configured increment each interval, up to the monthly ceiling. |
| **Observed usage headroom** (`observed_headroom`) | You want a reviewed power-user cohort to receive headroom based on recent observed usage. | Use recent consumption to estimate the next cap, within the monthly ceiling. |

### Fixed budget release

```text
slot = floor((current UTC time − anchor) / interval)
target cap = min(ceiling, start cap + slot × increment)
```

For a start cap of 500 credits, a weekly increment of 500, and a 2,000-credit ceiling, the targets are 500, 1,000, 1,500, and 2,000. The controller sets that cumulative monthly limit through the [ChatGPT Admin API](https://chatgpt.com/public/admin/api-reference). A repeated run in the same week keeps the same target. If a scheduled run is missed, the next run sets the target for the current week.

Choose `intervalHours: 24` for daily releases, `168` for weekly, `336` for every two weeks, or another whole-hour interval from 1 through 744. Set the increment alongside the interval: for this example, 500 weekly or 1,000 every two weeks. The controller measures intervals in elapsed UTC hours. The scheduler can check more frequently than the release interval.

### Individual starting limits

Use `individual_staircase` when you want to begin a release plan partway through the month. Capture reads each person's current monthly usage and calculates a starting limit with the headroom you choose:

```text
reviewed starting cap = min(ceiling, round up(observed period usage + initialHeadroom))
target cap = min(ceiling, reviewed starting cap + slot × increment)
```

The slot counts complete intervals since the UTC anchor. Round up to whole credits or USD cents, using the workspace's native unit. Capture saves each starting cap as `member.startCap` in the enrollment for review. Later usage does not recalculate that value during the period. Repeated runs in a slot keep the same target, and a missed run catches up to the current slot.

Initialize this policy with `--pattern individual_staircase`. Its configuration uses the headroom settings below; the enrollment supplies the individual starting caps. Omit `startCap` and `startCaps` from the policy configuration.

For a daily plan, choose `initialHeadroom: "500"`, `minimumInitialHeadroom: "100"`, `increment: "500"`, `ceiling: "2000"`, and `intervalHours: 24`. With the anchor set to the start of the plan, two people's limits would look like this:

| Monthly usage at capture | Starting limit | Limit after one day | Monthly maximum |
| --- | ---: | ---: | ---: |
| 800 credits | 1,300 | 1,800 | 2,000 |
| 1,200 credits | 1,700 | 2,000 | 2,000 |

`minimumInitialHeadroom` is the least capacity the starting limit must leave above observed usage. In this example, someone who has already used 1,950 credits cannot receive 100 more within the 2,000-credit ceiling, so capture stops for review. Both headroom settings must be positive, and the minimum cannot exceed `initialHeadroom` or the ceiling. The controller checks the remaining headroom again before the first write.

Review any reduction from an existing limit and use the same initial-reduction approval as other policies. This pattern uses current monthly usage and does not need daily usage history. At the next confirmed period, guided renewal calculates new starting caps from fresh snapshots and includes them in the new review.

### Observed usage headroom

```text
estimated headroom = observed daily average × coverageHours / 24 × multiplier
target cap = min(ceiling, max(current finite cap, start cap,
                            round up(current period usage + estimated headroom)))
```

For example, a person has used 800 credits and currently has a 900-credit limit. Their recent observed average is 100 credits per day. With 24 hours of coverage and a 1.5 multiplier, the next target is 950 credits, within the 2,000-credit monthly ceiling. `multiplierBps: 15000` represents 1.5; `coverageHours` sets how much future usage the estimate covers.

This pattern requires reported usage for each day in the selected lookback window. The [API contract](api-contract.md) explains data freshness and how the controller handles missing or corrected history.

## Choose the workspace and people

Set `workspaceId` to the workspace you administer. With `cohort.mode: "selected"`, combine user IDs, email addresses, and workspace group IDs. The snapshot resolves them to user IDs and removes duplicate people.

The following selection is illustrative. Replace its identifiers and address with values from your workspace:

```json
{
  "cohort": {
    "mode": "selected",
    "userIds": ["user_123"],
    "emails": ["alex@example.com"],
    "groupIds": ["group_456"]
  }
}
```

To capture every current member, use `"mode": "all"` with empty `userIds`, `emails`, and `groupIds` arrays. The enrollment fixes the reviewed list. Later joiners require a new enrollment. Missing or ambiguous email matches, unavailable groups, and empty groups stop capture. At the start of a run, email and group matches must still agree with the enrollment. A changed match stops new grants for review. Restoration continues to use the original enrolled user IDs.

Use separate configurations for populations with different budgets or schedules, and keep each person in one active configuration.

## Prepare a reviewed enrollment

An enrollment records the people included in the plan and their original settings. Save it, the configuration, and receipts in a private, access-controlled directory.

Confirm each person's current limit before including them. The [API contract](api-contract.md) covers supported settings. To capture a fresh snapshot, use a new output filename and that filename in subsequent `--enrollment` arguments.

1. Create a local configuration template. This example combines all three selection types. Replace the example values and omit any selector you do not need:

   ```bash
   node src/cli.mjs init --dir .private/pilot --workspace-id WORKSPACE_ID --pattern fixed_release --cohort selected --user-id USER_ID --email alex@example.com --group-id GROUP_ID --unit credit --interval-hours 168
   ```

   Repeat `--user-id`, `--email`, or `--group-id` to add selections. To capture all current members, use `--cohort all` and omit those three flags. You can also edit the arrays in `config.json` before capture.

2. Complete `.private/pilot/config.json` with your workspace and policy details. Confirm these choices before taking a snapshot:

   | Setting | What to review |
   | --- | --- |
   | `workspaceId`, `unit` | The intended workspace and its native `credit` or `usd` unit. Amounts are decimal strings. Credit caps use whole credits; USD caps use cents. Never convert between units. |
   | `cohort` | Choose `selected` with `userIds`, `emails`, and/or `groupIds`, or `all` with empty selector arrays. Review the resolved user IDs and saved email/group matches. |
   | `period` | Copy the current UTC start and end shown in Admin Console, confirm whether it is `calendar_month` or `billing_cycle`, and record the verification time and source in `verifiedAt` and `evidence`. Set `counterScopeConfirmed: true` only after confirming the counter covers that range. The API response omits period boundaries. |
   | `policy` | Pattern, its amount settings, UTC anchor, interval, and finite ceiling. Use the settings described for your chosen policy above. For a mid-period start, review consumption already recorded and the capacity each proposed limit leaves available. |
   | `allowInitialReduction` | Leave `false` unless the reviewed first target may lower a current cap or impose a finite cap on an unlimited or explicitly unset setting. Inspect every affected user before authorizing a reduction. |
   | `maxMembers` | An optional positive member-count guard. The default `null` adds no cohort-size ceiling. |
   | `concurrency`, `captureConcurrency` | Simultaneous member operations and snapshot reads, respectively. Both start at `1`; increase gradually against observed API throughput. |
   | `initialReviewMaxAgeMinutes` | Time allowed from capture start to first application. The default is `15`; choose a positive whole number no longer than the confirmed period. Capture, review, upload, and queued processing must fit this window and the same release interval. Changing it requires a new policy review. |
   | `apiLimits` | Optional positive `maxPages` and `maxRows` guards for paginated reads. The adapter defaults are 1,000 pages and 100,000 rows. Reaching a guard stops the read instead of using a partial list. |
   | `liveWrites` | Leave `false` during setup and preview. |

   The initializer also accepts `--max-members none|POSITIVE_INTEGER`, `--concurrency`, `--capture-concurrency`, `--initial-review-max-age-minutes`, `--api-max-pages`, and `--api-max-rows`. The last five take positive whole numbers. Choose a review window that covers measured capture, review, and initial processing time; a window never extends the confirmed period or release interval.

3. Obtain a workspace-scoped ChatGPT Admin key through your approved credential process. Use Usage limits read and Users read for the snapshot; add Usage limits write only for an authorized live change. Group selection also needs `chatgpt.enterprise.directory.read`. The headroom pattern needs `enterprise.analytics.usage.read`. Supply the key as `CHATGPT_ADMIN_API_KEY` from a secure runtime secret store. Keep it out of prompts, source files, commands, and receipts. API Platform inference keys cannot authenticate these requests. See [Admin key setup and permissions](https://help.openai.com/en/articles/20001407-managing-admin-keys-in-admin-console/).

4. Read the cohort and current settings, then inspect the saved enrollment and its printed hash. This command performs read-only API requests:

   ```bash
   node src/cli.mjs snapshot --config .private/pilot/config.json --out .private/pilot/enrollment.json
   ```

5. After reviewing the workspace, member list, source settings, period, policy, and any reduction, approve that exact local snapshot. Replace `REVIEWED_SHA256` with the printed hash:

   ```bash
   node src/cli.mjs approve --enrollment .private/pilot/enrollment.json --hash REVIEWED_SHA256
   node src/cli.mjs run --config .private/pilot/config.json --enrollment .private/pilot/enrollment.json --state .private/pilot/state
   ```

   `approve` records the review locally. `run` without `--apply` previews targets. Review its before and after values before proceeding. The first apply must occur within `initialReviewMaxAgeMinutes` of capture start and in the same interval slot. The default is 15 minutes. Capture records both its start and completion times; a slow capture does not extend the review deadline. A new initial operation checks freshness through its first write attempt. Recovery can retry an already saved exact increase after that window for fixed releases or observed headroom. Initial reductions and all first writes for individual starting limits remain bound to both the review age and their original slot. If a review expires before any operation was saved, capture and review a new snapshot. For a saved, unapplied initial operation that has expired, use the [read-only cancellation procedure](local.md#cancel-an-unapplied-initial-operation) before a new review. Reconcile any already-committed change. After a controller has applied changes, stop and restore before changing its budget policy or membership. Retain that state and use a new private pilot directory for a replacement local pilot. To continue the same policy into the next period on AWS, use [guided renewal](aws.md#7-renew-the-next-period).

## Stop, restore, and renew

1. Pause the chosen scheduler and set `liveWrites: false`. Confirm no run is active. Keep the private state directory: it contains the original settings and any pending operation.
2. Inspect receipts with `node src/cli.mjs inspect --state .private/pilot/state`. Reconcile an ambiguous write against current API state before another change. Do not delete a lock or journal to force progress.
3. Preview restoration with `node src/cli.mjs restore --config .private/pilot/config.json --enrollment .private/pilot/enrollment.json --state .private/pilot/state`. After authorizing restoration, temporarily enable the live write gate and repeat with `--apply`. Restore only while the confirmed period is current and the observed state matches this controller's last change. A later manual edit requires review. Verify both the original cap and its original override/inherited source, then turn the write gate off again.
4. Remove only this pilot's scheduler and disposable infrastructure using the chosen walkthrough. Revoke its dedicated key when no longer needed. Retain private receipts according to your organization's policy.

At the confirmed period end, the controller stops and its temporary limits expire. Confirm the settings that apply afterward. On AWS, [guided renewal](aws.md#7-renew-the-next-period) carries the existing policy and people forward, reads their current settings, and prepares the opening limits for review. Confirm the next period dates and approve that review, then preview and enable the renewed plan on the same deployment. The Admin API does not provide next-period dates, so the helper does not guess them. A billing-unit change requires a separate policy review.

For endpoint details, see the [ChatGPT Admin API reference](https://chatgpt.com/public/admin/api-reference).

For failures and recovery actions, use the [attention-receipt table](local.md#4-handle-attention-receipts). Preserve the saved intent and original settings when troubleshooting.
