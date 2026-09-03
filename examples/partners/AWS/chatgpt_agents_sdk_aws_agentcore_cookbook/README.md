# Build a ChatGPT plugin with the OpenAI Agents SDK and Amazon Bedrock AgentCore

In this cookbook, you'll build a private flight assistant for a fictional airline
and learn how to connect ChatGPT to an OpenAI Agents SDK workflow backed by
Amazon Bedrock. The sample **Eliza Airlines** flights use `ELZ` identifiers and
sample data; the tools can search and report status, but cannot book,
change, or cancel flights.

You'll learn how to expose validated, read-only tools to ChatGPT, connect a
private tool server through Secure MCP Tunnel, display results in a widget,
and evaluate agent responses separately from verifying trace delivery.

A joint cookbook by Eliza and OpenAI.

The default path runs the checked-in agent on your workstation. You can also
invoke an existing AgentCore Runtime supplied by your platform team. This
cookbook does not deploy a Runtime.

![Default request flow from ChatGPT through Secure MCP Tunnel to a local MCP adapter and Agents SDK agent, with model calls and trace export to AWS.](notebooks/images/cookbook-boundaries.svg)

The tunnel client opens an outbound HTTPS connection. The MCP server remains on
loopback and does not require a public URL or inbound firewall rule. Real agent
runs call cloud services and can create usage charges.

Commands assume macOS or Linux with Bash or Zsh. Windows developers should use
WSL 2.

## Before you start

This workflow crosses AWS, OpenAI Platform, and ChatGPT workspace boundaries.
Before starting, confirm that you have:

- an AWS account ID, approved Region, login profile, model entitlement, and
  Amazon Bedrock API key;
- membership in the required OpenAI organization and, for optional dual-mode
  trace export, the project associated with `OPENAI_TRACE_API_KEY`;
- access to a ChatGPT workspace that permits Developer mode and plugin
  creation;
- the complete hosted Secure MCP Tunnel ID and a tunnel runtime API key for a
  principal with **Tunnels Read + Use**; and
- a Platform administrator who can create the hosted tunnel and associate it
  with the correct OpenAI organization and ChatGPT workspace.

The repository cannot create the hosted tunnel or its organization-to-workspace
association. The detailed developer and administrator permissions are listed
in the matrix in step 1.

## How the pieces fit together

- **Model Context Protocol (MCP)** lets ChatGPT discover tools, call them with
  structured inputs, and receive structured results. The MCP adapter is the
  server that exposes the three flight tools and validates their inputs and
  outputs against schemas, which define the accepted fields and values.
- **The widget** is a small HTML view inside ChatGPT. It renders the validated
  tool result without calling the flight backend itself.
- **The local agent** uses the OpenAI Agents SDK to run the read-only function
  tool selected for each action. Amazon Bedrock supplies the model through an
  OpenAI-compatible endpoint.
- **Tracing** records the steps, timing, and errors in a run. A span represents
  one operation, such as a tool call. AWS AgentCore Observability receives the
  traces by default; dual mode also exports them to OpenAI Traces.

An **AgentCore Runtime** is AWS's managed agent hosting service. Its **Amazon
Resource Name (ARN)** identifies the resource to invoke when you choose the
optional deployed path.

To adapt the cookbook, replace the sample tool implementations and data in
`runtime-agent/tools.py`, preserve the strict MCP request/response schemas,
then change the widget copy and rendering for your domain. Configure your own
Bedrock Region/model, tunnel placement, and tracing destination without putting
credentials in the widget or source tree. The deeper component and trust-boundary
explanation is in [Architecture and trust boundaries](docs/openai-agentkit-cookbook.md).

## Command conventions

The root `.env` is the only project configuration file used by the documented
commands. Here, the example root is
`examples/partners/AWS/chatgpt_agents_sdk_aws_agentcore_cookbook/` inside your
OpenAI Cookbook checkout. Run commands from that directory unless a command
block says otherwise. Commands that target a component use `npm --prefix <component>` or
`uv run --project <component>` so readers do not need to retain a prior `cd`.

## 1. Choose the execution path and request access

Use the **local agent** path unless your enterprise gives you an existing
AgentCore Runtime ARN and an invoke-only role.

The Secure MCP Tunnel required in step 7 must be provisioned outside this
repository. A Platform administrator creates the hosted tunnel, associates it
with the exact OpenAI organization and ChatGPT workspace, and gives the
developer both the complete `tunnel_...` ID and a runtime key with **Tunnels
Read + Use**. The developer cannot complete that setup with `tunnel-client`
alone.

### Runtime ZIPs are not a setup step

The default path runs the checked-in agent locally and does not create or
consume a deployment ZIP. The optional deployed path invokes an existing
Runtime; its owner remains responsible for its CodeZip artifact, deployment,
and rollback. Do not copy local `dist/` artifacts into a Cookbook submission.

### Enterprise least-privilege matrix

| What the developer will use | Minimum developer access | What enterprise IT or an administrator must provide |
| --- | --- | --- |
| Local agent and Amazon Bedrock model | Approved AWS login/profile, model entitlement, and an Amazon Bedrock API key for `bedrock-mantle` | AWS account ID, Region, login method, enabled `openai.gpt-oss-120b`, and the API key or permission to create it |
| AWS telemetry from the local agent | `logs:DescribeLogStreams`, `logs:CreateLogStream`, and `logs:PutLogEvents` for `/aws/bedrock-agentcore/runtimes/chatgpt-agentcore-cookbook-local`; `xray:PutTraceSegments`, `xray:PutTelemetryRecords`, `xray:GetSamplingRules`, `xray:GetSamplingTargets`, and `xray:GetSamplingStatisticSummaries`; `cloudwatch:PutMetricData` restricted to the `bedrock-agentcore` namespace | Create the log group, enable CloudWatch Transaction Search, configure span ingestion and the X-Ray trace destination, and attach the scoped publishing policy from [AWS IAM details](docs/aws-iam.md#local-agent-telemetry-publisher) |
| Existing AgentCore Runtime instead of the local agent | `bedrock-agentcore:InvokeAgentRuntime` on the exact parent Runtime ARN and selected endpoint ARN | Runtime ARN, endpoint ARN, qualifier, Region, assumable invoke-only role, and confirmation that the Runtime owner manages deployment, credentials, and observability |
| Optional dual-mode OpenAI trace export and OpenAI Traces console | OpenAI organization **Reader**, project **Member** for the project associated with `OPENAI_TRACE_API_KEY`, and that project's trace API key | Add the developer to the organization and project; provide the key or permission to create it. Organization Owner and project Owner are not required for project trace use |
| Secure MCP Tunnel runtime | Platform principal with **Tunnels Read + Use**, its runtime API key, and ChatGPT Developer mode/plugin creation access | A Platform administrator with **Tunnels Read + Manage** creates the hosted tunnel, associates it with the exact Platform organization and ChatGPT workspace, and returns the complete `tunnel_...` ID |
| Promptfoo actual-agent evaluations | Same local model and AWS telemetry-publishing access used by the local agent; OpenAI trace access only when `COOKBOOK_TRACING_MODE=dual` | No dataset or additional evaluation service is required; the checked-in JSONL is used directly |
| AWS AgentCore on-demand evaluations | A separate assumable evaluation role: exact Runtime and endpoint invocation; `bedrock-agentcore:GetEvaluator` for the three built-ins; `bedrock-agentcore:Evaluate` with `Resource: "*"`; `logs:StartQuery` on the evaluation Runtime log group and `aws/spans`; `logs:GetQueryResults` with `Resource: "*"`; `bedrock:InvokeModel`, `bedrock:InvokeModelWithResponseStream`, `bedrock:Converse`, and `bedrock:ConverseStream` on the approved judge model or inference profile | A dedicated non-production evaluation Runtime deployed with approved message-content capture, its exact ARNs/log group/qualifier, enabled Transaction Search, judge-model access, and the evaluation role. No CDK, S3, ECR, Runtime-management, `iam:PassRole`, Lambda, or custom-evaluator permissions are needed by the developer |
| AWS console viewing of sessions and traces | Optional read-only CloudWatch/Application Signals access, such as the enterprise-approved equivalent of `CloudWatchApplicationSignalsReadOnlyAccess` | Attach the read-only policy or assign an administrator to verify ingestion. This access is not required for telemetry to be written |

Two IAM details matter:

- AgentCore Runtime invocation must authorize both the parent Runtime and the
  selected endpoint.
- AWS supports log-group scoping for `logs:StartQuery`, but not for
  `logs:GetQueryResults`; the latter accepts a query ID and therefore requires
  `Resource: "*"`.

Full policy shapes are in [AWS IAM and permissions](docs/aws-iam.md). The
copyable request for the optional AWS evaluation role is in
[AWS evaluation access request](docs/aws-evaluation.md#what-to-request-from-your-aws-administrator).

The keys are not interchangeable:

- `OPENAI_API_KEY` is issued by Amazon Bedrock and calls the model.
- `OPENAI_TRACE_API_KEY` is issued by OpenAI Platform and exports traces only
  when explicit dual mode is selected.
- `CONTROL_PLANE_API_KEY` is the Secure MCP Tunnel runtime key.

## 2. Install the required software

Install:

- [Git](https://git-scm.com/downloads)
- Node.js 24 or newer, including npm
- [`uv`](https://docs.astral.sh/uv/getting-started/installation/)
- AWS CLI v2
- `curl`

Verify:

```bash
git --version
node --version
npm --version
uv --version
aws --version
curl --version
```

## 3. Clone and install the project

```bash
git clone https://github.com/openai/openai-cookbook.git
cd openai-cookbook/examples/partners/AWS/chatgpt_agents_sdk_aws_agentcore_cookbook
test -f .env || install -m 600 .env.example .env
chmod 600 .env

cd runtime-agent
uv sync --locked --extra dev
npm ci

cd ../mcp-adapter
npm ci
npm run build
cd ..
```

Do not relax the `.env` file mode or commit the file.

## 4. Configure the selected execution path

### Standard local-agent path

Set these values in the root `.env`:

```dotenv
COOKBOOK_EXECUTION_MODE=local
AWS_REGION=us-west-2

OPENAI_BASE_URL=https://bedrock-mantle.us-west-2.api.aws/v1
OPENAI_API_KEY=<Amazon Bedrock API key>
OPENAI_AGENTS_MODEL=openai.gpt-oss-120b
COOKBOOK_TRACING_MODE=aws
# Optional reproducible override; omit it to use UTC today plus 45 days.
COOKBOOK_DEMO_TRAVEL_DATE=
```

For the standard local path, use the approved Region in both `AWS_REGION` and `OPENAI_BASE_URL`. The
cookbook intentionally accepts only the canonical
`https://bedrock-mantle.<region>.api.aws/v1` format; review AWS documentation,
then update and test the validator before using any future endpoint format.
If your shell also sets `AWS_DEFAULT_REGION`, it must match `AWS_REGION`.
`AGENTCORE_RUNTIME_REGION` is intentionally blank in `.env.example`: set it
only for deployed mode, to the Region in the supplied Runtime ARN. It takes
precedence for that Runtime invocation.
Keep the normal privacy defaults:

```dotenv
OPENAI_TRACE_INCLUDE_SENSITIVE_DATA=0
OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT=false
DISABLE_ADOT_OBSERVABILITY=false
OTEL_SDK_DISABLED=false
```

The standard telemetry records session, trace, span, tool, timing, error, and
usage structure without storing raw user prompts, model responses, or tool
content. AWS-only mode neither requires nor configures an OpenAI trace key.

To export to both AWS and OpenAI Traces, make that decision explicitly and use
a separate OpenAI Platform project credential:

```dotenv
COOKBOOK_TRACING_MODE=dual
OPENAI_TRACE_API_KEY=<OpenAI Platform project API key>
# Optional project routing; never send this to the Bedrock model endpoint.
OPENAI_PROJECT_ID=
```

The runtime rejects a missing or reused model key in dual mode. Do not set the
legacy `OPENAI_TRACING_ENABLED` toggle to select a destination.

Save the root `.env` before starting the MCP server in step 6. If the server is
already running, stop it with `Ctrl+C` and run `npm start` again; the tracing
mode is read when the server process starts.

### Optional existing-Runtime path

Use this path only with values supplied by the Runtime owner:

```dotenv
COOKBOOK_EXECUTION_MODE=deployed
AGENTCORE_RUNTIME_REGION=us-west-2
AGENTCORE_RUNTIME_AGENT_ARN=arn:aws:bedrock-agentcore:<REGION>:<ACCOUNT_ID>:runtime/<RUNTIME_ID>
AGENTCORE_RUNTIME_QUALIFIER=DEFAULT
```

The developer's profile must assume the invoke-only role from the permission
matrix. The Runtime—not the developer workstation—owns model credentials and
AWS telemetry publishing in this path. See
[existing Runtime setup](docs/existing-agentcore-runtime.md) for endpoint
details.

### Verify configuration without printing secrets

```bash
awk -F= '
  $1 == "OPENAI_API_KEY" || $1 == "OPENAI_TRACE_API_KEY" || $1 == "COOKBOOK_TRACING_MODE" {
    print $1 ": " (length($2) > 0 ? "set" : "MISSING")
  }
' .env

git check-ignore .env
```

The Bedrock model-key check is required for the local path. The OpenAI trace
key is required only when `COOKBOOK_TRACING_MODE=dual`. `git check-ignore` must
print `.env`.

## 5. Sign in to AWS and run the preflight

Replace `agentcore-dev` with the profile supplied by IT.

For IAM Identity Center:

```bash
aws sso login --profile agentcore-dev
aws sts get-caller-identity --profile agentcore-dev
export AWS_PROFILE=agentcore-dev
```

For environments using `aws login`:

```bash
aws login --profile agentcore-dev --region us-west-2
aws sts get-caller-identity --profile agentcore-dev
export AWS_PROFILE=agentcore-dev
```

Stop if the account or principal is not the one returned by the access request.
If the enterprise uses the default AWS credential chain, omit `AWS_PROFILE`.

Run the read-only observability preflight before a credentialed invocation:

```bash
uv run --project runtime-agent --locked --env-file .env -- \
  ./scripts/aws-observability-preflight.sh
```

This loads the cookbook Region and observability settings from the root `.env`
while preserving `AWS_PROFILE` from the shell. It checks the selected account
and Region, Transaction Search destination,
log-group/stream and resource-policy visibility, and the CloudWatch Logs quota
catalog. It does not create, modify, deploy, or invoke anything. See
[tracing and publication boundaries](docs/tracing-and-publication.md) for how
to interpret a failed check.

Run the smoke test for the selected path.

For the local path:

```bash
npm --prefix mcp-adapter run smoke:agent
```

For the existing-Runtime path:

```bash
npm --prefix mcp-adapter run smoke:live
```

Run only the command matching `.env`. The smoke searches DAL to MDW for the
configured future demo date, then checks the first result's live status. Resolve
that date at any time with `npm --prefix runtime-agent run --silent demo-date`.
Expected output contains `executionMode: "local"` or `executionMode: "deployed"`
accordingly.

A valid response proves agent execution, not trace delivery. Trace verification
comes after the plugin tool call in step 8.

## 6. Start and test the MCP server

In terminal 1:

```bash
cd /path/to/chatgpt-agents-sdk-aws-agentcore-cookbook
export AWS_PROFILE=agentcore-dev
cd mcp-adapter
npm start
```

Expected startup message:

```text
Flight MCP server listening on http://127.0.0.1:8787/mcp
```

In terminal 2, check health:

```bash
curl -fsS http://127.0.0.1:8787/
```

Expected response:

```json
{"status":"ok","mcp":"/mcp"}
```

List tools:

```bash
cd /path/to/chatgpt-agents-sdk-aws-agentcore-cookbook/mcp-adapter
npx -y @modelcontextprotocol/inspector@1.0.0 \
  --cli http://127.0.0.1:8787/mcp \
  --transport http \
  --method tools/list
```

The list must include:

- `search_flights`
- `get_upcoming_status`
- `get_live_status`

Make one real tool call:

```bash
DEMO_TRAVEL_DATE="$(npm --prefix ../runtime-agent run --silent demo-date)"
npx -y @modelcontextprotocol/inspector@1.0.0 \
  --cli http://127.0.0.1:8787/mcp \
  --transport http \
  --method tools/call \
  --tool-name get_live_status \
  --tool-arg flight_number=ELZ1234 \
  --tool-arg origin=DAL \
  --tool-arg destination=MDW \
  --tool-arg travel_date="$DEMO_TRAVEL_DATE"
```

The tools use deterministic sample data and never book, change, or cancel a
flight.

## 7. Connect the MCP server to ChatGPT

Do not continue until the direct MCP tool call succeeds.

Before starting the tunnel setup, coordinate with an OpenAI Platform
administrator. The administrator must:

- create the hosted Secure MCP Tunnel;
- associate it with the correct OpenAI organization and ChatGPT workspace; and
- give the developer the complete `tunnel_...` ID and a tunnel runtime key for
  a principal with **Tunnels Read + Use**.

These actions happen outside this repository. Running `tunnel-client init`
creates a local profile that uses an existing hosted tunnel; it does not create
the tunnel or associate it with an organization or workspace.

Developer mode must also be enabled before opening the ChatGPT Plugins page.
Until it is enabled, the Plugins page or controls for adding a connection may
not be visible. If the Developer mode setting is unavailable, ask the ChatGPT
workspace administrator to check the workspace policy.

### Install the tunnel client

Download the organization-approved release from
[OpenAI tunnel-client releases](https://github.com/openai/tunnel-client/releases/latest)
or the organization's Platform tunnel settings. Example:

```bash
mkdir -p "$HOME/.local/bin"
install -m 0755 /path/to/extracted/tunnel-client "$HOME/.local/bin/tunnel-client"
export PATH="$HOME/.local/bin:$PATH"
tunnel-client --version
```

> **macOS security note:** If macOS blocks `tunnel-client` because it cannot
> verify the developer, open **System Settings → Privacy & Security**, select
> **Allow Anyway** for `tunnel-client`, then run the command again. Use only the
> organization-approved release.

### Create the local tunnel profile once

```bash
export CONTROL_PLANE_API_KEY="<OpenAI tunnel runtime API key>"

tunnel-client init \
  --sample sample_mcp_remote_no_auth \
  --profile agentcore-cookbook \
  --tunnel-id "tunnel_0123456789abcdef0123456789abcdef" \
  --mcp-server-url "http://127.0.0.1:8787/mcp"
```

Use the complete tunnel ID exactly once. Skip `init` if the profile already
exists.

### Run and verify the tunnel

Keep the MCP server running. In terminal 2:

```bash
export CONTROL_PLANE_API_KEY="<OpenAI tunnel runtime API key>"
tunnel-client doctor --profile agentcore-cookbook --explain
tunnel-client run --profile agentcore-cookbook
```

In terminal 3:

```bash
curl -fsS http://127.0.0.1:8080/readyz
```

Do not continue until the tunnel reports ready.

### Create the ChatGPT plugin connection

1. In ChatGPT, open **Settings → Security and login** and turn on **Developer
   mode** before opening the Plugins page. Availability can depend on account
   and workspace policy.
2. Open [ChatGPT Plugins](https://chatgpt.com/plugins) and select the plus
   button. If the page or plus button is not visible, confirm that Developer
   mode is enabled and permitted by the workspace.
3. Enter a user-facing name and description for the plugin connection.
4. Under **Connection**, choose **Tunnel**, then select the hosted tunnel or
   paste its complete `tunnel_...` ID.
5. For the authentication type, choose **No authentication**. The tunnel
   runtime key authenticates `tunnel-client` to the tunnel service; do not paste
   `CONTROL_PLANE_API_KEY` into the plugin form.
6. Create the connection. ChatGPT starts tool discovery automatically; wait for
   it to list `search_flights`, `get_upcoming_status`, and `get_live_status`,
   then review the discovered metadata.
7. Start a new conversation, add the plugin connection from the tools menu,
   choose any future date in
   `YYYY-MM-DD` format, and ask:

   > Find flights from DAL to MDW on `<YYYY-MM-DD>`, then check the live status
   > of the first result.

If the tunnel is unavailable or workspace association fails, return to the
Secure MCP Tunnel row in the permission matrix. Local code cannot create the
hosted tunnel or repair an organization-to-workspace association.

You now have a private plugin connection for testing in ChatGPT Developer mode.
Before making it publicly available, your team needs a public service endpoint,
an operating and publishing owner, product and security/privacy reviews, and
any required listing approval. The [MIT License](LICENSE) covers this
repository's code; it does not provide release approval. See the
[publication requirements](docs/tracing-and-publication.md#private-testing-is-not-public-distribution).

## 8. Verify sessions and traces

Normal ChatGPT plugin usage creates operational telemetry for the activity that
passes through this plugin:

- one stable, hashed `chatgpt-...` session identifier when ChatGPT supplies
  `openai/session`;
- separate traces for individual requests and MCP tool calls in that session;
- spans for agent, model, and tool operations.

If ChatGPT does not supply `openai/session`, the adapter uses a new identifier
for each invocation and those calls cannot be grouped into one session.

| Execution path | OpenAI | AWS |
| --- | --- | --- |
| Local agent, `COOKBOOK_TRACING_MODE=aws` | Not configured | Local ADOT publishes service `chatgpt-agentcore-cookbook-local` using the developer's scoped telemetry role |
| Local agent, `COOKBOOK_TRACING_MODE=dual` | Workflow `ChatGPT flight agent (local)` | Local ADOT publishes service `chatgpt-agentcore-cookbook-local` using the developer's scoped telemetry role |
| Existing Runtime | Configured only when the Runtime owner explicitly selects dual mode | The Runtime execution role and AgentCore service publish the Runtime session and traces |

For dual mode, open [OpenAI Traces](https://platform.openai.com/traces) and
select the organization and project associated with `OPENAI_TRACE_API_KEY`. A
least-privilege developer is an organization Reader and project Member. Because
OpenAI's published role matrix does not list the Traces page separately,
enterprises should verify this once using a real non-admin project Member.

AWS telemetry is stored in CloudWatch and surfaced through AgentCore
Observability. In the AWS console, select the same account and Region used by
the MCP-server terminal, then open **CloudWatch → GenAI Observability → Amazon
Bedrock AgentCore** and use **Sessions View** or **Traces View**. For the local
path, select or filter for service `chatgpt-agentcore-cookbook-local`.
Developers do not need AWS read access for telemetry to be written. If the
developer cannot view it, either use the optional read-only permission in the
matrix or give the verifier:

- approximate invocation time;
- AWS Region;
- service or Runtime identifier;
- hashed session ID or trace correlation value, when available.

Do not send API keys. CloudWatch ingestion can take several minutes. A
successful agent response does not prove that either exporter accepted the
trace. Use the one trace-smoke sequence below; it generates the real correlation
values that the bounded AWS checker needs. Record any dual-mode OpenAI
confirmation separately as described in [tracing and publication boundaries](docs/tracing-and-publication.md#trace-verification-is-a-separate-step).

### Generate and verify one trace

With dependencies installed and the selected `.env`, build the adapter and run
one representative live-status request through the same route as the MCP server:

```bash
npm --prefix mcp-adapter run build
npm --prefix runtime-agent run --silent trace:run
```

In `local` mode this uses the ADOT-instrumented Python worker, including its
correlation baggage and AWS-only credential filtering. In `deployed` mode it
invokes the configured AgentCore Runtime; it does not run the agent locally or
require local model credentials.

The JSON contains the actual returned session and invocation IDs. Copy
`correlation_id` and `started_at` from that exact output. For `local` mode, also
copy the printed `tracing_mode` (`aws` or `dual`). For `deployed` mode the smoke
prints `tracing_mode: "unknown"`: local `.env` settings do not configure or
verify the Runtime's exporters. Ask the Runtime owner to confirm `aws` or
`dual` before setting `TRACE_MODE`; do not pass `unknown` to the verifier.
Use the Runtime's Region and span log group for the deployed check.

Then run the bounded, read-only AWS verification from the example root:

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

The smoke leaves delivery `not_checked`; a successful response is not proof of
ingestion. `verified` means the exact correlation ID was found in the configured
AWS span log group. In AWS-only mode, the OpenAI destination correctly reports
`not_configured`. For confirmed dual mode, have a named project member confirm
the same ID in OpenAI Traces; the cookbook
does not use an undocumented trace-query API.

## 9. Run evaluations

All evaluation paths use
`runtime-agent/evals/fixtures/flight-status-results.jsonl`. They do not create a
dataset in Promptfoo, OpenAI, or AWS.

Run every command in this table from `runtime-agent/`.

| Command | What it proves | Cloud calls |
| --- | --- | --- |
| `npm run eval:validate` and `npm run eval:run` | The checked-in response-contract cases remain internally valid | None |
| `npm run eval:agent:validate` | The actual-agent Promptfoo configuration is valid | None |
| `RUN_PROMPTFOO_AGENT_EVALUATION=1 npm run eval:agent` | Fresh local Agents SDK outputs satisfy the Runtime contract and exact expected behavior | Bedrock model plus configured trace exporters |
| `npm run eval:aws:validate` | AWS-tagged cases and ground truth are valid | None |

The overview table ends at `npm run eval:aws:validate` because validation is the
expected stopping point when the optional evaluation infrastructure has not
been provided. The live AWS evaluation command appears in step 6 of the
optional setup below and must run only after the required Runtime, role,
profile, and content-capture checks are complete.

### Recommended Promptfoo actual-agent evaluation

Promptfoo is the primary evaluator in this cookbook. The cookbook does not
create OpenAI Evals. OpenAI Traces is an optional observability view for the
agent runs, not a scoring service.

```bash
cd runtime-agent
npm run eval:agent:validate

AWS_PROFILE=agentcore-dev \
PROMPTFOO_AGENT_EVALUATION_CASE_IDS=upcoming-status \
RUN_PROMPTFOO_AGENT_EVALUATION=1 npm run eval:agent

AWS_PROFILE=agentcore-dev \
RUN_PROMPTFOO_AGENT_EVALUATION=1 npm run eval:agent
```

The first live command runs one lower-cost case; the second runs all tagged
canonical cases. Promptfoo receives the complete request, actual response,
expected response, assertions, and expected tool behavior directly. Normal
OpenAI and AWS trace exports retain the privacy defaults from step 4.

Results are saved privately under the ignored
`runtime-agent/evals/results/` directory.

### Optional AWS AgentCore on-demand evaluation

An invoke-only role cannot run the live evaluation. Complete these steps in
order:

1. Enter `runtime-agent/` and validate the AWS-tagged cases without making
   cloud calls:

   ```bash
   cd runtime-agent
   npm run eval:aws:validate
   ```

2. Ask the Runtime or AWS owner for a dedicated non-production evaluation
   Runtime, its Runtime ARN, qualifier, log group, and the separate evaluation
   role described in the permission matrix. If these have not been provided,
   stop after validation.

3. Configure the `agentcore-evaluation` profile in your local AWS config. Then
   set the Runtime-owner values in the root `.env` (`../.env` from
   `runtime-agent/`) while leaving both execution guards disabled:

   ```dotenv
   AGENTCORE_RUNTIME_REGION=us-west-2
   AGENTCORE_RUNTIME_AGENT_ARN=arn:aws:bedrock-agentcore:<REGION>:<ACCOUNT_ID>:runtime/<RUNTIME_ID>
   AGENTCORE_RUNTIME_QUALIFIER=DEFAULT
   AGENTCORE_EVALUATION_LOG_GROUP=/aws/bedrock-agentcore/runtimes/<RUNTIME_ID>-DEFAULT
   RUN_AWS_EVALUATION=0
   AGENTCORE_EVALUATION_CONTENT_CAPTURE_CONFIRMED=0
   ```

4. Verify that the profile resolves to the intended evaluation role:

   ```bash
   export AWS_PROFILE=agentcore-evaluation
   aws sts get-caller-identity
   ```

5. Have the Runtime owner confirm that the non-production Runtime has approved
   message-content capture enabled:

   ```text
   OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT=true
   ```

   The runner refuses to start until the Runtime owner confirms that content
   capture, retention, and access controls are approved.

6. Keep `AWS_PROFILE=agentcore-evaluation` set in the same shell and run the
   live AWS evaluation:

   ```bash
   AGENTCORE_EVALUATION_CONTENT_CAPTURE_CONFIRMED=1 \
   RUN_AWS_EVALUATION=1 \
   npm run eval:aws
   ```

The command invokes the evaluation Runtime, waits for its session spans, and
scores them with:

- `Builtin.Correctness`
- `Builtin.GoalSuccessRate`
- `Builtin.TrajectoryExactOrderMatch`

The synchronous on-demand API returns scores and the runner saves a redacted
local JSON report. It does not create a persistent AWS evaluation-run resource
or console URL. The associated sessions and traces appear in CloudWatch.

See [AWS evaluation details](docs/aws-evaluation.md) for wait controls,
troubleshooting, and evidence handling.

## 10. Everyday operation

Use the AWS profile selected in step 5. The example keeps the sample
`agentcore-dev` name.

Terminal 1:

```bash
cd /path/to/chatgpt-agents-sdk-aws-agentcore-cookbook
export AWS_PROFILE=agentcore-dev
cd mcp-adapter
npm start
```

Terminal 2:

```bash
export CONTROL_PLANE_API_KEY="<OpenAI tunnel runtime API key>"
tunnel-client run --profile agentcore-cookbook
```

Stop either process with `Ctrl+C`. Restart the MCP server after changing
`.env`; restart the tunnel client after changing its runtime key.

## 11. Troubleshooting

### Missing or rejected model key

If `OPENAI_API_KEY` is missing or Bedrock returns `401`, `403`, or an
expired-token error:

1. Renew the Amazon Bedrock API key.
2. Confirm that the key, model, and `OPENAI_BASE_URL` use the approved Region.
3. Restart the MCP server.

Do not send the key to the access team.

### OpenAI trace export returns `401`

Confirm that `OPENAI_TRACE_API_KEY` belongs to the selected OpenAI Platform
project and is not the Bedrock or tunnel key.

### Local AWS telemetry reports `AccessDenied`

Send the denied AWS action, Region, service name
`chatgpt-agentcore-cookbook-local`, and approximate time to the AWS access
team. Reference the local telemetry row in the permission matrix and
[AWS IAM details](docs/aws-iam.md).

### Existing Runtime invocation is denied

Confirm the account, Region, Runtime qualifier, and assumed role. IT must allow
`bedrock-agentcore:InvokeAgentRuntime` on both the exact parent Runtime and
endpoint ARNs.

### AWS evaluation is denied

An invoke-only role is expected to fail. Confirm that `AWS_PROFILE` selects the
evaluation role from the permission matrix. The denied action identifies
whether evaluator metadata, span query, evaluation, or judge-model access is
missing.

### Tunnel authentication or discovery fails

For `401 Unauthorized`, confirm that `CONTROL_PLANE_API_KEY` belongs to the
tunnel-owning organization and its principal has Tunnels Read + Use.

If the tunnel is missing from ChatGPT, ask the Platform/workspace administrator
to verify the workspace association and Developer mode. The error:

```text
We couldn't automatically verify the association between these workspaces and organizations.
```

means OpenAI could not verify the organization-to-workspace mapping. It is not
a local MCP or tunnel-client error. Ask the account team for a reviewed manual
association override if the administrator cannot complete the association.

For tool discovery, check:

```bash
curl -fsS http://127.0.0.1:8787/
tunnel-client doctor --profile agentcore-cookbook --explain
curl -fsS http://127.0.0.1:8080/readyz
```

### AWS login expired

```bash
aws sso login --profile agentcore-dev
aws sts get-caller-identity --profile agentcore-dev
```

Restart the MCP server after refreshing the login.

### A `.env` change is ignored

Exported shell variables override `.env`. Check variable presence without
printing values:

```bash
for name in OPENAI_API_KEY OPENAI_TRACE_API_KEY OPENAI_BASE_URL COOKBOOK_EXECUTION_MODE; do
  if printenv "$name" >/dev/null 2>&1; then
    printf '%s: exported\n' "$name"
  else
    printf '%s: not exported\n' "$name"
  fi
done
```

Unset stale values or open a clean terminal, then restart the server.

### Port `8787` or `8080` is already in use

On macOS:

```bash
lsof -nP -iTCP:8787 -iTCP:8080 -sTCP:LISTEN
```

On Linux:

```bash
ss -ltnp | grep -E ':(8787|8080)\b'
```

Stop only a process you recognize.

## Optional notebook and developer checks

Launch the notebook from the example root:

```bash
uv run --project runtime-agent --locked --extra dev --env-file .env \
  jupyter lab notebooks/chatgpt_agents_sdk_aws_agentcore_cookbook.ipynb
```

The notebook introduces the agent configuration and request flow, then runs
credential-free checks by default. Set the live-step flags before launching
Jupyter and restart the kernel after configuration changes. Supporting process
and report code lives in [notebook_helpers.py](runtime-agent/notebook_helpers.py).

Run all credential-free checks:

```bash
cd runtime-agent
npm test
npm run eval:validate
npm run eval:run
npm run eval:agent:validate
uv run pytest
uv run ruff check .
uv run ruff format --check .
uv run pyright

cd ../mcp-adapter
npm run build
npm run typecheck
npm run test
```

## Conclusion

You have connected a private tool server to ChatGPT, followed a flight request
through the Agents SDK workflow, and displayed validated results in a widget.
The checks cover different parts of that integration: local tests validate
contracts, fresh evaluations check agent responses, and matching traces confirm
telemetry delivery. Complete the live steps to verify your configured model,
Runtime, or ChatGPT connection.

To adapt the example, replace the sample functions in
[runtime-agent/tools.py](runtime-agent/tools.py) with read-only calls to your
service. Update the Python and MCP schemas, widget, and evaluation cases
together, then rerun the checks. Keep credentials outside the widget and source
tree, and choose hosting and tracing settings with your platform team. Stop
the MCP server and tunnel client with `Ctrl+C` when you finish testing.

## References

- [Architecture and trust boundaries](docs/openai-agentkit-cookbook.md)
- [Existing AgentCore Runtime](docs/existing-agentcore-runtime.md)
- [AWS AgentCore Evaluations](docs/aws-evaluation.md)
- [AWS IAM policy shapes](docs/aws-iam.md)
- [Executable notebook](notebooks/chatgpt_agents_sdk_aws_agentcore_cookbook.ipynb)
- [OpenAI Secure MCP Tunnels](https://developers.openai.com/api/docs/guides/secure-mcp-tunnels)
- [OpenAI Platform project roles](https://help.openai.com/en/articles/9186755-managing-your-work-in-the-api-platform-with-projects)
