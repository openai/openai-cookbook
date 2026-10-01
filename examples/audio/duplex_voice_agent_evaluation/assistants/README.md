# Evaluated assistant

One GPT Live voice frontend supports two backend-delegation architectures.
Both use the same evaluation scenarios, application state, and grading.
Commands below assume the harness directory; see [setup](../README.md#3-set-up-and-run)
for setup and installed-wheel usage. Live commands require model access and incur API usage.

```text
config.py                    environment settings, prompt loading, and session selection
resources.py                 assistant-owned prompt, tool, and fixture loading
runtime.py                   shared tool contracts and asynchronous execution
errors.py                    assistant lifecycle and delegated-tool errors
frontend/
  assistant.py                shared GPT Live connection, audio, and events
  connection.py               observable delegation events without evaluator execution
  events.py                   exactly-once terminal events and closed-stream handling
  transport.py                authenticated transport and session protocol
  prompts/voice.txt           shared voice-agent instructions
responses/
  assistant.py                OpenAI-managed Responses delegation
  delegation.py               assistant-owned tool execution and result injection
  prompts/backend.txt         backend instructions
  tools/definitions.json      Responses-owned application tool schema
  tools/restaurant.py         Responses-owned application tools and offline behavior
  tools/restaurant_facts.json Responses-owned authorized business facts
client/
  assistant.py                application-managed delegation
  backend.py                  provider-neutral application-backend contract
  openai_backend.py           optional OpenAI Responses reference adapter
  memory.py                   caller/assistant transcript context
  prompts/backend.txt         backend instructions
  tools/definitions.json      client-owned application tool schema
  tools/restaurant.py         client-owned application tools and offline behavior
  tools/restaurant_facts.json client-owned authorized business facts
```

Each backend is self-contained: edit its own prompt, tool schema,
implementation, and facts without changing the other backend. Only the voice
frontend and generic execution contracts are shared. Set models, voices,
credentials, and optional application endpoints in the selected `.env` file or
shell. See [environment-file selection](../README.md#environment-file-selection).

## Bundled comparison baseline

The two bundled restaurant assistants are intentionally independent copies.
For a controlled comparison of delegation architectures, their backend prompts,
tool schemas, business facts, authorization rules, and observable tool behavior
must agree. Their orchestration, conversation memory, and result-injection
mechanisms are expected to differ. Matching baseline behavior does not require
identical Python source or a shared restaurant implementation.

Run the offline contract tests after changing either backend:

```bash
uv run pytest assistants/tests/test_restaurant_baseline.py
```

The tests compare the bundled resources, exercise both implementations against
explicit success and failure expectations, check that denied actions cannot
mutate state, and verify that state and customizations stay isolated. They also
compare offline behavior over the bundled scenarios using only caller-visible
inputs and authorized application state. Evaluator-private expected answers,
grading rules, and completion criteria must not enter assistant code.

For a baseline bug fix, update both independently owned copies and add a common
regression case. For an intentional experiment, use a clearly named branch or
separate application backend; record which prompt, schema, facts, permissions,
model settings, or behavior differ. Keep the bundled baseline unchanged when
possible. If a reviewed product decision changes the bundled comparison itself,
replace only the affected parity assertion with explicit per-variant expected
behavior and document the difference here. Do not broadly skip the parity suite
or weaken authorization and state-isolation tests. Results from customized or
remote applications must not be described as an architecture-only comparison
unless their application behavior and relevant settings have been aligned.

## OpenAI-managed Responses delegation

```bash
uv run crawl-eval --example restaurant_005 --assistant responses
uv run run-eval --scenario restaurant_booking_complete --assistant responses
```

`responses/` configures `session.delegation.type: "responses"`.
GPT Live owns the delegated Responses conversation, and application tools
execute inside the assistant. After the invocation completes and every function
has returned, the assistant sends all `response.item.create` results followed by
one `response.create`. Nested `response.completed.output` is not the function inventory.

## Application-managed client delegation

```bash
uv run crawl-eval --example restaurant_005 --assistant client
uv run run-eval --scenario restaurant_booking_complete --assistant client
```

`client/` configures `session.delegation.type: "client"`. The application:

1. Observes actual caller and assistant transcript events.
2. Builds an incremental timestamped transcript for each delegation.
3. Calls any separately managed model, agent, or application backend.
4. Executes authorized application tools against scenario-isolated state.
5. Returns natural-language results using `session.commentary.append`.

V3 `session.delegation.created.delegation` contains IDs and a target, without task
text. The backend resolves the request from retained history and incremental
transcript fragments. Returned commentary carries the original `delegation_id`;
`session.commentary.appended.client_event_id` confirms acceptance, not speech.

GPT Live does not provide complete conversation memory to a client backend.
The application owns context, transcript history, backend continuity, and tool
execution. Implement the `ApplicationBackend` protocol for any model provider,
or use the bundled OpenAI adapter, which replays application-owned history with
`store: false`.

The evaluator uses `/v1/live/sessions`, Bearer authentication, and
`session.start` with `session.model`, startup `input`, and 24 kHz PCM audio.
`session.update` is reserved for supported same-mode delegation changes.
Transcript frames use the provider session clock; untimed output audio uses
local playout timing. Turns are derived from speech and transcript evidence.

Sessions created by this evaluator carry audio and control events on the same
authenticated WebSocket. The toolkit does not provide a WebRTC, SIP, or
separately attached sideband adapter.

## Existing application endpoint

Configure a separately deployed application in `.env`:

```dotenv
OPENAI_CLIENT_ASSISTANT_ENDPOINT=wss://agent.example.com/ws/assistant
# Set the same dedicated random secret on the service and evaluator.
OPENAI_CLIENT_ASSISTANT_TOKEN=<your-service-token>
```

```bash
uv run run-eval --scenario restaurant_booking_complete --assistant client
```

The endpoint must implement the WebSocket contract in `client/remote.py` and
authenticate its `Authorization: Bearer …` header before accepting the
WebSocket upgrade. The connector requires TLS outside loopback, rejects
credential-bearing URLs and redirects, and forwards only the transcript, turn,
delegation, and session-close events the backend needs. The service
maintains its own backend conversation, prompts, tools, and application state.
Tool execution stays inside that application. It reports observable
`tool.called`/`tool.completed` events and application-state snapshots to the
evaluator; no tool-execution callbacks are sent back to the harness.

Provision any scenario-specific application state inside the remote service.
The harness does not automatically forward scenario fixtures or business facts
to external endpoints.

For a remote application, tool events and state snapshots are evidence reported
by that service. The evaluator does not independently query its underlying
systems or enforce the service's business authorization rules.

`OPENAI_RESPONSES_API_KEY` optionally supplies a dedicated backend credential;
otherwise the existing `OPENAI_API_KEY` is reused. For local development,
`uv run client-assistant --port 8795` starts the bundled loopback-only example
after `OPENAI_CLIENT_ASSISTANT_TOKEN` has been configured. Generate a separate
secret with `uv run python -c 'import secrets; print(secrets.token_urlsafe(32))'`
and store the same value in the service's and evaluator's private environments.
Do not reuse an OpenAI API key, commit the secret, or put it in a URL. Existing
unauthenticated endpoints must be updated before using this connector. The
in-process client assistant does not require this extra token.

The reference service rejects browser Origins by default. An authenticated
nonbrowser client may omit Origin; use repeated `--allow-origin` options only
for exact trusted browser origins. An allowed Origin does not replace
authentication. `/health` remains public and exposes no application state.

Default limits are eight connections, four pending delegations per connection,
64 total delegations, 256 KiB messages, 8 MiB of session input, and 20,000 events.
Configuration must arrive within 10 seconds; sessions last at most 10 minutes,
and each delegation has a 60-second deadline. Embedders can pass a validated
`ServiceLimits` object to `create_app`. Service and transport error envelopes
omit backend exception details; authorized tool outputs and state snapshots
remain sensitive application data. Production deployments still need per-user authorization,
tenant isolation, rate limits, TLS termination, secret rotation, and controlled
logging. Tools with external side effects must enforce their own deadlines and
idempotency: cancelling an async task cannot undo an action or stop an already
running synchronous tool.

## Transport termination

### Delegation work

All delegation controllers implement the same `pending`, `wait()`, and `close()`
contract. `pending` becomes true when work is accepted and stays true through
result publication. For managed Responses it covers application-owned tool
calls; for the in-process client it covers backend handoffs and their injected
answers; for the remote client it covers forwarded delegation IDs until their
correlated answers and completion observations arrive. It does not claim that
the provider has finished speaking or that no future delegation can arrive.
RUN's live caller uses independent managed Responses reasoning without application
tools or a local delegation controller. Its local tool hooks report no pending
work and need no cleanup. RUN tracks caller Responses work separately and blocks
semantic completion while that work is pending.

`wait()` waits for accepted work to reach quiescence and raises a retained
lifecycle error if that work failed or was abandoned. Canceling or timing out a
waiter does not cancel the delegation. Callers that need a deadline can wrap
the wait in `asyncio.wait_for` and then explicitly close the session.
`close()` stops acceptance, cancels and joins locally owned tasks, closes owned
resources once, and wakes waiters. It is not a transaction rollback and cannot
stop an already-running synchronous external operation. A handled business-rule
rejection remains a normal observed `tool.failed` result, not necessarily an
infrastructure failure.

Remote applications must send one or more `live.send` messages containing
`session.commentary.append` with the original `delegation_id`, followed by
an `assistant.event` containing `client_delegation.completed` with the same
`delegation_id`. Completion before result injection, unknown IDs, unexpected
disconnects, and shutdown with unfinished work fail the lifecycle wait. Duplicate
completion observations do not complete another delegation. The single-turn
collector still separately checks active Responses/client-delegation IDs, pending
work, completed assistant turns, and post-tool speech before ending a response.

### Event streams

The frontend and single-turn wrapper deliver one terminal event. A protocol
`session.closed` ends normally; unexpected EOF, malformed events, and transport
failures produce an explicit error. Intentional cancellation and repeated
cleanup do not create extra infrastructure failures. Local shutdown events are
marked synthetic and cannot satisfy provider finalization: a started session
must return a real `session.closed` with cumulative `usage.seconds`. The remote connector
reports unexpected termination to the same consumer, so RUN can attribute the
failure to the affected participant instead of waiting for a generic timeout.
