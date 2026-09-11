# Use an existing Amazon Bedrock AgentCore Runtime without CDK

This is an optional compatibility path. The repository defaults to
`COOKBOOK_EXECUTION_MODE=local`, which runs the checked-in agent locally and
does not require any Runtime ARN. Use this page only when a team deliberately
wants the MCP adapter to call an already deployed Amazon Bedrock AgentCore
Runtime.

This supported **non-CDK consumer path** lets a
team invoke an AgentCore Runtime that already exists in its AWS account. It
does not require a deployment project, CDK bootstrap, S3 access, or permission
to create infrastructure. This repository contains no Runtime provisioning
stack.

It is intentionally not a generic non-CDK provisioning guide. The team that
owns the Runtime may use CDK, Terraform, the AgentCore CLI, or an approved
internal deployment pattern to create it. The adapter only needs an approved
Runtime ARN and an invoke-only AWS identity.

The Runtime owner chooses the trace destination. `COOKBOOK_TRACING_MODE=aws`
is the default and does not require an OpenAI trace key. Explicit
`COOKBOOK_TRACING_MODE=dual` additionally requires a distinct
`OPENAI_TRACE_API_KEY`; `OPENAI_PROJECT_ID` is optional project routing in that
mode. `DISABLE_ADOT_OBSERVABILITY` and `OTEL_SDK_DISABLED` must not be true.
When the Runtime is started through automatic OpenTelemetry instrumentation,
the owner must preserve the cookbook's manual AgentCore bridge configuration so
an AWS-only process does not initialize the OpenAI exporter. AgentCore Runtime
tracing and the account's CloudWatch Transaction Search setup are Runtime-owner
controls; the invoke-only MCP adapter cannot configure them.

For normal use, keep
`OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT=false` so prompt, response,
and tool payload content is not exported through ADOT. The optional AgentCore
Evaluations lane is different: its built-in evaluators need that content and
must target a dedicated non-production evaluation Runtime whose owner has
explicitly enabled and approved content capture. See
[Optional AWS-native AgentCore Evaluations](aws-evaluation.md).

In dashboards, this path is intentionally distinct from local execution. AWS
uses the deployed Runtime identity rather than `LOCAL_AGENT_SERVICE_NAME`. In
explicit dual mode, OpenAI traces use the workflow name `ChatGPT flight agent
(deployed)` rather than `ChatGPT flight agent (local)`, and the project is
determined by the Runtime's project-scoped trace credential or explicit
`OPENAI_PROJECT_ID`.

## Required configuration

Copy `.env.example` to `.env`, then set these values in the MCP host
environment:

```bash
export COOKBOOK_EXECUTION_MODE=deployed
export AGENTCORE_RUNTIME_AGENT_ARN='arn:aws:bedrock-agentcore:us-west-2:123456789012:runtime/flight_status_agent'
export AGENTCORE_RUNTIME_REGION=us-west-2
```

`AGENTCORE_RUNTIME_REGION` takes precedence over `AWS_REGION`, which takes
precedence over `AWS_DEFAULT_REGION`. If all three are empty, the adapter
defaults to `us-west-2`.

The read-only observability preflight and `verify_traces.py` use the same explicit
Region precedence in deployed mode. In local mode they ignore
`AGENTCORE_RUNTIME_REGION` and require `AWS_REGION` and `AWS_DEFAULT_REGION` to
match when both are set. If no applicable Region variable is set, these diagnostic
commands fall back to the selected AWS profile's Region and fail if it is missing;
they do not use the adapter's `us-west-2` default. Set an explicit Region in `.env`
to keep invocations and diagnostics aligned. Region selection does not change
`AWS_PROFILE`, assume a role, or alter the AWS credential chain.

Existing installations may continue using the legacy
`FLIGHT_DATA_SOURCE=agentcore-runtime` alias. If both variables are present,
they must select the same mode or the adapter fails configuration validation.

Optional configuration:

```bash
export AGENTCORE_RUNTIME_QUALIFIER=DEFAULT
# Set this only after deriving it from an authenticated principal.
export AGENTCORE_RUNTIME_USER_ID='approved-service-subject'
```

Do not accept `AGENTCORE_RUNTIME_USER_ID` from a browser, widget, or
unauthenticated MCP request. Supplying it adds
`bedrock-agentcore:InvokeAgentRuntimeForUser` alongside the required
`bedrock-agentcore:InvokeAgentRuntime`; see [AWS IAM notes](aws-iam.md).

## Caller permissions

The MCP host should assume a role that has only
`bedrock-agentcore:InvokeAgentRuntime` against both the exact parent Runtime
ARN and the exact selected endpoint ARN, for example
`arn:aws:bedrock-agentcore:<REGION>:<ACCOUNT_ID>:runtime/<RUNTIME_ID>/runtime-endpoint/DEFAULT`.
The application still receives the parent Runtime ARN through
`AGENTCORE_RUNTIME_AGENT_ARN` and the endpoint name through
`AGENTCORE_RUNTIME_QUALIFIER`. It does not need create, update, delete, or
wildcard Runtime permissions. The minimum policy shape is documented in
[AWS IAM notes](aws-iam.md).

The examples below use the profile name `agentcore-invoke-proof`; replace it
with the administrator-supplied invoke-only profile name.

## Build and start

```bash
export AWS_PROFILE=agentcore-invoke-proof
cd mcp-adapter
npm ci
npm run build
npm start
```

The server listens on `http://127.0.0.1:8787/mcp`. For a real AWS smoke test,
use the same scoped role and Runtime ARN:

```bash
export AWS_PROFILE=agentcore-invoke-proof
npm run smoke:live
```

The smoke command searches DAL to MDW for the configured synthetic demo date,
checks the first result's live status, and fails if the Runtime changes its
flight identity or date. The default date is 45 UTC days ahead; set
`COOKBOOK_DEMO_TRAVEL_DATE` for a deterministic approved test. It validates both
Runtime response shapes and intentionally does not print trace or session
identifiers. Record correlation evidence in the approved log or ticket system,
not in source control.

## What this path proves

With a real ARN and real scoped credentials, `npm run smoke:live` proves that
the adapter can invoke that deployed Runtime twice and validate the canonical
search-to-status response chain. It does not prove that either backend accepted
spans. Confirm AWS with the bounded checker in
[tracing and publication boundaries](tracing-and-publication.md#trace-verification-is-a-separate-step);
for explicit dual mode, a named verifier separately confirms OpenAI Traces.
This smoke does not prove ChatGPT host-loop behavior, a customer network
topology, public distribution, or production identity mapping.

## Cleanup

Stop the local MCP process and remove temporary environment values or ephemeral
credentials according to your organization's secret-handling process. This
consumer path creates no AWS resources. The Runtime owner controls cleanup of
the Runtime, its deployment artifacts, and its logs.

Runtime deployment, artifact updates, version selection, and rollback remain
outside this cookbook's consumer path and belong to the enterprise platform
team that owns the supplied Runtime.
