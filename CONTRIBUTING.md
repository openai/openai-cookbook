# Contributing the the cookbook

The OpenAI Cookbook is a collection of useful patterns and examples of working with the OpenAI platform, provided as a community resource.

> Contributions are reviewed on a best-effort basis - we can't provide guarantees around when or if content contributions will be reviewed or merged.

Stay tuned to this page for further guidance on cookbook contributions as they become available 🙏

## Cross-platform path safety

The repository enforces cross-platform path safety in CI. New files and directories must avoid:

- trailing spaces or periods in any path component
- Windows-reserved device names such as `CON`, `PRN`, `AUX`, `NUL`, `COM1`, or `LPT1`
- names that collide after Windows path normalization

If you contribute from Windows, prefer a WSL-based workflow:

- clone the repository inside the Linux filesystem rather than under `/mnt/c/...`
- open the repo with VS Code Remote - WSL (`code .`)
- run Git commands from WSL instead of Windows Git against a `\\\\wsl$` path

This keeps local development aligned with the repository's portability checks and avoids Windows path handling edge cases when working with older clones or historical revisions.
