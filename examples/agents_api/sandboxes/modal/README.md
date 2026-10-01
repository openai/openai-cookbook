# Modal sandboxes

Choose who provisions and cleans up the sandbox:

- [Application-managed](application_managed/README.md): run a report task with a
  sample file, then terminate the sandbox and delete the Agents API session.
- [Webhook-managed](webhook_managed/README.md): deploy a signed webhook receiver
  and reconnect sessions through named Modal sandboxes.

Both modes use [modal_executor.py](modal_executor.py) for the base image and
executor command. The application adds its report tools and sample file on top;
the webhook controller packages the shared Python source in its deployment.
Only the restricted executor key reaches the sandbox.
