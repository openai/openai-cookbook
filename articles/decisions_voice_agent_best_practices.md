# Build reliable GPT-Live application backends

GPT-Live can continue a spoken conversation while an application performs delegated work. A reliable agent must also preserve the user's current intent, execute only authorized tools, and report what actually happened. This guide combines documented API behavior with application design recommendations. It makes no measured performance claims.

## Choose the delegation boundary

**Documented behavior.** [GPT-Live delegation](https://developers.openai.com/api/docs/guides/live-delegation) supports a managed Responses backend and client delegation. Client delegation lets your application run a custom router, agent or service. It leaves application context, execution and result delivery under your control.

**Recommendation.** Use client delegation when your application needs to select among backends or enforce its own execution policy. Keep the interface small: a bounded request and context go in; a verified fact, clarification or failure comes out. Give the frontend conversational instructions and the backend precise task and tool instructions. Avoid repeating long tool descriptions in the voice prompt. Follow the [Live prompting guide](https://developers.openai.com/api/docs/guides/live-prompting) when tuning conversational behavior.

Start with one complete path before adding an evaluation campaign. The [supplied-WAV lookup example](../examples/audio/decisions_voice_agent.md#4-run-one-spoken-lookup) checks its input locally by default and requires `--run` for provider calls. It connects a support frontend to the Luna router and local MCP lookup through one command. If you deploy the backend separately, configure client delegation, a dedicated service token and the service endpoint explicitly; the example documents the additional loopback setting for local development.

## Reconstruct intent from the conversation

**Documented behavior.** A `session.delegation.created` event identifies the delegation and target; it does not supply a complete task description. Client applications consume transcript events and application context. Results can be appended as commentary, silent thinking context or instructions, with the appropriate delegation ID. The [delegation guide](https://developers.openai.com/api/docs/guides/live-delegation) documents these event forms and the 500-token append limit.

**Recommendation.** Keep durable task state in application code. Track the current request, corrections, authorization and completed actions separately from conversational history. Preserve relevant earlier context when transcript handoffs are incremental. If the user asks “What about the other one?” and the referent is missing, ask for clarification. Do not invent an entity from an incomplete transcript.

## Treat routing and authorization separately

**Recommendation.** A finite router should select an option from an application-owned list. An option can reference a fixed tool and validated arguments. Validate the selected option again before execution, then enforce the user's authorization at the tool boundary. A probability or a schema-valid answer does not grant permission.

Use a reasoning backend when the task requires interpretation or argument construction beyond that finite catalog. Apply the same authorization and result checks to its tool calls. Put confirmations before consequential actions and verify the resulting application state before claiming success. The read-only [lookup example](../examples/audio/decisions_voice_agent.md) demonstrates the smaller execution boundary.

**Documented behavior.** [Structured Outputs](https://developers.openai.com/api/docs/guides/structured-outputs) can constrain a Responses result to a JSON schema. Applications must still handle refusals and incomplete responses. Schema compliance does not establish semantic correctness.

## Keep tool and MCP content in the data boundary

**Recommendation.** Allow only the tools required by the task. Validate arguments, bound response size and execution time, and distinguish unavailable tools from successful empty results. For a Model Context Protocol (MCP) connection, pin the server you intend to run, limit its credentials and inspect the returned data. Tool output can contain untrusted text; it must not become a new system instruction. See the [official MCP Python SDK](https://github.com/modelcontextprotocol/python-sdk) for protocol lifecycle and client/server examples.

For data applications, separate context or catalog retrieval, query planning, query authorization and query execution. A catalog lookup provides information; it does not grant permission to execute a query. The same separation applies to a computer-use planner and the executor that changes application state.

## Cancel work and reject stale results

**Documented behavior.** Spoken interruption does not by itself cancel application-owned work. Applications must manage cancellation and state changes. See [client delegation responsibilities](https://developers.openai.com/api/docs/guides/live-delegation).

**Recommendation.** Assign each request a revision. On a correction or cancellation, invalidate the old revision and stop pending work where supported. Check the revision again before publishing results. A late successful lookup is still stale if it answers a superseded request. Record whether cancellation reached the tool; do not imply that cancelling a local coroutine reverses a remote side effect.

Set explicit session, delegation, tool and output limits. Audit retry defaults before testing a paid backend. If a request might have executed but its outcome is unknown, reconcile that attempt before retrying a consequential action. The sample backend stops new provider work in the current session after interrupted routing. A new connection creates fresh state; it does not settle the previous request's outcome or usage. Avoid automatic reconnect-and-replay behavior.

## Measure the answer the user needed

**Documented behavior.** The [voice-agent evaluation guide](https://developers.openai.com/cookbook/examples/audio/voice_agent_evaluation) separates interaction quality from task and tool outcomes. Its response-latency metric includes a qualifying spoken preamble; this is distinct from task completion.

**Recommendation.** Report routing latency, tool latency and time to a verified useful answer separately. For audio, measure from the end of audible user speech to first audible response and to the useful answer. Label filler speech as first response, not completion. Preserve failed, unanswered and censored attempts in the denominator. Document whether percentiles describe individual turns or per-run aggregates.

Compare backends with the same tasks, model identity where applicable, context, ordered action catalog including descriptions, tools and input audio. Record effort, service tier, caching and transport conditions. If a setting is not exposed on one endpoint, disclose that difference. Preserve initial connection failures and slow first calls; do not infer caching or warm-up from timing alone. Use repeated paired trials and uncertainty estimates; an offline fixture test is not a model or audio benchmark.

Use the configured network route when adding instrumentation or disabling retries. A custom HTTP transport can change proxy handling. Check the installed client's behavior before the first request and distinguish failures before HTTP transmission from requests whose outcome is unknown.

## Close sessions and retain usage evidence

**Documented behavior.** The [Live conversations guide](https://developers.openai.com/api/docs/guides/live-conversations) describes closing a session with `session.close` and receiving `session.closed`. Preserve the final cumulative `usage.seconds`; do not sum cumulative snapshots. Backend usage is separate.

**Recommendation.** Register the close listener before sending the close request, keep the receiver alive until the final event, and bound how long you wait. If the transport ends first, record final usage as unconfirmed. An application timeout is a shutdown trigger, not proof of a hard billing limit. Log correlation IDs, state revisions, selected and executed routes, tool outcomes and timing milestones with sensitive values redacted.

Use the [Live migration guide](https://developers.openai.com/api/docs/guides/live-migration) when updating integrations. Recheck current protocol fields and supported models before rerunning an old example.
