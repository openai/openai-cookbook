# Application-managed client delegation

Configures GPT Live with `session.delegation.type: "client"`. This assistant
owns transcript handoffs, backend conversation memory, application-tool
execution, and `session.commentary.append` result injection.

Commands assume the harness directory. See [setup](../../README.md#3-set-up-and-run)
for setup and installed-wheel usage; live commands incur API usage.

Everything needed to customize this backend lives in this folder:
`prompts/backend.txt`, `tools/restaurant.py`, `tools/definitions.json`, and
`tools/restaurant_facts.json`. Frontend instructions live in
`../frontend/prompts/voice.txt`.

The bundled restaurant behavior follows the
[comparison-baseline contract](../README.md#bundled-comparison-baseline).
Keep baseline fixes aligned with Responses; document intentional variants.

```bash
uv run run-eval --scenario restaurant_booking_complete --assistant client
```

Set `OPENAI_CLIENT_ASSISTANT_ENDPOINT` in the selected `.env` file or shell to connect an existing
application implementing the reference WebSocket contract. The remote
application owns its prompts, backend, memory, tools, and state; it reports
completed tool observations to the evaluator without requesting evaluator-side
execution. Configure application fixtures inside the remote service and set a
dedicated `OPENAI_CLIENT_ASSISTANT_TOKEN` on both sides; never reuse an API key.
See [service setup](../README.md#existing-application-endpoint).
Remote connections require TLS. For an intentionally plaintext loopback service,
also set `OPENAI_CLIENT_ASSISTANT_ALLOW_INSECURE_LOOPBACK=true`; this never permits
remote plaintext. See [security and artifact handling](../../README.md#artifact-and-connection-safety).

The backend is provider-neutral: implement `ApplicationBackend` for your own
model or agent, or use `openai_backend.py` as an optional OpenAI reference
adapter. Conversation history always belongs to the application.
