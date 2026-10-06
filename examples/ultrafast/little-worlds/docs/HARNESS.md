# Local agent runtime

Little Worlds runs a local Responses-based harness with one persistent builder session per space. It is not connected to the hosted Agents API. The application keeps identity, space routing, public data, execution, verification, and publication outside the model's authority.

For the local trust boundaries and deployment limitations, see [Security](../SECURITY.md). The precise endpoint and module contract is in [CONTRACT.md](CONTRACT.md).

## One person, one space, one saved thread

`server/identity.mjs` maintains `.local/identities.json`, mapping each person to a space ID. Mira keeps her original store at `.local/space.json`. James, Jake, Erica, Leo, and new people use `.local/spaces/<space-id>/space.json`. Every space store contains its own published code revisions, live state, model/tool item history, turn list, session ID, and latest 150 events. Each space has a separate transaction queue and turn workspace directory.

New personal spaces start with empty `projects`, `contributions`, and `extras`, plus the same seed module whose render output is empty. Nora is the exception: her first-created space includes the bundled Town Square board. `server/demo-prompts.mjs` holds creative briefs for the seven optional generated examples. Preparing those worlds submits the briefs through the ordinary authenticated builder, producing model output, tool results, checks, revisions, and saved conversations. A new account can request the same features through the same path.

With the local API running, `npm run prepare-demo` runs `scripts/prepare-demo.mjs` using temporary demo sign-in sessions and at most two concurrent builds. It records successful preparation in `.local/demo-preparation.json` only after the recorded turn completed, its revision passed checks, and required capabilities are present. Each entry identifies the prompt hash, session, turn, revision, and source hash. Repeating preparation checks that history and preserves later owner edits; an interrupted invocation can find its matching saved turn. `npm run prepare-demo -- --rebuild` requests new normal turns deliberately. It never resets a space or discards its history.

`meta.layout: 'canvas'` makes generated `space.js` responsible for the full personal page body, including headings, artwork, project tiles, service interfaces, and interactions. Identity, navigation, friendships, community discovery, the composer, and authenticated service transport remain trusted application code. The old `studio` kind remains only for storage compatibility; it does not select a privileged starter page or builder instruction set. Historical studio revisions without `meta.layout` retain display compatibility. Opening a saved space does not replace its source with a persona template.

Selecting a person at Demo sign-in creates a random bearer token, indexed by its hash in an in-memory server session. The default expiry is 12 hours. The browser keeps its token in per-tab session storage, allowing Iris and Leo to use independent tabs. This demonstrates authorization for a selected identity; it does not prove who selected that identity.

The HTTP router derives the actor from the token. Owners may submit, cancel, inspect revisions and their thread, restore, or reset their own space. Signed-in visitors receive published HTML, public state, and filtered change events. Their snapshot excludes generated source, tests, owner prompts, and private session history. Their actions always run as the server-derived actor, regardless of submitted `actor` fields. Legacy URLs remain authenticated aliases to the caller's own space, not a way to choose an arbitrary actor.

Signing out revokes the current token and closes its event streams. It does not cancel the space's running turn. Returning to the same person retrieves the same stored session and workspace state. Restarting the server invalidates tokens; saved people, spaces, and threads persist. An abandoned turn is marked interrupted, with missing tool-call results completed as interruptions before a later model request. A crashed turn is not transparently resumed.

## A build request

1. The router authenticates the request to `/api/spaces/:spaceId/turn` and verifies that the selected person owns that space. The service reads its current module, tests, and public state into the turn context. It supplies the owner's identity, not the account registry or another space's data
2. The service creates a turn workspace containing only `space.js` and `tests.js`. Mira uses `.local/workspaces/<turn-id>/`; other spaces use `.local/spaces/<space-id>/workspaces/<turn-id>/`
3. The Responses adapter requests `gpt-6-astra` with `service_tier: ultrafast`, streaming enabled, and `store: false`. It requests encrypted reasoning for stateless replay. Completed output items and function results are preserved locally; private reasoning is not inspected or displayed
4. The model writes JavaScript and behavioral tests. The Codex-style custom `apply_patch` tool combines write, verify, and publish into a host-controlled operation, reducing round trips while retaining verification. It handles both complete files and incremental line edits. Separate inspect, read, verify, and publish tools support inspection and repairs
5. The runtime compiles the module and executes it in QuickJS WASM in a worker without application credentials. No network, filesystem, Node API, or host DOM is exposed to generated code. Fresh interpreter contexts have memory and execution limits, plus a worker watchdog. The host applies any valid `meta.projects` declarations to a clone of current data, then tests actual render and reducer behavior against that candidate state
6. Publication verifies the exact source against the latest state and atomically saves the new revision and its candidate catalog. Live participation remains separate from generated source. A visitor action committed after verification causes the host to rebuild the candidate from the latest state and verify it again before publication. Contributions, extras, and unrelated state fields are preserved exactly; a verified project declaration may update or add catalog entries
7. The service emits real model, tool, check, publication, and visitor events. The canvas consumes lifecycle and draft events; detailed diagnostics are retained for debugging. Visitors receive only allowed public change notifications. Requested and served tier remain separate values

The model can repair failed checks up to three times, with a maximum of eight responses per turn. No extra model request is needed merely to announce successful publication. Failure preserves the previous published source.

The shared builder instructions in `server/harness.mjs` guide both typed and voice-submitted builds toward fluid, responsive motion that fits the owner's creative direction. They cover seamless loops, intentional timing, stable geometry, efficient rendering, and the local game runtime's transform interpolation, while retaining deliberate easing, discrete game rules, and stylized motion. Follow-up edits should preserve working animation and controls. These are generation guidelines for all spaces, not changes to saved pages or a frame-rate guarantee; the current code checks do not measure browser animation performance.

## Parallel service-tier comparison

The normal browser composer requests `compare: true`. The service snapshots the same source, tests, state, and saved conversation for two independent builders. Both use the configured model and low reasoning; one requests `service_tier: ultrafast`, and the other requests `service_tier: default`. The Ultrafast builder uses the real space store. Standard uses temporary storage, and its result cannot enter the saved world or builder history.

Both builders execute the full verification and repair loop. A verified Ultrafast result publishes immediately and becomes interactive. **Enter your world** closes the comparison and cancels any unfinished Standard run. A failed or cancelled Ultrafast turn keeps the previous published world. There is no winner-selection step.

A separate short `gpt-6-sol` request estimates a shared output budget for the progress bars. A failed estimate or a four-second timeout uses a local fallback. This adds API usage to the two builder workloads. Elapsed time and streaming-rate measurements describe the observed run; independent generations can differ in output length and repair work. Comparison state is transient and clears on server restart.

## Streaming the work

A bounded Codex patch parser projects streamed file additions and line edits into a draft. Legacy JSON call streams retain their partial-JSON decoder for compatibility. Preview work runs outside stream ingestion, with at most one active render and one latest pending snapshot. Stale work is discarded after cancellation, steering, or publication. When a completed render function can compile, the same isolated runtime produces an inert draft preview while the model continues writing the reducer and tests. The preview uses the same host catalog projection as verification, so a newly declared fourth tile appears before publication without changing saved data. Its event includes the module's layout, allowing the app to display a full canvas immediately. Incomplete syntax is ignored; preview parsing never evaluates JavaScript in Node.

At most four distinct preview frames are emitted per turn. A temporary no-op reducer may satisfy the preview module shape, but it is never saved or published. Only the original complete source can pass the normal publication path. A coherent draft can appear late in a generation, depending on where the model puts its completed render function; the app does not pretend that every token is a working visual update. Failure or cancellation dismisses the draft. Successful publication replaces it once the matching published HTML reaches the browser.

The display iframe has an opaque origin, restrictive CSP, and only the trusted action, service, and resize bridge script. Generated scripts, handlers, external resources, and navigation are rejected or blocked. Drafts are inert: ordinary actions, service requests, and reference opening are disabled.

## Services inside generated pages

Any published module can declare the services it needs from `health-chat`, `finance-news`, and `space-agent` in `meta.capabilities`. The model authors the entire visible interface in `render()`: layout, forms, loading states, conversation rows, article cards, and styling. There are no Jake- or James-specific React widgets appended outside the generated page. A normal new account has access to the same declaration and binding contract.

`space-agent` uses `meta.agent` for the owner-defined purpose and permitted reducer actions. It streams Astra Ultrafast replies using the server-held key, with temporary per-viewer conversation history separate from the builder thread. The host validates tool arguments and applies actions as the authenticated visitor. Shared canvases combine actor-owned marks, rendering the latest mark at each position, so visitors can paint over visible work without modifying another person's records.

The generated HTML uses named `data-service` sections, forms, templates, and text fields described in [CONTRACT.md](CONTRACT.md). `src/frame-service-bridge.ts` binds trusted response data to those authored elements using text content and approved reference links. It does not execute generated scripts. `src/space-services.ts` owns authenticated transport and transient conversation state; the iframe never receives credentials.

The parent checks the current frame, per-render bridge key, published capability list, operation, and input shape. Every network request then targets `/api/spaces/:spaceId/services/:capability` with the displayed revision ID. The server independently checks that this is still the current published revision and that its verified metadata enables the service. A caller-supplied capability list or a declaration appearing only in an unverified draft grants nothing. Unknown services, absent capabilities, and stale revisions are rejected.

Health replies stream from a separate model request with the host's educational scope, checked reference notes, and emergency handling. The generated page cannot replace those instructions. Conversation text stays in the current viewer's in-memory service session and transient HTTP request. It is not written to public space state, builder history, revisions, or the event ledger. Leaving the page, changing the published revision, signing out, or explicitly clearing the chat discards that session; stopping a response preserves visible partial text but excludes it from later model context. This local behavior makes no claim about model-provider retention.

Finance news comes from an allowlisted Federal Reserve feed. The host validates and dates items, caches retrieval, and reports saved-reference fallback honestly. A generated article link opens only if it matches an approved URL in the latest service result. Generated pages do not gain arbitrary network or navigation access.

## State, ownership, and turn control

Every space's mutations are serialized. An atomic file rename is the commit point. Its events have increasing IDs, allowing authenticated SSE reconnects to replay after `Last-Event-ID` without duplicating events. Replay is bounded to the latest 150 events.

A second owner message during generation is steering input. The pending instruction prevents stale work from publishing; the next model step receives it with the prior tool results. Cancellation aborts the upstream request and is checked again immediately before publication. Cancellation cannot undo an already committed revision or visitor action.

An interaction submits an action and revision ID. Stale revision IDs are rejected. The generated reducer enforces feature behavior, while independent host checks reject every reducer change to `state.projects` and prevent one actor from modifying another actor's contribution or feature records. This applies to owner clicks as well as visitor clicks. New feature data uses `extras.<feature>.<recordId> = {actorId, ...fields}`. Changed records must belong to the trusted actor; ownership cannot be reassigned. Aggregate counts are derived from these records.

Catalog editing takes a separate owner-authorized route: generated source may declare `meta.projects` with stable IDs, titles, descriptions, and colors. The host validates those declarations, updates matching entries, and appends new entries. Omitted projects remain, so their contributions cannot become orphaned. Declarations cannot replace contributions, extras, or unrelated project fields. The owner can therefore ask for another tile or redesign the page without giving public interaction code catalog-write permissions.

All generated state is public to visitors of that space. These record-write checks do not provide private fields or guarantee honest presentation by owner-controlled code. The owner may change what is displayed, and an explicit owner reset clears the space. Do not store secrets in generated state.

Restore projects the earlier module's catalog onto current data, verifies that candidate, and publishes it as a new revision. Earlier declarations may restore a tile's title, description, or color, but later projects omitted from those declarations remain with their contributions. A declared point budget smaller than an existing participant allocation is rejected. Reset is different: it deliberately creates a fresh seed and session for this space only, while idle.

## API references

The transport follows the official [streaming function-calling guide](https://developers.openai.com/api/docs/guides/function-calling#streaming), [reasoning item replay guidance](https://developers.openai.com/api/docs/guides/reasoning#keeping-reasoning-items-in-context), and [Ultrafast guide](https://developers.openai.com/api/docs/guides/ultrafast-mode). The application owns the local builder sessions and executes tools itself through the Responses API.

## Model transport

Per-space builder sessions use a persistent Responses WebSocket with a stable session cache key. Each request sends complete input with low reasoning, low verbosity, and `store: false`. This avoids relying on connection-local predecessor state after reconnecting or restoring a revision. The connection closes after 30 seconds idle, on cancellation, or on service shutdown. A changed session key replaces the connection.

The default transport is `auto`. An unavailable upgrade falls back to HTTP before sending; a request is never replayed after sending. Embedded agents and health conversations always use independent HTTP requests, including when an embedded agent supplies a space cache key. `LITTLE_WORLDS_TRANSPORT=http` disables WebSockets. Completion metrics record transport, connection reuse, cached input, reasoning tokens, and timing. See [Responses WebSocket mode](https://developers.openai.com/api/docs/guides/websocket-mode) for the API transport.

## Codex-style patches

The builder has one model-visible writer: `apply_patch`, a Responses custom tool using the Codex-derived Lark grammar in `server/codex-patch.mjs`. Full writes use `*** Add File`; edits use `*** Update File` with context and +/- lines. Parsing, sequential file operations, line matching, EOF handling, and LF normalization follow the corresponding Codex implementation. The in-memory adapter adds path and size/work limits: only `space.js` and `tests.js` can be addressed, and both must remain present in the final workspace. A malformed patch applies nothing. A failed verification leaves the working draft available for repair while the published page stays intact.

All edits for one request are batched into one tool call; parallel calls are disabled. Full verification, live-data checks, cancellation guards, and atomic publication still apply. Publication uses the verified module title rather than exposing the owner's request as a public revision title. The removed model-visible JSON writers remain executable for old saved histories and local adapters. Native custom call/result types are preserved through streaming, errors, and restart recovery.

Activity shows the raw patch text once, in arrival order. The patch preview machinery projects incoming edits into provisional file contents for rendering. Provisional contents are display-only; they never write to the working files or publish. The adapter retains Astra, `reasoning.effort: low`, Ultrafast, and the existing output budget.
