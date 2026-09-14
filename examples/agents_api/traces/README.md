# Export session traces to Braintrust

Export existing Agents API traces to a Braintrust project for inspection and
analysis. The script pages through your sessions, fetches their available traces,
and sends one trace page at a time as OTLP JSON. It does not collect the full
export in memory or add Braintrust-specific span attributes.

This is a one-off export or historical backfill. It exports only sessions visible
to your API key's project and traces still available under their retention policy.
It does not wait for late traces or take an atomic snapshot across pages. Use it
on completed sessions when you want to inspect finished work.

## Setup

You need Python 3.11+, [uv](https://docs.astral.sh/uv/), existing sessions with
traces, and a Braintrust project. The public session trace endpoint must be
available to your OpenAI project. Your OpenAI key needs permission to list
sessions and read traces.

Set these environment variables using your existing credentials:

- `OPENAI_API_KEY`: an OpenAI key for the sessions' project.
- `BRAINTRUST_API_KEY`: a Braintrust key that can write to the destination project.
- `BRAINTRUST_PROJECT`: the destination project name.

For an EU or self-hosted Braintrust data plane, also set `BRAINTRUST_API_URL`.
The default is `https://api.braintrust.dev`. See
[Braintrust's OpenTelemetry guide](https://www.braintrust.dev/docs/integrations/sdk-integrations/opentelemetry)
for endpoint and project header configuration.

The script uses HTTP directly so it does not require a preview SDK. OpenAI
requests go to `https://api.openai.com/v1` by default; `OPENAI_BASE_URL` overrides
that base URL for local testing. Each key is sent only to its respective service.

## Run the export

From the Cookbook repository root, start with the five most recent sessions:

```bash
uv run examples/agents_api/traces/export_to_braintrust.py
```

Export all accessible sessions:

```bash
uv run examples/agents_api/traces/export_to_braintrust.py --all
```

Or choose a smaller set with `--max-sessions 10`. Each upload preserves the
original trace IDs, span IDs, parent relationships, and attributes. In Braintrust,
open the destination project's logs to inspect the imported traces. Provider
rendering of messages, costs, and other summaries may differ.

## Failures and retries

The script reports each session and exits nonzero if any session fails. A session
with no available traces reports zero. A failure listing sessions stops the run;
a failure fetching or uploading a session's traces is reported and the script
continues with the next session. HTTP errors and OTLP partial rejections count as
failures, even when Braintrust returns HTTP 200.

Retry a failed session using the ID printed by the script:

```bash
uv run examples/agents_api/traces/export_to_braintrust.py --session-id sess_...
```

Repeat `--session-id` to retry several sessions. If a trace page exceeds a size
limit, try `--page-size 1`; an individual oversized trace may still fail.

An earlier page may have been accepted before a failure. The script does not
retry uploads automatically or track delivery across runs. Re-running can resend
spans; do not assume the receiver will deduplicate them. This example is not a
continuous delivery service.

## Test without credentials

The focused tests use mock HTTP responses for pagination and upload failures:

```bash
uv run --with pytest --with httpx pytest examples/agents_api/traces/test_export_to_braintrust.py
```
