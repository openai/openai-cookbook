# Build interactive worlds with Ultrafast

Little Worlds is a runnable React and Node.js application that turns a natural-language request into an interactive personal page. A local agent writes JavaScript and tests through the Responses API, streams its work, and publishes the page after the host verifies it. Each person has a separate world, saved builder conversation, and participation data.

The example compares two independent builds using the same model and starting context: one requests `service_tier: "ultrafast"`, and the other requests `service_tier: "default"`. You can inspect their output, elapsed time, and observed streaming rate while the pages take shape. See the [Ultrafast guide](https://developers.openai.com/api/docs/guides/ultrafast-mode) for API behavior and availability.

## Prerequisites

- Node.js 22 or newer and npm; Node.js 24 is recommended and selected by `.nvmrc`
- An OpenAI API key with access to `gpt-6-astra` and the Ultrafast service tier for the default comparison
- Optional model access for the progress estimate (`gpt-6-sol`), generated profile icons (`gpt-image-2.5-flare`), and voice (`gpt-live-1`)

Each submitted comparison runs two model workloads. It also requests a short progress estimate, and a first successful build can trigger an image request for its profile icon. These requests incur API usage. You can explore Nora's bundled message board and run the automated tests without an API key.

This is a local demo with simulated sign-in. Anyone using it can select any demo person. It binds to loopback and is not ready to host as a public multi-user service. See [Security](SECURITY.md) before adapting it for deployment.

## Run locally

Clone the Cookbook and install dependencies inside this example:

```sh
git clone https://github.com/openai/openai-cookbook.git
cd openai-cookbook/examples/ultrafast/little-worlds
npm ci
cp .env.example .env
```

Set `OPENAI_API_KEY` in `.env`, then start the API and frontend:

```sh
npm run dev
```

Open [Little Worlds on port 5173](http://127.0.0.1:5173). The API runs on port 4318, and Vite proxies `/api` requests to it. Keep both processes running. Frontend edits reload automatically; restart the command after backend edits.

The backend reads `.env` from this `little-worlds` directory, not the Cookbook root. Existing process environment values take precedence. The API key stays on the server; never put it in a `VITE_*` variable, which exposes values to the frontend. Keep `.env` out of Git.

To run the compiled application:

```sh
npm run build
npm start
```

Then open [Little Worlds on port 4318](http://127.0.0.1:4318).

## Build and visit a world

1. Choose **Log in**, select **Leo**, and open his blank world. You can also create a new person
2. Submit: **“Build a small garden with three plant cards and a button on each card to record that I watered it”**
3. Watch the **Ultrafast** and **Standard** lanes stream their work. Both write a page and tests, then run the same verification and repair loop
4. When the Ultrafast build succeeds, interact with its published page. Select **Enter your world** to close the comparison and stop any unfinished Standard build
5. Submit a follow-up such as **“Add a fourth plant card, keeping all existing watering records”**. The builder continues from the current source, data, and conversation
6. Open **Community**, visit **Nora**, and post on the bundled Town Square board. In another tab, sign in as a different person to try visitor interactions and friend requests

Only the Ultrafast lane publishes to your saved world. The Standard lane runs in a temporary workspace and displays a read-only result. There is no winner-selection step. If Ultrafast fails or is cancelled, **Return to world** preserves the previously published page. Independent generations can produce different code, output lengths, and repair attempts even with the same starting context.

**Thread** shows earlier requests. **History** can restore an older compatible design while retaining current participation data. **Reset this space** clears that person's page, data, and builder conversation; use it deliberately. Friendships are stored separately.

## How the comparison works

The browser submits an owner-authorized turn with `compare: true`. The server starts the two builders from the same snapshot, using the same API key, model, low reasoning effort, prompt, tools, history, source, and data. The service tier differs:

```js
// Request settings selected by the two build lanes.
const ultrafast = {
  model: "gpt-6-astra",
  service_tier: "ultrafast",
  reasoning: { effort: "low" },
};

const standard = { ...ultrafast, service_tier: "default" };
```

The complete requests also include the workspace instructions, conversation items, tools, and `store: false`. The transport retains completed output items locally for future turns. It uses [Responses WebSocket mode](https://developers.openai.com/api/docs/guides/websocket-mode) when available and falls back to HTTP if the initial connection upgrade fails. It does not replay an already-sent request automatically.

Each builder follows this sequence:

1. Read the current `space.js`, `tests.js`, and public state
2. Generate a patch with the custom `apply_patch` tool
3. Compile and execute the candidate in a resource-limited QuickJS worker
4. Run host checks and the generated behavioral tests, with repairs when needed
5. Publish a verified Ultrafast result atomically, or retain the verified Standard result for comparison

The host checks ownership and current data again before publication. Generated code cannot access the server's credentials, filesystem, or network. Incomplete previews are inert and do not change saved state. Read the [harness guide](docs/HARNESS.md) and [module and HTTP contract](docs/CONTRACT.md) for the implementation details.

Each lane displays actual elapsed time and observed output. The approximate tokens-per-second display estimates visible output tokens as they arrive; it excludes initial waiting, tool execution, and hidden reasoning. The progress bar uses a shared predicted output budget from a short `gpt-6-sol` request. If that request fails or takes more than four seconds, it uses a local estimate. Progress is approximate because the builds are independent. These measurements describe the current run and are not a latency guarantee or a controlled benchmark.

## Configuration

The defaults are in [.env.example](.env.example).

| Variable | Default | Purpose |
| --- | --- | --- |
| `OPENAI_API_KEY` | Empty | Server-side API credential |
| `LITTLE_WORLDS_MODEL` | `gpt-6-astra` | Builder and embedded-agent model |
| `LITTLE_WORLDS_TIER` | `ultrafast` | Tier for ordinary turns and embedded agents; the comparison explicitly uses `ultrafast` and `default` |
| `LITTLE_WORLDS_TRANSPORT` | `auto` | Builder transport; set `http` to disable WebSockets |
| `LITTLE_WORLDS_LIVE_MODEL` | `gpt-live-1` | Optional voice model |
| `SPACE_ICON_MODEL` | `gpt-image-2.5-flare` | Generated profile icon model |
| `HEALTH_CHAT_MODEL` | `gpt-6-astra` | Optional health-education service model |
| `HEALTH_CHAT_TIER` | `ultrafast` | Tier for the health-education service |
| `FINANCE_NEWS_MODE` | `feed` | Use `saved` to skip the Federal Reserve feed request |
| `PORT` | `4318` | API port; keep this value for the included Vite proxy |

Changing `LITTLE_WORLDS_TIER` does not change the two tiers used by the comparison UI. To run that comparison, the selected model and API project must support both requested tiers. The Activity stream distinguishes the requested tier from the served tier reported by the API.

## Optional examples and voice

Nora's bundled Town Square works immediately. The other fictional people start with blank worlds. With the server running, use a second terminal in this directory to generate the seven example worlds:

```sh
npm run prepare-demo
```

This submits the [creative briefs](server/demo-prompts.mjs) through the same authenticated builder and makes real model calls, with at most two builds at once. Examples include a garden, a painting canvas, language lessons, and games. Preparation is optional and never runs automatically on startup. It records successful work in `.local/demo-preparation.json` and skips it on subsequent runs, preserving later edits. Use `npm run prepare-demo -- --only mira` for one person. Add `--rebuild` only when you intend to submit new build requests.

An offline arcade example is also available. Stop the server, run `npm run prepare-arcade`, then restart it. This verifies and installs the bundled arcade only if Karen's page is blank, and installs James's bundled profile icon. It makes no model or image API calls and preserves existing nonblank pages.

Profile icons can be generated in the background after a first build or when a saved built world lacks an icon. Those image requests use the server key and incur additional usage. Click your world's circular icon to upload an image or request a new one; uploaded images are normalized and stripped of metadata. Regular page edits do not regenerate an existing icon.

Select **Go live** to try voice, then grant microphone permission. For example, say **“Show me the community”** or **“Type a request for a watercolor garden, but don't submit it.”** Speech uses `gpt-live-1`; delegated UI actions use the configured builder model. Voice, delegated planning, and submitted builds incur API usage. Audio and relevant conversation and UI context are sent to OpenAI. Voice transcripts stay in transient app memory, while submitted builder requests and ordinary actions use their normal persistence. End voice to release the microphone and connection. See the [GPT-Live guide](https://developers.openai.com/api/docs/guides/live) for the API.

Generated pages can declare an embedded conversational agent with bounded actions. The host validates those actions and executes them as the signed-in visitor. The optional health and finance examples are educational demonstrations. Keep sensitive information out of demo conversations and public world data.

## Data and security boundaries

Saved worlds, revisions, participation, and builder conversations live in the ignored `.local/` directory beside this README. Demo-reset backups live in `.local-reset-history/`. Neither belongs in a commit or issue attachment. Restarting the server ends simulated login sessions but preserves saved worlds; sign in again to continue.

The React shell owns sign-in, navigation, friend requests, and the builder controls. Generated code owns the personal page and runs through the constrained module contract. Owners can edit their own worlds; visitors can use the published controls. Participation records are checked against the selected identity. All generated world state is public to visitors of that world, so it must not contain secrets.

The local session and sandbox checks demonstrate application boundaries. Production deployment requires verified identity, appropriate storage and retention, abuse controls, and a security review. The [security notes](SECURITY.md) describe the limits.

## Verify changes

Run the TypeScript build and automated tests:

```sh
npm run check
```

These tests use local fixtures and mocked model responses; no API key or model charges are required. They cover runtime containment, owner and visitor permissions, record ownership, persistence, cancellation, repair, comparison behavior, and publication.

For a browser comparison with mocked builders and temporary data:

```sh
node tests/browser/build-activity-server.mjs --natural-seeds
```

Open the [comparison fixture on port 5190](http://127.0.0.1:5190), sign in as Mira, and submit `quick`. Try `standard first quick` to reverse completion order or `standard fail` to exercise an independent error. The fixture does not call model APIs or edit your saved worlds. Stop it to remove its temporary data.

With Vite running, the [voice surface fixture](http://127.0.0.1:5173/tests/browser/voice-surface.html) checks UI control discovery without a microphone or API calls. The [comparison layout fixture](http://127.0.0.1:5173/tests/browser/build-comparison-layout.html) checks transitions, responsive layout, and reduced motion.

To run the opt-in smoke test against the real API:

```sh
npm run test:live -- --confirm-api-usage
```

This uses the configured key for a live comparison with fresh temporary data. It incurs model usage but does not generate icons, use voice, retrieve news, or modify your saved demo worlds.

## License

The example follows the Cookbook's MIT license, with Apache-2.0 terms for the Codex-derived patch grammar and adapter. See [NOTICE](NOTICE) and the included [Codex license](licenses/Codex-Apache-2.0.txt).
