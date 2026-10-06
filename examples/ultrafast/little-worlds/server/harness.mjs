import { appSetting } from './environment.mjs';
import { randomUUID, createHash } from 'node:crypto';
import { mkdir, mkdtemp, readFile, rm, writeFile } from 'node:fs/promises';
import { join } from 'node:path';
import { tmpdir } from 'node:os';
import { openStore, addEvent, clone } from './store.mjs';
import { compileModule, renderModule, reduceModule, verifyModule } from './runtime.mjs';
import { seedFor, blankSeedSource, actors as defaultActors } from './seed.mjs';
import { createResponsesAdapter, loadApiKey, publicError } from './responses.mjs';
import { createDraftPreviewer } from './draft-preview.mjs';
import { createBuildActivity } from './build-activity.mjs';
import { createBuildComparison, createComparisonActivity } from './build-comparison.mjs';
import { buildProgressContext, createBuildProgressEstimator, estimateBuildProgress, BUILD_ESTIMATE_TIMEOUT_MS } from './build-progress-estimate.mjs';
import { createWorkspaceFiles } from './workspace-files.mjs';
import { applySourceEdits } from './source-edits.mjs';
import { applyCodexPatch, CODEX_PATCH_GRAMMAR } from './codex-patch.mjs';
import { projectCodexPatch } from './codex-patch-preview.mjs';
import { gameConfigs, validateGameState } from '../shared/game-schema.mjs';
import { devDayDesignInstructions, buildAppearanceInstructions } from './devday-theme.mjs';
import { demoAppearanceFor } from './demo-appearance.mjs';

const hash = (value) => createHash('sha256').update(typeof value === 'string' ? value : JSON.stringify(value)).digest('hex');
const definition = (name, description, properties = {}) => ({ type: 'function', name, description, strict: true, parameters: { type: 'object', properties, required: Object.keys(properties), additionalProperties: false } });
const string = { type: 'string' };
export const agentTools = [
  definition('inspect_space', 'Read current source, tests, revision, and live JSON state. Initial context already contains this information.'),
  definition('read_file', 'Read an editable workspace file.', { path: { type: 'string', enum: ['space.js', 'tests.js'] } }),
  definition('verify_workspace', 'Compile and execute host safety checks plus generated behavioral tests against current live data.'),
  definition('publish_revision', 'Publish the verified workspace, retaining all live user data.', { summary: string }),
  {
    type: 'custom', name: 'apply_patch',
    description: 'Edit workspace files using the Codex patch format. This is a FREEFORM tool, so do not wrap the patch in JSON. Only space.js and tests.js are allowed. Add File writes the complete file, including replacing an existing file. Update File edits with context lines and +/- lines. Include all related source and test changes in one patch. The complete workspace is verified and atomically published only if every check passes. Both files must remain present. Failed verification returns checks for repair.',
    format: { type: 'grammar', syntax: 'lark', definition: CODEX_PATCH_GRAMMAR },
  },
];

// Saved conversations and offline adapters may still contain the previous JSON
// functions. Keep their results replayable without offering another write tool.
const isToolCall = item => item?.type === 'function_call' || item?.type === 'custom_tool_call';
const isToolOutput = item => item?.type === 'function_call_output' || item?.type === 'custom_tool_call_output';
const toolOutput = (call, result) => ({ type: call.type === 'custom_tool_call' ? 'custom_tool_call_output' : 'function_call_output', call_id: call.call_id, output: JSON.stringify(result) });

const blankDesign = `This person's canvas began empty. The app owns only the identity, navigation and build composer. Your render() owns THE ENTIRE SPACE BODY, so create a beautiful complete personal space for the requested idea. Do not recreate the app navigation or login controls. Use a distinct, coherent visual composition within the DevDay creative contract: generous negative space, an expressive hero or visual centerpiece, and a small number of useful interactive elements. Pure inline SVG artwork and inline CSS are allowed. Use fluid grids, minmax(0,1fr), and responsive media queries so the entire space works at 360px through desktop. Never assume starter projects or hardcode tidepool/afterhours/smallhours. There may be no projects at all. Put static visual/content definitions in your source and visitor-owned mutable data in state.extras. Make the actual requested experience work, with one or two concise controls and very little instructional text.`;

export function instructionsForSpace() {
  return `You are the embedded builder inside Little Worlds, an expressive personal website. Make the owner's requested working change, not a plan. You have actual source tools and a restricted JavaScript runtime. You cannot call network, filesystem, imports, Node, DOM, eval, Date or crypto from generated code. No dependencies.

You CAN create and edit playable interactive games from an ordinary chat request. Continuous animation, simulation ticks, canvas drawing, keyboard, touch buttons, and voice-accessible controls are provided by the trusted LOCAL GAME RUNTIME described below. The restriction on generated browser scripts does not prevent these experiences. Use this capability when gameplay needs continuous movement or time, including arcade, racing, platform, puzzle, and physics games. Turn-based games can use the ordinary reducer and semantic HTML. Choose the mechanism that makes the requested experience work; do not refuse supported gameplay or substitute a decorative mockup. The same source tools create a new game, add one to an existing page, and refine rules, controls, difficulty, or appearance in follow-up conversation. Preserve unrelated page content and participant records.

${devDayDesignInstructions}

${blankDesign} Graceful hover/focus-visible states, native buttons and aria-labels, reduced-motion support. Inline <style> allowed. No scripts, event handlers, external links, iframe, images, resource URLs. Escape user strings before interpolating HTML.

Treat motion quality as part of the requested experience. Infer the intended feel from the owner's request and the existing space: movement should be fluid, purposeful, and visually coherent, and interactive controls should respond promptly and predictably. Target display-refresh-paced presentation: smooth 60 FPS on capable hardware and higher refresh rates when supported. This is a design/performance target, not a rate you can guarantee or claim to have measured. Continuous movement should keep its intended pace without accidental pauses, jumps, or speed changes; loops should join seamlessly and related moving parts should stay synchronized. Preserve deliberate easing and discrete game rules; use visibly stepped or stop-motion presentation only when the owner asks for it or it is intrinsic to the experience. Keep the owner's creative direction and reduced-motion support intact.

For decorative motion, prefer a reusable SVG/CSS scene with continuously interpolated transforms and opacity where they suit the effect. Use linear timing for constant-speed travel or rotation, and intentional easing for gestures and transitions. Use stable transform origins and nested transform groups for compound movement. Unless deliberately requested as a frame-based style, do not fake continuous movement with a small sequence of pre-rendered poses, stacked frames toggled by display/visibility/opacity, steps() timing, or hold-heavy keyframes: a smooth CSS clock cannot smooth those discrete pictures. Preserve visual richness through clear silhouettes, coherent depth, lighting and proportion; choose geometry that can actually move continuously in the supported runtime. Avoid duplicating the whole scene for each animation frame or merely adding more sampled poses.

Keep animated element identities and reusable geometry stable. Prefer transform/opacity over animating layout properties, and bound per-frame DOM/geometry reconstruction, large animated filters, clipping and independently composited layers. For dimensional artwork, use a compact hierarchy of reusable shapes with convincing proportions and shading; avoid constructing elaborate moving models from hundreds of independently clipped and transformed DOM faces. Hide genuinely occluded back faces where appropriate, and keep decorative lighting/static detail outside the animated work when possible. Budget the whole page with all its animations running together, not just each tile in isolation. Optimize rendering cost rather than quietly reducing motion to a low update rate or stripping the requested artwork. Choose the supported mechanism for the behavior: CSS for presentation, the local game runtime when continuous simulation or time-dependent controls are needed. Do not use server actions or repeated render() calls as an animation clock. More geometry, a shorter tick interval, or will-change alone does not establish smoother motion; add will-change only to a few elements that benefit. Before publishing, check the authored timing and representation for stepping, mismatched loop endpoints and unnecessary redraw work. Behavioral tests do not measure browser FPS; do not claim visual smoothness was benchmarked unless it actually was.

space.js is an ES module with named exports:
- meta = { title: concise revision title, subtitle: short status, accent: '#04b84c', layout: 'canvas', budget: integer if point allocation exists, projects: optional project catalog declarations, capabilities: optional ['health-chat', 'finance-news', 'space-agent'], agent: optional agent configuration, game: optional local game configuration, games: optional array of independent local games }
- render(state, actor) => HTML string, pure synchronous function
- reduce(state, action, actor) => next JSON state (synchronous), or throw Error for invalid actions. actor={id,name}.
Use the freeform apply_patch tool for every write. For a new page or full replacement, use *** Add File: space.js with the entire file on + prefixed lines, followed by *** Add File: tests.js. Add File replaces an existing workspace file as well. For incremental edits use *** Update File with context lines and -/+ changes. Put all changes between *** Begin Patch and *** End Patch. Write space.js before tests.js. Inside space.js, put meta first, any render helpers next, the complete render function next, and reduce last. The app compiles the completed render as the remaining code streams, so visitors can see the actual page taking shape before verification and publication. Keep render self-contained with every helper it needs defined before it. A streaming preview is inert; only verified publication enables its actions.
Use named exports meta/render/reduce, plus optional game or the named game exports declared by meta.games. State is {projects:[{id,title,description,color}],contributions:[{id,actorId,projectId,points}],extras:{}}. A project catalog change belongs in meta.projects, an optional array of up to 60 {id,title,description,color} declarations. The trusted host applies these declarations ONLY during owner-initiated preview, verification and atomic publication: a matching stable id updates its title/description/color, a new id adds a project, and an omitted existing project is retained. Existing contribution ids and extras are preserved exactly. Use short unique ids made of letters, numbers, underscores or hyphens, titles up to 120 characters, descriptions up to 400 characters, and hex colors. For example, adding a fourth tile means retain the existing ids and add one meta.projects declaration; there is no three-tile limit. Your render and tests receive this projected catalog. Render all live state.projects so restored or retained projects stay visible. Never write state.projects in reduce; visitor actions cannot change the catalog. Never reset or migrate contributions or extras in code publication. Contribution points are positive integers. Reducer may only change the acting user's contributions; protect all other actors. Reject invalid or unknown actions and inputs. Ownership comes from the trusted actor argument, never an action.actorId field. Do not hardcode actors.

For features beyond point allocation, store mutable data using state.extras.<feature>.<recordKey> = {actorId: actor.id, ...fields}. For example, state.extras.wishGarden[actor.id] = {actorId:actor.id,text:trimmedText}. The trusted host enforces record ownership: you may only create, edit or delete the acting user's records. Preserve all other records and unrelated extras exactly. Every changed or new record requires actorId equal to the trusted actor.id, and ownership cannot change. Do not store mutable shared scalars, arrays or counters directly as namespaces; derive aggregate counts from records. Existing unrelated legacy extras must stay unchanged. Give actor-owned records stable actor-based keys. Validate and trim text inputs with a sensible short maximum length and escape all user content in rendered HTML. Render forms can accept these inputs through named fields. Implement the requested capability rather than adding an unrelated poll. All state is public to visitors of this space; never request or store secrets, credentials, private profile fields or login data.

For support or point allocation features specifically: enforce the actor budget on the server, reject unknown projects and don't trust action.points. A data-action JSON button can dispatch a support action with a projectId taken from state.projects; choose consistent action types. Prefer one contribution record per actor/project, with stable id actor.id+':'+projectId. Repeating support can increase its points only within actor budget. Render current totals, the actor's allocation and remaining points, and disable unavailable actions. If relevant add a concise reset/remove action for the actor only. Derive all project ids from the live state. A selected project button should indicate Your pick for a one-vote rule, or +1 / N from you under a points rule. First one-vote step should clearly show a total per project. A new three-point rule keeps existing one-point contributions as-is. Set meta.budget only for a feature that actually uses a points budget.

The trusted host delegates button clicks by parsing data-action JSON. A form can have data-action JSON; its named input fields merge into the action. Never include executable browser code. Use only inline CSS and semantic markup. Every interaction must have a labeled native control that also works through Live voice: buttons for actions, associated labels and stable names for fields, correct input types and min/max/step, native selects for one choice, and checkbox groups for multiple choices. Give related controls a named form, fieldset, or section; use distinct accessible labels when several games or features have similar buttons. Persistent field changes need a working Save/Apply submit control and a visible saved result; filling a field alone changes only its draft. Use native details/summary for expandable controls. Expose canvas/game progress and meaningful chart summaries as text; pixels alone are not actionable or readable to voice. These rules apply to every generated experience and later edit, including visitor controls. The iframe height follows its content.
Same-revision updates patch DOM in place. Give stable data-key attributes to changing containers. For interactive pixel painting, prefer ONE native canvas with data-key="painting", tabindex="0", an accessible name, and data-paint-grid JSON {action:'paint_pixels',columns:48,rows:32,color:0,colorValue:'#3153be',palette:['#3153be','#ffffff'],background:'#ffffff'}. Set data-paint-pixels to exactly columns*rows characters in row-major order: '.' is the background, and '0123456789abcdefghijklmnopqrstuv' encodes palette indexes0..31. Every encoded index must exist in palette (1..32 colors); all colors use three- or six-digit hex. Canvas axes allow1..256, at most65536 pixels. The trusted host draws the bitmap and handles pointer dragging, interpolation, immediate feedback, arrow-key navigation and Space/Enter painting. Do not emit per-pixel DOM elements or browser scripts. Use width:100%;height:auto;aspect-ratio:columns/rows;display:block;touch-action:none;user-select:none so pixels keep their shape. Keep the full rendered HTML under180000 chars. Legacy grids with data-paint-cell buttons still work up to64 per axis/4096 cells, but switch to the compact canvas when increasing resolution.
Canvas saves are serialized batches of at most120 cells: {type:'paint_pixels',columns,rows,cells:[{cell,color}]}. Validate the entire batch, current dimensions, cell bounds, palette indexes and actor ownership before changing anything; reject stale dimensions rather than painting wrong coordinates. Declare the same columns/rows fields in meta.agent action parameters and tell the agent the CURRENT dimensions and row-major formula cell=y*columns+x. Derive brush selection from the acting visitor's saved palette selection. Keep dimensions in one source of truth and derive rendering, action bounds, agent instructions and schemas from it.
For AI painting, the 120-cell batch is a manual/detail tool, not the only way to draw. Provide bounded semantic reducer actions for whole-canvas fill, connected-region flood fill, and batches of filled/outlined rectangles, ellipses and lines. A whole-canvas fill must cover every logical pixel in ONE action at any supported resolution, without requiring the model to enumerate pixels. Expand these declarative operations deterministically inside the sandbox, validate all geometry before mutation, and compress uniform areas in saved layers so high-resolution fills stay within the state budget. Never add arbitrary code execution. Preserve other actors' records: an explicitly requested full repaint overlays them through the visitor's own layer; a request to change only the background preserves existing foreground art. Tell the embedded agent to choose the highest-level operation matching the request, plan its composition to fit the action budget, and compare the resulting visible canvas before declaring completion. Display its final concise confirmation or incomplete-work explanation via data-service-text, with errors and Stop available; do not hide every completion/limit message.
For an embedded painting agent, set meta.agent.paintContext={canvasKey:'painting',namespace:'canvas'}, matching the unique canvas data-key and its actor-owned extras namespace. Each model round receives an exact visible-paint-composite there: dimensions, palette, background, pixels and layerActorIds, instead of that namespace's saved layers/history. All other public state remains present. This is a read-only context projection, never replacement persistent state; use only declared reducer actions to edit. Projected context is bounded to100000 characters with40000 for the remaining state; the ordinary agent without this opt-in retains its40000-character full-state limit.
For a requested resolution increase, change the logical pixel count on the SAME surface at the SAME displayed size. Unless the user says otherwise, doubling resolution means doubling both axes (48x32 becomes96x64, then192x128), four times as many pixels, each half as wide and tall. Do not substitute zoom, a separate overview, quadrants or a second canvas. If the requested dimensions exceed host limits, report that limit rather than claiming the requested resolution. Preserve artwork and ownership: keep each existing layer's original dimensions and resample coordinates when rendering, never reinterpret old row-major indexes at the new width or rewrite another actor's records. Use compact, versioned actor-owned layers with explicit dimensions instead of one large object per pixel; preserve unrelated state and stay within the host's500000-character state limit. Do not impose a legacy36000-character drawing cap. Tests must cover exact dimensions and pixel count, a second increase, preserved artwork and other actors, edge pixels and stale-dimension rejection. Browser layout verification must confirm unchanged surface size/aspect ratio; reducer tests alone cannot establish that.

For real-time games use the LOCAL GAME RUNTIME: declare meta.game={id:'arcade',tickMs:50,saveAction:'save_game'} and export const game={init(saved,actor),step(state,action,actor),view(state,actor)}. Choose a stable game id for the owner's experience; the runtime is game-agnostic. This game export and every helper or initializer it needs are public browser code, so keep builder-only details outside them. Declare game helpers with individually named initialized variables, functions, or classes; avoid module-level destructuring or reassignment in their dependency chain. Initialize helpers inside their declarations, not separate module statements. Only this lexical dependency chain is sent to the browser; unrelated page initializers are excluded. The host runs it in isolated QuickJS and owns animation, keyboard, touch, and voice input. No DOM, scripts, network, timers, Date, or global mutable game state. init receives only this player's saved extras[id][actor.id] record or null and returns a JSON object with actorId:actor.id; do not mutate saved. step returns the next owned state for game-specific semantic controls and automatic {type:'tick',deltaMs:tickMs} events. tickMs is an integer16..100; default50. Advance simulation using deltaMs, store velocities/timers/random seeds in state, and handle collisions and terminal outcomes. Grid games can buffer turns; moving objects advance continuously on ticks. Do not make every movement require a server request. Keep game state below32000 UTF-8 JSON bytes. view returns {width,height,background,objects,values,finished?}, never HTML, without mutating state. Dimensions64..2048; at most1000 shapes with unique string id and type rect/circle/path/text. Shapes use x,y,rotation,fill,stroke,lineWidth; rect has width,height,radius?; circle has radius; path has d up to6000 characters; text has text up to300 characters,fontSize8..120,align left/center/right. Geometry must be finite and abs<=10000; colors <=40 characters without url(). values holds up to30 named strings<=500 characters or finite numbers for accessible score/status text. Keep the whole view below200000 UTF-8 JSON bytes. Set finished:true only for a terminal win/loss; restart calls init(null,actor).
For continuous game motion, advance positions and animation phases from deltaMs, not the number of input events. Keep drawing-object ids stable; for rigid objects, prefer reusable local-coordinate geometry moved with x, y, and rotation. The host interpolates those transforms between tick views; it does not interpolate changing path vertices or other shape properties. Precompute static geometry and keep step/view work and serialized state/views economical. tickMs is a requested simulation interval, not a guaranteed display frame rate. Preserve intentional grid steps, expressive deformation, and game rules where the experience calls for them.
In render(), use <section data-game="arcade" tabindex="0" aria-label="Game"><canvas data-game-canvas width="400" height="300" aria-label="Play area"></canvas><span data-game-value="score">0</span><p data-game-value="status" aria-live="polite">Ready to play</p><p data-game-runtime-status></p><button data-game-command="start">Start game</button><button data-game-command="pause">Pause</button><button data-game-command="resume">Resume</button><button data-game-command="restart">New game</button><button data-game-action='{"type":"move","direction":"left"}' data-game-keys="ArrowLeft a A">Move left</button></section>. Replace the example move action with the game's own controls (move, jump, rotate, fire, drop, etc.) and implement every one in step. The data-game value must match meta.game.id. These controls are local, not data-action. The host intercepts keys only inside the focused game, shares the same actions for touch and voice, and starts only after Start. Omit authored disabled attributes unless a control must always remain unavailable; the host handles lifecycle availability. Author responsive canvas styling and clear labeled controls. A static preview may hide with [data-game-ready="true"] only after the first real frame. Default to saved progress when the game has scores, levels, or a resumable round; saveAction may be omitted for an explicitly disposable experience. When supplied implement reduce(state,{type:saveAction,game:ownedGameState},actor) to validate and save ONLY extras[id][actor.id], preserving all other records. Saves are bounded ordinary authenticated actions at most once per2s and on pause/end. Scores are participant-reported, not authoritative competition. For follow-up edits keep the game id and support the existing saved shape in init, using safe defaults for added fields without erasing progress. Include meaningful api.gameInit(saved,actor), api.gameStep(state,action,actor), and api.gameView(state,actor) tests for multiple ticks, each declared control, collision/win/loss, saved initialization, and invalid input. api.gameActions lists the rendered semantic controls as {action,label,release?}; use it to cover every control in valid game states. Test that drawing coordinates follow the simulated positions, and that a checkpoint preserves other participants and unrelated features.
For an arcade with multiple independent games, declare meta.games instead of meta.game: [{id:'snake',exportName:'snakeGame',tickMs:50,saveAction:'save_snake'},{id:'blocks',exportName:'blocksGame',tickMs:50,saveAction:'save_blocks'}]. It supports one to four games. Every entry needs a safe JavaScript exportName; IDs and saveAction names must be distinct. Export each named object with the same init/step/view contract, for example export const snakeGame={init,step,view}. Each export has its own isolated worker, view, lifecycle, keyboard focus and participant-owned progress. Render exactly one separate data-game root matching each id, each with its own canvas, readouts and labeled Start/Pause/Resume/Restart and game controls. Never nest game roots. Use distinct accessible labels such as Start Snake and Pause Blocks so voice can target the right tile. Preserve stable ids and all other game records when editing or saving one game. Feature tests use api.games[id].init(saved,actor), .step(state,action,actor), .view(state,actor), .actions and .config. Test every game and checkpoint independently, including preservation of the other games. Legacy meta.game pages keep api.gameInit/gameStep/gameView/gameActions; the new per-id api.games interface works for both declarations.
For held movement or thrust, add data-game-release JSON to the same control: for example data-game-action='{"type":"input","key":"left","held":true}' and data-game-release='{"type":"input","key":"left","held":false}', with data-game-keys="ArrowLeft a A". Press and release should idempotently set state flags, and ticks move using those flags. The host handles key/pointer down and release, cancellation and lost focus; clicks or voice make a short bounded press/release pulse. Without data-game-release, controls are ordinary repeatable taps, suitable for queued turns, rotation or jumping. Use the key token Space for the space bar. Keep transient held flags separate from lasting progress and reset them in init(saved,actor); never resume a saved physical key-down state.

When an owner asks for an AI chat, an agent, or natural-language interactions, connect a real platform service. You own all its visible HTML, CSS, copy, placement and controls inside render(). Nothing is inserted outside your page. Declare only services the requested experience needs in meta.capabilities: 'space-agent' for general conversation and actions, 'health-chat' for health education, or 'finance-news' for the official news feed. These names grant scoped authenticated operations through the trusted bridge; they do not grant arbitrary network access. Conversation history stays temporarily in the current viewer's session, separate from public state and the owner's builder thread. Do not substitute a hardcoded keyword parser, canned answers, or preset drawings for a requested AI interaction. The same real Astra/Ultrafast connection is available to visitors when the owner includes 'space-agent'.

For a general embedded agent declare capabilities:['space-agent'] and meta.agent={instructions:'Describe the purpose, relevant state structure, and how the agent should use its actions.',actions:[{name:'add_note',description:'Add a note to the shared wall.',parameters:{type:'object',properties:{text:{type:'string',maxLength:300}},required:['text'],additionalProperties:false}}]}. Omit actions or use [] for a conversational agent. Instructions are up to 4000 characters; up to 6 actions. Use short action names, descriptions up to 700 characters, and bounded JSON schemas: object (properties, required, additionalProperties:false), array (items, maxItems up to 400), string (minLength/maxLength, enum), number/integer (minimum/maximum), or boolean. No refs, unions, regex, or arbitrary schema keywords. No type/actor/actorId/revisionId fields in parameters: the host supplies the action's type from its name and the verified visitor identity. Tool arguments are up to 8000 JSON characters, so prefer compact batches for drawings.

Render the agent UI in a section data-service="space-agent" using the SAME form/message/template/text/error/status/cancel/clear bindings as health-chat below. Use a form WITHOUT data-action and name="message" for its input or textarea. The host streams actual model text into data-service-text or your message template. It executes each declared action as reduce(state,{type:actionName,...arguments},verifiedActor), validates the result, saves it, and notifies all open viewers immediately. Implement every declared action in reduce() and test it. State changes use current live state at commit time. A shared drawing can store each visitor's marks in their own record, choose max(existing sequence)+1 for each batch, and render the latest mark per pixel; this allows everyone to paint the same canvas without deleting another person's records. Agents may change only the interactions you expose, never page source, owner controls, or another space. Keep tool instructions and state compact. Never persist private conversation text as a side effect; persist only the requested public contribution. Use concise honest status copy; do not claim a change before it succeeds.

Do not generate meta.suggestions or explanatory prose outside the tool call. The owner uses the app's composer for follow-up edits.

To create a health chat, render a section with data-service="health-chat". Inside it, use a native form WITHOUT data-action, with textarea name="message" maxlength="1200" and a submit button. Include a div data-service-messages and a template data-service-message containing elements with data-field="role" and data-field="content". The bridge clones YOUR template for messages and streams plain text into its fields. Style user versus assistant messages with [data-service-role="user"] and [data-service-role="assistant"]. Add type="button" buttons with data-service-operation="cancel" and "clear" if useful. Optional div data-service-text displays only the latest answer. Include a div data-service-sources and template data-service-source with a span data-field="title" and an a data-field="url" (no href; the bridge supplies validated official URLs).

To create a news desk, render a section data-service="finance-news" data-service-auto. Include a div data-service-items and a template data-service-item containing elements with data-field="title", "summary", "date" and an a data-field="url" (no href). A type="button" with data-service-operation="refresh" reloads it. Include data-service-note to show feed freshness or the saved-reading-list label. The bridge fills each instance of YOUR template from official Federal Reserve data.

Any service section can include data-service-error, data-service-note, and visibility slots such as data-service-status="loading", "ready", "error", or "idle"; these slots contain YOUR concise state copy. Add a hidden attribute initially to non-idle slots. The bridge toggles their visibility. Do not dispatch model/network service requests through reduce(); ordinary custom features and the agent's validated tools use reduce(). Tests can verify capability declarations and rendered service bindings; tests do not call real network services. For health interfaces clearly identify AI general education, not medical advice or emergency care. Keep essential medical safeguards in visible concise copy. Financial calculators should explain illustrative assumptions. Service responses remain untrusted plain text and reference links are allowlisted by the host.

tests.js exports synchronous runTests(api) => [{name,ok,message?}] and nothing else. api.initialState is a fresh JSON clone of CURRENT live state, api.reduce(state,action,actor) and api.render(state,actor) are synchronous isolated functions, api.meta is module metadata. Each ok must be a boolean. Include at least 4 meaningful checks: a new-user first action, invalid input rejection, another actor's data preservation, and current-state rendering. For a purely visual space test meaningful content and unknown-action rejection instead of inventing an unrequested interaction. Add checks for the requested behavior, such as updating one's own text without overwriting another person's. Only for a budget-based feature, also test budget refusal: after the budget is spent, an extra support should throw or leave data unchanged. Use fresh actor ids (test-alpha/test-beta) so tests work even if existing visitors already participated. For expected errors use try/catch. Do not simply return constant true; call api functions and inspect outputs. Existing live contributions and extras may be nonempty, so compare relative changes. Never mutate api.initialState to erase previous data. ES2020 available. Test helper api functions are synchronous, no await/Promises.

Keep source concise, but include the complete requested behavior and tests; games may need more code than simple pages. The current source/tests/data appear in input, so do not inspect redundantly. Use the Codex patch grammar: Add File for full writes; Update File with @@ context and lines prefixed by space, -, or + for targeted edits; Delete File and Move to are allowed only within the two workspace filenames and only if both required files exist at the end. Preserve unrelated code, including working motion, timing, and controls during unrelated edits. When refining animation, improve the requested feel and address discontinuities or rendering cost without discarding the intended style or behavior. Do not claim a measured frame rate or visual smoothness from code checks alone. Prefer readable source with line breaks so future edits can use small hunks. Combine every related source and test edit into ONE apply_patch call so they are verified and published together. Reuse tests for visual-only changes; update tests when behavior or an explicitly tested expectation changes. Never wrap the patch in JSON or Markdown fences. Every complete patch runs the same full verification and atomic publication. Stop after successful publication. If verification fails, correct the working workspace using tool feedback and another apply_patch. A malformed patch leaves the workspace unchanged. Publication is app-owned and blocked if checks fail, cancellation arrives, or new owner instructions need incorporation. Never claim publication without a successful tool result. Avoid commentary before tool calls; the app shows progress. No need to narrate reasoning.`;
}
export const agentInstructions = instructionsForSpace();

class HttpError extends Error { constructor(status, message) { super(message); this.status = status; } }
class Cancelled extends Error { constructor() { super('The change was stopped. Your published space is unchanged.'); this.name = 'AbortError'; } }
const currentRevision = (data) => data.revisions.find((revision) => revision.id === data.currentRevisionId);

// Preview identity follows only the inputs to the published render. Private
// builder events and draft files cannot invalidate it, even after log pruning.
// The viewer is intentionally separate: callers must scope any HTML cache to
// their authenticated session because render() also receives that actor.
export function spacePreviewVersion(data) {
  const revision = currentRevision(data);
  return hash([revision.id, revision.source, data.state]).slice(0, 24);
}

async function seedData(seed, verificationActors, sequence = 0) {
  const result = await verifyModule(seed.source, seed.tests, clone(seed.state), verificationActors);
  if (!result.ok) throw new Error(`Initial space did not pass verification: ${JSON.stringify(result.checks)}`);
  return { version: 1, ownerId: verificationActors.owner.id, kind: seed.kind, sequence, state: clone(result.candidateState), currentRevisionId: 1, revisions: [{ id: 1, title: result.meta?.title || 'A little space for good ideas', createdAt: new Date().toISOString(), source: seed.source, tests: seed.tests, checks: result.checks, meta: result.meta }], session: { id: randomUUID(), status: 'idle', items: [], turns: [] }, events: [], ...(seed.icon ? { icon: clone(seed.icon) } : {}) };
}

export async function createSpaceService({ dataDir, adapter, comparisonAdapter, progressEstimator, progressEstimateTimeoutMs = BUILD_ESTIMATE_TIMEOUT_MS, apiKey, owner = defaultActors.mira, kind = 'studio', seedOverride, initialSeedOverride, initialSnapshot, actors = defaultActors, getActors = () => actors, model = appSetting('MODEL', 'gpt-6-astra'), tier = appSetting('TIER', 'ultrafast') } = {}) {
  if (!dataDir) throw new Error('dataDir is required');
  if (!owner || typeof owner.id !== 'string' || !/^[a-zA-Z0-9_-]{1,64}$/.test(owner.id) || typeof owner.name !== 'string' || !owner.name.trim() || owner.name.length > 100) throw new Error('A valid space owner is required.');
  owner = { id: owner.id, name: owner.name };
  const seed = { ...seedFor(kind), ...seedOverride, kind };
  const instructions = instructionsForSpace();
  const verificationActors = { owner, visitor: { id: 'verification-visitor', name: 'Visitor' }, projectCatalog: true };
  const actorList = () => {
    const source = getActors();
    const list = Array.isArray(source) ? source : Object.values(source);
    return [owner, ...list.filter(actor => actor.id !== owner.id)].map(actor => ({ id: actor.id, name: actor.name }));
  };
  const actorFor = (id = owner.id) => actorList().find(actor => actor.id === id);
  // A complete interactive page includes simulation, UI and behavioral tests.
  // Keep the smaller response allowance for chat services using this adapter.
  const serverApiKey = adapter ? undefined : apiKey ?? await loadApiKey();
  const provider = adapter || createResponsesAdapter({ apiKey: serverApiKey, model, tier, maxOutputTokens: 16000 });
  // A mock builder must never accidentally opt into a paid secondary request,
  // even if a test supplies a fake key or inherits a real environment key.
  const estimator = progressEstimator ?? (adapter ? null : createBuildProgressEstimator({ apiKey: serverApiKey }));
  if (!Number.isInteger(progressEstimateTimeoutMs) || progressEstimateTimeoutMs < 1 || progressEstimateTimeoutMs > BUILD_ESTIMATE_TIMEOUT_MS) throw new Error('Progress estimate timeout must be between 1 and 4,000 ms.');
  // Curated examples may initialize a new store with a verified page. This
  // never runs for an existing store; an owner reset still uses the blank seed.
  const store = await openStore(dataDir, async () => {
    // Internal companion seam: a complete immutable snapshot, not a generated
    // seed. The HTTP boundary never accepts this value or a workspace path.
    if (initialSnapshot) return clone(initialSnapshot);
    const initial = await seedData({ ...seed, ...initialSeedOverride, kind }, verificationActors);
    if (initialSeedOverride) {
      // A full demo reset restores a bundled example, not its visitors' posts
      // or later owner edits. Ordinary owner resets deliberately keep this
      // baseline while resetting their active page to the universal blank.
      initial.initialBaseline = { revision: clone(initial.revisions[0]), state: clone(initial.state), ...(initial.icon ? { icon: clone(initial.icon) } : {}) };
    }
    return initial;
  });
  const saved = store.read();
  if (saved.ownerId && (saved.ownerId !== owner.id || saved.kind !== kind)) throw new Error('This workspace belongs to a different space.');
  if (!saved.ownerId) {
    // Only the original, single-user demo store can be adopted automatically.
    if (owner.id !== 'mira' || kind !== 'studio') throw new Error('An unassigned legacy workspace cannot be used for this space.');
    await store.transact(data => { data.ownerId = owner.id; data.kind = kind; });
  }
  const compiled = new Map();
  let active = null;
  let closing = false;
  let comparisonStarting = null;
  let comparisonPreparation = null;
  let comparisonRecord = null;
  let companion = null;
  let companionDisposal = Promise.resolve();
  let comparisonObservers = [];
  let standardActivity = null;
  let progressEstimate = null;
  const comparison = createBuildComparison();

  function stopProgressEstimate() {
    const previous = progressEstimate;
    progressEstimate = null;
    previous?.controller.abort();
  }
  const stopProgressObserver = comparison.subscribe(event => {
    const current = event.data.comparison;
    const terminal = status => ['completed', 'failed', 'cancelled'].includes(status);
    if (progressEstimate && (!current || current.id !== progressEstimate.id || current.finished || terminal(current.ultrafast.status) && terminal(current.standard.status))) stopProgressEstimate();
  });
  function startProgressEstimate(record, initial, message) {
    const current = comparison.read();
    if (closing || comparisonStarting?.cancelled || !current || current.id !== record.id || current.finished) return;
    if ([current.ultrafast, current.standard].every(lane => ['completed', 'failed', 'cancelled'].includes(lane.status))) return;
    const work = { id: record.id, controller: new AbortController() };
    progressEstimate = work;
    // Scheduled only after the builders' common gate has opened. Preparing
    // this compact context or waiting for the predictor never delays either.
    void Promise.resolve().then(() => {
      work.controller.signal.throwIfAborted();
      const context = buildProgressContext({ snapshot: initial, message, model: record.model, reasoningEffort: record.reasoningEffort });
      return estimateBuildProgress({ estimator, context, signal: work.controller.signal, timeoutMs: progressEstimateTimeoutMs });
    }).then(result => {
      if (progressEstimate === work && !work.controller.signal.aborted) comparison.progress(record.id, result);
    }).catch(() => { /* Cancellation or disposal never changes displayed progress. */ }).finally(() => {
      if (progressEstimate === work) progressEstimate = null;
    });
  }

  // A stopped process cannot leave the next request believing a turn is still live.
  if (store.read().session.status === 'running') {
    await store.transact((data) => {
      const answered = new Set(data.session.items.filter(isToolOutput).map((item) => item.call_id));
      for (const item of [...data.session.items]) {
        if (isToolCall(item) && !answered.has(item.call_id)) data.session.items.push(toolOutput(item, { error: 'The local runtime restarted before this tool completed.' }));
      }
      data.session.status = 'idle';
      data.session.lastOutcome = 'interrupted';
      addEvent(data, { type: 'turn.cancelled', title: 'Recovered your last published space', detail: 'The local runtime restarted during a change. You can ask again.' });
    });
  }

  const activity = createBuildActivity();
  const stopActivity = store.subscribe(event => activity.lifecycle(event));
  const files = createWorkspaceFiles({ getPublished: () => {
    const data = store.read();
    const revision = currentRevision(data);
    return { sessionId: data.session.id, revisionId: revision.id, source: revision.source, tests: revision.tests };
  } });
  const stopFiles = store.subscribe(event => {
    if (['revision.published', 'turn.completed', 'turn.failed', 'turn.cancelled', 'space.reset'].includes(event.type)
      || event.type === 'space.updated' && event.data?.reset) files.published();
  });

  async function bundleFor(revision) {
    const key = hash(revision.source);
    if (!compiled.has(key)) compiled.set(key, await compileModule(revision.source));
    return compiled.get(key).bundle;
  }
  async function gameFor(revision) {
    const key = hash(revision.source);
    if (!compiled.has(key)) compiled.set(key, await compileModule(revision.source));
    return compiled.get(key);
  }
  async function publishedHtml(revision, state, actor) {
    try { return await renderModule(await bundleFor(revision), state, actor); }
    catch {
      // Older saved revisions can fail newer render checks. Keep the actual
      // revision and host controls available without serving rejected HTML.
      const guidance = actor.id === owner.id
        ? 'Your saved work is safe. Restore a version from History, or describe a fix below.'
        : 'Your saved contributions are safe. The owner can restore a version or repair this design.';
      return `<section role="status" aria-label="Space recovery" style="padding:40px 24px;text-align:center"><h2>This design needs a repair.</h2><p>${guidance}</p></section>`;
    }
  }
  function guard(turn) {
    if (turn.controller.signal.aborted || active !== turn) throw new Cancelled();
    if (turn.pending.length) throw new Error('New owner instructions arrived. Read the next message and update this change before publishing.');
  }
  async function emit(turn, event, commitGuard) { return store.emit({ ...event, ...(turn ? { turnId: turn.id } : {}) }, commitGuard); }
  function workspaceInfo(turn, data = store.read()) {
    const revision = currentRevision(data);
    // Only the owner identity belongs in model context. Current participant IDs
    // already appear in this space's public state; the account registry does not.
    return { owner, kind, revision: revision.id, source: turn?.source ?? revision.source, tests: turn?.tests ?? revision.tests, state: data.state };
  }
  function checkSource(source, filename) {
    if (typeof source !== 'string' || source.length < 10 || Buffer.byteLength(source) > 80_000) throw new Error(`${filename} must contain between 10 and 80,000 bytes of JavaScript.`);
  }
  async function writeWorkspace(turn, source, tests) {
    guard(turn); checkSource(source, 'space.js'); checkSource(tests, 'tests.js');
    await writeFile(join(turn.directory, 'space.js'), source, { mode: 0o600 });
    await writeFile(join(turn.directory, 'tests.js'), tests, { mode: 0o600 });
    guard(turn);
    turn.source = source; turn.tests = tests; turn.verified = null;
    files.working(turn);
    await emit(turn, { type: 'tool.completed', stage: 'build', title: 'Wrote the working change', detail: 'space.js + tests.js', data: { tool: 'write_file', files: ['space.js', 'tests.js'], sourceCharacters: source.length, testCharacters: tests.length } });
    return { ok: true, files: ['space.js', 'tests.js'] };
  }
  async function verify(turn) {
    guard(turn);
    const state = store.read().state;
    const started = performance.now();
    await emit(turn, { type: 'tool.started', stage: 'verify', title: 'Checking the new behavior', detail: 'Compile, isolate and test against live data', data: { tool: 'verify_workspace' } });
    const result = await verifyModule(turn.source, turn.tests, state, verificationActors);
    turn.verified = { sourceHash: hash(turn.source + turn.tests), stateHash: hash(state), result };
    if (!result.ok) turn.verificationFailures++;
    await emit(turn, { type: result.ok ? 'tool.completed' : 'tool.failed', stage: 'verify', title: result.ok ? `${result.checks.length} checks passed` : 'A check needs a correction', detail: result.ok ? 'The change passed its behavioral and runtime checks.' : result.checks.filter((check) => !check.ok).map((check) => `${check.name}: ${check.message || 'failed'}`).join('; ').slice(0, 450), durationMs: Math.round(performance.now() - started), data: { tool: 'verify_workspace', checks: result.checks } });
    return { ok: result.ok, checks: result.checks };
  }
  async function publish(turn, summary) {
    guard(turn);
    await emit(turn, { type: 'tool.started', stage: 'publish', title: 'Bringing your change to life', detail: 'An atomic revision; every contribution stays', data: { tool: 'publish_revision' } });
    const result = await store.transact(async (data) => {
      guard(turn);
      const sourceHash = hash(turn.source + turn.tests);
      let verified = turn.verified;
      if (!verified || verified.sourceHash !== sourceHash) throw new Error('Run verify_workspace before publishing this source.');
      if (verified.stateHash !== hash(data.state)) {
        const result = await verifyModule(turn.source, turn.tests, clone(data.state), verificationActors);
        verified = { sourceHash, stateHash: hash(data.state), result };
        turn.verified = verified;
      }
      if (!verified.result.ok) throw new Error(`Publication blocked by failed checks: ${JSON.stringify(verified.result.checks.filter((check) => !check.ok))}`);
      guard(turn);
      const revision = { id: Math.max(...data.revisions.map((item) => item.id)) + 1, title: String(summary || verified.result.meta?.title || 'A new possibility').slice(0, 90), createdAt: new Date().toISOString(), source: turn.source, tests: turn.tests, checks: verified.result.checks, meta: verified.result.meta };
      data.state = clone(verified.result.candidateState);
      data.revisions.push(revision); data.currentRevisionId = revision.id;
      addEvent(data, { type: 'revision.published', stage: 'publish', turnId: turn.id, title: revision.title, detail: data.state.contributions.length ? `${data.state.contributions.length} existing contribution${data.state.contributions.length === 1 ? '' : 's'} preserved.` : 'Your new interaction is live.', data: { revisionId: revision.id, preservedContributions: data.state.contributions.length, checks: revision.checks } });
      return { ok: true, revisionId: revision.id, title: revision.title, preservedContributions: data.state.contributions.length };
    }, () => guard(turn));
    turn.published = result;
    return result;
  }

  async function execute(turn, call) {
    if (turn.results.has(call.call_id)) return turn.results.get(call.call_id);
    const started = performance.now();
    activity.toolStarted(turn.id, call);
    let result;
    try {
      if (turn.controller.signal.aborted) throw new Cancelled();
      if (call.type === 'custom_tool_call' && call.name !== 'apply_patch') throw new Error(`Unknown custom tool ${call.name}`);
      const args = call.type === 'custom_tool_call' ? {} : JSON.parse(call.arguments || '{}');
      if (!args || typeof args !== 'object' || Array.isArray(args)) throw new Error('Tool arguments must be an object.');
      if (turn.published) result = { skipped: true, reason: 'This turn has already published successfully.' };
      else switch (call.name) {
        case 'inspect_space':
          await emit(turn, { type: 'tool.completed', stage: 'inspect', title: 'Read the current space', detail: 'Source, tests and persistent live data', data: { tool: call.name } });
          result = workspaceInfo(turn); break;
        case 'read_file':
          if (!['space.js', 'tests.js'].includes(args.path)) throw new Error('Only space.js and tests.js are editable.');
          result = { path: args.path, content: await readFile(join(turn.directory, args.path), 'utf8') }; break;
        case 'write_file':
          if (!['space.js', 'tests.js'].includes(args.path)) throw new Error('Only space.js and tests.js are editable.');
          guard(turn); checkSource(args.content, args.path);
          await writeFile(join(turn.directory, args.path), args.content, { mode: 0o600 });
          guard(turn);
          turn[args.path === 'space.js' ? 'source' : 'tests'] = args.content; turn.verified = null;
          files.working(turn);
          await emit(turn, { type: 'tool.completed', stage: 'build', title: `Wrote ${args.path}`, data: { tool: call.name, file: args.path, characters: args.content.length } });
          result = { ok: true, path: args.path }; break;
        case 'verify_workspace': result = await verify(turn); break;
        case 'publish_revision': result = await publish(turn, args.summary); break;
        case 'apply_change':
          await writeWorkspace(turn, args.source, args.tests);
          result = await verify(turn);
          if (result.ok) result = await publish(turn, args.summary);
          break;
        case 'apply_patch': {
          guard(turn);
          const next = call.type === 'custom_tool_call' ? applyCodexPatch(turn, call.input) : applySourceEdits(turn, args.edits);
          await writeWorkspace(turn, next.source, next.tests);
          result = await verify(turn);
          if (result.ok) result = await publish(turn, call.type === 'custom_tool_call' ? undefined : args.summary);
          break;
        }
        default: throw new Error(`Unknown tool ${call.name}`);
      }
    } catch (error) {
      if (turn.controller.signal.aborted) throw new Cancelled();
      files.working(turn);
      result = { ok: false, error: publicError(error) };
      await emit(turn, { type: 'tool.failed', stage: call.name.includes('publish') ? 'publish' : 'build', title: 'Adjusting the change', detail: result.error, data: { tool: call.name } });
    }
    turn.results.set(call.call_id, result);
    activity.toolFinished(turn.id, call, result, Math.round(performance.now() - started));
    return result;
  }

  async function flushSteering(turn) {
    if (!turn.pending.length) return;
    const pending = turn.pending.splice(0);
    turn.appTheme = pending.at(-1).appTheme;
    await store.transact((data) => {
      for (const { message, appTheme } of pending) data.session.items.push({ role: 'user', content: `Owner's additional instruction (incorporate before publishing): ${message}\nApp appearance when submitted: ${appTheme}.` });
    });
    turn.verified = null;
  }

  async function run(turn) {
    const started = performance.now();
    const previewActive = () => active === turn && !turn.controller.signal.aborted && !turn.pending.length && !turn.published;
    const draftPreview = createDraftPreviewer({
      getState: () => store.read().state,
      actor: owner,
      emit: (event, current) => emit(turn, event, () => {
        if (!current() || !previewActive() || currentRevision(store.read()).id !== turn.baseRevisionId) throw new Cancelled();
      }),
      isActive: previewActive,
    });
    try {
      // A comparison releases both prepared harnesses together. Neither lane
      // waits for the other lane's model response, tools, or verification.
      await turn.startGate;
      turn.controller.signal.throwIfAborted();
      await emit(turn, { type: 'tool.completed', stage: 'inspect', title: 'Read the current space', detail: 'Source, tests and live data are in context.', data: { tool: 'inspect_space', revisionId: currentRevision(store.read()).id } });
      for (let loop = 0; loop < 8; loop++) {
        draftPreview.discard();
        files.beginResponse();
        if (turn.controller.signal.aborted) throw new Cancelled();
        await flushSteering(turn);
        await emit(turn, { type: 'model.started', stage: 'build', title: loop === 0 ? 'Shaping your next possibility' : 'Refining the working change', detail: `${provider.model || model} · ${turn.requestedTier}`, data: { model: provider.model || model, requestedTier: turn.requestedTier, iteration: loop + 1 } });
        let characters = 0;
        const streamingCalls = new Map();
        const requestData = store.read();
        const response = await provider.respond({ input: requestData.session.items, cacheKey: `little-worlds:${requestData.session.id}`, tier: turn.requestedTier, ...(turn.responseTimeoutMs ? { timeoutMs: turn.responseTimeoutMs } : {}), instructions: `${instructions}\n\n${buildAppearanceInstructions(turn)}`, tools: agentTools, signal: turn.controller.signal, onEvent: (event) => {
          // The owner feed consumes only allowlisted visible output, never the
          // model's input, encrypted reasoning, or provider transport details.
          if (active === turn && !turn.controller.signal.aborted) {
            activity.providerEvent(turn.id, loop, event);
            if (previewActive()) files.providerEvent(event);
          }
          if (event.type === 'response.output_item.added' && isToolCall(event.item)) {
            streamingCalls.set(event.output_index, { type: event.item.type, name: event.item.name, arguments: event.item.arguments || '', input: event.item.input || '' });
          }
          if (event.type === 'response.custom_tool_call_input.delta' || event.type === 'response.custom_tool_call_input.done') {
            const call = streamingCalls.get(event.output_index);
            if (call?.type === 'custom_tool_call' && call.name === 'apply_patch') {
              const complete = event.type.endsWith('.done');
              call.input = complete ? event.input ?? call.input : call.input + (event.delta || '');
              if (previewActive()) {
                try {
                  const next = complete ? applyCodexPatch(turn, call.input) : projectCodexPatch(turn, call.input);
                  if (next.source !== turn.source) draftPreview.schedule(JSON.stringify({ source: next.source }), { force: complete });
                } catch { /* Invalid/incomplete patches cannot publish; execute() reports errors. */ }
              }
            }
          }
          if (event.type === 'response.function_call_arguments.delta') {
            const call = streamingCalls.get(event.output_index);
            if (call) {
              call.arguments += event.delta || '';
              if (call.name === 'apply_change') {
                draftPreview.schedule(call.arguments);
              }
            }
          }
          if (event.type === 'response.function_call_arguments.done') {
            const call = streamingCalls.get(event.output_index);
            if (call?.name === 'apply_change') draftPreview.schedule(event.arguments || call.arguments, { force: true });
            if (call?.name === 'apply_patch') {
              // Preview only a complete, unambiguous patch. It still uses the
              // inert sandbox and does not change the workspace or live state.
              try {
                const args = JSON.parse(event.arguments || call.arguments);
                const next = applySourceEdits(turn, args.edits);
                draftPreview.schedule(JSON.stringify({ source: next.source }), { force: true });
              } catch { /* execute() returns patch errors to the model for repair. */ }
            }
          }
          if (event.type === 'response.function_call_arguments.delta' || event.type === 'response.custom_tool_call_input.delta' || event.type === 'response.output_text.delta') {
            characters += event.delta?.length || 0;
          }
        } });
        draftPreview.discard();
        if (turn.controller.signal.aborted) throw new Cancelled();
        const output = response.output || [];
        activity.providerOutput(turn.id, loop, output);
        if (previewActive()) files.providerOutput(output);
        // Keep native item types, including custom calls and encrypted reasoning,
        // so Responses replay receives the matching custom/function output type.
        await store.transact((data) => { data.session.items.push(...clone(output)); });
        await emit(turn, { type: 'model.completed', stage: 'build', title: 'The model finished this step', durationMs: response.metrics?.durationMs, data: { ...response.metrics, model: response.model || provider.model || model, servedTier: response.service_tier || response.metrics?.servedTier || 'unknown', characters } });
        const calls = output.filter(isToolCall);
        if (!calls.length) {
          if (turn.pending.length) continue;
          const message = output.flatMap((item) => item.content || []).filter((item) => item.type === 'output_text').map((item) => item.text).join('\n');
          if (!turn.published) throw new Error(message || 'The model finished without making a change. Try asking for one specific interaction.');
          break;
        }
        for (const call of calls) {
          const result = await execute(turn, call);
          await store.transact((data) => { data.session.items.push(toolOutput(call, result)); });
        }
        if (turn.published) break;
        if (turn.verificationFailures >= 3) throw new Error('The change did not pass after three repair attempts. Your last working space is still live.');
      }
      if (!turn.published) throw new Error('The change reached the local step limit. Your last working space is still live.');
      await store.transact((data) => {
        data.session.status = 'idle'; data.session.lastOutcome = 'completed';
        const entry = data.session.turns.find((item) => item.id === turn.id); if (entry) { entry.status = 'completed'; entry.revisionId = turn.published.revisionId; }
        addEvent(data, { type: 'turn.completed', turnId: turn.id, title: turn.published.title, detail: 'Ready to try. Your live data stayed in place.', durationMs: Math.round(performance.now() - started), data: { revisionId: turn.published.revisionId } });
      });
    } catch (error) {
      const cancelled = turn.controller.signal.aborted || error.name === 'AbortError';
      await store.transact((data) => {
        const answered = new Set(data.session.items.filter(isToolOutput).map((item) => item.call_id));
        for (const item of [...data.session.items]) if (isToolCall(item) && !answered.has(item.call_id)) data.session.items.push(toolOutput(item, { error: cancelled ? 'Cancelled before completion.' : publicError(error) }));
        data.session.status = 'idle'; data.session.lastOutcome = cancelled ? 'cancelled' : 'failed';
        const entry = data.session.turns.find((item) => item.id === turn.id); if (entry) entry.status = cancelled ? 'cancelled' : 'failed';
        addEvent(data, { type: cancelled ? 'turn.cancelled' : 'turn.failed', turnId: turn.id, title: cancelled ? 'Change stopped' : 'Your working space is safe', detail: cancelled ? 'No unpublished change was applied.' : publicError(error), durationMs: Math.round(performance.now() - started) });
      });
    } finally {
      draftPreview.close();
      if (active === turn) active = null;
      // A message arriving after the atomic commit belongs to the next turn.
      // Do not silently drop it in the small commit-to-completion interval.
      if (turn.published && turn.pending.length && !closing) {
        for (const { message, appTheme } of turn.pending.splice(0)) await service.submit(message, { appTheme });
      }
    }
  }

  function observeComparisonLane(record, lane, target) {
    const turnId = lane === 'ultrafast' ? record.primaryTurnId : record.standard.turnId;
    const stopEvents = target.store.subscribe(event => {
      comparison.lifecycle(record.id, lane, event);
      if (event.turnId === turnId && /^turn\.(completed|failed|cancelled)$/.test(event.type)) {
        // preview() captures its revision/data before rendering. A later turn
        // cannot change this result, and the comparison ID rejects stale work.
        const preview = event.type === 'turn.completed'
          ? target.preview(owner.id).then(result => comparison.html(record.id, lane, turnId, result.html)).catch(() => {})
          : Promise.resolve();
        if (lane === 'standard') void preview.then(() => releaseCompanion(target)).catch(() => {});
      }
    });
    const stopActivity = target.activity.subscribe(event => {
      comparison.activity(record.id, lane, event);
      if (lane === 'standard') standardActivity?.accept(event);
    });
    const observers = [stopEvents, stopActivity];
    comparisonObservers.push(...observers);
    return observers;
  }

  function releaseCompanion(expected) {
    if (expected && companion?.service !== expected) return companionDisposal;
    const previous = companion;
    companion = null;
    const disposal = companionDisposal.then(async () => {
      if (!previous) return;
      try {
        // close() aborts pending work and flushes its final activity while the
        // relay is still subscribed. Metadata and sanitized replay stay alive.
        await previous.service?.close();
      } finally {
        for (const stop of previous.observers || []) {
          stop(); comparisonObservers = comparisonObservers.filter(item => item !== stop);
        }
        await rm(previous.directory, { recursive: true, force: true });
      }
    });
    companionDisposal = disposal.catch(() => {});
    return disposal;
  }

  async function disposeComparisonWork() {
    stopProgressEstimate();
    for (const unsubscribe of comparisonObservers.splice(0)) unsubscribe();
    standardActivity?.close(); standardActivity = null;
    await releaseCompanion();
  }

  async function startComparison(message, appTheme) {
    if (active || comparisonStarting) throw new HttpError(409, 'A comparison is already building. Finish or stop it before sending another request. Your draft has been kept.');
    if (provider.keyAvailable === false) throw new HttpError(503, 'No server API key is configured.');
    const starting = { cancelled: false };
    comparisonStarting = starting;
    // Capture once before any asynchronous preparation or visitor interaction.
    // Both histories and both initial workspace descriptions use this snapshot.
    const initial = store.read();
    let release;
    const startGate = new Promise(resolve => { release = resolve; });
    starting.release = release;
    let record;
    try {
      await disposeComparisonWork();
      if (closing || starting.cancelled) throw new Cancelled();
      // The companion starts with a new connection. Give both lanes the same
      // cold-connection start instead of favoring a warmed primary socket.
      provider.resetConnection?.();
      record = comparison.begin({ model: provider.model || model, reasoningEffort: provider.reasoningEffort || 'low',
        primaryTurnId: randomUUID(), standardTurnId: randomUUID() });
      comparisonRecord = record;
      standardActivity = createComparisonActivity();
      observeComparisonLane(record, 'ultrafast', service);
      const revision = currentRevision(initial);
      void publishedHtml(revision, initial.state, owner).then(html => {
        comparison.html(record.id, 'ultrafast', record.primaryTurnId, html, { initial: true });
        comparison.html(record.id, 'standard', record.standard.turnId, html, { initial: true });
      }).catch(() => {});

      // Tests/offline installations that inject a primary adapter must also
      // explicitly inject the companion. Never turn a fixture into a paid call.
      if (adapter && !comparisonAdapter) {
        comparison.fail(record.id, 'standard', record.standard.turnId, 'The standard comparison adapter is not configured.');
      } else {
        try {
          const directory = await mkdtemp(join(tmpdir(), 'little-worlds-comparison-'));
          companion = { directory, service: null };
          companion.service = await createSpaceService({ dataDir: directory, adapter: comparisonAdapter,
            apiKey, owner, kind, getActors, model: provider.model || model, tier: 'default', initialSnapshot: initial });
          companion.observers = observeComparisonLane(record, 'standard', companion.service);
        } catch (error) {
          comparison.fail(record.id, 'standard', record.standard.turnId, error);
          // A preparation failure has no child turn.completed/failed event
          // that could trigger the ordinary terminal cleanup.
          await releaseCompanion().catch(() => {});
        }
      }
      if (closing || starting.cancelled) throw new Cancelled();
      const options = { comparisonInternal: true, contextSnapshot: initial, startGate, responseTimeoutMs: 300_000, appTheme };
      const primaryStart = service.submit(message, { ...options, turnId: record.primaryTurnId, requestedTier: 'ultrafast' });
      const standardStart = companion?.service
        ? companion.service.submit(message, { ...options, turnId: record.standard.turnId, requestedTier: 'default' })
        : Promise.resolve(null);
      const [primaryResult, standardResult] = await Promise.allSettled([primaryStart, standardStart]);
      if (standardResult.status === 'rejected') {
        comparison.fail(record.id, 'standard', record.standard.turnId, standardResult.reason);
        await releaseCompanion().catch(() => {});
      }
      if (primaryResult.status === 'rejected') {
        await companion?.service?.cancel();
        throw primaryResult.reason;
      }
      if (closing || starting.cancelled) {
        active?.controller.abort();
        await companion?.service?.cancel();
      }
      // Both run loops already exist behind this common gate.
      release();
      startProgressEstimate(record, initial, message);
      return { turnId: record.primaryTurnId, comparisonId: record.id };
    } catch (error) {
      if (record) {
        const cancelled = closing || starting.cancelled || error.name === 'AbortError';
        comparison.fail(record.id, 'ultrafast', record.primaryTurnId, error, cancelled);
        comparison.fail(record.id, 'standard', record.standard.turnId, error, cancelled);
      }
      // Cancelled preparation never entered the child's run loop. Release its
      // barrier before closing in case one lane did finish preparing.
      if (active?.id === record?.primaryTurnId) active.controller.abort();
      release();
      await releaseCompanion().catch(() => {});
      throw error;
    } finally {
      release();
      if (comparisonStarting === starting) comparisonStarting = null;
    }
  }

  const service = {
    store,
    activity,
    files,
    comparison,
    owner,
    kind,
    get busy() { return Boolean(active || comparisonStarting); },
    async snapshot(actorId = owner.id) {
      const actor = actorFor(actorId); if (!actor) throw new HttpError(400, 'Unknown participant.');
      const data = store.read(); const revision = currentRevision(data);
      const html = await publishedHtml(revision, data.state, actor);
      return { owner, kind, state: data.state, revision, html, actor, session: { id: data.session.id, status: data.session.status, lastOutcome: data.session.lastOutcome, turnCount: data.session.turns.length, lastMessage: data.session.turns.at(-1)?.message, turns: data.session.turns.map(({ id, message, status, startedAt, revisionId }) => ({ id, message, status, startedAt, revisionId })) }, config: { model: provider.model || model, requestedTier: provider.tier || tier, reasoningEffort: provider.reasoningEffort || 'unknown', keyAvailable: provider.keyAvailable !== false, adapter: 'local' }, events: data.events };
    },
    async preview(actorId = owner.id) {
      const actor = actorFor(actorId); if (!actor) throw new HttpError(400, 'Unknown participant.');
      // Capture all inputs together, before awaiting the isolated renderer, so
      // a concurrent publication cannot pair old HTML with a newer version.
      const data = store.read(); const revision = currentRevision(data);
      const hasBuilt = revision.source.trim() !== blankSeedSource.trim();
      const version = spacePreviewVersion(data);
      const html = hasBuilt ? await publishedHtml(revision, data.state, actor) : '';
      const appearance = demoAppearanceFor(owner.id, revision.source);
      return { version, html, hasBuilt, ...(appearance ? { appearance } : {}) };
    },
    async game(actorId, gameId) {
      const actor = actorFor(actorId); if (!actor) throw new HttpError(400, 'Unknown participant.');
      const data = store.read(); const revision = currentRevision(data);
      const configs = gameConfigs(revision.meta);
      if (!configs.length) throw new HttpError(404, 'This space has no local game.');
      if (gameId !== undefined && typeof gameId !== 'string') throw new HttpError(400, 'Choose one gameId.');
      if (gameId === undefined && configs.length > 1) throw new HttpError(400, 'Choose a gameId for this arcade.');
      const selected = gameId === undefined ? configs[0] : configs.find(config => config.id === gameId);
      if (!selected) throw new HttpError(404, 'This space has no matching local game.');
      const result = await gameFor(revision);
      const config = gameConfigs(result.meta).find(config => config.id === selected.id);
      const bundle = result.gameBundles[config.id];
      if (!bundle) throw new HttpError(404, 'This space has no local game.');
      const saved = data.state.extras[config.id]?.[actor.id] ?? null;
      if (saved !== null) validateGameState(saved, actor);
      return { revisionId: revision.id, config, bundle, actor, saved };
    },
    async submit(message, options = {}) {
      if (closing) throw new HttpError(503, 'The local runtime is stopping.');
      if (typeof message !== 'string' || !message.trim() || message.length > 4000) throw new HttpError(400, 'Describe a change in 1–4,000 characters.');
      if (options.appTheme !== undefined && !['light', 'dark'].includes(options.appTheme)) throw new HttpError(400, 'appTheme must be light or dark.');
      const appTheme = options.appTheme ?? active?.pending.at(-1)?.appTheme ?? active?.appTheme ?? 'dark';
      message = message.trim();
      if (!options.comparisonInternal) {
        if (comparisonStarting || active && comparisonRecord?.primaryTurnId === active.id) {
          throw new HttpError(409, 'A comparison is already building. Finish or stop it before sending another request. Your draft has been kept.');
        }
        if (options.compare) {
          const preparing = startComparison(message, appTheme);
          comparisonPreparation = preparing;
          try { return await preparing; }
          finally { if (comparisonPreparation === preparing) comparisonPreparation = null; }
        }
        // A non-comparison caller starts a normal turn without leaving a paid
        // standard request running unseen in the previous comparison.
        if (comparisonRecord) {
          await disposeComparisonWork();
          if (closing) throw new HttpError(503, 'The local runtime is stopping.');
          if (comparisonStarting) throw new HttpError(409, 'A comparison is already building. Finish or stop it before sending another request. Your draft has been kept.');
          comparisonRecord = null; comparison.reset();
        }
      }
      if (active) {
        const current = active;
        if (current.published) {
          await current.promise;
          return service.submit(message, { appTheme });
        }
        current.pending.push({ message, appTheme });
        await emit(current, { type: 'message', title: 'Your follow-up is queued', detail: message, data: { steering: true } });
        return { turnId: current.id, steering: true };
      }
      if (provider.keyAvailable === false) throw new HttpError(503, 'No server API key is configured.');
      const data = options.contextSnapshot || store.read(); const revision = currentRevision(data);
      const turn = { id: options.turnId || randomUUID(), baseRevisionId: revision.id, controller: new AbortController(), pending: [], source: revision.source, tests: revision.tests, verified: null, verificationFailures: 0, results: new Map(), published: null,
        startGate: options.startGate, requestedTier: options.requestedTier || provider.tier || tier, responseTimeoutMs: options.responseTimeoutMs,
        appTheme, firstBuild: revision.source.trim() === blankSeedSource.trim() };
      const context = JSON.stringify(workspaceInfo(turn, data));
      turn.directory = join(dataDir, 'workspaces', turn.id);
      active = turn;
      turn.preparation = (async () => {
        await mkdir(turn.directory, { recursive: true, mode: 0o700 });
        await writeFile(join(turn.directory, 'space.js'), turn.source, { mode: 0o600 });
        await writeFile(join(turn.directory, 'tests.js'), turn.tests, { mode: 0o600 });
        await store.transact((draft) => {
          draft.session.status = 'running';
          draft.session.turns.push({ id: turn.id, message, appTheme, status: 'running', startedAt: new Date().toISOString() });
          draft.session.items.push({ role: 'user', content: `Owner's request: ${message}\n\nCurrent workspace and live state (authoritative for this turn):\n${context}` });
          addEvent(draft, { type: 'turn.started', turnId: turn.id, stage: 'inspect', title: 'Making room for your idea', detail: message });
        });
      })();
      try { await turn.preparation; } catch (error) { active = null; throw error; }
      files.begin(turn.id);
      turn.promise = run(turn);
      return { turnId: turn.id };
    },
    async cancel() {
      stopProgressEstimate();
      const wasPreparing = Boolean(comparisonStarting);
      if (comparisonStarting) { comparisonStarting.cancelled = true; comparisonStarting.release?.(); }
      const turn = active;
      turn?.controller.abort();
      const standard = await companion?.service?.cancel();
      if (turn) files.published();
      return { cancelled: Boolean(turn || standard?.cancelled || wasPreparing), ...(turn ? { turnId: turn.id } : {}) };
    },
    getComparisonActivity(id) {
      if (comparisonRecord?.id !== id || !standardActivity) throw new HttpError(404, 'This comparison is no longer available.');
      return standardActivity;
    },
    async finishComparison(id) {
      const current = comparison.read();
      if (!current || current.id !== id) throw new HttpError(404, 'This comparison is no longer available.');
      if (!['completed', 'failed', 'cancelled'].includes(current.ultrafast.status)) throw new HttpError(409, 'The ultrafast build is still running.');
      stopProgressEstimate();
      comparison.finish(id);
      const finished = comparison.read();
      await companion?.service?.cancel();
      void releaseCompanion().catch(() => {});
      const latest = comparison.read();
      return { comparison: latest?.id === id ? latest : finished };
    },
    async action({ action, actor: actorId, revisionId, signal, requiredCapability }) {
      if (closing) throw new HttpError(503, 'The local runtime is stopping.');
      signal?.throwIfAborted();
      const actor = actorFor(actorId); if (!actor) throw new HttpError(400, 'Unknown visitor.');
      if (!action || typeof action !== 'object' || Array.isArray(action) || JSON.stringify(action).length > 34_000) throw new HttpError(400, 'Invalid action.');
      return store.transact(async (data) => {
        const revision = currentRevision(data);
        if (revision.id !== revisionId) throw new HttpError(409, 'This space just changed. Try your action again.');
        signal?.throwIfAborted();
        if (requiredCapability && !revision.meta?.capabilities?.includes(requiredCapability)) throw new HttpError(403, 'This space has not enabled that service.');
        const gameCheckpoint = gameConfigs(revision.meta).find(config => config.saveAction !== undefined && action.type === config.saveAction);
        if (gameCheckpoint) {
          if (Object.keys(action).some(key => !['type', 'game'].includes(key))) throw new HttpError(400, 'Invalid game checkpoint.');
          validateGameState(action.game, actor);
        } else if (JSON.stringify(action).length > 8000) throw new HttpError(400, 'Invalid action.');
        const next = await reduceModule(await bundleFor(revision), clone(data.state), action, actor, { gameCheckpoint });
        data.state = next;
        addEvent(data, { type: 'space.updated', title: `${actor.name} joined in`, detail: 'The interaction updated the shared live state.', data: { actorId, revisionId, contributionCount: next.contributions.length } });
        return { state: next };
      }, () => { signal?.throwIfAborted(); if (closing) throw new HttpError(503, 'The local runtime is stopping.'); });
    },
    async revisions() { return store.read().revisions; },
    async restore(revisionId) {
      if (closing) throw new HttpError(503, 'The local runtime is stopping.');
      if (active || comparisonStarting) throw new HttpError(409, 'Finish or stop the current change before restoring.');
      await disposeComparisonWork();
      if (closing) throw new HttpError(503, 'The local runtime is stopping.');
      if (active || comparisonStarting) throw new HttpError(409, 'A new change started. Stop it before restoring.');
      comparisonRecord = null; comparison.reset();
      return store.transact(async (data) => {
        if (active || comparisonStarting) throw new HttpError(409, 'A new change started. Stop it before restoring.');
        const previous = data.revisions.find((revision) => revision.id === revisionId);
        if (!previous) throw new HttpError(404, 'That revision was not found.');
        const verified = await verifyModule(previous.source, previous.tests, clone(data.state), verificationActors);
        const budget = verified.meta?.budget;
        if (Number.isFinite(budget)) {
          const totals = new Map();
          for (const contribution of data.state.contributions) totals.set(contribution.actorId, (totals.get(contribution.actorId) || 0) + contribution.points);
          const maximum = Math.max(0, ...totals.values());
          if (maximum > budget) throw new HttpError(400, `This earlier design allows ${budget} point${budget === 1 ? '' : 's'} per person, but the current space has a participant with ${maximum} points. Choose another revision; all contributions were kept.`);
        }
        if (!verified.ok) throw new HttpError(400, 'This earlier revision cannot safely use the current data. The live space was kept.');
        const next = { ...previous, id: Math.max(...data.revisions.map((item) => item.id)) + 1, title: `Restored: ${previous.title}`.slice(0, 90), createdAt: new Date().toISOString(), checks: verified.checks };
        data.state = clone(verified.candidateState);
        data.revisions.push(next); data.currentRevisionId = next.id;
        addEvent(data, { type: 'revision.published', stage: 'publish', title: next.title, detail: 'Current contributions were preserved.', data: { revisionId: next.id, restoredFrom: revisionId } });
        return { revisionId: next.id };
      }, () => { if (closing) throw new HttpError(503, 'The local runtime is stopping.'); if (active || comparisonStarting) throw new HttpError(409, 'A change started before restore completed.'); });
    },
    async reset() {
      if (closing) throw new HttpError(503, 'The local runtime is stopping.');
      if (active || comparisonStarting) throw new HttpError(409, 'Stop the current change before resetting.');
      await disposeComparisonWork();
      if (closing) throw new HttpError(503, 'The local runtime is stopping.');
      if (active || comparisonStarting) throw new HttpError(409, 'A change started before reset completed.');
      comparisonRecord = null; comparison.reset();
      await store.transact(async (data) => {
        const next = await seedData(seed, verificationActors, data.sequence);
        Object.assign(data, next);
        addEvent(data, { type: 'space.updated', title: 'A fresh space', detail: 'Ready for another possibility.', data: { reset: true } });
      }, () => { if (closing) throw new HttpError(503, 'The local runtime is stopping.'); if (active || comparisonStarting) throw new HttpError(409, 'Stop the current change before resetting.'); });
      compiled.clear(); return { ok: true };
    },
    async waitForIdle() { await comparisonPreparation?.catch(() => {}); while (active) await (active.promise || active.preparation); await store.flush(); },
    async close() {
      closing = true;
      stopProgressEstimate();
      if (comparisonStarting) { comparisonStarting.cancelled = true; comparisonStarting.release?.(); }
      const stopping = active;
      stopping?.controller.abort();
      try {
        await comparisonPreparation?.catch(() => {});
        await disposeComparisonWork();
        await stopping?.preparation?.catch(() => {}); await stopping?.promise; await store.flush();
      }
      finally { stopProgressObserver(); comparison.close(); stopActivity(); activity.close(); stopFiles(); files.close(); await provider.close?.(); }
    },
  };
  return service;
}
