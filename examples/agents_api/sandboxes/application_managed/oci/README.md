# Application-managed OCI GenAI Sandbox

Your application creates an Agents API session and an OCI GenAI Sandbox, starts
`codex exec-server`, and asks the agent to turn `brief.txt` into `plan.md`.
It prints the plan, stops and deletes the sandbox, and deletes the session.

## Before you begin

OCI GenAI Sandboxes are in beta. Contact your Oracle account manager to request
access for your account.

Get the beta Python SDK from Oracle. Create a sandbox-enabled Generative AI
Project and save its OCID.

Grant your OCI group permission to manage projects and sandboxes in the chosen
compartment:

```text
allow group <group-name> to manage generative-ai-sandbox in compartment <compartment-name>
allow group <group-name> to manage generative-ai-project in compartment <compartment-name>
```

Use a runtime with Node.js and npm. Allow outbound HTTPS to `registry.npmjs.org`
and `api.openai.com`, plus WebSocket connections to
`codex-cloud-environments.chatgpt.com`. Allow any additional hosts your task needs.

## Configure access

Authenticate an OCI security-token profile with the OCI CLI:

```bash
uv tool run --from oci-cli oci session authenticate --profile-name Sandbox --region us-chicago-1
```

Set `OPENAI_API_KEY` and a separate restricted `OPENAI_EXECUTOR_API_KEY`.
The keys must have the same owner, organization, and project. Only the executor
key enters the sandbox as `CODEX_API_KEY`. See
[executor authentication](https://developers.openai.com/api/docs/guides/agents-api/environments/self-hosted#authentication).

Set your project OCID and the path to the beta SDK wheel from Oracle:

```bash
export OCI_SANDBOX_PROJECT_ID="ocid1.generativeaiproject..."
export OCI_SANDBOX_SDK_WHEEL="/path/to/oci-<beta-version>-py3-none-any.whl"
```

The script uses the `Sandbox` profile and `us-chicago-1` region. Optional settings:

| Variable | Default |
| --- | --- |
| `OCI_SANDBOX_PROFILE` | `Sandbox` |
| `OCI_SANDBOX_REGION` | `us-chicago-1` |
| `OCI_SANDBOX_ENDPOINT` | `https://inference.generativeai.<region>.oci.oraclecloud.com` |
| `OCI_SANDBOX_RUNTIME` | `python-3.11` |
| `OCI_SANDBOX_SHAPE` | `SMALL` |
| `OCI_SANDBOX_EXPIRATION` | `PT30M` |

Confirm the runtime, shape, region, and endpoint with your beta onboarding
instructions. The runtime must include npm or support installing it.

## Run

From the Cookbook repository root, run with [uv](https://docs.astral.sh/uv/):

```bash
uv run --with "$OCI_SANDBOX_SDK_WHEEL" examples/agents_api/sandboxes/application_managed/oci/main.py
```

The script declares the Agents API dependency inline and loads Oracle's beta SDK
through `--with`. The beta SDK must provide `oci.generative_ai_sandbox`; use the
package Oracle supplies for your tenancy.

The example waits up to two minutes for sandbox startup and six minutes for the
agent turn. It requests a 30-minute sandbox expiration and attempts cleanup of
both resources in `finally`. If cleanup fails, use the printed IDs to remove the
remaining resources.

Keep the session and sandbox alive for follow-up turns. Do not attach a
provisioning webhook handler to sessions this application manages.

## References

- [OCI Generative AI documentation](https://docs.oracle.com/en-us/iaas/Content/generative-ai/)
- [OCI Python SDK](https://docs.oracle.com/en-us/iaas/Content/API/SDKDocs/pythonsdk.htm)
- [OCI TypeScript SDK](https://docs.oracle.com/en-us/iaas/Content/API/SDKDocs/typescriptsdk.htm)
- [OCI CLI authentication](https://docs.oracle.com/en-us/iaas/Content/API/SDKDocs/clitoken.htm)

The SDK links cover OCI generally. Use Oracle's beta Python SDK for this example.
