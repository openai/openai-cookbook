# Vercel sandboxes

Choose who starts and reconnects the executor:

- [Application-managed](application_managed/README.md): a Python application
  creates a non-persistent sandbox, reads the output, and cleans up both resources.
- [Webhook-managed](webhook_managed/README.md): TypeScript functions verify
  webhooks and use Vercel Queues to provision named sandboxes.

The modes use different provider SDKs and keep their implementations separate.
Both run `codex exec-server` with a restricted `OPENAI_EXECUTOR_API_KEY`; the
application/session-read key stays outside the sandbox. The two OpenAI keys must
have the same owner, organization, and project.

Use a dedicated Vercel project with Sandbox access. The webhook mode also needs
Queues access. Test deployments should use a separate project, not overwrite an
existing application. Each mode's README covers credentials, execution limits,
and cleanup.
