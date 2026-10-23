# DigitalOcean sandboxes

[DigitalOcean Managed Agents](https://docs.digitalocean.com/products/managed-agents/)
is in public preview. These examples use its Harness Runtime and require PyDo
0.41.0 or later with async support:

- [Application-managed](application_managed/README.md): create a sandbox, run a
  task, download its output, and delete both the sandbox and Agents API session.
- [Webhook-managed](webhook_managed/README.md): run a signed webhook controller
  that provisions sandboxes and resumes them on reconnect.

Both modes use [environment.yaml](environment.yaml). The `codex-agentapi`
template starts the executor, and only the restricted executor key is supplied
to the sandbox.
The webhook controller is separate from sandbox compute and can run locally or
on App Platform.
