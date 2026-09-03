# Tracing, verification, and publication boundaries

This cookbook distinguishes a successful invocation, confirmed trace delivery,
ChatGPT testing, and public distribution. None implies the next.

## Trace destinations and credentials

`COOKBOOK_TRACING_MODE=aws` is the default. It exports through the AgentCore
ADOT bridge and does not require, read, forward, or configure
`OPENAI_TRACE_API_KEY`. The Bedrock OpenAI-compatible model uses
`OPENAI_API_KEY` and `OPENAI_BASE_URL` only for inference.

`COOKBOOK_TRACING_MODE=dual` is an explicit opt-in. It adds the OpenAI Agents
SDK backend exporter and requires a non-empty `OPENAI_TRACE_API_KEY` that is
different from the Bedrock model key. `OPENAI_PROJECT_ID` is forwarded only in
that mode. Prompt, response, and tool content stay disabled by default through
`OPENAI_TRACE_INCLUDE_SENSITIVE_DATA=0` and
`OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT=false`.

The local invoker disables automatic `openai_agents` instrumentation and adds
the AgentCore bridge itself. This prevents the SDK's default OpenAI exporter
from being initialized before AWS-only setup. Do not override the invoker's
`COOKBOOK_MANUAL_OPENAI_AGENTS_INSTRUMENTATION` or
`OTEL_PYTHON_DISABLED_INSTRUMENTATIONS` values without testing the resulting
processor configuration.

## AWS read-only preflight

Before a credentialed run, have the approved AWS identity execute:

```bash
export AWS_PROFILE=agentcore-dev
uv run --project runtime-agent --locked --env-file .env -- \
  ./scripts/aws-observability-preflight.sh
```

The command loads cookbook configuration from the root `.env` and preserves
`AWS_PROFILE` from the shell. The script only calls read APIs. It records the
active account and Region,
checks the CloudWatch Transaction Search destination, span log-group and stream
visibility, resource-policy visibility, and the CloudWatch Logs quota catalog.
It does not create a log group, enable Transaction Search, change a policy,
assume a role, deploy a Runtime, or invoke a model.

This is an observability preflight, not a complete Bedrock/AgentCore capacity check.
Before a live run, an AWS owner must separately confirm same-Region model entitlement,
inference quota, AgentCore Runtime quota, and any organization-level restriction for the
selected account. See [Bedrock OpenAI-Compatible Model Access](aws-iam.md#bedrock-openai-compatible-model-access).

The preflight requires an account/Region selected by the organization and the
corresponding read permissions. A failed check can mean a missing permission,
SCP or permissions-boundary restriction, absent service-linked prerequisite,
quota issue, or unconfigured destination. Route remediation to the AWS account
or organization administrator; do not make account changes merely to clear a
cookbook check. See [AWS IAM](aws-iam.md#cloudwatch-smoke-verification) for
the minimally scoped verification permissions.

## Trace verification is a separate step

`trace:run` uses the same selected invoker as the MCP server and reports its
actual session ID, invocation ID, and start time. The local route starts the
ADOT-instrumented Python worker with correlation baggage and AWS-only credential
filtering. The deployed route calls the configured AgentCore Runtime instead
of starting a local model run. `trace_smoke.py` remains a compatibility launcher
for this same adapter command, not a separate Python agent path.

A successful smoke response proves only that the agent response completed. It
does not prove CloudWatch or OpenAI accepted a span.

From the example root, generate the values first:

```bash
npm --prefix mcp-adapter run build
npm --prefix runtime-agent run --silent trace:run
```

Copy `correlation_id` and `started_at` from the emitted `trace_verification`
JSON. They identify this one invocation; sample values cannot verify a trace.
Select the verification mode according to the actual execution route:

- **Local:** preserve the printed `tracing_mode` (`aws` or `dual`). The local
  launcher configures that mode for its worker.
- **Deployed:** the printed mode is `unknown`, and both destinations remain
  `not_checked`. Local `COOKBOOK_TRACING_MODE` does not configure the remote
  Runtime. Its owner must confirm the deployed `aws` or `dual` mode before you
  set `TRACE_MODE` below, and provide the Runtime's Region and span log group.
  Do not pass `unknown` to the verifier or infer `aws` from a local default.

Then run the bounded read-only AWS query:

```bash
TRACE_ID='<correlation_id from trace:run output>'
TRACE_STARTED_AT='<started_at from trace:run output>'
TRACE_MODE='<aws or dual from local output, or confirmed by the Runtime owner>'

uv run --project runtime-agent --locked --env-file .env \
  python runtime-agent/verify_traces.py \
  --correlation-id "$TRACE_ID" \
  --started-at "$TRACE_STARTED_AT" \
  --tracing-mode "$TRACE_MODE"
```

The verifier runs one Logs Insights query against the configured `aws/spans`
log group, polls for at most `COOKBOOK_TRACE_VERIFY_TIMEOUT_SECONDS` (60
seconds by default, maximum 300), and prints a redaction-safe JSON report. Its
AWS status is independent of deployment or smoke success:

| Status | Meaning |
| --- | --- |
| `verified` | A matching span appeared in the queried AWS log group. |
| `failed` | The bounded query completed without a match or failed. Delayed ingestion can still be retried later. |
| `not_configured` | The selected destination or log group is not visible in the selected Region. |
| `not_checked` | The verifier did not have read access or an explicit manual check remains. |

For local dual mode, preserve the printed `dual` value; for a deployed Runtime,
use its owner's confirmed mode. The report deliberately leaves the OpenAI
destination `not_checked` in dual mode: the cookbook
uses no undocumented OpenAI trace-query API. A named verifier must manually
confirm the same correlation ID in the selected OpenAI project and record that
evidence outside the repository.

For the AWS observability prerequisites and console behavior, consult the
[AgentCore observability configuration guide](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/observability-configure.html)
and [viewing guide](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/observability-view.html).

## Private testing is not public distribution

Use Secure MCP Tunnel to test the plugin privately in ChatGPT Developer mode.
Your administrator associates the hosted tunnel with your workspace, and the
MCP adapter stays on loopback or a private network. Completing this setup does
not create a public plugin or public HTTPS endpoint, or establish eligibility
for public distribution.

Before a public release, your team must arrange a public service endpoint and
operating model, assign maintenance, publishing, support, and incident owners,
and complete product, security/privacy, and any marketplace or listing reviews.
The repository is MIT-licensed, but it does not designate those owners or supply
a public account or release approval. The responsible owners must resolve
these items before presenting the plugin as publicly available.
