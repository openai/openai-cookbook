# Application-managed Databricks Sandbox

Your application creates an Agents API session and a Databricks sandbox, starts
`codex exec-server` in the sandbox, and runs one turn in which the agent writes a
greeting file. The example reads the file back to verify, then stops the executor,
deletes the session, and deletes the sandbox. The application drives the whole
lifecycle through outbound calls only; no inbound endpoint or webhook is involved.

## Before you begin

- A Databricks workspace with the sandbox feature enabled, and `databricks-sdk >= 0.153.0`.
- Python 3.11+ (the script declares its dependencies inline for `uv`).
- Two OpenAI keys, from the same organization, project, and user or service-account:
  - `OPENAI_API_KEY` - the application key that creates sessions (kept outside the sandbox).
  - `OPENAI_EXECUTOR_API_KEY` - a dedicated environment key created on the OpenAI
    Agents tab (`platform.openai.com/agents` -> Environments -> Keys), with every
    other permission set to None. It enters the sandbox as `CODEX_API_KEY`. A general
    API key does not work for the executor: it is rejected with `403 missing required
    scope api.agents.environments.connect`. See
    [executor authentication](https://developers.openai.com/api/docs/guides/agents-api/environments/self-hosted#authentication).
- If your OpenAI organization enforces an IP allowlist, the sandbox's egress IP must
  be added to the allowlist; Managed Agents then rejects traffic from unregistered
  IPs. See [Databricks Outbound IPs](https://docs.databricks.com/aws/en/resources/ip-domain-region#outbound-ips)
  for the list of Databricks IPs that need to be allowlisted.

Note: the Agents API does not yet support Zero Data Retention (ZDR), including with
self-hosted sandboxes. Factor this into customer use cases.

## Configure access

The example uses a Databricks SDK config profile for the workspace and reads the
OpenAI keys from the environment:

```bash
export DATABRICKS_CONFIG_PROFILE=my-workspace   # For additional Databricks authentication modes, see https://docs.databricks.com/aws/en/dev-tools/auth/
export OPENAI_API_KEY=sk-...                    # application key
export OPENAI_EXECUTOR_API_KEY=sk-...           # agent environment key
```

## Run

From the Cookbook repository root, run with [uv](https://docs.astral.sh/uv/):

```bash
uv run examples/agents_api/sandboxes/databricks/application_managed/main.py
```

The script:

1. Creates a `self_hosted` OpenAI session with `workspace_directory` set to a path in the sandbox.
2. Provisions the sandbox (`create_sandbox`, or reuse and `start_sandbox`) and waits for it to reach `RUNNING`.
3. Creates the agent's workspace directory in the sandbox.
4. Runs `codex exec-server` in the sandbox.
5. Runs one turn: the agent writes a greeting file; the example reads it back to verify.
6. Tears down: stops the executor, deletes the session, and deletes the sandbox.

Keep the session and sandbox alive for follow-up turns. Do not attach a
provisioning webhook handler to sessions this application manages.

## References

- [Databricks Sandbox product docs](https://docs.databricks.com/aws/en/compute/serverless/sandbox)
- [Databricks SDK sandbox API](https://databricks-sdk-py.readthedocs.io/en/latest/workspace/sandbox/sandbox.html)
- [Databricks SDK sandbox command execution](https://databricks-sdk-py.readthedocs.io/en/latest/sandbox-command-execution.html)
- [Self-hosted sandboxes](https://developers.openai.com/api/docs/guides/agents-api/environments/self-hosted)
