# Source attribution

## AWS paid-research companion sample

- Contributor: Nick (`mccartnick`), AWS Solutions Architect
- Reviewed revision: `85aa4e5ca9a2d55ad7c412f2d015011095b2222d`
- Review date: August 5, 2026
- License: Apache-2.0

The companion sample reports a live multi-agent testnet run using a
Bedrock-hosted OpenAI model, AgentCore Payments, delegated wallet signing, an
x402 V2 challenge, and a paid retry that returned HTTP 200. That is evidence
for the AWS sample at the reviewed revision, not for this example's optional
live path.

The provider-neutral setup language and below-price session exercise informed
this example. No source code from the AWS sample is copied. This example
independently implements a narrower one-agent, one-tool pattern with
application-owned authorization, challenge validation, idempotency, receipts,
audit evidence, and deterministic local tests.
