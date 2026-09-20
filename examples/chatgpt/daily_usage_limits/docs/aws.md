# I run the controller with AWS

AWS is the worked example for running the controller on organization-managed infrastructure, independently of an individual's computer. Use it after testing the release policy with a small group. Your organization can also adapt the controller to a managed virtual machine or another cloud environment with scheduled execution, secure credential storage, persistent records, and monitoring.

Use Amazon EventBridge Scheduler to wake a Lambda function hourly. The shared controller decides whether a daily, weekly, or other configured interval is due. DynamoDB preserves the intended absolute cap, original settings, and receipts across invocations. This adjusts cumulative monthly hard caps; it does not reset a daily usage counter.

The template starts with the schedule **disabled** and live writes **off**. It uses Node.js 24, a 120-second Lambda timeout, reserved concurrency of one, and 180-second per-user leases. This Lambda path accepts at most **25 enrolled members**. Begin with one member and measure completion time before increasing the cohort. A larger all-members deployment needs a separately reviewed batching design; this example does not demonstrate enterprise-scale throughput.

Run commands from `examples/chatgpt/daily_usage_limits`. AWS steps require an approved account and region, AWS CLI v2, deployment permissions, and existing private resources: a versioned S3 artifact bucket, an operations SNS topic with a reachable subscriber, and a Secrets Manager secret. The secret must contain `{"apiKey":"..."}` using a workspace-scoped ChatGPT Admin key with the [required permissions](api-contract.md). Supply the secret through your organization's approved process; do not put its value in source, parameters, command arguments, logs, or this walkthrough. The template creates no secret, subscription, public endpoint, or bucket.

## 1. I verify the code without AWS credentials

```bash
node --test test/aws*.test.mjs
npm run package --prefix aws
```

The tests inject AWS transports and a synthetic Admin API. They exercise the real handler and controller through apply, duplicate delivery, the next interval, and exact restoration. Store tests check that an expired lease holder cannot overwrite state or release a newer holder's lock. **These are local tests, not AWS service acceptance.**

Packaging installs the pinned SDK dependencies with install scripts disabled and writes `aws/dist/controller.zip`, its SHA-256, and `source-manifest.json`. Only the runtime's source import graph and dependencies enter the ZIP. No upload occurs. Review the manifest; it must contain neither a private configuration nor an enrollment, credential, fixture, or receipt.

For an optional local CloudFormation syntax and schema check, install `cfn-lint` in an isolated environment and run:

```bash
python3 -m venv .private/cfn-validation
.private/cfn-validation/bin/pip install cfn-lint==1.40.4
.private/cfn-validation/bin/cfn-lint -t aws/template.yaml
```

This check does not prove that the deployment identity has permissions or that AWS will accept the stack in your account.

I can also rehearse preparation of the protected control item without sending anything to AWS:

```bash
node src/cli.mjs init --dir .private/aws-rehearsal --pattern fixed_release --cohort all --unit credit --interval-hours 168 --synthetic --allow-initial-reduction
node src/cli.mjs snapshot --config .private/aws-rehearsal/config.json --out .private/aws-rehearsal/enrollment.json --synthetic
```

Review the three fictional members, each with a 2,000-credit monthly target and 500-credit weekly releases. The explicit reduction option permits the first reviewed change from 2,000 to 500 in this simulation. Replace `REVIEWED_SHA256` with the printed snapshot hash:

```bash
node src/cli.mjs approve --enrollment .private/aws-rehearsal/enrollment.json --hash REVIEWED_SHA256
node aws/prepare-control.mjs .private/aws-rehearsal/config.json .private/aws-rehearsal/enrollment.json cookbook-usage-limits .private/aws-rehearsal/control-item.json
node aws/event.mjs probe .private/aws-rehearsal/probe.json
```

The preparation command prints a `ControlSha256` that binds the complete configuration and enrollment. Its private output is a DynamoDB item, not a deployment request. Keep rehearsal controls separate from live controls.

## 2. I prepare a disabled cloud pilot for review

The following steps upload code and create billable AWS resources. Perform them only after the account owner approves the account, region, resource ownership, cost, expiry, and deployment role. Set `AWS_PROFILE` and `AWS_REGION` to the approved CLI profile and region. Use a deployment role; do not paste AWS access keys into files.

1. Run `aws sts get-caller-identity`. Confirm the returned account and role. Check that the existing artifact bucket is private and versioned, and that the secret and SNS topic are in the intended account and region. If a customer-managed KMS key protects the secret, obtain its ARN and confirm its key policy permits the generated runtime role.
2. Set the nonsecret shell variables `DAILY_LIMIT_STACK`, `DAILY_LIMIT_CODE_BUCKET`, and `DAILY_LIMIT_CODE_KEY` to the reviewed stack name, artifact bucket, and a unique object key. Upload the ZIP:

   ```bash
   aws s3api put-object --bucket "$DAILY_LIMIT_CODE_BUCKET" --key "$DAILY_LIMIT_CODE_KEY" --body aws/dist/controller.zip --query VersionId --output text
   ```

   Record the returned version ID. A missing or `null` version is a stop condition: this example requires an immutable S3 object version.
3. Copy `aws/parameters.example.json` to `.private/aws-parameters.json` and replace every `REPLACE_...` value. Match `DeploymentId` to the chosen Lambda name. Use the uploaded bucket, key, and version. Set a finite `PilotExpiresAt` no later than the confirmed current usage-period end; use UTC `YYYY-MM-DDTHH:MM:SSZ`. Leave `ControlSha256` as the all-zero bootstrap value, `ScheduleState` as `DISABLED`, `ScheduledAction` as `preview`, and `ApplyEnabled` as `false`. The bootstrap hash intentionally cannot match real controls.
4. Review `aws/template.yaml` and the private parameters, then create the disabled stack:

   ```bash
   aws cloudformation create-stack --stack-name "$DAILY_LIMIT_STACK" --template-body file://aws/template.yaml --parameters file://.private/aws-parameters.json --capabilities CAPABILITY_IAM
   aws cloudformation wait stack-create-complete --stack-name "$DAILY_LIMIT_STACK"
   aws cloudformation describe-stacks --stack-name "$DAILY_LIMIT_STACK" --query 'Stacks[0].Outputs'
   ```

   Set `DAILY_LIMIT_FUNCTION`, `DAILY_LIMIT_TABLE`, and `DAILY_LIMIT_GROUP` from the returned function, table, and schedule-group outputs. These variables hold names, never credentials.
5. Read back the deployed controls:

   ```bash
   aws lambda get-function-configuration --function-name "$DAILY_LIMIT_FUNCTION" --query '{Runtime:Runtime,Timeout:Timeout,Variables:Environment.Variables}'
   aws lambda get-function-concurrency --function-name "$DAILY_LIMIT_FUNCTION"
   aws scheduler get-schedule --group-name "$DAILY_LIMIT_GROUP" --name usage-limit-check
   ```

   Expect `nodejs24.x`, timeout `120`, concurrency `1`, `APPLY_ENABLED=false`, and schedule state `DISABLED`. Check the expiry, fixed control hash, exact secret ARN, target role, retry policies, and both failure queues. Keep the returned configuration private.

The runtime role can read one secret and the reviewed control partition. It can update only controller state, locks, and its own receipts; it cannot update the control document, secret, schedule, or its own permissions. The external deployment role and the operator who provisions controls remain privileged. The hash detects changed controls; it is not a substitute for IAM access control or review.

## 3. I prove AWS delivery, then make a read-only preview

First prove manual Lambda invocation without touching the Admin API:

```bash
node aws/event.mjs probe .private/aws-probe.json
aws lambda invoke --function-name "$DAILY_LIMIT_FUNCTION" --cli-binary-format raw-in-base64-out --payload file://.private/aws-probe.json .private/aws-probe-result.json
```

Inspect `.private/aws-probe-result.json`. Expect `ok: true` and `action: probe`. Also verify a new `aws_invocation` receipt in the private DynamoDB table. An HTTP `200` alone is insufficient: a synchronous Lambda invocation can return a `FunctionError` in the CLI metadata.

To prove **timed delivery**, open EventBridge Scheduler in the approved AWS account. In the stack's schedule group, create one temporary one-time schedule a few minutes ahead in UTC. Select the deployed Lambda and the stack's existing scheduler execution role; use the existing delivery-failure queue, turn the flexible window off, and choose automatic deletion after completion. Use this target input:

```json
{"version":1,"action":"probe","scheduledAt":"<aws.scheduler.scheduled-time>"}
```

Wait for the scheduled time. Match the Scheduler invocation metric and Lambda log entry to a new private invocation receipt; verify the one-time schedule disappears. A manual invocation or local test does not satisfy this step. Keep the recurring `usage-limit-check` schedule disabled.

Now prepare the live preview:

1. Complete the [README's live enrollment steps](../README.md#prepare-a-reviewed-enrollment) in `.private/aws-live`, with no local writer running. Confirm the real workspace, unit, period boundaries, counter scope, selected members, and original cap/source. Use at most 25 members. Keep `liveWrites: false`. Snapshot, review, and approve the enrollment **after cloud setup**; the first apply requires a snapshot no older than 15 minutes and the same policy interval.
2. Prepare its protected item:

   ```bash
   node aws/prepare-control.mjs .private/aws-live/config.json .private/aws-live/enrollment.json cookbook-usage-limits .private/aws-live/control-item.json
   ```

   Replace `cookbook-usage-limits` if you chose another `DeploymentId`. Put the printed `ControlSha256` into `.private/aws-parameters.json`, leaving the other gates off.
3. Provision the reviewed control item with the deployment identity, then update the hash:

   ```bash
   aws dynamodb put-item --table-name "$DAILY_LIMIT_TABLE" --item file://.private/aws-live/control-item.json --condition-expression 'attribute_not_exists(PK)'
   aws cloudformation update-stack --stack-name "$DAILY_LIMIT_STACK" --template-body file://aws/template.yaml --parameters file://.private/aws-parameters.json --capabilities CAPABILITY_IAM
   aws cloudformation wait stack-update-complete --stack-name "$DAILY_LIMIT_STACK"
   node aws/event.mjs preview .private/aws-preview.json
   aws lambda invoke --function-name "$DAILY_LIMIT_FUNCTION" --cli-binary-format raw-in-base64-out --payload file://.private/aws-preview.json .private/aws-preview-result.json
   ```

4. Inspect every private member receipt and the invocation result. Confirm `mode: preview`, the correct identities/unit, original settings, intended cap, ceiling, and no PATCH. This validates real secret retrieval, network access, Admin API reads, and private durable receipts. It still does not prove a live cap change or model enforcement.

To inspect receipts, use the DynamoDB console's item explorer on the output table and query `PK = RECEIPT#<DeploymentId>`. Receipts contain private identifiers and settings; do not paste them into public issues. The Lambda response and logs contain only a short run summary.

## 4. I review the first live change and ongoing schedule

1. Obtain explicit approval for the proposed member caps, any initial reduction, the bounded trial, and restoration. Coordinate all manual admin edits and disable any local or Codex writer for the same users. Separate stacks have separate lock tables and cannot protect against overlapping owners.
2. Set `liveWrites: true` in the same reviewed configuration. This gate does not change the policy approval hash, but it does change the AWS control-document hash. Regenerate the item to a **new** private output path and review both hashes. Replace the old control item only while the schedule is disabled, using a conditional write that checks its previous `documentSha256`; do not blindly overwrite another operator's update. Update `ControlSha256` and `ApplyEnabled=true` in the stack parameters, keeping `ScheduleState=DISABLED`. Apply and verify that stack update. If setup consumed the 15-minute first-apply window, recapture and reapprove the untouched enrollment before proceeding.
3. Generate a fresh `apply` event and invoke it as in the preceding preview command. Expect `ok: true`, private `applied` receipts, and independent readback of each absolute cap with its temporary expiry. Repeat the same current-slot invocation and expect no additional writes. A delayed invocation uses the current policy slot, not the event's old time. Inspect all members: the handler fails if any member needs attention or could not start within the time budget.
4. With recurring delivery still disabled, generate a `restore` event and invoke it. Verify that the API's settings and source match the saved original state exactly for each member. Turn `ApplyEnabled` off again. This closes that enrollment; use a fresh, reviewed enrollment and a new private state table for a continuing pilot.
5. For the continuing pilot, first prove a bounded manual apply with fresh reviewed controls. Only then set `ScheduledAction=apply` and `ScheduleState=ENABLED` through a reviewed stack update. Verify a real hourly trigger and its receipt. The policy's `intervalHours` controls release frequency. Keep the same state table throughout this enrollment; changing tables loses reconciliation and original-state records.

For a conditional control replacement, write `.private/expected-control-hash.json` containing `{":expected":{"S":"PREVIOUS_CONTROL_SHA256"}}`, substitute the previous recorded control hash, then use:

```bash
aws dynamodb put-item --table-name "$DAILY_LIMIT_TABLE" --item file://.private/aws-live/NEW_CONTROL_ITEM.json --condition-expression 'documentSha256 = :expected' --expression-attribute-values file://.private/expected-control-hash.json
```

`NEW_CONTROL_ITEM.json` is the new reviewed item produced by `prepare-control.mjs`. A conditional failure means the previous control changed; stop and read it back. Never weaken the condition to force an update. The first installation uses `attribute_not_exists(PK)` instead.

The handler checks the finite pilot expiry before secrets and refuses any run outside the reviewed period. It does not enroll the next month automatically. Set expiry with enough time to restore while the confirmed period remains current. At a unit transition or a different billing-cycle boundary, stop and review new evidence; no implicit conversion or period inference occurs.

## 5. I verify failures and alerts

Scheduler invokes Lambda asynchronously. Scheduler delivery retries and Lambda execution retries are separate; the template provides an SQS queue for each. Lambda can deliver duplicates even after a successful run, so correctness depends on durable absolute targets and readback, not delivery uniqueness. [Scheduler invocation behavior](https://docs.aws.amazon.com/lambda/latest/dg/with-eventbridge-scheduler.html), [Lambda retry behavior](https://docs.aws.amazon.com/lambda/latest/dg/invocation-async-error-handling.html).

| Signal | Meaning and action |
| --- | --- |
| `ControllerIssue` | A controller result needs review. Inspect private member receipts and the invocation's safe failure code. |
| Lambda `Errors` or `Throttles` | Execution failed or concurrency was unavailable. Inspect the queues, expiry, IAM, and pending intent before retrying. |
| Delivery queue contains a message | Scheduler exhausted delivery retries before successful handoff. |
| Execution queue contains a message | Lambda exhausted its execution retries after accepting the event. |
| `DestinationDeliveryFailures` | Lambda could not send a failure record to its destination queue. |
| `InvocationsFailedToBeSentToDeadLetterCount` | Scheduler could not send its failed event to the delivery queue. |
| Missing-run alarm | No successful hourly invocation for about three hours while recurring delivery is enabled. Check the schedule and expiry. |

Verify actual alert delivery to the owner, then test a controlled failed invocation and recovery while writes are off. For example, invoke an event with an invalid action asynchronously and confirm retries, the execution queue, alarm receipt, and recovery. Use a separate approved test if you need to exercise Scheduler delivery failure; do not modify a production target or permission to manufacture an outage. A defined alarm or a nonempty queue is not proof that a person received a notification.

The code stops starting users as time runs low and reserves time before a PATCH for readback. A timeout can still leave a pending intent. Rerun the same operation after reconciliation; do not delete state or grant a different target. Measure your cohort's worst-case time before enabling recurring delivery. If repeated invocations cannot complete all 25 or fewer members, reduce the approved cohort or design durable batching; do not claim unprocessed members are covered. API rate-limit delays can outlast Lambda's retries; the saved retry time is honored on a later invocation.

For a repaired authentication failure, keep recurring delivery disabled, inspect the halted receipt, then generate and manually invoke a `resume_auth` event. It clears the halt only after current state is verified; it does not change caps or discard the pending target. Preview and explicitly rerun the original operation afterward. If a first attempted write never took effect and its initial review expired, inspect the before-state and use `cancel_initial` to close that untouched enrollment, then capture a fresh pilot. Neither recovery action is available as a recurring schedule action. Both use the same reviewed controls and state table; never reset the table as a recovery shortcut.

The table encrypts stored data and enables point-in-time recovery. Only receipt items have a TTL; state, before-settings, controls, and unresolved intents do not expire automatically. DynamoDB TTL deletion is asynchronous, so it is not a precise retention deadline. Apply your organization's retention and access policy to the private table, logs, backups, artifact versions, and queues. [DynamoDB TTL behavior](https://docs.aws.amazon.com/amazondynamodb/latest/developerguide/TTL.html).

## 6. I stop, restore, and verify cleanup

1. Set `ScheduleState=DISABLED` and `ApplyEnabled=false` through a stack update. Read back the disabled schedule and gate. Wait for any in-flight invocation to finish; inspect both failure queues and private pending state. Do not delete the table to stop writes.
2. While the pilot and reviewed period are still current, review a restore. Keep the schedule disabled and temporarily enable only the write gates needed for a manual `restore` invocation. Resolve an existing pending apply first using its saved target. Verify every member's exact original settings and source by independent API readback, then turn the write gate off. If the period has ended, the controller intentionally refuses restoration: have the workspace admin inspect the current inherited/override state and approve any required manual correction instead of replaying an old period's settings.
3. Record the stack outputs and owned artifact version. Archive required private receipts and restore evidence. Delete the stack only after reconciliation and restoration are complete:

   ```bash
   aws cloudformation delete-stack --stack-name "$DAILY_LIMIT_STACK"
   aws cloudformation wait stack-delete-complete --stack-name "$DAILY_LIMIT_STACK"
   ```

4. Verify the Lambda, recurring schedule/group, queues, roles, and alarms are gone. The table and log group deliberately remain under `DeletionPolicy: Retain` so deletion cannot silently destroy recovery evidence. Review their contents and retention obligations, then explicitly delete only those owned retained resources if authorized. Also delete the precise uploaded S3 object version if no longer required; never empty a shared bucket.
5. Verify the retained-resource inventory and any temporary probe schedule. Revoke a dedicated ChatGPT key through your approved credential process if the pilot no longer needs it. The pre-existing secret, bucket, SNS topic/subscriptions, and optional KMS key are outside this stack and must not be deleted as incidental cleanup.

Pilot expiry stops runtime work and scheduled invocation; it does not restore caps, remove resources, stop all AWS charges, or guarantee deletion. The final acceptance record should distinguish local tests, cloud delivery, live read-only preview, approved change/readback/restore, timed recurring execution, delivered alerts, and verified cleanup.
