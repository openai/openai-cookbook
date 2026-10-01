# Runloop sandboxes

Run Agents API tasks in Runloop devboxes with either provisioning model:

- [Application-managed](application_managed/README.md): the application creates
  a devbox, runs a task, and cleans up the devbox and API session.
- [Webhook-managed](webhook_managed/README.md): a signed webhook controller
  creates or resumes a worker devbox for each session.

Both modes use [sandbox.py](sandbox.py) to install and launch `codex exec-server`.
Application-managed tasks use `/home/user/workspace` and pass the restricted
executor key as an environment variable. Webhook-managed workers use `/workspace`
and a Runloop secret reference; the controller's main API key stays behind a
Runloop gateway.
