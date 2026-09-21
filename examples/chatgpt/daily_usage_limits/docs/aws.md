# Deploy the controller on AWS

Deploy the controller on AWS to run scheduled releases independently of an individual's computer. This serverless design uses one Lambda function for dispatch and member processing:

**EventBridge Scheduler → Lambda dispatcher → SQS → Lambda workers**

The queue spreads an enrollment across invocations. Worker concurrency controls how much work reaches the Admin API at once. This fits AWS's guidance to [use direct EventBridge and SQS triggers for straightforward message processing](https://docs.aws.amazon.com/lambda/latest/dg/with-step-functions.html).

| Service | Purpose |
| --- | --- |
| EventBridge Scheduler, Lambda, and SQS | Start hourly runs, queue each person's work, and resume unfinished processing. |
| DynamoDB | Preserve original settings, intended changes, progress, and receipts across invocations. |
| Secrets Manager | Supply the Admin key to the runtime. |
| CloudWatch and SNS | Record operational signals and notify the operating owner. |
| S3 | Store the exact version of the deployment package. |

The template starts with the schedule and queue processing **disabled**, and live writes **off**. It processes larger enrollments across multiple invocations. Begin with one person, then try 5 to 25 people and measure completion time before expanding. Configure worker capacity and read concurrency around the Admin API throughput you observe.

Run commands from the extracted starter folder, or from `examples/chatgpt/daily_usage_limits` in the full repository. You need an approved AWS account and region, AWS CLI v2, deployment permissions, and three existing resources: a private versioned S3 artifact bucket, an operations SNS topic with a reachable subscriber, and a Secrets Manager secret. The secret contains `{"apiKey":"..."}` using a workspace-scoped ChatGPT Admin key with the [required permissions](api-contract.md). Supply it through your organization's credential process. Keep the key out of source, parameters, command arguments, and logs. The deployment has no public endpoint.

## Choose your setup environment

Use Bash on macOS or Linux for this walkthrough. From Windows, use your organization's managed Linux host or [AWS CloudShell](https://docs.aws.amazon.com/cloudshell/latest/userguide/welcome.html) in the AWS console. CloudShell provides a Linux terminal in your browser and uses your signed-in AWS identity.

1. Open CloudShell in the approved account and region, then select Bash.
2. Run `node --version`, `npm --version`, and `aws --version`. Use Node.js 24 or later and AWS CLI v2. Your technology team can provide the approved Node.js runtime if needed.
3. Upload the starter ZIP using **Actions > Upload file**, then run `unzip chatgpt-usage-budget-starter.zip` followed by `cd chatgpt-usage-budget-starter`.
4. Run `node src/demo.mjs`. Look for the fictional limits moving from 2,000 to 500, then 1,000, before restoration to 2,000.

Use CloudShell for setup and inspection. The deployed AWS services run after your browser session ends. Preserve private enrollment and configuration records in your organization's approved storage.

## 1. Test the kit you will deploy

Use a fresh extraction of the starter download for these checks. Record its SHA-256 and the matching source revision as described in [Verify the starter download](verification.md#verify-the-starter-download). Build the deployment package from that same folder.

```bash
umask 077
mkdir -p .private
npm test
node src/demo.mjs
npm ci --prefix aws --ignore-scripts --no-audit --no-fund
npm run package --prefix aws
```

The tests use injected AWS transports and a synthetic Admin API. They cover control integrity, queued work, progress, duplicate delivery, recovery, and restoration. The `npm ci` command installs the pinned SDK dependencies needed by the upload and status helpers later in this guide. Packaging installs its own dependencies in a temporary staging directory and writes `aws/dist/controller.zip`, its SHA-256, and `source-manifest.json`. Review the manifest: private configuration, enrollment, credentials, fixtures, and receipts belong outside the deployment ZIP.

Packaging works in PowerShell or a terminal on Windows, macOS, and Linux. Continue the preparation and deployment steps in Bash on macOS or Linux. For an optional local CloudFormation schema check:

```bash
python3 -m venv .private/cfn-validation
.private/cfn-validation/bin/pip install cfn-lint==1.40.4
.private/cfn-validation/bin/cfn-lint -t aws/template.yaml
```

## 2. Prepare a disabled deployment

These steps upload code and create billable AWS resources. Obtain the account owner's approval for the account, region, operating owner, cost, expiry, and deployment role. Set `AWS_REGION` to the approved region. Set `AWS_PROFILE` for a named local CLI profile; CloudShell uses your signed-in identity.

1. Run `aws sts get-caller-identity`. Confirm the account and role. Check that the artifact bucket is private and versioned, and that the secret and SNS topic are in the intended account and region. If a customer-managed KMS key protects the secret, confirm that its policy permits the generated runtime role.
2. Set the nonsecret shell variables `DAILY_LIMIT_STACK`, `DAILY_LIMIT_CODE_BUCKET`, and `DAILY_LIMIT_CODE_KEY` to the chosen stack name, artifact bucket, and a unique object key. Upload the package:

   ```bash
   aws s3api put-object --bucket "$DAILY_LIMIT_CODE_BUCKET" --key "$DAILY_LIMIT_CODE_KEY" --body aws/dist/controller.zip --query VersionId --output text
   ```

   Record the returned version ID. The template requires a specific S3 object version.
3. Copy `aws/parameters.example.json` to `.private/aws-parameters.json` and replace every `REPLACE_...` value. Set `DAILY_LIMIT_DEPLOYMENT` to its `DeploymentId`. Set `PilotExpiresAt` no later than the confirmed period end, using UTC `YYYY-MM-DDTHH:MM:SSZ`. Leave the all-zero bootstrap `ControlSha256`, `ScheduleState=DISABLED`, `ScheduledAction=preview`, `WorkProcessingEnabled=false`, `ApplyEnabled=false`, and `AllowedWriteAction=none`.
4. Review the template and parameters, then create the disabled stack:

   ```bash
   aws cloudformation create-stack --stack-name "$DAILY_LIMIT_STACK" --template-body file://aws/template.yaml --parameters file://.private/aws-parameters.json --capabilities CAPABILITY_IAM
   aws cloudformation wait stack-create-complete --stack-name "$DAILY_LIMIT_STACK"
   aws cloudformation describe-stacks --stack-name "$DAILY_LIMIT_STACK" --query 'Stacks[0].Outputs'
   ```

   Set `DAILY_LIMIT_FUNCTION`, `DAILY_LIMIT_TABLE`, `DAILY_LIMIT_GROUP`, and `DAILY_LIMIT_MAPPING` from the `FunctionName`, `StateTableName`, `ScheduleGroupName`, and `WorkMappingId` outputs. Record the work queue and failure queue URLs.
5. Read back the deployed settings:

   ```bash
   aws lambda get-function-configuration --function-name "$DAILY_LIMIT_FUNCTION" --query '{Runtime:Runtime,Timeout:Timeout,MemorySize:MemorySize,Variables:Environment.Variables}'
   aws lambda get-event-source-mapping --uuid "$DAILY_LIMIT_MAPPING"
   aws scheduler get-schedule --group-name "$DAILY_LIMIT_GROUP" --name usage-limit-check
   ```

   Expect Node.js 24, the configured timeout and memory, `APPLY_ENABLED=false`, `ALLOWED_WRITE_ACTION=none`, a disabled event-source mapping, and a disabled schedule. Check the expiry, control hash, secret ARN, target role, retry settings, and failure queues.

The runtime role reads the reviewed controls and one secret. Its writes cover state, locks, progress, receipts, metrics, and its work queue. The operator who uploads controls has separate deployment permissions. Protect both identities through your normal access review.

### Configure capacity

| Parameter | Default | Purpose |
| --- | ---: | --- |
| `WorkBatchSize` | 1 | Queue records delivered in one Lambda invocation, from 1 to 10. |
| `RecordConcurrency` | 1 | Records processed concurrently inside an invocation, up to its batch size. |
| `WorkerConcurrency` | 2 | Maximum concurrent SQS worker invocations, subject to account quotas and API capacity. |
| `DispatchBatchSize` | 100 | Members queued by one feeder invocation before continuing from its saved position. |
| `WorkerMemorySize` | 1,024 MB | Memory for the runtime and full approved enrollment loaded by each worker. |
| `WorkerTimeoutSeconds` | 120 | Choose 120, 300, 600, or 900 seconds. The template derives a longer lease and queue visibility timeout. |
| `MaxReceiveCount` | 10 | Delivery-attempt limit before retry exhaustion or queue redrive. |

These settings control processing capacity. `maxMembers` in the policy remains an optional enrollment guard; its default is `null`. Choose `captureConcurrency`, API read bounds, and `initialReviewMaxAgeMinutes` before capture. Measure the complete first rollout, including capture, review, upload, and queued work. It must fit the configured review window and the same release interval.

## 3. Verify AWS delivery

Run a manual probe. It records a receipt without accessing the Admin API:

```bash
node aws/event.mjs probe .private/aws-probe.json
aws lambda invoke --function-name "$DAILY_LIMIT_FUNCTION" --cli-binary-format raw-in-base64-out --payload file://.private/aws-probe.json .private/aws-probe-result.json
```

Expect `ok: true`, `action: probe`, `apiAccessed: false`, `capWrites: 0`, and a private `aws_probe` receipt. This verifies Lambda invocation and receipt storage. Check the CLI metadata for `FunctionError`, including when the HTTP status is `200`.

To verify timed delivery, create one temporary one-time schedule in the stack's EventBridge Scheduler group, a few minutes ahead in UTC. Select the deployed Lambda, the existing scheduler execution role and delivery-failure queue, no flexible window, and automatic deletion after completion. Use this input:

```json
{"version":1,"action":"probe","scheduledAt":"<aws.scheduler.scheduled-time>"}
```

Match the timed invocation to its private receipt and verify that the temporary schedule disappears. Keep the recurring `usage-limit-check` schedule disabled.

## 4. Check the workspace connection

Before configuring budgets or capturing members, verify access from the deployed Lambda. Keep the schedule, queue processing, and writes disabled. The all-zero bootstrap control hash can remain in place; this check needs no enrollment or uploaded controls.

Set the nonsecret `DAILY_LIMIT_WORKSPACE` variable to the exact workspace ID. Confirm that `PilotExpiresAt` is still in the future, then generate and invoke a fresh event:

```bash
node aws/event.mjs check_connection .private/aws-connection.json "$DAILY_LIMIT_WORKSPACE"
aws lambda invoke --function-name "$DAILY_LIMIT_FUNCTION" --cli-binary-format raw-in-base64-out --payload file://.private/aws-connection.json .private/aws-connection-result.json
cat .private/aws-connection-result.json
```

Expect `ok: true`, `action: check_connection`, the intended `workspaceId`, `unit: credit` or `unit: usd`, `usersRead: true`, `capWrites: 0`, and `receiptRecorded: true`. Save the `checkId` with the result. Check the invocation metadata for `FunctionError` as well as the result's `ok` field.

The runtime reads its configured secret, verifies the workspace, reads at most one member, and checks that member's monthly-usage response for the billing unit. It returns no member details. This establishes credential and read access for those routes. Group selection, usage history, individual cap responses, and approved writes are checked later in their respective workflows.

If `ok` is false, use the returned code:

| Code | What to check |
| --- | --- |
| `ADMIN_HTTP_401` | The API rejected the credential. Confirm that the secret contains a current ChatGPT Admin key for this workspace; check its status, expiry, and creator's access in Admin Console. |
| `ADMIN_HTTP_403` | The API denied access. Confirm the workspace ID, workspace eligibility, and the key's `chatgpt.enterprise.usage_limit.read` and `chatgpt.enterprise.user.read` permissions. |
| `CONNECTION_MEMBER_UNAVAILABLE` | No member was returned to establish the unit. Verify active workspace membership and retry after directory updates. |
| `USAGE_UNIT_UNAVAILABLE` | No supported billing unit was confirmed. Review the workspace billing setup before selecting credit or USD policy amounts. |
| `INVALID_SECRET_FORMAT` | The configured secret must contain valid JSON with a nonempty `apiKey` string. |
| `CONNECTION_CHECK_FAILED` | Check the runtime role's access to the configured secret and optional KMS key, along with AWS connectivity. |

The [Admin key access guide](https://help.openai.com/en/articles/20001407-managing-admin-keys-in-admin-console/) explains where to review workspace access and permissions. Keep secrets and raw service error bodies out of shared reports. Correct the identified issue, then generate a new event and rerun this check; authentication failures are not retried automatically. If `receiptRecorded` is false, resolve receipt storage before continuing.

## 5. Prepare the budget and preview the limits

Rehearse preparing the private controls:

```bash
node src/cli.mjs init --dir .private/aws-rehearsal --pattern fixed_release --cohort all --unit credit --interval-hours 168 --synthetic --allow-initial-reduction
node src/cli.mjs snapshot --config .private/aws-rehearsal/config.json --out .private/aws-rehearsal/enrollment.json --synthetic
```

Review the three fictional members and their proposed weekly releases. Replace `REVIEWED_SHA256` with the snapshot command's printed hash:

```bash
node src/cli.mjs approve --enrollment .private/aws-rehearsal/enrollment.json --hash REVIEWED_SHA256
node aws/prepare-control.mjs .private/aws-rehearsal/config.json .private/aws-rehearsal/enrollment.json cookbook-usage-limits .private/aws-rehearsal/controls
node aws/event.mjs probe .private/aws-rehearsal/probe.json
```

The preparation command creates a new private directory containing `part-00000000.json` and any additional numbered parts, plus `manifest.json`. The printed `ControlSha256` binds the manifest and its verified chain of parts to the complete configuration and approved enrollment. Each stored part stays below DynamoDB's item-size limit. Keep rehearsal controls separate from live controls.

Prepare a live read-only preview:

1. Complete the [enrollment steps](operations.md#prepare-a-reviewed-enrollment) in `.private/aws-live`, with no other writer for those users. Confirm the workspace, unit, period, selectors, resolved IDs, and original settings. Keep `liveWrites: false`. Start with one person and a review window that covers the workflow.
2. Prepare its controls in a new directory:

   ```bash
   node aws/prepare-control.mjs .private/aws-live/config.json .private/aws-live/enrollment.json "$DAILY_LIMIT_DEPLOYMENT" .private/aws-live/controls
   ```

   Set `DAILY_LIMIT_CONTROL_SHA` to the printed `ControlSha256`. Put the same value in `.private/aws-parameters.json`.
3. Upload with the deployment identity. The helper validates the local parts, accepts identical previously uploaded parts, and installs the manifest last:

   ```bash
   node aws/upload-control.mjs .private/aws-live/controls "$DAILY_LIMIT_TABLE" "$DAILY_LIMIT_CONTROL_SHA"
   ```

   Set `WorkProcessingEnabled=true` in the parameters while leaving the recurring schedule and write gate off. Apply and inspect the stack update:

   ```bash
   aws cloudformation update-stack --stack-name "$DAILY_LIMIT_STACK" --template-body file://aws/template.yaml --parameters file://.private/aws-parameters.json --capabilities CAPABILITY_IAM
   aws cloudformation wait stack-update-complete --stack-name "$DAILY_LIMIT_STACK"
   aws lambda get-event-source-mapping --uuid "$DAILY_LIMIT_MAPPING"
   ```

4. Start a preview run:

   ```bash
   node aws/event.mjs preview .private/aws-preview.json
   aws lambda invoke --function-name "$DAILY_LIMIT_FUNCTION" --cli-binary-format raw-in-base64-out --payload file://.private/aws-preview.json .private/aws-preview-result.json
   ```

   A successful response means the run was accepted. Set `DAILY_LIMIT_RUN` to its `runId`, then inspect processing:

   ```bash
   node aws/run-status.mjs "$DAILY_LIMIT_TABLE" "$DAILY_LIMIT_DEPLOYMENT" "$DAILY_LIMIT_RUN"
   ```

### Read run progress

| Field | Meaning |
| --- | --- |
| `total` | People in this reviewed enrollment. |
| `queued` | People whose work has been dispatched. |
| `completed` | People with a recorded final outcome for this run. |
| `succeeded` | Successful outcomes, including previews or a limit already handled in this slot. |
| `attention` | Final outcomes that need review. |
| `outstanding` | People without a final outcome yet. |

A clean run reaches `completed = total`, `outstanding = 0`, and `attention = 0`. A started run or an empty visible queue alone does not establish completion. Inspect every private member receipt to confirm the intended cap, unit, ceiling, and original source.

Use the DynamoDB console's item explorer to query `PK = RECEIPT#<DeploymentId>` for detailed receipts. Run progress and per-member outcomes use `PK = RUN#<DeploymentId>#<runId>`. Keep identifiers and settings private. Record live cap enforcement separately during the approved apply trial.

## 6. Review the first change and recurring schedule

1. Obtain approval for the member caps, any initial reduction, the bounded trial, and restoration. Coordinate manual admin edits and disable other writers for these users. Separate stacks have separate lock tables, so assign disjoint users to them.
2. Finish or cancel existing runs using the stop procedure below. Keep the schedule and work processing disabled while replacing controls. Set `liveWrites: true` in the reviewed configuration, then prepare a **new** output directory. The policy approval hash stays the same, but the AWS control hash changes:

   ```bash
   node aws/prepare-control.mjs .private/aws-live/config.json .private/aws-live/enrollment.json "$DAILY_LIMIT_DEPLOYMENT" .private/aws-live/controls-apply
   ```

3. Set `DAILY_LIMIT_PREVIOUS_SHA` to the installed control hash, and `DAILY_LIMIT_CONTROL_SHA` to the newly printed hash. Upload the replacement with an explicit check of the old version:

   ```bash
   node aws/upload-control.mjs .private/aws-live/controls-apply "$DAILY_LIMIT_TABLE" "$DAILY_LIMIT_CONTROL_SHA" "$DAILY_LIMIT_PREVIOUS_SHA"
   ```

   Set the new `ControlSha256`, `ApplyEnabled=true`, `AllowedWriteAction=apply`, and `WorkProcessingEnabled=true` in the stack parameters, keeping `ScheduleState=DISABLED`. Set `RunEventsNotBefore` to the current UTC time so earlier start events remain excluded. Apply the stack update using the command under “Prepare the budget and preview the limits,” and verify its settings. A replacement conflict requires reading and reviewing the current controls before another attempt.
4. Generate an `apply` event with `node aws/event.mjs apply .private/aws-apply.json`, invoke it as in the preview, and track its new `runId` to completion. Verify each absolute cap and temporary expiry by independent API readback. Repeat the current-slot run and confirm that no additional budget is released. Resolve attention results before expanding.
5. With recurring delivery still disabled, complete a supervised restoration trial using the stop and restore procedure below. Restoration closes that pilot. For ongoing operation within the same period, use a separate reviewed enrollment and fresh state, retaining the trial records. Prove its bounded manual apply, then set `ScheduledAction=apply` and `ScheduleState=ENABLED` through a reviewed stack update. Keep `AllowedWriteAction=apply` and a current `RunEventsNotBefore` cutoff. Verify a real hourly trigger and completed member outcomes. Later monthly renewals use the same ongoing deployment, as described next.

The policy's `intervalHours` determines release frequency. Keep the same state table throughout an enrollment; it contains reconciliation records and original settings.

## 7. Renew the next period

Keep the existing AWS stack, state table, code package, credentials, and operating policy. After the previous period ends, the renewal helper reads the saved records and current API settings, then prepares the same people's opening limits for review. You confirm the new dates because the Admin API does not report the next period boundaries.

1. Stop the schedule and queue processing, set `ApplyEnabled=false` and `AllowedWriteAction=none`, and advance `RunEventsNotBefore` using the first step under [Stop, restore, and verify cleanup](#9-stop-restore-and-verify-cleanup). Cancel unfinished runs. Preserve the stack and table. Every enrolled member needs a settled previous state; pending writes, authorization halts, changed membership, or conflicting settings must be resolved before renewal.
2. Copy the `period` object from the previous configuration into `.private/aws-next-period.json`. Confirm the new current period in Admin Console, then replace `start`, `end`, `verifiedAt`, and `evidence`. The file contains only this object; the following dates are illustrative:

   ```json
   {
     "kind": "calendar_month",
     "start": "2030-05-01T00:00:00Z",
     "end": "2030-06-01T00:00:00Z",
     "verifiedAt": "2030-05-01T00:05:00Z",
     "evidence": "Current period and counter scope confirmed in Admin Console",
     "counterScopeConfirmed": true
   }
   ```

   Keep `kind` consistent with the verified calendar-month or billing-cycle setting. The previous period must have ended, and the new period must already be current. Renewal retains the budget amounts, release interval, and frozen member list. Its release schedule starts at the new period boundary; a later renewal previews the cumulative release for the intervals already elapsed.
3. With your AWS deployment identity and approved credential provider supplying `CHATGPT_ADMIN_API_KEY`, prepare the next review. Point `--config` and `--enrollment` to the prior period's installed controls and choose a new private output directory:

   ```bash
   node aws/renew-period.mjs prepare --stack "$DAILY_LIMIT_STACK" --config .private/aws-live/config.json --enrollment .private/aws-live/enrollment.json --period .private/aws-next-period.json --out .private/aws-renewal
   ```

   This command verifies the stopped stack and waits for old workers to finish before capturing current settings. It makes read-only AWS and Admin API requests, saves `config.json`, `enrollment.json`, and `activation.json` locally, and prints the review hash. Review the period, each person's current settings and opening limit, and any reductions. Replace `REVIEWED_SHA256` with that exact hash:

   ```bash
   node src/cli.mjs approve --enrollment .private/aws-renewal/enrollment.json --hash REVIEWED_SHA256
   ```

4. Activate the reviewed controls on the existing stack:

   ```bash
   node aws/renew-period.mjs activate --stack "$DAILY_LIMIT_STACK" --dir .private/aws-renewal
   ```

   Activation verifies that the deployed schedule, workers, and write gates remain off. It reuses the completed worker wait when the stopped configuration is unchanged, uploads the reviewed controls conditionally, and updates the same stack's control hash, expiry, and cutoff. The code package, resources, and saved history remain in place. Expect `activated: true`, `schedule: DISABLED`, `workers: Disabled`, `writes: false`, and `capWrites: 0`.

   Keep `activation.json`. If a network interruption leaves the AWS update uncertain, rerun **the same activation command with the same directory**. The saved journal lets it inspect and resume that update.
5. Use `.private/aws-renewal/config.json` and `.private/aws-renewal/enrollment.json` for the next preview and first apply, with the existing state table. Refresh your saved parameters before another stack update:

   ```bash
   aws cloudformation describe-stacks --stack-name "$DAILY_LIMIT_STACK" --query 'Stacks[0].Parameters' --output json > .private/aws-parameters.json
   ```

   Set `WorkProcessingEnabled=true`, keeping the schedule and writes off, then update the stack and start a preview using [the preview commands](#5-prepare-the-budget-and-preview-the-limits). For the renewed files, follow steps 1 through 4 under [Review the first change and recurring schedule](#6-review-the-first-change-and-recurring-schedule) to authorize and verify the first apply. After successful readback, enable `ScheduledAction=apply` and `ScheduleState=ENABLED` and verify a timed run. The existing review window covers capture, review, activation, and the first queued change.

If that window expires before any member starts the new period, prepare another review in a new directory using the original previous-period files and the same confirmed next-period object. The helper verifies that every prior state is still settled and unchanged. Once any member has transitioned, keep the reviewed files and reconcile the partial run; recapture must not bypass a pending operation.

Renewal begins a new period for the same policy and people. Use a separate policy review for a new billing unit, changed budget, or different membership. A restored pilot cannot be reopened within its original period through this command.

## 8. Verify failures and alerts

SQS delivery can repeat a message. The template follows [AWS's SQS configuration guidance](https://docs.aws.amazon.com/lambda/latest/dg/services-sqs-configure.html): queue visibility is six times the worker timeout, the retry limit is at least five deliveries, and partial batch responses return only failed records. The controller reconciles saved absolute targets before another write. See [Lambda's SQS processing behavior](https://docs.aws.amazon.com/lambda/latest/dg/with-sqs.html) and [partial batch responses](https://docs.aws.amazon.com/lambda/latest/dg/services-sqs-errorhandling.html).

| Signal | Action |
| --- | --- |
| `ControllerIssue` or a nonzero run `attention` count | Inspect private member receipts and the saved intent. |
| Run `outstanding` remains above zero | Check its feeder position, work queue, retries, expiry, and worker capacity. |
| Lambda `Errors` or `Throttles` | Inspect runtime failures, quotas, and queued work. |
| Delivery-failure queue contains a message | Scheduler exhausted its delivery retries. |
| Execution-failure queue contains a message | An asynchronous start invocation exhausted Lambda retries. |
| Work-failure queue contains a message | A feeder or member record exhausted queue delivery attempts. Reconcile it with the run's outstanding work. |
| Oldest-work or missing-run alarm | Inspect queue delay, run progress, schedule, and expiry. A successful run start does not mean every member finished. |
| Failure-destination alarm | Inspect whether Scheduler or Lambda could deliver its failure record. |

Verify that the operating owner receives an alarm. Test a controlled failure and recovery with writes off. Keep delivery failure, queue failure, and member attention results distinct in the record.

The feeder checkpoints its position. Workers reserve time for readback before writing, and respect saved retry times. Rate-limit responses delay the run; raising concurrency does not override that delay. A timeout can leave a pending intent. Reconcile that saved target and current state before retrying. Preserve the table throughout recovery.

For a repaired authentication failure, keep the recurring schedule off and start a `resume_auth` run. It checks current state and clears matching authorization halts without changing caps. Preview and explicitly retry the original operation afterward. An expired, unapplied initial reduction can be closed with `cancel_initial` after checking that its original state is untouched. Both actions use the same controls and state; see [recovery details](local.md#4-handle-attention-receipts).

State, original settings, controls, and unresolved intents persist. Receipt and run records have a retention period; DynamoDB removes expired items asynchronously. Apply your retention policy to the table, backups, logs, artifact versions, and queues. See [DynamoDB TTL behavior](https://docs.aws.amazon.com/amazondynamodb/latest/developerguide/TTL.html).

## 9. Stop, restore, and verify cleanup

1. Set `ScheduleState=DISABLED`, `WorkProcessingEnabled=false`, `ApplyEnabled=false`, and `AllowedWriteAction=none`. Advance `RunEventsNotBefore` to the current UTC time; `date -u +%Y-%m-%dT%H:%M:%SZ` prints a suitable value. Apply the stack update and read back the schedule, event-source mapping, cutoff, and gates. Wait at least the configured worker timeout after the update completes for old in-flight workers to finish, and inspect their receipts. The cutoff rejects earlier asynchronous start events and stops older queued runs.
2. Explicitly cancel each unfinished run you are closing before resuming processing for another action. Set `DAILY_LIMIT_RUN` to the run being stopped:

   ```bash
   node aws/event.mjs cancel_run .private/aws-cancel-run.json "$DAILY_LIMIT_RUN"
   aws lambda invoke --function-name "$DAILY_LIMIT_FUNCTION" --cli-binary-format raw-in-base64-out --payload file://.private/aws-cancel-run.json .private/aws-cancel-run-result.json
   node aws/run-status.mjs "$DAILY_LIMIT_TABLE" "$DAILY_LIMIT_DEPLOYMENT" "$DAILY_LIMIT_RUN"
   ```

   Expect `status: cancelled`. Cancellation stops remaining queued work for that run; it preserves completed changes and pending controller state. Keep all run IDs from starts and receipts so every unfinished run can be accounted for.
3. While the pilot and confirmed period remain current, review restoration. Resolve any pending apply using its saved target first. Keep the recurring schedule off. Set `ApplyEnabled=true`, `AllowedWriteAction=restore`, and `WorkProcessingEnabled=true`, with the current cutoff retained. After the stack update completes, generate a fresh `restore` event, invoke it, and track its new run ID. The action gate excludes apply runs during restoration. Verify every member's original settings and source by independent API readback. Turn processing and writes off after completion, set `AllowedWriteAction=none`, and advance the cutoff again. If the period ended, have the workspace admin inspect current settings and approve any required correction.
4. Record the stack outputs and owned artifact version. Archive required receipts and restoration evidence, then delete the stack:

   ```bash
   aws cloudformation delete-stack --stack-name "$DAILY_LIMIT_STACK"
   aws cloudformation wait stack-delete-complete --stack-name "$DAILY_LIMIT_STACK"
   ```

5. Verify that the Lambda, event-source mapping, schedule/group, queues, roles, and alarms are gone. The table and log group remain under `DeletionPolicy: Retain`. Review their retention obligations before explicitly deleting those owned resources. Delete only the precise uploaded S3 object version when it is no longer needed.
6. Verify the retained-resource inventory and any temporary probe schedule. Revoke the dedicated ChatGPT key if no longer needed. The existing secret, bucket, SNS topic/subscriptions, and optional KMS key are outside this stack.

Pilot expiry stops runtime work and scheduled invocation. Complete restoration and cleanup separately. Retained resources continue to incur applicable charges.
