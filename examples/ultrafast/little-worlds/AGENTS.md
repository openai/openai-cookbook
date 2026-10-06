# Working on Little Worlds

This example has a React/Vite frontend and a local Node/Express Responses agent runtime. Read [README.md](README.md), [SECURITY.md](SECURITY.md), and [docs/CONTRACT.md](docs/CONTRACT.md) before changing the generated-page boundary.

- Run commands from this `little-worlds` directory, using Node 22 or newer, `npm ci`, and the committed lockfile; Node 24 is recommended
- Run `npm run check` for code changes. Tests use fixtures and mock model responses; no API key is required
- Keep credentials server-side. Never commit `.env`, API keys, session tokens, `.local/`, `.local-reset-history/`, logs, database exports, or dependency and build output. Never use `VITE_*` for secrets
- Use temporary test directories. Do not reset saved worlds or call paid model APIs as part of routine tests; live tests require explicit opt-in
- Preserve owner and visitor authorization, record ownership, sandbox restrictions, and atomic verification and publication. Generated code must not gain host credentials or unrestricted network or filesystem access
- Preserve the comparison's independent starting snapshots. Only Ultrafast publishes to the saved world; Standard runs in temporary storage
- Keep the app bound to loopback. Simulated sign-in must not be presented as production authentication
- Keep the existing visual style, reduced-motion support, and globe momentum behavior
- Apply the repository's docs-editor skill to changed Markdown, and keep the Cookbook registry entry synchronized with the example
