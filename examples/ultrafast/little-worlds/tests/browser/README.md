# Browser checks

These fixtures exercise browser behavior that the Node test suite cannot fully cover, including layout, focus, animation, canvas input, and reloads. They are not run by `npm run check`. Some have a **Run checks** button; others expose controls for manual verification. An opened page alone is not a passing result.

Run commands below from `examples/ultrafast/little-worlds` after `npm ci`. Use a dedicated browser tab and record the fixture, viewport, motion setting, and observed result. Keep animation checks visible in the foreground. Use desktop and narrow viewports for layout changes, and repeat relevant checks with reduced motion enabled.

## Standalone fixtures

Start Vite without the application API:

```sh
npm exec vite -- --host 127.0.0.1 --port 5173
```

These pages use local fixtures or mocks. They do not call model APIs or modify saved worlds. Voice fixtures simulate the microphone and connection; the refresh fixture temporarily uses the tab's session storage and provides cleanup.

| Page | What to exercise |
| --- | --- |
| [Comparison layout](http://127.0.0.1:5173/tests/browser/build-comparison-layout.html) | **Run layout checks**; iframe identity, layout transitions, height changes, and reduced motion |
| [Comparison pressure](http://127.0.0.1:5173/tests/browser/comparison-pressure.html) | Both pressure-check buttons at desktop and narrow widths; `?reduce` exercises reduced motion |
| [Desktop preview](http://127.0.0.1:5173/tests/browser/desktop-preview.html) | **Run desktop preview checks**; centered previews and transition geometry at different viewport sizes |
| [Presentation layout](http://127.0.0.1:5173/tests/browser/presentation-layout.html) | **Check layout** across blank, split-build, finished-world, and voice states |
| [Frame sizing](http://127.0.0.1:5173/tests/browser/frame-sizing.html) | Switch widths and scenes, grow or shrink content, and create a new revision; inspect scrolling and frame size |
| [Theme transition](http://127.0.0.1:5173/tests/browser/theme-transition.html) | **Run checks** with normal motion enabled; inspect the theme fade and final colors |
| [Seasonal contrast](http://127.0.0.1:5173/tests/browser/preset-seasons.html) | Read the checks that run on load for all six season/theme combinations |
| [Game runtime](http://127.0.0.1:5173/tests/browser/game-runtime.html) | Start games, switch between one and four games, change revision, and test simulated voice controls |
| [Raster painting](http://127.0.0.1:5173/tests/browser/paint-raster.html) | Draw at different resolutions and display scales, hold or reject saves, and reload the frame |
| [Painting service](http://127.0.0.1:5173/tests/browser/paint-service.html) | Use **Paint** inside the frame with completing and stalled mock streams; inspect status and saved marks |
| [Voice surface](http://127.0.0.1:5173/tests/browser/voice-surface.html) | **Run checks** for control discovery, forms, dialogs, stale controls, and confirmation behavior |
| [Voice navigation](http://127.0.0.1:5173/tests/browser/voice-navigation.html) | **Run navigation checks** for the app shell with mocked API and voice responses |
| [Voice reload](http://127.0.0.1:5173/tests/browser/voice-refresh.html) | **Prepare muted Live**, reload the tab, inspect the result, then **Finish and clean up** |

## Application fixtures with mocked APIs

The comparison fixture starts its own frontend on port 5190 and API on port 4391, using temporary data:

```sh
node tests/browser/build-activity-server.mjs
```

Open the [fixture app](http://127.0.0.1:5190), sign in as Mira, and submit `quick`. Try `standard first quick`, `standard fail`, `ultrafast fail`, and `cancel` to exercise completion order, independent failures, and cancellation. Add `estimate slow`, `estimate offline`, or `estimate small` to check progress estimation. Use `--natural-seeds` when starting the script to test fresh blank worlds and Nora's bundled board. Stop the script with Ctrl+C to remove its temporary data.

The following pages use that same server:

| Page | What to exercise |
| --- | --- |
| [Activity performance](http://127.0.0.1:5190/tests/browser/build-activity-performance.html) | **Run Activity checks** for stream rendering and scrolling |
| [Build speedometer](http://127.0.0.1:5190/tests/browser/build-speedometer.html) | Start the sample stream and run the animation alignment check; try each telemetry state |
| [Comparison voice controls](http://127.0.0.1:5190/tests/browser/inspection-panels.html) | Sign in as Mira, then **Run comparison voice checks** and each estimate case; repeat at a narrow width and with reduced motion |

For painting with the real application router and reducer but a mocked agent, run:

```sh
node tests/browser/painting-operations-server.mjs
```

Open the [painting fixture](http://127.0.0.1:5193/?space=iris), sign in as Iris, and use **Paint with words**. Try `paint the whole canvas green`, `shapes`, and `flood`. Add `slow` to exercise stopping a request. This server uses API port 4394, makes no external service calls, and removes temporary data when stopped.

## Bundled arcade fixture

Build the ignored fixture JSON, then start Vite as described above:

```sh
node scripts/build-arcade-fixture.mjs
```

Open the [arcade runtime fixture](http://127.0.0.1:5173/tests/browser/arcade-runtime.html). Test each game's controls, draft and published modes, revision changes, and frame removal. Add `?presentation` to inspect its presentation layout and use **Run layout checks**. The fixture builder makes no model calls and does not change saved worlds. Its optional `--prepared` flag reads the current saved Karen source instead of the bundled proposal.

## Optional real voice test

[live-smoke.html](live-smoke.html) runs the actual app and real model requests, using a synthetic microphone. It is separate from the mocks above and from the command-line `npm run test:live -- --confirm-api-usage` comparison test.

Use it only with an intentionally disposable app instance started by `npm run dev`, configured with a key that can use the voice and builder models. Open [the voice smoke page](http://127.0.0.1:5173/tests/browser/live-smoke.html), sign in, choose a local spoken audio file of at most 60 seconds, start **Go live**, and select **Play phrase into microphone**. Inspect captions, actions, and the fixture's event log. No test audio is bundled; use the file picker instead of the sample server-WAV path.

This test incurs API usage and can submit real builder requests and actions against that instance's saved worlds. End voice when finished. The synthetic microphone avoids recording hardware microphone input; it does not make API calls or resulting actions simulated.
