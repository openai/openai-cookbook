# Amazon Bedrock AgentCore IAM and permissions

The cookbook runs the checked-in agent locally by default. An enterprise can
instead give a developer invoke-only access to one already-deployed Amazon
Bedrock AgentCore Runtime. That existing-Runtime path does not require the
developer to create, update, or delete AWS infrastructure.

The policies below are intentionally scoped as implementation guidance, not a
copy-paste production policy.

Official references checked for this package:

- Amazon Bedrock AgentCore Runtime invocation: https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/runtime-invoke-agent.html
- Amazon Bedrock AgentCore Runtime permissions: https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/runtime-permissions.html
- Amazon Bedrock AgentCore CLI getting started: https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/agentcore-get-started-cli.html
- AWS on-demand evaluation permissions: https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/iam-permissions-on-demand.html
- AWS ground-truth evaluations: https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/ground-truth-evaluations.html

## Local Tools

Install these before running the notebook or sample checks:

- `uv`
- Node.js 24 or later and `npm`
- Python 3.10 or later
- AWS CLI v2 with SSO, environment credentials, or an assumed role

## Local-agent telemetry publisher

The standard local path runs the agent on the developer workstation. Its AWS
ADOT process therefore uses the developer's AWS credential chain to publish
logs, traces, and metrics. The Runtime invoke-only role does not grant these
permissions.

The AWS administrator creates the log group and completes the account-level
Transaction Search and X-Ray destination setup. The developer publisher policy
has this shape:

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "DescribeCookbookLogStreams",
      "Effect": "Allow",
      "Action": "logs:DescribeLogStreams",
      "Resource": "arn:aws:logs:<REGION>:<ACCOUNT_ID>:log-group:/aws/bedrock-agentcore/runtimes/chatgpt-agentcore-cookbook-local"
    },
    {
      "Sid": "WriteCookbookLogs",
      "Effect": "Allow",
      "Action": [
        "logs:CreateLogStream",
        "logs:PutLogEvents"
      ],
      "Resource": "arn:aws:logs:<REGION>:<ACCOUNT_ID>:log-group:/aws/bedrock-agentcore/runtimes/chatgpt-agentcore-cookbook-local:log-stream:*"
    },
    {
      "Sid": "WriteCookbookTraces",
      "Effect": "Allow",
      "Action": [
        "xray:PutTraceSegments",
        "xray:PutTelemetryRecords",
        "xray:GetSamplingRules",
        "xray:GetSamplingTargets",
        "xray:GetSamplingStatisticSummaries"
      ],
      "Resource": "*"
    },
    {
      "Sid": "WriteCookbookMetrics",
      "Effect": "Allow",
      "Action": "cloudwatch:PutMetricData",
      "Resource": "*",
      "Condition": {
        "StringEquals": {
          "cloudwatch:namespace": "bedrock-agentcore"
        }
      }
    }
  ]
}
```

This role publishes telemetry; it does not need permission to read the
CloudWatch or AgentCore Observability consoles.

## Existing Runtime invoke-only developer setup

Use this path when an AWS administrator has already created the Runtime and
gives the developer:

- The exact parent Runtime ARN.
- The exact endpoint ARN and endpoint name or qualifier. For the automatically
  created endpoint, the name is `DEFAULT`.
- The Runtime Region.
- An invoke-only IAM role ARN, such as `AgentCoreInvokeOnlyProof`.
- The name of an existing AWS CLI source profile that is allowed to assume
  that role.

The administrator keeps the IAM policy in AWS. The developer does **not** copy
the policy JSON into the repository or application. The role policy has this
shape:

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "InvokeOnlyApprovedAgentCoreRuntime",
      "Effect": "Allow",
      "Action": "bedrock-agentcore:InvokeAgentRuntime",
      "Resource": [
        "arn:aws:bedrock-agentcore:<REGION>:<ACCOUNT_ID>:runtime/<RUNTIME_ID>",
        "arn:aws:bedrock-agentcore:<REGION>:<ACCOUNT_ID>:runtime/<RUNTIME_ID>/runtime-endpoint/<ENDPOINT_NAME>"
      ]
    }
  ]
}
```

AgentCore authorizes Runtime operations hierarchically. The identity policy
must therefore allow `InvokeAgentRuntime` on both the parent Runtime and the
selected endpoint; parent-only and endpoint-only policies are incomplete. The
application receives the parent Runtime ARN in
`AGENTCORE_RUNTIME_AGENT_ARN` and the endpoint name in
`AGENTCORE_RUNTIME_QUALIFIER`. Use `DEFAULT` when no custom endpoint is
selected.

The AWS administrator can copy both values from the Runtime endpoint details
page or retrieve them without constructing the endpoint ARN by hand:

```bash
aws bedrock-agentcore-control get-agent-runtime-endpoint \
  --agent-runtime-id <RUNTIME_ID> \
  --endpoint-name DEFAULT \
  --region <REGION> \
  --query '{parentRuntimeArn:agentRuntimeArn,endpointArn:agentRuntimeEndpointArn}'
```

Keep the endpoint ARN in the IAM policy; the application's `.env` stores the
parent Runtime ARN and optional qualifier, not the endpoint ARN.

The role trust policy must allow the developer's source identity to assume the
role, and that source identity must be allowed to call `sts:AssumeRole`.

### Configure the local AWS CLI profile

Add a profile to `~/.aws/config`. Replace the role ARN and source profile with
the values supplied privately by the AWS administrator:

```ini
[profile agentcore-invoke-proof]
role_arn = arn:aws:iam::<ACCOUNT_ID>:role/AgentCoreInvokeOnlyProof
source_profile = YOUR_EXISTING_AWS_PROFILE
region = us-west-2
```

Do not add this profile or its source credentials to the repository.

Verify the assumed identity:

```bash
aws sts get-caller-identity --profile agentcore-invoke-proof
```

If role assumption fails, the AWS administrator must check both the source
identity's `sts:AssumeRole` permission and the target role's trust policy.

### Configure and test the cookbook

Set the existing-Runtime values in the root `.env`:

```dotenv
COOKBOOK_EXECUTION_MODE=deployed
AGENTCORE_RUNTIME_REGION=us-west-2
AGENTCORE_RUNTIME_AGENT_ARN=arn:aws:bedrock-agentcore:<REGION>:<ACCOUNT_ID>:runtime/<RUNTIME_ID>
```

Use `COOKBOOK_EXECUTION_MODE=deployed` for new setup. The older
`FLIGHT_DATA_SOURCE=agentcore-runtime` value remains only as a compatibility
alias and must not conflict with the canonical setting.

The MCP npm scripts automatically load the root `.env`. Export only the AWS
profile, then run the live smoke:

```bash
export AWS_PROFILE=agentcore-invoke-proof
cd mcp-adapter
npm ci
npm run build
npm run smoke:live
```

A successful two-step search-to-status response proves that the developer can
invoke the one configured Runtime. It does not prove that the developer can
create infrastructure or invoke any other Runtime.

See [Use an existing AgentCore Runtime without CDK](existing-agentcore-runtime.md)
for the full application path, live smoke command, and evidence boundaries.

## Optional AgentCore Evaluations runner role

The optional AgentCore Evaluations workflow is a separate permission lane. Do
not add evaluation permissions to every invoke-only developer. Give them to a
dedicated role, such as `AgentCoreFlightEvaluation`, only when the developer is
expected to run the live evaluation.

The role must target a dedicated non-production evaluation Runtime whose owner
has enabled and approved
`OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT=true`. The built-in
evaluators need the prompt, response, and tool content in that Runtime's spans;
do not enable content capture on an ordinary production Runtime.

The developer assumes this role through an AWS CLI profile in
`~/.aws/config`, exports that profile as `AWS_PROFILE`, and runs the evaluation
from their workstation. `AWS_PROFILE` is never stored in the repository
`.env`.

The role needs:

- `bedrock-agentcore:InvokeAgentRuntime` on both one exact existing parent
  Runtime ARN and its exact selected endpoint ARN.
- `bedrock-agentcore:Evaluate` and `bedrock-agentcore:GetEvaluator` for the
  three approved built-ins.
- `logs:StartQuery` for the configured Runtime log group and `aws/spans`. The
  runner uses exact log-group names and does not discover other groups.
- `logs:GetQueryResults` with `Resource: "*"`. AWS does not support
  resource-level scoping for this action; it retrieves results by query ID.
- Calls to the specifically approved Amazon Bedrock judge model or inference
  profile. `Builtin.Correctness` and `Builtin.GoalSuccessRate` use a judge
  model; `Builtin.TrajectoryExactOrderMatch` is programmatic.

The following is a policy shape for an AWS administrator to adapt. Replace all
placeholders. AWS currently documents `Resource: "*"` for the on-demand
`Evaluate` permission, while the Runtime and judge-model permissions can be
scoped to exact ARNs.

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "InvokeOneFlightRuntime",
      "Effect": "Allow",
      "Action": "bedrock-agentcore:InvokeAgentRuntime",
      "Resource": [
        "arn:aws:bedrock-agentcore:<REGION>:<ACCOUNT_ID>:runtime/<RUNTIME_ID>",
        "arn:aws:bedrock-agentcore:<REGION>:<ACCOUNT_ID>:runtime/<RUNTIME_ID>/runtime-endpoint/<ENDPOINT_NAME>"
      ]
    },
    {
      "Sid": "RunApprovedBuiltinEvaluators",
      "Effect": "Allow",
      "Action": [
        "bedrock-agentcore:Evaluate"
      ],
      "Resource": "*"
    },
    {
      "Sid": "ReadApprovedBuiltinEvaluators",
      "Effect": "Allow",
      "Action": "bedrock-agentcore:GetEvaluator",
      "Resource": [
        "arn:aws:bedrock-agentcore:::evaluator/Builtin.Correctness",
        "arn:aws:bedrock-agentcore:::evaluator/Builtin.GoalSuccessRate",
        "arn:aws:bedrock-agentcore:::evaluator/Builtin.TrajectoryExactOrderMatch"
      ]
    },
    {
      "Sid": "StartQueriesOnlyForRuntimeSpans",
      "Effect": "Allow",
      "Action": "logs:StartQuery",
      "Resource": [
        "arn:aws:logs:<REGION>:<ACCOUNT_ID>:log-group:<RUNTIME_LOG_GROUP>",
        "arn:aws:logs:<REGION>:<ACCOUNT_ID>:log-group:aws/spans"
      ]
    },
    {
      "Sid": "ReadStartedQueryResults",
      "Effect": "Allow",
      "Action": "logs:GetQueryResults",
      "Resource": "*"
    },
    {
      "Sid": "InvokeApprovedJudge",
      "Effect": "Allow",
      "Action": [
        "bedrock:InvokeModel",
        "bedrock:InvokeModelWithResponseStream",
        "bedrock:Converse",
        "bedrock:ConverseStream"
      ],
      "Resource": [
        "arn:aws:bedrock:<REGION>::foundation-model/<APPROVED_JUDGE_MODEL_ID>",
        "arn:aws:bedrock:<REGION>:<ACCOUNT_ID>:inference-profile/<APPROVED_INFERENCE_PROFILE_ID>"
      ]
    }
  ]
}
```

`Evaluate` requires `Resource: "*"`, while `GetEvaluator` is scoped to the
three public built-in evaluator ARNs. Remove the model or inference-profile ARN
that is not used. The four Bedrock actions match
[AWS's current on-demand evaluation IAM baseline](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/iam-permissions-on-demand.html)
and remain limited to the approved judge resources. The administrator should
also confirm that AgentCore Runtime observability and CloudWatch Transaction
Search are enabled and that the configured log group contains the dedicated
evaluation Runtime's session spans.

This role does not need:

- CDK, S3 artifact, ECR, Runtime create/update/delete, or `iam:PassRole`
  permissions.
- Evaluator or online-evaluation configuration create/update/delete
  permissions.
- Lambda permissions, because this cookbook uses only AWS built-in evaluators
  and does not create a custom code evaluator.

See [Optional AWS-native AgentCore Evaluations](aws-evaluation.md) for the
developer setup and commands.

## Runtime-owner deployment outside this repository

This repository contains no Runtime provisioning stack and the notebook never
assumes a deploy/bootstrap identity. The AWS platform or Runtime-owning team
chooses and maintains its CDK, Terraform, AgentCore CLI, CodeZip, ECR, or
internal deployment process. That team should use a separate operator identity
whose permissions are limited to the exact resources created by its selected
process. The MCP caller must not receive those permissions.

If the Runtime owner chooses CodeZip, use a platform-precreated private bucket
and prefix. Enable Block Public Access and encryption, define lifecycle and
cleanup ownership, grant the deployment operator only the required object
read/write permissions on that prefix, and grant `s3:ListBucket` only with a
matching prefix condition when the deployment tool requires it. Do not grant
the notebook developer, MCP caller, or evaluation role `s3:CreateBucket`.
Grant the Runtime execution role read access only to the exact artifact objects
when the chosen deployment pattern requires it.

## Runtime Execution Role

The Runtime execution role should trust the AgentCore service principal used by
Amazon Bedrock AgentCore Runtime and grant only the downstream services the
agent needs.

For this cookbook, that means:

- CloudWatch log writes for Runtime diagnostics.
- Artifact access for the selected deploy method.
- `bedrock:InvokeModel` and, if streaming is enabled, `bedrock:InvokeModelWithResponseStream` for the selected AWS Bedrock OpenAI-compatible model.
- Access to the AgentCore credential provider or secret path that stores the OpenAI-compatible API key.

Do not put the API key in the ChatGPT widget, MCP response, notebook output, committed `.env`, or README examples.

## MCP Caller Invoke Role

The MCP server or hosted caller role needs the same two exact-ARN
`bedrock-agentcore:InvokeAgentRuntime` permission shown in
[Existing Runtime invoke-only developer setup](#existing-runtime-invoke-only-developer-setup).

Pass the exact parent Runtime ARN returned by deploy to the application, and
authorize both that parent ARN and the selected endpoint ARN in IAM. Do not
send `AGENTCORE_RUNTIME_USER_ID` by default. If an authenticated service
deliberately derives and sends a user identity, separately grant
`bedrock-agentcore:InvokeAgentRuntimeForUser` on the same two ARNs. Never trust
a user ID supplied directly by an unauthenticated client.

## Bedrock OpenAI-Compatible Model Access

The sample assumes the AWS Bedrock `bedrock-mantle` OpenAI-compatible endpoint. AWS documents `openai.gpt-oss-120b` for `bedrock-mantle`; the lower-level `bedrock-runtime` endpoint uses the Bedrock runtime model id form such as `openai.gpt-oss-120b-1:0`.

```bash
export OPENAI_BASE_URL="https://bedrock-mantle.us-west-2.api.aws/v1"
export OPENAI_API_KEY="$AWS_BEDROCK_OPENAI_KEY"
export OPENAI_AGENTS_MODEL="openai.gpt-oss-120b"
```

Confirm model entitlement in the same AWS Region where the Runtime runs. Use `openai.gpt-oss-20b` for lower-cost smoke tests when available and compatible with your demo account.

Before a guarded smoke, the AWS owner must also confirm sufficient Amazon Bedrock and
AgentCore quotas for the selected Region, model, Runtime, and expected concurrency. The
observability preflight checks the CloudWatch Logs quota catalog only; it does not prove
model entitlement, inference throughput, Runtime availability, or AgentCore service
quota headroom. Record the approved model or inference profile and quota evidence in the
release record without committing account identifiers.

## CloudWatch smoke verification

For correlation by exact Runtime session or trace ID, give the verifier Logs
Insights access only to the known Runtime log group and `aws/spans`:

```json
[
  {
    "Effect": "Allow",
    "Action": "logs:StartQuery",
    "Resource": [
      "arn:aws:logs:<REGION>:<ACCOUNT_ID>:log-group:<RUNTIME_LOG_GROUP>",
      "arn:aws:logs:<REGION>:<ACCOUNT_ID>:log-group:aws/spans"
    ]
  },
  {
    "Effect": "Allow",
    "Action": "logs:GetQueryResults",
    "Resource": "*"
  }
]
```

`logs:GetQueryResults` cannot be scoped to a log-group ARN because it accepts a
query ID rather than a log-group resource. The query itself remains restricted
by the `logs:StartQuery` statement.

If a console verifier must discover group names, grant
`logs:DescribeLogGroups` separately with `Resource: "*"` because that action
does not support resource-level scoping. If the organization instead verifies
raw streams, scope `logs:DescribeLogStreams` to the exact group and
`logs:GetLogEvents` to that group's exact stream ARNs. Do not use a copyable
all-log read statement for normal verification.

## Least-Privilege Checklist

- Operator role can deploy Runtime infrastructure but is not used by ChatGPT/MCP traffic.
- Runtime execution role can call only the approved model and required logging/credential resources.
- MCP caller role has only invoke actions scoped to the exact parent Runtime
  and selected endpoint ARNs.
- Optional evaluation runner uses a separate role with query access and only
  the approved built-in evaluation and judge-model calls.
- API keys live in AWS credential/secret paths, not in source control.
- CloudWatch read permissions are sufficient to verify smoke evidence and trace correlation.

## Production least-privilege separation

Use the deployment operator, Runtime execution role, MCP invoke role, and log
verifier as separate identities. Do not use a shared administrator or operator
identity for normal MCP traffic. Use only the checked-in sample data, not
customer data or a production ChatGPT plugin.

For a separately maintained CodeZip deployment, the artifact S3 location is
deployment material, not an application-data store. Use the precreated private
bucket and scoped prefix described above. Record bucket, prefix, log,
ARN-suffix, role, and cleanup evidence outside source control.

After validating a disposable deployment, the Runtime-owning team deletes the
resources created by its deployment process, removes temporary credentials,
and confirms the artifact and log retention or deletion outcome.

An existing Runtime ARN does not require CDK, S3, or any deployment project in
the MCP host environment. See
[Use an existing AgentCore Runtime without CDK](existing-agentcore-runtime.md)
for the invoke-only consumption path.

Keep restricted-role, negative-permission, artifact, log, and cleanup records
in the enterprise-approved evidence system rather than in this repository.
