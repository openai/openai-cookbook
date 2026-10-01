# Daytona sandboxes

Run Agents API tasks with `codex exec-server` in Daytona sandboxes:

- [Application-managed](application_managed/README.md): create a sandbox, run a task,
  read its output, and clean up the sandbox and session.
- [Webhook-managed](webhook_managed/README.md): deploy a controller that provisions
  workers and restarts stopped workers when a session needs a connection.

Both modes use [sandbox.py](sandbox.py) for executor installation and launch.
Workers receive only the restricted executor key; application credentials stay
in the application or webhook controller.
