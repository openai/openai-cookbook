# Build a read-only lookup backend for a GPT-Live voice agent

## What you'll build

Build a small application backend that selects a read-only support lookup, calls a local Model Context Protocol (MCP) server, and returns a verified synthetic fact. The example separates route selection, tool authorization and result delivery so you can test them independently.

Start with an offline scripted router and a real local MCP lookup. Then run an optional client-delegation service with a GPT-6 Luna Structured Outputs router. The service uses the existing voice evaluator's application boundary, reconstructs the current transcript and rejects stale work. Starting the service alone does not open a GPT-Live session; a frontend supplies the audio connection.

This builds on the [GPT-Live evaluation guide](https://developers.openai.com/cookbook/examples/audio/voice_agent_evaluation) by Kait Healy, Karsten Schroer, and Erika Kettleson. That guide supplies the CRAWL, WALK and RUN evaluation strategy; this example focuses on the application backend for a small, inspectable task. Attribution does not imply review or endorsement of this example.

## Prerequisites

- Python 3.12 or later and [uv](https://docs.astral.sh/uv/).
- A checkout of [OpenAI Cookbook](https://github.com/openai/openai-cookbook).
- Access to the package index for the initial dependency install. Subsequent runs can use the installed environment offline.

The default example needs no API key, microphone, database or customer data. MCP runs as a local subprocess using synthetic records. The dependency declaration is in [pyproject.toml](decisions_voice_agent/pyproject.toml).

## 1. Keep the responsibilities small

```text
Timestamped user transcript + application context
                    |
         Application backend
                    |
       Finite route selection
                    |
  Validate option + fixed tool arguments
          /                    \
 Local MCP lookup          Clarify / unsupported
          \                    /
      Reject stale or cancelled work
                    |
          Verified result text
```

In a complete voice application, GPT-Live sits before and after this flow. It handles the spoken interaction and delegates work to the application. [Client delegation](https://developers.openai.com/api/docs/guides/live-delegation) is the documented boundary for a custom router or backend. It does not make an arbitrary routing service a managed Responses backend.

The synthetic task has two lookup options: the status of order `DEMO-1001` and the return policy. Application code owns the tool names and arguments. The router can select an option, ask for clarification or declare the request unsupported. It cannot create a new tool or grant access to another order.

## 2. Run the local example

From the repository root:

```bash
cd examples/audio/decisions_voice_agent
env -u VIRTUAL_ENV uv run python demo.py
```

The demo starts a real MCP session, looks up the synthetic order and prints routing and tool events followed by:

```text
Order DEMO-1001 has shipped. Its estimated delivery is Friday.
```

A successful local lookup verifies the protocol and application path. It does not demonstrate provider routing accuracy or a spoken response.

Read the implementation in this order:

1. [agent.py](decisions_voice_agent/agent.py): the finite choices, application-owned mapping and backend lifecycle.
2. [support_server.py](decisions_voice_agent/support_server.py): the synthetic read-only tools.
3. [mcp_tools.py](decisions_voice_agent/mcp_tools.py): the local MCP connection and tool-result handling.
4. [demo.py](decisions_voice_agent/demo.py): the offline composition.

The MCP client and server use the [official Python SDK](https://github.com/modelcontextprotocol/python-sdk). They do not use a model to generate or execute tool arguments.

## 3. Verify failures as well as the successful lookup

Run the offline tests from the same directory:

```bash
env -u VIRTUAL_ENV uv run pytest -q
```

The test suite exercises the real local MCP boundary and checks routing and lifecycle failures: ambiguity, unsupported requests, incorrect or invalid routes, unavailable tools and interruption. A cancelled or superseded request must not publish a late answer. The standalone router clarifies incremental follow-ups; the optional voice service supplies full current-session transcript snapshots. It does not persist state across sessions.

The scripted router is useful for testing these application invariants. Its behavior is authored into the fixture, so test pass counts are not estimates of model accuracy. The wrong-route test deliberately returns the policy when asked about an order: that choice is allowed by the schema but still produces a semantically wrong answer. The application does not secretly correct it with an answer key. Keep evaluator expectations separate from the information supplied to a real router.

## 4. Reuse the voice evaluation boundary

The existing evaluator defines [ApplicationBackend](duplex_voice_agent_evaluation/assistants/client/backend.py):

```python
class ApplicationBackend(Protocol):
    async def run(self, handoff: DelegationHandoff, emit: EventCallback) -> str: ...
    async def close(self) -> None: ...
```

`DelegationHandoff` carries generic work instructions, a timestamped transcript and a follow-up indicator. Use the user's conversation and verified state to establish intent; do not route on generic `handoff.task` instructions. In a production backend, retain the relevant earlier state when each handoff contains only an incremental transcript.

The evaluator's [client service](duplex_voice_agent_evaluation/assistants/client/service.py) accepts backend and controller factories. [voice_service.py](decisions_voice_agent/voice_service.py) uses these hooks to provide a bounded support service. Each connection owns its router, transcript and synthetic tool executor. This service calls the same fixture functions directly; it does not measure MCP transport latency.

From the sample directory, install the optional dependencies and set a dedicated local service token:

```bash
export OPENAI_CLIENT_ASSISTANT_TOKEN="$(python -c 'import secrets; print(secrets.token_urlsafe(36))')"
env -u VIRTUAL_ENV uv run --extra live python serve.py
```

This starts the scripted service at `ws://127.0.0.1:8795/ws/assistant`. Keep the token private and use it in the frontend's client-service configuration. It must be separate from your API key. To use a model router, configure `OPENAI_API_KEY` securely and explicitly select Luna:

```bash
env -u VIRTUAL_ENV uv run --extra live python serve.py --router luna
```

The service permits one connection, one pending delegation and at most two delegations per session, with finite session, work and cleanup deadlines. It reconstructs full transcript snapshots and preserves delegation IDs. New user text invalidates pending answers. If a provider request is cancelled, the service stops admitting work because local cancellation cannot establish provider completion or usage. Offline fixtures can demonstrate replacement work without that uncertainty.

Run the optional service tests with `uv run --extra live pytest -q`. The default tests skip service integration when those dependencies are absent. For an actual voice connection, supply the support frontend instructions, matching application resources and documented [client-delegation session configuration](https://developers.openai.com/api/docs/guides/live-delegation). The existing evaluator's restaurant resources are not interchangeable with this support example. A local service test does not establish spoken output or device playback.

## 5. Replace the fixture and compare fairly

A model router should receive the same bounded user request, application context and ordered option catalog. It should return only a declared option. Preserve the original selection and any effective route after validation so that a fallback does not hide a routing failure.

The [Luna adapter](decisions_voice_agent/luna_router.py) uses [GPT-6 Luna](https://developers.openai.com/api/docs/models/gpt-6-luna) with reasoning disabled, Standard service tier and a strict [Structured Outputs](https://developers.openai.com/api/docs/guides/structured-outputs) enum. It includes option descriptions, bounds input and output, disables SDK retries, and rejects refusal, incomplete output or malformed responses before tool execution. Other providers can implement the same `RoutingBackend.choose()` interface using their documented contracts.

Evaluate three questions separately:

| Question | Controlled comparison |
| --- | --- |
| Can a backend select the right finite option? | Identical request, context, ordered choices and model identity where supported; no fallback hiding wrong choices. |
| Does the workflow produce the correct fact? | Same tool catalog and reasoning fallback; report selected routes, executed routes, abstentions and verified results. |
| Does the voice agent help the user promptly? | Same audio, frontend instructions and tools; measure first audible response and useful verified answer separately. |

Include ambiguous requests, wrong-entity requests, tool outages and corrections. Freeze held-out cases before prompt tuning. Repeat paired trials with balanced execution order. Record the actual model identifiers, effort, service tier, caching, transport and retry settings; disclose settings that cannot be matched. The same mutable model alias does not establish identical frozen weights across endpoints.

Report correctness and coverage alongside latency, including errors and timeouts in the attempt count. Match the option descriptions as well as their names: an enum-only schema and a described choice catalog provide different information. Do not compare a finite classification request with a reasoning agent's complete tool workflow and attribute the entire difference to the routing interface. This public example does not publish provider or voice performance results.

## Next steps

Use the [backend best-practices guide](../../articles/decisions_voice_agent_best_practices.md) for context, authorization, cancellation, observability and session closure. Extend this lookup only after verifying the real provider and voice boundaries. Computer use and text-to-SQL require their own supported execution and authorization designs; this example does not implement them.
