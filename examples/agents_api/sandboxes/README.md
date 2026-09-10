# Self-hosted sandbox examples

Choose how your application starts sandbox compute. Both modes run the agent in
OpenAI's cloud and connect the sandbox through `codex exec-server`.

| Mode | Your application | Sandbox provisioning |
| --- | --- | --- |
| [Application-managed](application_managed/README.md) | Run a provider-specific `main.py`. It calls both the Agents API and the sandbox provider. | Your application starts and stops compute directly; no webhook handler. |
| [Webhook-managed](webhook_managed/README.md) | Run the shared `client.py`. It calls only the Agents API. | A separately deployed handler starts or reconnects compute when OpenAI sends a webhook. |

Choose one provisioning mode per session. Deleting an API session does not stop
provider compute; each example documents cleanup of both.

```text
sandboxes/
├── application_managed/
│   ├── blaxel/main.py
│   ├── cloudflare/      # Python application + provisioning Worker
│   ├── daytona/main.py
│   ├── digitalocean/    # Python application + sandbox manifest
│   ├── docker/main.py   # Application + Docker provisioning
│   ├── e2b/main.py
│   ├── modal/main.py    # Application + Modal provisioning
│   ├── oci/main.py      # Application + OCI provisioning
│   ├── runloop/main.py  # Application + Runloop provisioning
│   └── vercel/main.py
└── webhook_managed/
    ├── client.py        # Shared application; Agents API only
    ├── modal/           # Deployable provider handler
    ├── vercel/          # Deployable provider handler
    ├── cloudflare/      # Deployable provider handler
    ├── blaxel/          # Deployable provider handler
    ├── daytona/         # Deployable provider handler
    ├── digitalocean/    # Deployable provider handler
    └── e2b/             # Deployable provider handler
```

Start with the README for your chosen mode, then the provider README. Run commands
from the Cookbook repository root unless a provider README says otherwise.
