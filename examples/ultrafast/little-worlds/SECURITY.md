# Security model

Little Worlds is a loopback-only local demo with simulated sign-in. Anyone using it can select a demo identity. The server enforces the permissions of that selected identity, but does not verify who selected it. Do not expose it as a public multi-user service without real authentication, abuse controls, production storage, and a security review.

API keys belong in the process environment or the ignored `.env` in this example's directory. They must remain on the server and must never use a `VITE_*` name. Generated pages run in a constrained QuickJS runtime and display through an opaque-origin iframe. Host checks control publication and record ownership. See the [application contract](docs/CONTRACT.md) for those boundaries. These checks are not an audited multi-tenant isolation guarantee.

`.local/` contains saved identities, generated code, participation data, private builder conversations, and event history. `.local-reset-history/` contains backups of that data. Keep both directories out of Git, build artifacts, and issue attachments. Generated world state is visible to visitors of that world; do not store credentials or sensitive records in it. Model-powered features send relevant prompts and context to the OpenAI API.

Before contributing, run `npm run check` and inspect your changes for credentials, local data, and generated artifacts. If a credential is exposed, revoke or rotate it; deleting the visible file does not remove it from Git history. Report vulnerabilities privately using [OpenAI's security reporting process](https://openai.com/security-and-privacy/), without posting credentials or private conversations in a public issue.
