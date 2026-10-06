# Local app contract

The current application uses a local persistent Responses harness, not the hosted Agents API. Each registered person owns a separate space and builder session. See [Security](../SECURITY.md) for the security model and [HARNESS.md](HARNESS.md) for execution flow.

API credentials stay server-side. The default model is `gpt-6-astra`, with `service_tier: ultrafast`. The backend loads `.env` from the `little-worlds` example directory, with existing process environment values taking precedence; the key is never included in browser responses.

## Identity and storage

`server/identity.mjs` maps immutable person IDs to immutable space IDs in `.local/identities.json`. The nine demo people are Mira, James, Jake, Erica, Leo, Iris, Luca, Karen, and Nora, each with a matching lowercase person and space ID. New personal accounts and the original eight demo people start with the same empty state and blank module. Seven example pages can be prepared by submitting the creative briefs in `server/demo-prompts.mjs` through the normal authenticated builder; Leo remains a blank starting space. Nora starts with a bundled, verified Town Square message board and icon, without a model call. Existing stores are never replaced by this initialization. Prepared pages are ordinary verified revisions. New names receive server-generated person/space UUIDs. Display names are not authorization identifiers. Mira's retained `studio` kind identifies her legacy store; it does not select different creation or editing powers.

Iris is a painter whose example uses `space-agent` and a declared `paint_pixels` action to combine manual and AI contributions on a shared canvas, initially 48 × 32 pixels. Her brief uses one compact raster surface so later owner edits can increase the resolution without adding thousands of DOM controls. It retains a large, initially blank white surface, small heading, circular palette, and compact AI input, with no seeded artwork. Luca is a language teacher whose example combines scored Spanish lessons with a conversational `space-agent`. Lesson progress belongs to each participant, and the tutor does not award XP. These behaviors live in generated source and use the same publication and runtime checks as any other space.

Fresh communities start with seven sample friendships. Adding new demo identities to an existing registry preserves its saved community graph. A demo reset restores the sample graph and a reusable baseline of default spaces. Recognized older five-, seven-, and eight-person baselines are extended to nine lazily at reset, using verified prepared revisions for only the missing people, or verified current revisions when no valid preparation record exists. Nora's bundled board supplies its clean initial baseline. Existing baseline spaces, histories, and preparation markers are retained. The explicit arcade installer can separately update James's baseline icon after backing up the original baseline.

Mira's existing store stays at `.local/space.json`. All other spaces use `.local/spaces/<space-id>/space.json`. Each store has its own state, revisions, model items, turn list, session ID, and bounded event ledger. Turn files live under that store directory's `workspaces/<turn-id>/`.

Demo sign-in selects an identity without verifying it. The server then creates a 32-byte random bearer token, stores a hash-indexed in-memory session, and derives the actor from that session on every authenticated request. Sessions default to 12 hours. The frontend stores the token in per-tab session storage and sends it in `Authorization`, including for streamed fetches. Tokens do not appear in URLs or event bodies.

Logout revokes only the current token and terminates its event streams; it does not cancel ongoing generation. Server restart invalidates all tokens but keeps the saved people, spaces, and threads. An unfinished turn recovers as interrupted, not as a silently resumed execution.

The owner-only `/api/spaces/:spaceId/files` stream (legacy alias `/api/files`) exposes the generated workspace, never arbitrary filesystem paths. Each `files.snapshot` event replaces the complete view of `space.js` and `tests.js`, including their contents, status, session ID, and published revision ID. Each file retains the builder's 80,000-byte limit. Partial writes and uniquely matched patches are projected in memory and marked as streaming; they are not executable or published. Working writes, publication, cancellation, failure, reset, and restore update the same view. Reconnect sends a fresh full snapshot, updates are coalesced, slow sockets keep only the latest pending snapshot, and session revocation closes the connection.

## Generated module

A space's ES module exports:

```js
export const meta = {
  title: 'A personal space',
  subtitle: '',
  accent: '#687957',
  layout: 'canvas',
  capabilities: ['finance-news'], // Optional named host services.
  suggestions: [{ label: 'Add a guestbook', prompt: 'Add a small visitor-owned guestbook.' }],
  // Optional: the host applies these declarations during owner publication.
  projects: [
    { id: 'glasshouse', title: 'Glasshouse', description: 'A place to grow.', color: '#76916a' }
  ]
};
export function render(state, actor) { return '<section>...</section>'; }
export function reduce(state, action, actor) { return state; }
```

`meta.layout: 'canvas'` assigns the whole personal page body to the module. Historical modules may omit it; no other explicit layout value is accepted. `meta` may also include an integer `budget` from 1 through 1,000 for a points-based feature. Optional `capabilities` contains only `health-chat`, `finance-news`, and/or `space-agent`, without duplicates. Optional `suggestions` contains up to three `{label, prompt}` entries, with nonempty labels up to 60 characters and prompts up to 1,500 characters. These suggestions drive the host composer without persona-specific branching. `render` returns HTML without changing saved state. `reduce` returns the next JSON state or throws for an invalid action. Imports, dependencies, direct network access, filesystem, Node APIs, and arbitrary browser execution are unavailable. Compilation and execution use esbuild and QuickJS WASM, never `node:vm` or host `eval`.

The state shape is:

```js
{
  projects: [{ id, title, description, color }],
  contributions: [{ id, actorId, projectId, points }],
  extras: {
    wishGarden: {
      '<record-id>': { actorId: '<person-id>', text: 'A little wish' }
    }
  }
}
```

All new spaces start with empty arrays and `extras: {}`. A previously saved Mira canvas may retain the stable project IDs `tidepool`, `afterhours`, and `smallhours` so existing contributions survive redesigns. Never assume those projects exist in another space, or that any catalog stays at three entries. The trusted actor is `{id, name}`; generated code must not hardcode participant identities or trust `action.actorId`.

The host rejects every reducer change to `state.projects`, even when the acting person owns the space, and rejects changes to another actor's contributions. New feature collections use `extras.<feature>.<recordId> = {actorId, ...fields}`. Only the acting person may create, change, or delete their records. Ownership cannot change. Unrelated existing data stays unchanged; aggregates are computed from records. No private fields or secrets belong in this state, which is visible to visitors.

### Owner project declarations

An owner-initiated code change can include `meta.projects` when `meta.layout` is `canvas`. This declarative catalog edit is applied by the trusted host. The host accepts up to 60 declarations per module, each containing only:

| Field | Validation |
| --- | --- |
| `id` | Unique within the declaration; 1–64 letters, numbers, underscores, or hyphens. Keep IDs stable to preserve contribution associations. |
| `title` | Nonempty string, at most 120 characters. |
| `description` | String, at most 400 characters. |
| `color` | Hex color with 3, 4, 6, or 8 digits. |

`projectStateForPublication(meta, liveState)` clones current state, updates declared fields on matching project IDs, and appends new IDs. It retains omitted projects, their order, and any unrelated existing project fields. Additional projects can accumulate across publications, subject to the runtime's overall state size limit. Render all live `state.projects`, including projects retained from later revisions.

Draft preview, verification, publication, and restore use this same projection. Verification tests the candidate catalog without committing it. Publication atomically saves verified source and its candidate state; if participation changed after verification, the host recomputes and verifies against the latest state before commit. Contributions, extras, and unrelated state fields remain unchanged. A failed check or cancelled turn leaves the published catalog and source intact.

Restore applies the selected earlier source's declarations to current state and verifies the result. It may revert declared project labels or colors, but cannot remove later projects or orphan their contributions. It also rejects an earlier point budget below a current participant's allocation. Explicit owner reset is different: it deliberately discards that space's current data and thread and returns to the common blank seed.

`createSpaceService` retains a `seedOverride` injection seam for isolated fixtures and tests. Its separate `initialSeedOverride` installs Nora's verified board and icon only when creating her store. Existing stores bypass initialization; explicit owner reset retains the universal blank seed. There is no automatic persona-source replacement when opening a store. Preparing or rebuilding any existing page is an ordinary owner turn against the current data, followed by the same preview, verification, and publication path as any new account.

`npm run prepare-demo` uses `scripts/prepare-demo.mjs` to authenticate as each example owner and submit seven creative briefs, including Karen's four-game arcade, through the normal HTTP turn endpoint. It runs at most two builds concurrently, observes recorded completion and verification, checks the brief's required capabilities, `requiredAgentActions` names, and `requiredGames` IDs, and stores prompt/session/turn/revision/source identifiers in `.local/demo-preparation.json`. These metadata checks do not replace testing the generated interactions. A matching completed preparation is skipped on repeat, preserving later edits; a matching pending or completed turn can recover an interrupted script invocation. `npm run prepare-demo -- --only karen` selects her brief. `--rebuild` submits new ordinary turns for the selected examples, or all seven when no selection is supplied, and never calls reset. No preparation runs automatically on server startup.

`npm run prepare-arcade` is an explicit offline alternative for Karen. The API server must be stopped; the script probes its local port and refuses an active server or unfinished target edit. A deterministic proposal assembled from `server/arcade/` enters the ordinary Codex-style `apply_patch` harness through a local adapter, with the same verification and atomic publication. Only a blank current Karen page is filled; an existing nonblank page is preserved. The script records successful preparation, installs `public/space-icons/james-finance.webp` as James's bubble icon, and makes no model or image API calls. It does not reset spaces or replace James's code, data, or conversation. If a reset baseline exists, it backs up that file and changes only James's icon; adding Karen to an older baseline remains the reset runtime's verified append operation. Repeated installation preserves later Karen edits. See the [optional examples](../README.md#optional-examples-and-voice) for setup.

`node scripts/upgrade-painting.mjs --apply --update-baseline` explicitly upgrades the recognized legacy Iris canvas to the curated raster implementation. Stop the API server first. The script verifies the proposal against current state, backs up affected files, and publishes through the ordinary owner harness without model calls or changes to saved artwork. It refuses unknown or later custom source revisions. `--update-baseline` also verifies and updates the original Iris reset/initial baseline without copying live participation into it; other baseline worlds are preserved. Omit `--apply` for verification and a dry-run plan, or omit `--update-baseline` to leave reset behavior unchanged.

### Display contract

Owner submissions from the host composer request a parallel comparison. Two copies of the same initial source, tests, state and conversation run through this full contract with the same model and low reasoning. The primary requests `ultrafast`; the companion requests `default`. Both use the same five-minute per-response deadline. Ordinary API submissions without `compare: true` retain single-provider behavior.

The composer captures `appTheme: 'light' | 'dark'` at submission, including requests submitted through inspiration tiles and Live. Both lanes receive the same captured appearance, even if the app theme changes during a build. The server validates this enum; omitted preferences default to dark for new API turns and inherit the active preference for steering. The builder's creative contract gives explicit owner theme requests priority, applying a page theme change across backgrounds, text, cards, controls and states. Without an explicit theme, a first build follows the captured app mode; edits preserve the existing world's palette. Blank detection uses the same persisted blank source sentinel as the UI, including after a reset. Theme selection guides generated source and does not inject host CSS or recolor saved worlds automatically.

The eight reviewed demo sources have optional, server-supplied `space.appearance` styles: `lightCss` for their light palettes and `presentationCss` for larger responsive typography. The manifest requires both the expected owner ID and an exact source hash; editing source invalidates these overrides without changing the owner's code or state. These trusted styles are appended inside the existing sandbox, with closing style tags escaped. Typography uses the frame's logical width. Both comparison previews retain the finished canvas's responsive width and uniformly scale their wrappers to fit their respective panes, so opening Activity does not stack or rearrange authored tiles. The scaled footprint tracks content height for scrolling; entering the world removes the scale without remounting the primary iframe. Voice visibility is clipped to the displayed scroll area and converted to logical frame coordinates. The general frame font is a readable fallback, while authored custom font sizes remain authoritative. Builder instructions request readable text, labels and controls for future creations, but these design instructions are not a visual verification guarantee.

Only the primary can publish to the owner's store. The standard companion runs in a temporary, isolated store and workspace with its own adapter and connection; its previews are always inert. Ending or failing either run cannot overwrite the other run's result. Standard resources are released on completion, cancellation or failure, while a bounded owner-only projection retains its visible Activity and comparison metrics. No companion state, revisions or conversation enter the real world's history or visitor surfaces.

The owner-only comparison stream replays the latest metadata, previews, token counts, and shared progress budget on reconnect. A separate, single `gpt-6-sol` request with `reasoning.effort: none` estimates visible output tokens from the task, bounded current source/tests, and builder requirements. It runs concurrently with both builders, has no tools or publication authority, and never changes their input or settings. The estimate is advisory: timeout, invalid output, missing model access, or other failure selects a local fallback without blocking either build. Only the bounded numeric budget and its status enter the owner-only projection; the estimator's prompt and raw response do not.

Both Build progress bars initially use that frozen budget and each lane's actual streamed output count. A successful Ultrafast completion supplies its positive final visible-output count as a separate calibration reference for Standard in the same comparison. Failed/cancelled runs never supply a reference, and the estimator budget itself remains unchanged. Late reference/output telemetry cannot decrease displayed progress. Pending estimates display indeterminate activity unless a completed reference or a real build milestone is available. Verification and publication events provide 90% and 97% progress floors; repairs preserve the previous fill. Only an actual successful terminal harness event fills the bar completely. Failed and cancelled runs retain partial progress. No partial numeric percentage is shown because independent generations can require different output lengths and repairs. Calibration requires no extra API request and does not alter either builder.

Ultrafast becomes interactive once its matching published world loads, even while standard continues. **Enter your world** then stops any unfinished companion and expands that same interactive world. Failed/cancelled primary runs offer **Return to world** instead. Follow-up drafts are kept until the active comparison is finished or stopped.

The React host owns sign-in, identity, navigation, friendships, community discovery, the composer, runtime controls, and privileged host capabilities. Canvas modules own the personal page body inside that shell, including headings, artwork, a dynamic catalog of project tiles, and their interactions. This applies to every prepared example and newly built space. Historical studio revisions without the canvas flag retain their older display compatibility. Generated code cannot rewrite host source or permissions.

Return fluid HTML and inline CSS with concise controls. Plain inline SVG is allowed within the restrictive content policy. Generated scripts, event handlers, external resource URLs, nested frames, and navigation are rejected or blocked. Escape all user content. Render controls using `data-action` JSON:

```html
<button data-action='{"type":"support","projectId":"tidepool"}'>Support</button>
<form data-action='{"type":"saveWish"}'>
  <input name="text" aria-label="Your wish" maxlength="180">
  <button type="submit">Plant a wish</button>
</form>
```

Rendered markup must complete its tags, quoted attributes, comments, text elements such as `style` and `textarea`, and templates. Verification rejects incomplete markup that can swallow the remaining page or the trusted frame bridge. These host checks run independently of generated feature tests, so a passing text-content assertion cannot publish an unfinished stylesheet. A failed change leaves the published revision and data intact and returns feedback to the builder for correction.

If an older saved revision cannot compile or render under current checks, snapshots and community previews show a trusted, noninteractive recovery message. The actual revision, history, data, and owner permissions remain available so the owner can restore a version or submit a repair. Reading a broken revision does not rewrite it or run a model.

A trusted nonce-bearing iframe script delegates clicks and forms, merging named form fields into the action. The parent accepts messages only from its current frame with the current bridge key, attaches the displayed revision ID, and sends the action to the selected space endpoint. The server derives identity. The frame uses `sandbox="allow-scripts allow-forms"` without `allow-same-origin`; CSP disables network connections and form navigation. No token or API key enters the frame. Drafts are inert, and their action and service messages are ignored.

Participation updates within the same revision patch the existing frame's DOM instead of reloading its document. Compatible elements retain their identity, preserving pointer capture, edited form inputs, and host-populated service conversations. Use stable `data-key` or `id` values for elements that move; paint cells are keyed automatically by `data-paint-cell`. Publishing a different revision creates a new frame context.

Interactive frames measure their content at full width before deciding whether to show an internal vertical scrollbar. Ordinary pages expand with their content; pages exceeding the 8,000px frame-height limit remain scrollable inside the frame. Horizontal overflow and authored inner scroll containers remain accessible. Resize, rendered-content updates, disclosures, and changed controls refresh the measurement without an animation polling loop.

For painting, declare one native `canvas` outside any `data-service` section. Its `data-paint-grid` describes the dimensions, palette, background, action and current brush; `data-paint-pixels` describes the current composed image. This small complete example has four columns and two rows:

```html
<canvas data-key="painting" tabindex="0" aria-label="Shared painting"
  data-paint-grid='{"action":"paint_pixels","columns":4,"rows":2,"color":0,"colorValue":"#3153be","palette":["#3153be","#04b84c"],"background":"#ffffff"}'
  data-paint-pixels="..01...."
  style="display:block;width:100%;height:auto;aspect-ratio:4/2;touch-action:none;user-select:none">
</canvas>
```

The raster string must contain exactly `columns * rows` characters in row-major order. `.` means background; the alphabet `0123456789abcdefghijklmnopqrstuv` encodes palette indexes 0–31. Every encoded index must exist in the supplied palette. A raster permits 1–256 columns and rows, at most 65,536 pixels, and 1–32 palette colors. Palette, background and brush colors use three- or six-digit hex. The host paints the native bitmap; generated source needs no browser script, per-pixel button or custom animation loop. The normal 180,000-character rendered-HTML limit still applies.

The trusted bridge handles pointer capture, continuous dragging, interpolation across skipped cells, immediate previews, and keyboard navigation with the arrow keys and Space/Enter to paint. It submits ordered batches of at most 120 cells as `{type: 'paint_pixels', columns, rows, cells: [{cell, color}]}`. The reducer must validate the entire batch, require the current dimensions, check cell and palette bounds, and enforce participant ownership before changing state. Stale dimensions must be rejected so a queued mark cannot move to a different coordinate after a resolution change. A rejected save removes unsaved previews. If an embedded agent uses this action, its declared parameter schema must also contain the dimensional fields required by the reducer; its instructions must reflect the current dimensions and row-major formula `cell = y * columns + x`.

Resolution and displayed size are separate. Doubling resolution normally doubles both axes, such as 48 × 32 → 96 × 64 → 192 × 128, while retaining the displayed surface size and aspect ratio. It produces four times as many pixels, each half as wide and tall. Derive render dimensions, validation bounds and agent metadata from one source of truth. Keep each saved layer's original dimensions and resample during rendering, rather than interpreting old row-major indexes using a new width. Existing legacy Iris marks use a 48 × 32 coordinate system. A code publication cannot migrate other participants' records; compact, versioned actor-owned layers allow new detail without rewriting those records. The usual 500,000-character state bound applies. Tests should check exact raster dimensions and count, repeated increases, edge coordinates, stale batches, artwork placement and preservation of other actors. Browser checks establish that the displayed dimensions remain unchanged.

AI painting must not rely on enumerating manual pixel batches to cover large areas. Curated Iris declares three additional bounded reducer actions: `fill_canvas({columns, rows, color})`, `flood_fill({columns, rows, x, y, color})`, and `paint_shapes({columns, rows, shapes})`. A shape supplies `kind` (`rect`, `ellipse`, or `line`), inclusive integer endpoints `x1,y1,x2,y2`, palette `color`, boolean `filled`, and integer `width` (1–32). Shape calls permit 1–32 shapes and cumulative bounding work of at most eight canvas areas. Validate all arguments before applying any marks. Flood fill uses four-connected pixels of the same visible color; blank background and the matching palette color count as the same region. Full fill covers all pixels, including existing art, in one action at any supported resolution.

These operations use the authenticated participant's existing layer ownership rules. Overlaying earlier artwork never deletes or rewrites another participant's stored records, and clearing the new overlay reveals those records again. Curated raster chunks accept both original raw cells and compact run-length encoding for uniform areas; the usual state and execution limits remain unchanged. Owner instructions select semantic operations for areas and shapes, reserve pixel batches for detail, and check the refreshed visible composite before claiming completion. Include a visible `data-service-text` result even if the full agent transcript is hidden, so unfinished work or exhausted action budgets are reported.

Legacy markup remains supported: a `data-paint-grid` container without raster data can contain compact, indexed `data-paint-cell` buttons with accessible labels and background colors. Legacy grids permit 1–64 columns and rows, at most 4,096 cells, and dispatch `{type: 'paint_pixels', cells: [{cell, color}]}`. Native keyboard activation of those buttons is retained. New painting surfaces and resolution upgrades should use the single-canvas raster form.

### Continuous games

Pages can opt into a local simulation alongside `render` and `reduce`:

```js
export const meta = {
  title: 'Arcade', subtitle: '', accent: '#687957', layout: 'canvas',
  game: { id: 'arcade', tickMs: 50, saveAction: 'save_game' }
};
export const game = {
  init(saved, actor) { return saved || { actorId: actor.id, x: 20 }; },
  step(state, action) {
    return action.type === 'tick' ? { ...state, x: (state.x + 20 * action.deltaMs / 1000) % 260 } : state;
  },
  view(state) {
    return { width: 260, height: 260, objects: [
      { id: 'player', type: 'circle', x: state.x, y: 130, radius: 8, fill: '#e8c655' }
    ], values: { position: state.x } };
  }
};
```

For multiple games, use `meta.games` with one to four configurations and an `exportName` identifying each simulation's named export:

```js
export const meta = {
  title: 'One more game', subtitle: '', accent: '#9be7be', layout: 'canvas',
  games: [
    { id: 'pacman', exportName: 'pacmanGame', tickMs: 50, saveAction: 'save_pacman' },
    { id: 'space-invaders', exportName: 'invadersGame', tickMs: 50, saveAction: 'save_invaders' },
    { id: 'snake', exportName: 'snakeGame', tickMs: 50, saveAction: 'save_snake' },
    { id: 'tetris', exportName: 'tetrisGame', tickMs: 50, saveAction: 'save_tetris' }
  ]
};
// Export pacmanGame, invadersGame, snakeGame, and tetrisGame from this module.
// Each object implements init(saved, actor), step(state, action, actor), and view(state, actor).
```

Use either `meta.game` or `meta.games`, never both. Game IDs and supplied `saveAction` names must be unique within the page. Each game gets its own matching `data-game` root, runtime controller, worker, input state, and participant-owned progress. Starting, pausing, or restarting one game does not reset another. The existing `meta.game` plus `game` export remains supported.

Each game export and its required helpers are public code. Keep private builder information out of that dependency graph. Authenticated `GET /api/spaces/:spaceId/game?gameId=snake` returns the current revision, only the selected public game bundle and configuration, the authenticated actor, and that actor's saved `state.extras[gameId][actor.id]` record. It does not return other games' code or progress, the page's rendering/reducer source, or builder history. Omitting `gameId` is accepted only when the page has one game; multi-game requests without a selection return 400, and unknown game IDs return 404.

Public helpers must have individual named declarations and initialize inside those declarations. Reassigned module bindings, reachable destructuring declarations, and separate statements that configure public helpers are rejected. The compiler selects the public lexical dependency graph before bundling, so unused page initializers cannot leak into the game artifact.

Render a focusable `data-game="arcade"` section with `canvas[data-game-canvas]`. Native buttons declare `data-game-command="start|pause|resume|restart"`. Direction buttons use, for example, `data-game-action='{"type":"direction","direction":"left"}'` and `data-game-keys="ArrowLeft a A"`. These buttons work with clicks, touch, keyboard, and Live voice. Keyboard steering applies only inside the focused game, never while typing in a field. Use readable `data-game-value="position"` text bindings and a `data-game-runtime-status` element so progress and pauses remain accessible.

For held movement, pair a press action with `data-game-release`, for example `data-game-action='{"type":"input","key":"left","held":true}'` and `data-game-release='{"type":"input","key":"left","held":false}'`. These actions should idempotently set input flags; simulation ticks use the flags to move. Key/pointer release, cancellation, lost focus, and leaving the game release held inputs. Click-only activation, including Live, produces a 150 ms pulse after the worker accepts the press. Multiple physical inputs are tracked independently. Tap-only actions accept normal keyboard repeat. Use `Space` in `data-game-keys` for the space bar. Reset transient input flags in `init(saved,actor)` so saved progress never restores a held physical key. Both action payloads are limited to 4,096 serialized characters.

The host manages lifecycle visibility and enables controls when available; omit authored `disabled` unless a control must always remain unavailable. Controls behave as type-button elements even inside a form. An optional static preview can be hidden with `[data-game-ready="true"]`, which is set only after the canvas receives its first valid scene. Authored score text remains visible until that scene arrives.

Starting the game lazily creates a dedicated worker containing a bounded QuickJS interpreter. Generated code never runs as browser JavaScript. The worker advances at the declared 16–100 ms interval and returns validated drawing instructions for a trusted canvas renderer. Views contain up to 1,000 uniquely identified `rect`, `circle`, `path`, or `text` objects; see `shared/game-schema.mjs` for geometry, color, text, and byte limits. Stable object IDs allow smooth interpolation. Reduced-motion preferences disable interpolation, and simulation always requires an explicit start. Leaving the game or hiding the page pauses it; continuing requires Start or Resume. Changing revision, identity, or page destroys the old worker.

Games with `saveAction` checkpoint at most every two seconds and on pause/end. The action is `{type: config.saveAction, game: state}` through the ordinary authenticated reducer, with the captured revision. The reducer must save the complete record in `extras[config.id][actor.id]` while preserving other participants, other games owned by the same participant, and all unrelated data. The host independently enforces this boundary. Each game's state is bounded to 32 KB; only a validated checkpoint gets the larger action allowance. Scores are participant-reported, not server-authoritative competitive results. A failed save pauses that game with a visible retry message. A final departure checkpoint is best effort; expired or revoked authentication cannot save.

Publication verifies every game's owner and visitor simulation as well as normal render/reducer checks. It rejects missing, mismatched, duplicate, or nested game roots, missing canvases or usable Start controls, orphan hooks, malformed actions, and unsupported commands. It simulates up to five ticks per game and verifies fresh/progressed checkpoint save-and-reload behavior without changing other records. One failed game blocks publication of the whole revision.

Generated feature tests select `api.games[gameId]`, which exposes `config`, `actions`, `init(saved, actor)`, `step(state, action, actor)`, and `view(state, actor)`. For example, `api.games.snake.step(api.games.snake.init(null, actor), {type: 'tick', deltaMs: 50}, actor)` advances only Snake. `actions` lists that game's rendered controls as `{action,label,release?}` so tests can exercise each in an appropriate state. Legacy `meta.game` pages also retain `api.gameInit`, `api.gameStep`, `api.gameView`, and `api.gameActions`. Pages without either game declaration keep their existing behavior.

### Generated service interfaces

The same service interface is available to every generated page. A published `meta.capabilities` declaration authorizes a named service; it does not grant arbitrary HTTP access or replace the service's host policy. All visible markup, CSS, copy, controls, and templates belong to `space.js`. The host transports data and fills bindings instead of appending a fixed React widget.

For health chat, a minimal interface is:

```html
<section data-service="health-chat">
  <p>AI general health education, not a clinician or emergency service.</p>
  <p>Keep questions general and omit personal details.</p>
  <div data-service-messages role="log" aria-live="polite"></div>
  <template data-service-message>
    <article>
      <span data-field="role" data-role-user="You" data-role-assistant="AI health guide"></span>
      <p data-field="content"></p>
    </article>
  </template>
  <div data-service-sources></div>
  <template data-service-source>
    <a data-field="url"><span data-field="title"></span></a>
  </template>
  <p data-service-status="loading" hidden>Preparing an answer…</p>
  <p data-service-error role="alert"></p>
  <form data-service-reset-on-submit>
    <textarea name="message" aria-label="A general health question" maxlength="1200" required></textarea>
    <button type="submit">Ask</button>
  </form>
  <button type="button" data-service-operation="cancel">Stop answer</button>
  <button type="button" data-service-operation="clear">Clear conversation</button>
</section>
```

A service form must not use `data-action`. Forms within a service section route to that service, and ordinary persistent-action buttons within the section are ignored. Put unrelated persistent features outside the service section. Service result bindings are display text, not form values. Health questions and replies must never be written to `state`, `extras`, source, tests, or builder messages. The controller holds complete exchanges only in the current viewer's memory, sends at most five exchanges plus a new question, and keeps incomplete answers out of follow-up context. It discards this context on explicit clear, page departure, identity change, or published revision change. Local transience is not a model-provider retention guarantee.

Finance news uses `data-service="finance-news"`, optionally `data-service-auto` for automatic loading. Supply `data-service-items` and a `template[data-service-item]` containing `data-field="title"`, `summary`, `date`, `source`, and an anchor with `data-field="url"`. Include `data-service-note` for the host's checked/saved provenance text, `data-service-error`, and a type-button control with `data-service-operation="refresh"`. Only this read-only feed can start automatically.

For an embedded general agent, declare `space-agent` and `meta.agent: {instructions, actions}`. Instructions describe the space's purpose and public state, up to 4,000 characters. Actions are optional (zero means conversational only), with at most six `{name, description, parameters}` definitions. Parameters use bounded object/array/string/number/integer/boolean JSON schemas with `additionalProperties: false` on objects. Arrays require `maxItems`, at most 400; the validator rejects identity and action-routing keys in model arguments. See `server/space-agent-schema.mjs` for the exact supported subset.

A raster painting agent can additionally declare `meta.agent.paintContext: {canvasKey: 'painting', namespace: 'canvas'}`. The key must identify one raster canvas in the authenticated visitor's render, and the namespace must contain participant-owned records in `state.extras`. Before every model round, the host replaces only that namespace in the model's context with a `representation: 'visible-paint-composite'` object containing `columns`, `rows`, `palette`, `background`, exact row-major `pixels`, and `layerActorIds`. All other public state remains present. The projection explicitly excludes the stored layers and edit history: it is never written back to state. Declared reducer actions remain the only edit path and retain all normal ownership checks. Projected context allows 100,000 serialized characters, with a separate 40,000-character limit for the remaining state; ordinary agents retain the 40,000-character full-state limit.

Use `data-service="space-agent"` with a native form containing an input or textarea named `message` and the same chat bindings below. Do not use `data-action` on that form. The host sends replies as text and executes declared tools through `reduce(state, {...arguments, type: name}, authenticatedActor)`. Ordinary ownership checks still apply. Conversations stay transient; successful actions persist and broadcast public state updates. Unsaved chat drafts survive same-revision public updates in memory and are discarded when the viewer, space, or revision changes.

Shared bindings and operations:

| Binding | Behavior |
| --- | --- |
| `data-service-operation` | Health and space agent: `submit`, `clear`, `cancel`. Finance: `load`, `refresh`, `cancel`. Default chat form operation is `submit`. |
| `data-service-input` | JSON string fields for a button, such as `{"message":"How much sleep do adults need?"}`. A form sends its named string fields. |
| `data-service-status="idle\|loading\|ready\|error"` | Shows authored content only during that status. Initially hide non-idle slots. A bare `data-service-status` reads authored `data-status-*` labels. |
| `data-service-text`, `data-service-error`, `data-service-note` | Host data written with `textContent`, never HTML. |
| `data-service-empty`, `data-service-filled` | Shows the empty or populated state of message/item lists. |
| `data-service-urgent`, `data-service-stopped` | Shows authored urgent/incomplete-response copy when that flag is true. |
| `data-service-messages`, `data-service-items`, `data-service-sources` | Populated using the corresponding authored `template[data-service-message\|item\|source]`. |
| `data-field` | Binds a named record field as text. URL fields must be anchors; only host-approved URLs are installed. |
| `data-service-role` | Added to each rendered message's root element as `user` or `assistant`, enabling generated CSS to distinguish them. |
| `data-service-disable-loading` | Disables a control while a request is running. Submit/request controls are disabled automatically. |

The parent filters capability names, operations, and bounded string inputs, and ties responses to the current service context. The server independently requires the current published revision and its capability declaration. Draft metadata cannot enable a service. Reference clicks are sent back to the parent; it opens only approved HTTPS URLs present in the latest service result, with `noopener,noreferrer`. Generated code cannot invent navigable links by placing a URL in source.

## Runtime exports: `server/runtime.mjs`

| Function | Result and responsibility |
| --- | --- |
| `compileModule(source)` | `{bundle, meta}` after compilation and export validation. |
| `projectStateForPublication(meta, liveState)` | Cloned candidate state with valid declared project fields updated or added; all omitted projects and participation retained. Called by trusted preview and publication code, never exposed to generated reducers. |
| `renderModule(bundle, state, actor)` | HTML after state/actor validation, rendering, content checks, and nonmutation checks. |
| `reduceModule(bundle, state, action, actor)` | Next state, with independent host checks for schema, project preservation, and cross-actor ownership. |
| `verifyModule(source, testsSource, state, {owner, visitor, projectCatalog}?)` | `{ok, checks, bundle?, meta?, candidateState?}`. With `projectCatalog: true`, tests a host-projected candidate against that space's actors; otherwise tests the supplied state. The harness enables projection for seed, publication, and restore verification. |

Tests export synchronous `runTests(api)`, returning check objects with string `name` and boolean `ok`. The isolated API supplies `initialState`, `render`, `reduce`, and `meta`. Failed or malformed checks prevent publication. Host checks cannot be removed by editing `tests.js`. The model is prompted to write meaningful feature checks; passing its own tests is not treated as a security proof.

Interpreter contexts are fresh for each invocation. Current limits include 16 MB QuickJS memory, a 120 ms ordinary execution deadline, 250 ms for rendering and individual game calls, and a worker watchdog. A generated feature-test suite receives 500 ms, or 500 ms per declared game up to 2 seconds for four games, because it exercises all games in one context. Render output must be a bounded primitive string and preserve its input; the trusted host validates the serialized HTML once, outside the generated render's execution budget. No shared generated global state persists between spaces. The shared worker queue is a local implementation detail, not production tenant fairness or complete process isolation.

## HTTP: `server/index.mjs`

The backend binds to `127.0.0.1:4318`; Vite at port 5173 proxies `/api`. Only loopback hosts/origins are accepted, cross-site requests are rejected, and POST requests require `application/json`. These local restrictions do not replace verified production identity.

### Sign-in routes

| Method and path | Request / response |
| --- | --- |
| `GET /api/auth/people` | Public demo list: `{users: [{id, name, ownSpaceId}], simulated: true}`. |
| `POST /api/auth/sign-in` | `{userId}` selects an existing person; `{name}` creates a new one. Returns `{token, user: {id,name}, ownSpaceId, simulated: true}`. |
| `GET /api/auth/session` | Requires bearer. Returns `{user, ownSpaceId, simulated: true}`. |
| `POST /api/auth/sign-out` | Requires bearer; revokes that session. Returns `{ok: true}`. |

New names are trimmed and validated by the server, with a maximum of 48 characters. The local demo permits up to 100 registered people. Selecting an existing person is deliberately open; this endpoint must not be mistaken for a production authentication provider.

### Space routes

Every route below requires `Authorization: Bearer <token>`.

| Method and path | Access and behavior |
| --- | --- |
| `GET /api/spaces` | Signed-in person. `{spaces: [{id, owner, kind, revisionId, hasBuilt}]}`. Powers **Community → Our spaces**. |
| `GET /api/spaces/:spaceId` | Signed-in person. Viewer-scoped snapshot. |
| `GET /api/spaces/:spaceId/events` | Signed-in person. Authenticated SSE, filtered by owner/visitor role. |
| `GET /api/spaces/:spaceId/revisions` | Owner only. Revision metadata, source, tests, and checks. |
| `POST /api/spaces/:spaceId/turn` | Owner only. `{message, appTheme?, compare?}` accepts optional `appTheme: 'light' \| 'dark'` and boolean `compare`. Returns HTTP 202 and `{turnId}` (plus `comparisonId` for comparisons); an ordinary active turn receives steering at its next checkpoint. |
| `POST /api/spaces/:spaceId/cancel` | Owner only. Aborts the active request and prevents uncommitted publication; preserves live code and data. |
| `POST /api/spaces/:spaceId/action` | Signed-in person. `{action, revisionId}` executes as the authenticated person. Returns `{state}`. |
| `POST /api/spaces/:spaceId/restore` | Owner only, while idle. `{revisionId}` verifies old source against current data and publishes a new revision. |
| `POST /api/spaces/:spaceId/reset` | Owner only, while idle. Returns this space to the universal blank seed and creates a fresh builder session. Other spaces are unaffected. |

Owner snapshots include `state`, full `revision`, `html`, `actor`, `session`, `config`, `events`, `space`, and `permissions`. Session data includes its ID, status, turn count, and saved user-request summaries. Full model/tool items are persisted server-side rather than exposed by this snapshot.

Visitor snapshots retain published `html`, public `state`, actor and space metadata, revision ID/title/date/meta, current session status, and public events. They omit source, tests, checks, owner prompts, thread IDs/history, model configuration, and private runtime events. `permissions` indicates `canEdit: false` and `canViewRuntime: false`.

Unknown/missing sessions return 401; owner-only operations by visitors return 403; missing spaces return 404. Stale action revisions return 409; invalid actions or incompatible restores return an error without mutation. The server ignores client-supplied actor identities.

Legacy `/api/space`, `/api/events`, `/api/revisions`, `/api/turn`, `/api/cancel`, `/api/action`, `/api/restore`, and `/api/reset` remain **authenticated aliases for the caller's own space**. `?actor=leo` or an `actor` body field does not impersonate Leo.

### Capability routes

All capability routes require an authenticated viewer, an existing space, the exact current `revisionId`, and the named capability in that published revision's verified metadata. They are available to owners and signed-in visitors under the same rules, regardless of persona. The request cannot provide a capability list, substitute a service policy, or choose an upstream URL.

| Method and path | Request / response |
| --- | --- |
| `POST /api/spaces/:spaceId/services/finance-news` | `{revisionId}`. Returns validated feed items, `refreshedAt`, and `mode: 'feed'` or `'saved'`. |
| `POST /api/spaces/:spaceId/services/health-chat` | `{revisionId, messages}`. Returns SSE `delta`, `complete`, or `error` events. A completion includes checked source references and an urgent flag. |
| `POST /api/spaces/:spaceId/services/space-agent` | `{revisionId, messages}`. Returns SSE `delta`, `action`, `complete`, or `error`. Completion includes `actionsApplied`, `model`, and `servedTier`; an `action` event confirms a server-applied reducer action. |

Unknown services return 404, missing published capability 403, and a stale revision 409. Unexpected request fields are rejected. Health messages must alternate user/assistant roles and end with the user's question: at most 11 messages, 1,200 characters per user message, 6,000 per assistant message, and 16,000 total. The endpoint permits one active health answer per authenticated person and uses a 90-second timeout; disconnect and session revocation abort it. These messages are transient service inputs, not a builder turn or reducer action, and are never appended to the store or event ledger.

The health service retains host-owned general-education instructions, checked references, and urgent-help handling. News retrieval permits only the configured Federal Reserve feed and validated official links. Old unscoped `/api/health-chat` and `/api/finance-news` endpoints are not service authority paths.

The space agent uses the same message size and role limits as health chat, reads at most 40,000 serialized characters of public state by default, and permits eight model responses with eight total action attempts. The explicit `paintContext` projection described above allows up to 100,000 characters while retaining the 40,000-character bound on other state. It allows one active request per viewer per space and eight globally, with a 120-second timeout. Cancellation, disconnect, session revocation, revision changes, and reset stop further actions. Already committed changes remain saved. Owner instructions, tool definitions, and revision scope come from the published module, never from the caller.

HTTP model and browser service streams finish on their validated completion event, without waiting for socket closure. The browser also has a 125-second transport watchdog covering response headers and body reads. If a connection stalls, it aborts the request, releases the busy controls, and shows an error while preserving completed changes and partial text. Late replies cannot overwrite a newer request. Transport cancellation is best-effort and cannot delay completion or error display.

### Events

Each event has `{id, type, time, turnId?, stage?, title, detail?, durationMs?, data?}`. Stages are `inspect`, `build`, `verify`, and `publish`. The store retains 150 events per space; `Last-Event-ID` or `since` provides a replay cursor. Fetch-based SSE sends the bearer in headers. Revocation/expiry closes existing streams as well as blocking new requests.

Owners can receive turn, model, tool, check, preview, publication, steering-message, and visitor events. Visitors receive only allowlisted public change events with sanitized titles and optional revision IDs; replay uses the same filtering. Source, tests, prompts, and tool data do not leak through visitor history.

`model.delta` can carry decoded `sourcePreview` for the owner. `draft.preview` carries `{html, layout?, sourceCharacters, renderedSourceCharacters, actorId, preview: true}`. The actor ID is the current space owner, not a fixed Mira identity. HTML comes from a completed render prefix executing in QuickJS against the projected candidate catalog. `layout: 'canvas'` makes the preview occupy the full personal body, even before a legacy space's first canvas publication. At most four distinct preview frames are emitted per turn. A preview-only reducer stub is never saved or published. Dismiss drafts on a new turn, publication, completion, failure, or cancellation.

## Harness tools and publication

The model-visible tools are `inspect_space`, `read_file`, `verify_workspace`, `publish_revision`, and the custom `apply_patch` tool. `apply_patch` uses the same Lark grammar as Codex, supplied as a Responses custom tool with `format: {type: "grammar", syntax: "lark", definition: ...}`. File access is restricted to the active turn's `space.js` and `tests.js`; generated code cannot select another store or workspace. There is only one model-visible write tool.

`apply_patch` accepts raw text between `*** Begin Patch` and `*** End Patch`. `Add File` writes a complete file (replacing an existing file); `Update File` applies context-based line hunks; `Delete File` and `Move to` are limited to the two allowed paths and cannot leave either required file missing. The parser follows Codex's default LF-normalizing behavior and whitespace/punctuation matching fallbacks. All operations apply in memory before either workspace file is written. The final workspace projects the optional catalog onto current state, verifies the real code against that candidate, and atomically publishes on success. It emits actual build/check/publication events and returns failed checks for repair. Tool results are deduplicated by call ID within the turn. Publication is a host decision and checks cancellation, pending owner instructions, exact source, and current data before commit. Only the owner-authorized builder and restore paths can commit catalog declarations; ordinary `/action` requests cannot.

The harness allows up to eight model responses and three failed verification attempts per turn, with a 16,000-token builder request output cap. Completed Responses items, including encrypted reasoning items, are preserved for replay with `store: false`. The application owns these local sessions and executes tools itself through the Responses API.

Custom calls and results retain their native `custom_tool_call` / `custom_tool_call_output` types in saved history and restart recovery. Older JSON `apply_change`, `write_file`, and exact-replacement `apply_patch` function calls remain supported for existing history and local adapters, but are not offered to the model as write tools. Activity displays the raw patch stream. The patch preview machinery projects edits into provisional file contents without writing them to disk.
