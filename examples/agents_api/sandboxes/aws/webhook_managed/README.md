# Webhook-managed AWS Lambda MicroVM

An OpenAI webhook starts a MicroVM through API Gateway and Lambda.
[main.py](main.py) asks the agent to write `hello.txt`, then downloads and checks it.
It terminates the VM and deletes the session. See the [AWS guide](../README.md)
for the architecture.

## Setup

Create the runtime role and image with the
[application-managed setup](../application_managed/README.md).
The deploy script reads its `.local/image.json` and `.local/execution-role.json`.
You also need AWS permissions for Lambda, API Gateway, IAM, and Secrets Manager.
Run these commands from the repository root:

```bash
export AWS_PROFILE=your-profile
export AWS_REGION=us-west-2
export EXAMPLE_DIR=examples/agents_api/sandboxes/aws/webhook_managed
```

Set `OPENAI_API_KEY` to the same application key. Create an agent for this webhook
and set its returned ID:

```bash
uv run "$EXAMPLE_DIR/main.py" --create-agent codex-microvm-webhook-demo
export OPENAI_AGENT_ID=agent_...
```

### 1. Create the controller secret

Create `codex/agents-api/webhook-controller` in Secrets Manager with these JSON fields:

- `OPENAI_API_KEY`: the application key.
- `OPENAI_WEBHOOK_SECRET`: leave empty until the webhook is registered.

Use the default Secrets Manager encryption key.

```bash
export CONTROLLER_SECRET_ARN="$(aws secretsmanager describe-secret \
  --secret-id codex/agents-api/webhook-controller --region "$AWS_REGION" \
  --query ARN --output text)"
```

### 2. Deploy and register

```bash
uv run "$EXAMPLE_DIR/deploy.py" \
  --agent-id "$OPENAI_AGENT_ID" \
  --controller-secret-arn "$CONTROLLER_SECRET_ARN"
```

[deploy.py](deploy.py) creates the Lambda and API Gateway's `POST /webhook` route.
It saves resource IDs in `.local/deployment.json`. Rerun it to deploy code changes
or use a new image version.

In your OpenAI project's **Settings → Webhooks**, register the printed URL for
`agent.session.action_required` and `agent.session.failed`. Copy the signing secret
into `OPENAI_WEBHOOK_SECRET` in the controller secret, preserving `OPENAI_API_KEY`.

### 3. Run

```bash
uv run "$EXAMPLE_DIR/main.py"
cat "$EXAMPLE_DIR/.local/hello.txt"
```

[handler.py](handler.py) verifies the webhook signature and checks that the session
belongs to the configured agent and still needs an executor. It launches the VM
and saves its ID in session metadata for the client to read.

The client needs AWS permission to read VM details, create an authentication token, and
terminate the VM.

To test webhook-driven resume, rebuild the image, redeploy the handler, then run:

```bash
uv run "$EXAMPLE_DIR/main.py" --suspend-resume
```

The client suspends the VM after the first turn, then sends another input.
The webhook resumes the same VM. The agent reads the existing `hello.txt`, and
the client downloads it again to verify its contents.

The client also needs `lambda:SuspendMicrovm`. The deployment script grants the
launcher `lambda:GetMicrovm` and `lambda:ResumeMicrovm`.

## Lifetime and retries

The client stops the VM after the final turn. Subagent events do not trigger
cleanup. The handler also stops the VM on
`agent.session.failed` after checking the current session state.

Each VM has a 15-minute lifetime limit. With `--suspend-resume`, it can remain
suspended for five minutes. Only suspend between turns, after tools finish.
If the recorded VM expires, start a new session. Webhook retries before a VM ID
is recorded can still launch extra VMs.

## Monitoring and cleanup

Set `MICROVM_IMAGE_ARN` to the `image_arn` in the shared `.local/image.json`.

```bash
aws logs tail /aws/lambda/codex-agents-api-webhook --since 10m --region "$AWS_REGION"
aws lambda-microvms list-microvms --image-identifier "$MICROVM_IMAGE_ARN" \
  --region "$AWS_REGION" --query 'items[].{id:microvmId,state:state}' --output table
```

HTTP 400 means the signature is invalid; 503 means the signing secret is missing.
For HTTP 500, check the error type in CloudWatch and the handler's IAM permissions.

To remove the deployment, delete the OpenAI webhook and stop new runs first.
Terminate remaining VMs, then remove the API Gateway API, Lambda, role, and log
group listed in `.local/deployment.json`. Delete the agent and controller secret
when no longer used. The image and executor secret are shared with the
application-managed example.
