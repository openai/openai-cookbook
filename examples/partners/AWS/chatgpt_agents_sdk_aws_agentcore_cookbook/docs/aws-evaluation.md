# Optional Amazon Bedrock AgentCore Evaluations

Use this lane to evaluate the deterministic flight cases against one dedicated
non-production Amazon Bedrock AgentCore Runtime. It is optional, makes live AWS
calls to create test invocations, and scores their completed spans afterward.
It is separate from both production traffic and the offline Promptfoo contract
suite.

AWS documents that the OpenAI Agents integration reconstructs the prompt,
response, and tool activity from the Runtime's
[OpenTelemetry spans](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/supported-frameworks-openai-agents.html).
The cookbook's normal tracing defaults redact that content, so this lane
requires a **dedicated non-production evaluation Runtime** configured by its
owner with `OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT=true`. Do not
enable content capture on an ordinary production Runtime. The Runtime owner must
approve the test data, access, retention, and cleanup controls before handing
its ARN to the evaluator.

| Command | Purpose | Live credentials | Creates charges |
| --- | --- | --- | --- |
| `npm run eval:run` | Check all response-contract fixtures with Promptfoo's echo provider | No | No |
| `npm run eval:agent:validate` | Validate the actual-agent Promptfoo configuration | No | No |
| `RUN_PROMPTFOO_AGENT_EVALUATION=1 npm run eval:agent` | Run and score three fresh local Agents SDK outputs | Yes | Yes |
| `npm run eval:aws:validate` | Validate the AWS-tagged canonical fixture metadata | No | No |
| `AGENTCORE_EVALUATION_CONTENT_CAPTURE_CONFIRMED=1 RUN_AWS_EVALUATION=1 npm run eval:aws` | Invoke the configured evaluation Runtime, retrieve its spans, and run AgentCore built-in evaluators | Yes | Yes |

The live command is never run in CI. This repository does not contain committed
proof of a live evaluation. The runner uses AgentCore's on-demand evaluation
API and saves its redacted result locally; it does not create a persistent
evaluation run in the AWS console.

## What the live runner evaluates

All three evaluation lanes read
`runtime-agent/evals/fixtures/flight-status-results.jsonl`, but they do not
replace or call each other:

- The credential-free Promptfoo suite checks every applicable checked-in
  contract fixture through the echo provider.
- The guarded actual-agent Promptfoo suite invokes the local Agents SDK
  workflow for the three tagged canonical cases and checks each fresh response
  against the Runtime contract and exact expected output.
- The AWS runner uses only valid canonical cases that are explicitly tagged
  with `aws_evaluation` metadata. Negative and contract-only cases are not sent
  to AWS.

For each tagged case, the runner:

1. Invokes the exact `AGENTCORE_RUNTIME_AGENT_ARN` with a new retained session
   ID and generated W3C trace context.
2. Waits for that session's spans to reach the configured CloudWatch log group.
3. Calls `EvaluationClient.run` with:
   - `Builtin.Correctness`
   - `Builtin.GoalSuccessRate`
   - `Builtin.TrajectoryExactOrderMatch`
4. Supplies the case's expected response, assertions, and expected tool order
   through `ReferenceInputs`.
5. Writes a redacted local result under `runtime-agent/evals/results/`.

The canonical fixture stores the local Promptfoo response. The AWS loader
first verifies that response against the current deterministic workflow, then
derives the same expected facts with `executionMode: "deployed"` for the
Runtime evaluation. Assertions and the expected tool trajectory live in the
case's `aws_evaluation` tag. This keeps one versioned flight dataset without
mislabeling the route, while preserving the independent evaluation commands.

This lane does not require the OpenAI tunnel, a ChatGPT plugin, CDK, or a local
agent process. It does require an already-deployed Runtime that emits its
session spans to CloudWatch in the same account and Region used by the
evaluation role.

## What to request from your AWS administrator

Copy this text into an enterprise access ticket and replace any values you
already know:

```text
I need to run the optional live AgentCore Evaluations workflow in the
flight-status cookbook against one dedicated non-production evaluation Runtime.

Please provide:
- The exact parent AgentCore Runtime ARN, endpoint ARN, Region, Runtime
  qualifier, and CloudWatch Runtime log-group name.
- A role I can assume from my existing AWS CLI identity.
- bedrock-agentcore:InvokeAgentRuntime on only those exact parent Runtime and
  selected endpoint ARNs.
- bedrock-agentcore:Evaluate and bedrock-agentcore:GetEvaluator for the
  approved AWS built-in evaluators.
- CloudWatch Logs query access needed to retrieve the Runtime session spans:
  logs:StartQuery for the designated Runtime log group and aws/spans, and
  logs:GetQueryResults with Resource "*"; AWS does not support resource-level
  scoping for GetQueryResults.
- bedrock:InvokeModel, bedrock:InvokeModelWithResponseStream,
  bedrock:Converse, and bedrock:ConverseStream on only the approved Amazon
  Bedrock judge model or inference profile used by Builtin.Correctness and
  Builtin.GoalSuccessRate.
- Confirmation that Runtime observability and CloudWatch Transaction Search
  are enabled in this account and Region and that the named log group receives
  the Runtime's session spans.
- Confirmation that this is a dedicated non-production evaluation Runtime with
  `OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT=true`, and that its trace
  content, access, retention, and cleanup have been approved.

This runner uses only Builtin.Correctness, Builtin.GoalSuccessRate, and
Builtin.TrajectoryExactOrderMatch. It does not deploy or change the Runtime and
does not create custom evaluators.

I do not need CDK, S3 artifact, ECR, Runtime create/update/delete,
iam:PassRole, Lambda, or custom-evaluator creation permissions.

Please return the evaluation role ARN, the approved source-profile/login
method, the exact Runtime values, the judge model or inference-profile ID, and
the expected AWS account ID so I can verify the assumed identity.
```

Send the administrator [the evaluation runner policy shape](aws-iam.md#optional-agentcore-evaluations-runner-role)
if they ask for implementation details. The administrator owns the AWS policy;
do not paste policy JSON or AWS credentials into the application.

## Configure the AWS CLI profile

Add the role returned by the administrator to `~/.aws/config`. Replace the
placeholders:

```ini
[profile agentcore-evaluation]
role_arn = arn:aws:iam::<ACCOUNT_ID>:role/AgentCoreFlightEvaluation
source_profile = YOUR_EXISTING_AWS_PROFILE
region = us-west-2
```

Your organization may use IAM Identity Center or another credential source
instead of `source_profile`. Follow its normal login instructions.

Verify the identity before running the evaluation:

```bash
aws sts get-caller-identity --profile agentcore-evaluation
```

Stop if the returned account or role is not the one named in the access ticket.

## Configure the cookbook

From the repository root, create `.env` if it does not exist:

```bash
test -f .env || install -m 600 .env.example .env
chmod 600 .env
```

Mode `600` keeps the credential file readable and writable only by its owner.

Set the values supplied by the administrator:

```dotenv
AGENTCORE_RUNTIME_REGION=us-west-2
AGENTCORE_RUNTIME_AGENT_ARN=arn:aws:bedrock-agentcore:<REGION>:<ACCOUNT_ID>:runtime/<RUNTIME_ID>
AGENTCORE_RUNTIME_QUALIFIER=<QUALIFIER>
AGENTCORE_EVALUATION_LOG_GROUP=/aws/bedrock-agentcore/runtimes/<RUNTIME_ID>-DEFAULT
RUN_AWS_EVALUATION=0
AGENTCORE_EVALUATION_CONTENT_CAPTURE_CONFIRMED=0
```

Use the exact log-group name; do not infer it from a display name. Set the
qualifier to the value supplied by the Runtime owner. Leave it empty only when
that owner confirms the Runtime should use its default qualifier.

Keep both guards set to `0` in `.env`. The live command sets them to `1` only
for that process after the Runtime owner confirms the dedicated evaluation
Runtime's content-capture and data-handling configuration.

The optional controls and their defaults are:

```dotenv
AGENTCORE_EVALUATION_WAIT_SECONDS=180
AGENTCORE_EVALUATION_POLL_SECONDS=30
AGENTCORE_EVALUATION_ATTEMPTS=5
AGENTCORE_EVALUATION_MIN_SCORE=0.5
AGENTCORE_EVALUATION_CASE_IDS=
```

`AGENTCORE_EVALUATION_CASE_IDS` accepts comma-separated case IDs. Leave it
empty to run every tagged canonical case. Select one case for a lower-cost
first proof:

```dotenv
AGENTCORE_EVALUATION_CASE_IDS=<CASE_ID>
```

Do not put `AWS_PROFILE` or AWS credentials in `.env`. Export the profile in
the shell that runs the command.

## Validate without AWS

Install the locked dependencies, then validate the tagged cases:

```bash
cd runtime-agent
uv sync --locked --extra dev
npm ci
npm run eval:aws:validate
```

This command does not invoke the Runtime, query CloudWatch, or call an
evaluator. Fix any missing or invalid AWS fixture metadata before proceeding.
If `AGENTCORE_EVALUATION_CASE_IDS` contains an unknown ID, the live command
rejects it before creating any AWS client.

## Run the live evaluation

Sign in using your organization's normal AWS flow, then run:

```bash
export AWS_PROFILE=agentcore-evaluation
aws sts get-caller-identity
AGENTCORE_EVALUATION_CONTENT_CAPTURE_CONFIRMED=1 \
RUN_AWS_EVALUATION=1 \
npm run eval:aws
```

The command initially waits 180 seconds because Runtime spans are not
immediately queryable. It then makes up to five evaluation attempts, with 30
seconds between attempts that find no spans. The pinned AgentCore SDK may spend
up to 60 seconds querying CloudWatch within each attempt, so a no-spans failure
can take roughly ten minutes with the defaults, plus normal evaluator time.
Tune these settings only when the Runtime owner expects different ingestion
timing.

The command fails if it cannot invoke the Runtime, retrieve the matching
session spans, obtain all required evaluator results, or meet the configured
minimum score. A low score is an evaluation result, not an IAM failure.

## Handle the result

The runner prints a summary and saves a redacted JSON artifact under
`runtime-agent/evals/results/`. That directory is ignored by Git. The artifact
contains case and evaluator results plus redacted correlation values; it must
not contain AWS credentials or raw secrets.

Treat the artifact as environment evidence:

- Share it only through your organization's approved evidence location.
- Check it before sharing even though the runner redacts correlation values.
- Do not force-add it to Git.
- Record the Runtime suffix, Region, evaluation time, evaluator IDs, and
  pass/fail result with the external evidence.

No live artifact is committed by default because live success depends on the
caller's AWS account, role, Runtime, judge-model access, and observability
configuration.

## Troubleshooting

### `RUN_AWS_EVALUATION=1 is required`

This guard prevents accidental live calls. Run `npm run eval:aws:validate`
first. Set the guard only on the command that should create AWS activity:

```bash
AGENTCORE_EVALUATION_CONTENT_CAPTURE_CONFIRMED=1 \
RUN_AWS_EVALUATION=1 \
npm run eval:aws
```

### `AGENTCORE_EVALUATION_CONTENT_CAPTURE_CONFIRMED=1 is required`

Do not bypass this guard for a normal production Runtime. Ask the Runtime owner
for a dedicated non-production evaluation Runtime whose deployment sets
`OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT=true`, then confirm the
organization has approved the trace-content access, retention, and cleanup
controls. Set the confirmation flag only on the intended evaluation command.

### Runtime invocation is denied

Ask the administrator to confirm
`bedrock-agentcore:InvokeAgentRuntime` is allowed on both the exact parent ARN
in `AGENTCORE_RUNTIME_AGENT_ARN` and the exact endpoint ARN selected by
`AGENTCORE_RUNTIME_QUALIFIER`. Also confirm the assumed role and Region.

### Evaluator access is denied

Send the denied action to the administrator. The runner requires
`bedrock-agentcore:Evaluate` and `bedrock-agentcore:GetEvaluator` for its
built-ins. Judge-related denials require access to the specifically approved
Bedrock model or inference profile for `bedrock:InvokeModel`,
`bedrock:InvokeModelWithResponseStream`, `bedrock:Converse`, and
`bedrock:ConverseStream`.

### No spans are found

Confirm all of the following:

- `AGENTCORE_EVALUATION_LOG_GROUP` is the exact Runtime log-group name.
- Runtime observability and CloudWatch Transaction Search are enabled in the
  same account and Region.
- The role can start a query and read its results.
- The Runtime invocation succeeded.
- The selected Runtime is the dedicated evaluation Runtime and its deployment
  has message-content capture enabled.

CloudWatch ingestion can take several minutes. Increase the wait or retry
settings only after checking the log group and Region.

If spans exist but correctness, goal-success, or trajectory evaluation reports
missing input, output, or tool content, stop and ask the Runtime owner to verify
the evaluation deployment. Do not enable content capture on production traffic
as a troubleshooting shortcut.

### One evaluator scores below the threshold

Open the redacted result and identify the case and evaluator. A correctness
failure concerns the expected response, a goal-success failure concerns the
case assertions, and an exact-trajectory failure means the observed tool names
or order differ from the tagged expected trajectory. Re-run the offline
Promptfoo suite before changing a canonical fixture:

```bash
npm run eval:validate
npm run eval:run
```

Do not lower the minimum score merely to turn a genuine regression green.
