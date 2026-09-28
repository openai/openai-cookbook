# Self-hosted sandbox examples

Choose how your application starts sandbox compute. Both modes run the agent in
OpenAI's cloud and connect the sandbox through `codex exec-server`.

| Mode | Your application | Sandbox provisioning |
| --- | --- | --- |
| Application-managed | Run the provider's `application_managed/main.py`. | Your application starts and stops compute directly; no webhook handler. |
| [Webhook-managed](webhook_managed.md) | Run the provider's `webhook_managed/client.py`. It calls only the Agents API. | A separately deployed handler starts or reconnects compute when OpenAI sends a webhook. |

Choose one provisioning mode per session. Deleting an API session does not stop
provider compute; each example documents cleanup of both.

## Choose a provider

| Provider | Application-managed | Webhook-managed |
| --- | --- | --- |
| [Blaxel](blaxel/README.md) | [Run](blaxel/application_managed/README.md) | [Deploy](blaxel/webhook_managed/README.md) |
| [Cloudflare](cloudflare/README.md) | [Run](cloudflare/application_managed/README.md) | [Deploy](cloudflare/webhook_managed/README.md) |
| [Daytona](daytona/README.md) | [Run](daytona/application_managed/README.md) | [Deploy](daytona/webhook_managed/README.md) |
| [DigitalOcean](digitalocean/README.md) | [Run](digitalocean/application_managed/README.md) | [Deploy](digitalocean/webhook_managed/README.md) |
| [Docker](docker/README.md) | [Run](docker/application_managed/README.md) | Not included |
| [E2B](e2b/README.md) | [Run](e2b/application_managed/README.md) | [Deploy](e2b/webhook_managed/README.md) |
| [Modal](modal/README.md) | [Run](modal/application_managed/README.md) | [Deploy](modal/webhook_managed/README.md) |
| [OCI](oci/README.md) | [Run](oci/application_managed/README.md) | Not included |
| [Runloop](runloop/README.md) | [Run](runloop/application_managed/README.md) | [Deploy](runloop/webhook_managed/README.md) |
| [Vercel](vercel/README.md) | [Run](vercel/application_managed/README.md) | [Deploy](vercel/webhook_managed/README.md) |

Each provider folder contains its examples and shared sandbox setup. Webhook
examples include their own client; they do not import code from another provider.
Run commands from the Cookbook repository root unless the provider README says otherwise.
