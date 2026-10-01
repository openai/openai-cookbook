# Application-managed AWS Lambda MicroVM

[main.py](main.py) asks the agent to write `hello.txt` in a MicroVM, then downloads
and checks it. It terminates the VM and deletes the session.
See the [AWS guide](../README.md) for the architecture.

## Setup

You need Python 3.11+, `uv`, AWS credentials with Lambda MicroVMs access, and an
`OPENAI_API_KEY` with Agents API access. Run these commands from the repository root:

```bash
export AWS_PROFILE=your-profile
export AWS_REGION=us-west-2
export EXAMPLE_DIR=examples/agents_api/sandboxes/aws/application_managed
aws sts get-caller-identity --region "$AWS_REGION"
```

Set `OPENAI_API_KEY` for the local application. Store a separate environment key
(`OPENAI_EXECUTOR_API_KEY`) in Secrets Manager as `codex/agents-api/executor`.
The two keys must share the same organization, project, and user or service-account
owner. Use a plaintext SecretString or JSON with an `OPENAI_EXECUTOR_API_KEY` field,
and the default Secrets Manager encryption key.

### 1. Create the runtime role

```bash
export EXECUTOR_SECRET_ARN="$(aws secretsmanager describe-secret \
  --secret-id codex/agents-api/executor --region "$AWS_REGION" \
  --query ARN --output text)"
uv run "$EXAMPLE_DIR/configure_execution_role.py" \
  --executor-secret-arn "$EXECUTOR_SECRET_ARN"
```

Run once to create `codex-agents-api-executor` with read access to that secret.
The role and secret ARNs are saved in `.local/execution-role.json`.
A customer-managed KMS key also requires `kms:Decrypt` permission.

### 2. Build the image

```bash
uv run "$EXAMPLE_DIR/build_image.py" --name codex-executor
```

The script creates an S3 source bucket, build role, and CloudWatch log group,
then uploads the [Dockerfile](Dockerfile) and [sandbox_server.py](sandbox_server.py).
AWS builds the image with 8 GB memory (4 vCPU baseline). The script saves its ARN
and version in `.local/image.json`.

### 3. Run

```bash
uv run "$EXAMPLE_DIR/main.py"
cat "$EXAMPLE_DIR/.local/hello.txt"
```

To reuse the VM across two turns:

```bash
uv run "$EXAMPLE_DIR/main.py" --suspend-resume
```

The script suspends and resumes the VM after the first turn. The next turn reads
the existing `hello.txt`, and the script downloads it again to verify its contents.

Use `--image-state`, `--execution-state`, or `--output` to change the local paths.
State and output files are saved in `.local/`, which Git ignores.

## Runtime hooks

[sandbox_server.py](sandbox_server.py) handles AWS's lifecycle hooks. The ready
hook lets AWS snapshot the idle server. At launch, the run hook receives the
session's environment ID, remote URL, and secret ARN. It reads the key through
the VM's IAM role and starts Codex with `CODEX_API_KEY` in its environment.
The validate hook checks Codex and workspace access. Suspend and terminate stop
the executor and flush writes. Resume reloads the key and reconnects.

## Transfer files

Both routes use AWS's authenticated ingress proxy and paths relative to `/workspace`:

- `PUT /upload/<path>` writes raw bytes to a file and creates missing directories.
  The limit is 64 MiB. An incomplete upload leaves the existing file unchanged.
- `GET /download/<path>` downloads a file.

Directories and paths or symlinks outside `/workspace` return 404.
The shared helpers handle AWS authentication and URL encoding:

```python
from pathlib import Path
from common import upload_file, download_file

await upload_file(microvms, vm_id, Path("input.csv"), "data/input.csv")
await download_file(microvms, vm_id, "reports/result.csv", Path("result.csv"))
```

The executor connects outbound to OpenAI through AWS's internet egress connector.
Use a different connector for private networking.

## Reuse and cleanup

The image, roles, source bucket, log group, and secret stay in AWS for reuse.
Rebuild after changing the Dockerfile or server:

```bash
uv run "$EXAMPLE_DIR/build_image.py" --rebuild
```

Cleanup runs on success or error. Each VM has a 15-minute maximum lifetime and a
10-minute inbound idle limit; outbound executor traffic doesn't reset the idle timer.
The suspend/resume example allows up to five minutes suspended. Rebuild an older
image before using this option. Only suspend between turns, after tools finish.

To remove the example, terminate remaining VMs and delete the image, source bucket,
log group, and roles listed in the state files. Delete the secret when no other
workloads use it. The [webhook-managed example](../webhook_managed/README.md)
shares the image and runtime role.
