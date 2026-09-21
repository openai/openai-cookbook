# Deploy the controller on AWS

Deploy the controller on AWS to run scheduled releases independently of an individual's computer. Amazon EventBridge Scheduler starts a run hourly. A resumable feeder places one work item per enrolled person on an Amazon SQS queue. Lambda workers process those items, and DynamoDB preserves progress, original settings, intended caps, and receipts.

The template starts with the schedule and queue processing **disabled**, and live writes **off**. It processes larger enrollments across multiple invocations. Begin with one person, then try 5 to 25 people and measure completion time before expanding. Configure worker capacity and read concurrency around the Admin API throughput you observe.

Run commands from the extracted starter folder, or from `examples/chatgpt/daily_usage_limits` in the full repository. You need an approved AWS account and region, AWS CLI v2, deployment permissions, and three existing resources: a private versioned S3 artifact bucket, an operations SNS topic with a reachable subscriber, and a Secrets Manager secret. The secret contains `{"apiKey":"..."}` using a workspace-scoped ChatGPT Admin key with the [required permissions](api-contract.md). Supply it through your organization's credential process. Keep the key out of source, parameters, command arguments, and logs. The deployment has no public endpoint.

## Choose your setup environment

Use Bash on macOS or Linux for this walkthrough. From Windows, use your organization's managed Linux host or [AWS CloudShell](https://docs.aws.amazon.com/cloudshell/latest/userguide/welcome.html) in the AWS console. CloudShell provides a Linux terminal in your browser and uses your signed-in AWS identity.

1. Open CloudShell in the approved account and region, then select Bash.
2. Run `node --version`, `npm --version`, and `aws --version`. Use Node.js 24 or later and AWS CLI v2. Your technology team can provide the approved Node.js runtime if needed.
3. Upload the starter ZIP using **Actions > Upload file**, then run `unzip chatgpt-usage-budget-starter.zip` followed by `cd chatgpt-usage-budget-starter`.
4. Run `node src/demo.mjs`. Look for the fictional limits moving from 2,000 to 500, then 1,000, before restoration to 2,000.

Use CloudShell for setup and inspection. The deployed AWS services run after your browser session ends. Preserve private enrollment and configuration records in your organization's approved storage.

## 1. Check the AWS example locally

```bash
node --test test/aws*.test.mjs
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

## 3. Verify delivery and preview the limits

Run a manual probe. It records a receipt without accessing the Admin API:

```bash
node aws/event.mjs probe .private/aws-probe.json
aws lambda invoke --function-name "$DAILY_LIMIT_FUNCTION" --cli-binary-format raw-in-base64-out --payload file://.private/aws-probe.json .private/aws-probe-result.json
```

Expect `ok: true`, `action: probe`, and a private `aws_probe` receipt. Check the CLI metadata for `FunctionError`, including when the HTTP status is `200`.

To verify timed delivery, create one temporary one-time schedule in the stack's EventBridge Scheduler group, a few minutes ahead in UTC. Select the deployed Lambda, the existing scheduler execution role and delivery-failure queue, no flexible window, and automatic deletion after completion. Use this input:

```json
{"version":1,"action":"probe","scheduledAt":"<aws.scheduler.scheduled-time>"}
```

Match the timed invocation to its private receipt and verify that the temporary schedule disappears. Keep the recurring `usage-limit-check` schedule disabled.

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

## 4. Review the first change and recurring schedule

1. Obtain approval for the member caps, any initial reduction, the bounded trial, and restoration. Coordinate manual admin edits and disable other writers for these users. Separate stacks have separate lock tables, so assign disjoint users to them.
2. Finish or cancel existing runs using the stop procedure below. Keep the schedule and work processing disabled while replacing controls. Set `liveWrites: true` in the reviewed configuration, then prepare a **new** output directory. The policy approval hash stays the same, but the AWS control hash changes:

   ```bash
   node aws/prepare-control.mjs .private/aws-live/config.json .private/aws-live/enrollment.json "$DAILY_LIMIT_DEPLOYMENT" .private/aws-live/controls-apply
   ```

3. Set `DAILY_LIMIT_PREVIOUS_SHA` to the installed control hash, and `DAILY_LIMIT_CONTROL_SHA` to the newly printed hash. Upload the replacement with an explicit check of the old version:

   ```bash
   node aws/upload-control.mjs .private/aws-live/controls-apply "$DAILY_LIMIT_TABLE" "$DAILY_LIMIT_CONTROL_SHA" "$DAILY_LIMIT_PREVIOUS_SHA"
   ```

   Set the new `ControlSha256`, `ApplyEnabled=true`, `AllowedWriteAction=apply`, and `WorkProcessingEnabled=true` in the stack parameters, keeping `ScheduleState=DISABLED`. Set `RunEventsNotBefore` to the current UTC time so earlier start events remain excluded. Apply the stack update using the command under “Verify delivery and preview the limits,” and verify its settings. A replacement conflict requires reading and reviewing the current controls before another attempt.
4. Generate an `apply` event with `node aws/event.mjs apply .private/aws-apply.json`, invoke it as in the preview, and track its new `runId` to completion. Verify each absolute cap and temporary expiry by independent API readback. Repeat the current-slot run and confirm that no additional budget is released. Resolve attention results before expanding.
5. With recurring delivery still disabled, complete the stop and restore procedure below. This closes the enrollment. Prepare a fresh enrollment in a new deployment and state table for continued operation, retaining the earlier records. Prove a bounded manual apply with its controls. Only then set `ScheduledAction=apply` and `ScheduleState=ENABLED` through a reviewed stack update. Keep `AllowedWriteAction=apply` and a current `RunEventsNotBefore` cutoff for this rollout. Verify a real hourly trigger and completed member outcomes.

The policy's `intervalHours` determines release frequency. Keep the same state table throughout an enrollment; it contains reconciliation records and original settings. The confirmed period and pilot expiry stop new processing. Plan restoration while both remain current. For the next period, use a fresh reviewed enrollment and deployment with its own state table; retain the prior table according to your records policy.

## 5. Verify failures and alerts

SQS delivery can repeat a message. The handler returns individual failed records so successful records can finish, and the controller reconciles saved absolute targets before another write. See [Lambda's SQS processing behavior](https://docs.aws.amazon.com/lambda/latest/dg/with-sqs.html) and [partial batch responses](https://docs.aws.amazon.com/lambda/latest/dg/services-sqs-errorhandling.html).

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

## 6. Stop, restore, and verify cleanup

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
