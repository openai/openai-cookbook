# Application-managed sandboxes

Your application calls both the Agents API and the sandbox provider. Run one
provider-specific `main.py` locally or in your own cloud; no webhook handler is
deployed.

## How it works

Each example creates an API session, starts the sandbox and executor, submits
input, streams the result, then cleans up both the sandbox and session.

## Choose an example

| Provider | Application and provisioning code | Setup |
| --- | --- | --- |
| Blaxel | [blaxel/main.py](blaxel/main.py) | [Run with Blaxel](blaxel/README.md) |
| Cloudflare | [cloudflare/main.py](cloudflare/main.py) + Worker | [Run with Cloudflare](cloudflare/README.md) |
| Daytona | [daytona/main.py](daytona/main.py) | [Run with Daytona](daytona/README.md) |
| DigitalOcean | [digitalocean/main.py](digitalocean/main.py) | [Run with DigitalOcean](digitalocean/README.md) |
| Docker | [docker/main.py](docker/main.py) | [Run locally](docker/README.md) |
| E2B | [e2b/main.py](e2b/main.py) | [Run with E2B](e2b/README.md) |
| Modal | [modal/main.py](modal/main.py) | [Run with Modal](modal/README.md) |
| Runloop | [runloop/main.py](runloop/main.py) | [Run with Runloop](runloop/README.md) |
| Oracle Cloud Infrastructure (OCI) | [oci/main.py](oci/main.py) | [Run with OCI](oci/README.md) |
| Vercel | [vercel/main.py](vercel/main.py) | [Run with Vercel](vercel/README.md) |

Each provider directory includes its sample and setup instructions.
Run the example from the Cookbook repository root.

For an application that only calls the Agents API, use
[webhook-managed sandboxes](../webhook_managed/README.md) instead. Do not attach a
provisioning webhook handler to sessions already managed by these examples.
