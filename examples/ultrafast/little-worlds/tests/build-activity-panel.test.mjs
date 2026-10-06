import test from 'node:test';
import assert from 'node:assert/strict';
import { createRequire } from 'node:module';
import { createElement } from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { build } from 'esbuild';

// Render the real component with React. CSS is verified in the browser; these
// checks cover content that must be available without expanding or filtering.
const compiled = await build({
  entryPoints: [new URL('../src/BuildActivityPanel.tsx', import.meta.url).pathname],
  bundle: true, write: false, platform: 'node', format: 'cjs', packages: 'external',
  jsx: 'automatic', loader: { '.css': 'empty' },
});
const module = { exports: {} };
new Function('module', 'exports', 'require', compiled.outputFiles[0].text)(module, module.exports, createRequire(import.meta.url));
const { BuildActivityPanel } = module.exports;

const time = '2026-09-21T12:00:00.000Z';
const entry = (overrides = {}) => ({
  id: 'write-1', time, turnId: 'turn-1', kind: 'tool', title: 'Writing a file',
  tool: 'apply_change', status: 'completed', ...overrides,
});
const render = (entries = [], props = {}) => renderToStaticMarkup(createElement(BuildActivityPanel, {
  entries, busy: false, connected: true, model: 'gpt-6-astra', tier: 'ultrafast', onClose() {}, ...props,
}));

test('a comparison lane shows only its own run while history retains earlier runs', () => {
  const entries = [
    entry({ id: 'earlier', turnId: 'earlier-turn', kind: 'message', text: 'Earlier generation', tool: undefined }),
    entry({ id: 'current', kind: 'message', text: 'Current generation', tool: undefined }),
  ];
  const comparison = render(entries, { embedded: true, turnId: 'turn-1' });
  assert.ok(comparison.includes('Current generation'));
  assert.ok(!comparison.includes('Earlier generation'));
  const starting = render(entries, { embedded: true, turnId: '__preparing__', busy: true });
  assert.ok(!starting.includes('Earlier generation'));
  assert.ok(!starting.includes('Current generation'));
  assert.ok(render(entries).includes('Earlier generation'));
});

test('continuous progress replaces phases only in the two comparison trackers', () => {
  const progress = { id: 'comparison-1', status: 'ready', expectedOutputTokens: 1000, outputTokens: 400, laneStatus: 'running' };
  for (const [tier, label] of [['ultrafast', 'Ultrafast'], ['standard', 'Standard']]) {
    const html = render([], { embedded: true, tier, comparisonProgress: progress });
    assert.match(html, /Build progress/);
    assert.match(html, new RegExp(`aria-label="${label} build progress"`));
    assert.match(html, /aria-valuenow="36"/);
    assert.ok(Math.abs(Number(html.match(/scaleX\(([^)]+)\)/)?.[1]) - .36) < .001);
    assert.doesNotMatch(html, /class="build-phases"|Build stages/);
    assert.doesNotMatch(plainText(html), /\d+%/);
  }
  assert.match(render([], { comparisonProgress: progress }), /class="build-phases"/);
  assert.doesNotMatch(render([], { comparisonProgress: progress }), /Build progress/);
  assert.match(render([], { embedded: true }), /class="build-phases"/);
});

test('comparison trackers show pending, terminal and measured progress independently', () => {
  const progress = { id: 'comparison-1', status: 'pending', outputTokens: 900, laneStatus: 'running' };
  const pending = render([], { embedded: true, comparisonProgress: progress });
  assert.match(pending, /data-progress-state="pending"/);
  assert.match(pending, /build-progress-highlight/);
  assert.doesNotMatch(pending, /aria-valuenow=/);
  const ready = { ...progress, status: 'fallback', expectedOutputTokens: 1000 };
  const completed = render([], { embedded: true, comparisonProgress: { ...ready, laneStatus: 'completed' } });
  assert.match(completed, /aria-valuenow="100"/);
  assert.match(completed, /data-progress-state="completed"/);
  for (const laneStatus of ['failed', 'cancelled']) {
    const stopped = render([], { embedded: true, comparisonProgress: { ...ready, laneStatus } });
    assert.match(stopped, /aria-valuenow="81"/);
    assert.doesNotMatch(stopped, /build-progress-highlight|data-progress-state="completed"/);
  }
});

test('comparison trackers calibrate Standard from the completed peer without changing Ultrafast', () => {
  const comparisonProgress = {
    id: 'comparison-1', status: 'ready', expectedOutputTokens: 2000,
    outputTokens: 600, laneStatus: 'running', completedReferenceTokens: 1000,
  };
  const standard = render([], { embedded: true, tier: 'standard', comparisonProgress });
  assert.match(standard, /data-progress-basis="ultrafast"/);
  assert.match(standard, /data-expected-output-tokens="1000"/);
  assert.match(standard, /aria-valuenow="54"/);
  const ultrafast = render([], { embedded: true, tier: 'ultrafast', comparisonProgress });
  assert.match(ultrafast, /data-progress-basis="estimate"/);
  assert.match(ultrafast, /data-expected-output-tokens="2000"/);
  assert.match(ultrafast, /aria-valuenow="27"/);
});

test('comparison progress reflects actual verification and publication events for that lane', () => {
  const comparisonProgress = {
    id: 'comparison-1', status: 'ready', expectedOutputTokens: 2000,
    outputTokens: 600, laneStatus: 'running', completedReferenceTokens: 1000,
  };
  const props = { embedded: true, tier: 'standard', turnId: 'turn-1', busy: true, comparisonProgress };
  const stages = [
    [{ tool: 'inspect_space' }, 54],
    [{ tool: 'apply_patch' }, 54],
    [{ tool: 'verify_workspace' }, 90],
    [{ tool: 'publish_revision' }, 97],
    [{ tool: undefined, kind: 'event', eventType: 'revision.published' }, 97],
  ];
  for (const [stage, progress] of stages) {
    const html = render([entry({ ...stage, status: 'running' })], props);
    assert.match(html, new RegExp(`aria-valuenow="${progress}"`));
    assert.doesNotMatch(html, /data-progress-state="completed"/);
    assert.doesNotMatch(html, /class="build-phases"|Build stages/);
  }
  const completed = render([entry({ tool: undefined, eventType: 'turn.completed' })], {
    ...props, comparisonProgress: { ...comparisonProgress, laneStatus: 'completed' },
  });
  assert.match(completed, /aria-valuenow="100"/);
  assert.match(completed, /data-progress-state="completed"/);

  const otherTurn = render([
    entry({ tool: 'apply_patch', status: 'running' }),
    entry({ id: 'old-verification', turnId: 'previous-turn', tool: 'verify_workspace' }),
    entry({ id: 'old-published', turnId: 'previous-turn', tool: undefined, eventType: 'revision.published' }),
  ], props);
  assert.match(otherTurn, /aria-valuenow="54"/, 'another turn cannot advance the current lane');
});

test('real milestones advance a comparison even when the estimator is still pending', () => {
  const comparisonProgress = { id: 'comparison-1', status: 'pending', outputTokens: 100, laneStatus: 'running' };
  for (const [tool, progress] of [['verify_workspace', 90], ['publish_revision', 97]]) {
    const html = render([entry({ tool, status: 'running' })], { embedded: true, tier: 'standard', comparisonProgress });
    assert.match(html, new RegExp(`aria-valuenow="${progress}"`));
    assert.match(html, /data-progress-state="active"/);
    assert.doesNotMatch(html, /build-progress-highlight/);
  }
});
const plainText = html => html.replace(/<[^>]+>/g, '').replace(/&(?:amp|lt|gt|quot|#x27|#39);/g, entity => ({
  '&amp;': '&', '&lt;': '<', '&gt;': '>', '&quot;': '"', '&#x27;': "'", '&#39;': "'",
}[entity]));
function preText(html, label) {
  const match = [...html.matchAll(/<pre\b([^>]*)>([\s\S]*?)<\/pre>/g)]
    .find(([, attributes]) => attributes.includes(`aria-label="${label}"`));
  assert.ok(match, `Expected visible output labelled ${label}`);
  return plainText(match[2]);
}

test('all generated code, arguments, and results are visible without disclosures', () => {
  const lines = Array.from({ length: 125 }, (_, index) => `const line_${String(index + 1).padStart(3, '0')} = ${index};`);
  const tests = 'assert.equal(line_125, 124);';
  const arguments_ = JSON.stringify({ source: lines.join('\n'), tests, summary: 'Keep every code line visible' });
  const result = JSON.stringify({ ok: true, message: 'Published the complete file' });
  const html = render([entry({ arguments: arguments_, result, durationMs: 428 })]);

  assert.doesNotMatch(html, /<(?:details|summary)\b/i, 'outputs must not be hidden in a disclosure');
  assert.doesNotMatch(plainText(html), /Show (?:all|latest) \d+ lines/);
  const code = preText(html, 'space.js generated code');
  for (const line of lines) assert.ok(code.includes(line), `Missing code line: ${line}`);
  assert.equal((code.match(/const line_\d{3} =/g) || []).length, 125);
  assert.equal((plainText(html).match(/const line_\d{3} =/g) || []).length, 125, 'source is rendered once, not repeated as escaped JSON');
  assert.ok(preText(html, 'tests.js generated code').includes(tests));
  assert.equal(plainText(html).split(tests).length - 1, 1, 'test code is also rendered once');
  assert.deepEqual(JSON.parse(preText(html, 'apply_change arguments')), { summary: 'Keep every code line visible' });
  assert.ok(preText(html, 'apply_change result').includes('Published the complete file'));
});

test('partial code and text appear while running, with later output rendered as it arrives', () => {
  const initial = [
    entry({ id: 'message-1', kind: 'message', tool: undefined, status: 'running', text: 'Preparing the new' }),
    entry({ status: 'running', arguments: '{"source":"const first = 1;\\nconst next' }),
  ];
  const first = render(initial, { busy: true });
  assert.ok(plainText(first).includes('Preparing the new'));
  assert.ok(preText(first, 'space.js generated code').includes('const first = 1;'));
  assert.ok(preText(first, 'space.js generated code').includes('const next'));
  assert.doesNotMatch(first, /aria-label="apply_change arguments"/, 'source-only output has no duplicate raw-JSON block');
  assert.equal(plainText(first).split('const next').length - 1, 1);

  const complete = render([
    { ...initial[0], status: 'completed', text: 'Preparing the new layout' },
    { ...initial[1], status: 'completed', arguments: JSON.stringify({ source: 'const first = 1;\nconst next = 2;' }), result: '{"verified":true}' },
  ]);
  assert.ok(plainText(complete).includes('Preparing the new layout'));
  assert.ok(preText(complete, 'space.js generated code').includes('const next = 2;'));
  assert.doesNotMatch(complete, /aria-label="apply_change arguments"/);
  assert.ok(preText(complete, 'apply_change result').includes('"verified": true')
    || preText(complete, 'apply_change result').includes('"verified":true'));
});

test('large streamed patch blocks preserve exact text, empty lines, and long lines across their boundaries', () => {
  const body = '*** Begin Patch\n*** Add File: space.js\n'
    + Array.from({ length: 160 }, (_, index) => `+const value_${index} = "A wrapped line with <tags>, ampersands &, and Unicode 🌍";\n${index % 7 === 0 ? '\n' : ''}`).join('')
    + '+' + 'long_source_line_'.repeat(600) + '\n*** End Patch';
  for (const suffix of ['', '\n', '\n\n']) {
    const source = body + suffix;
    const html = render([entry({ tool: 'apply_patch', inputFormat: 'patch', arguments: source, status: 'running' })]);
    assert.equal(preText(html, 'apply_patch arguments'), source, 'chunking must not add or remove any text or line breaks');
    assert.doesNotMatch(html, /<(?:details|summary)\b/i);
  }
});

test('write_file shows content once and retains its path and other arguments', () => {
  const content = 'export function render() {\n  return "updated layout";\n}';
  const html = render([entry({
    tool: 'write_file', arguments: JSON.stringify({ path: 'space.js', content, reason: 'Refresh the layout' }),
  })]);

  assert.ok(preText(html, 'space.js generated code').includes('return "updated layout";'));
  assert.equal(plainText(html).split('export function render()').length - 1, 1);
  assert.deepEqual(JSON.parse(preText(html, 'write_file arguments')), { path: 'space.js', reason: 'Refresh the layout' });
});

test('apply_patch shows each replacement once and retains paths, search snippets, and metadata', () => {
  const edits = [
    { path: 'space.js', search: 'const color = "blue";', replace: 'const color = "green";\nconst changed = true;' },
    { path: 'tests.js', search: 'assert.equal(color, "blue");', replace: 'assert.equal(color, "green");' },
  ];
  const html = render([entry({ tool: 'apply_patch', arguments: JSON.stringify({ edits, summary: 'Change the color and its check' }) })]);

  for (const [index, edit] of edits.entries()) {
    const code = preText(html, `${edit.path} · edit ${index + 1} generated code`);
    for (const line of edit.replace.split('\n')) {
      assert.ok(code.includes(line));
      assert.equal(plainText(html).split(line).length - 1, 1, 'replacement is not repeated in metadata');
    }
  }
  assert.deepEqual(JSON.parse(preText(html, 'apply_patch arguments')), {
    edits: edits.map(({ path, search }) => ({ path, search })),
    summary: 'Change the color and its check',
  });
});

test('request, response, code, arguments, and result markup remain inert text', () => {
  const source = 'const html = "<img src=x onerror=alert(1)>";\n// </code><script>unsafe()</script>';
  const payload = '<iframe src="javascript:unsafe()"></iframe> & "quoted"';
  const html = render([
    entry({ id: 'request-1', kind: 'request', tool: undefined, text: payload }),
    entry({ id: 'message-1', kind: 'message', tool: undefined, text: '<script>response()</script>' }),
    entry({ arguments: JSON.stringify({ source, summary: payload }), result: payload }),
  ]);

  assert.doesNotMatch(html, /<(?:script|iframe|img)\b/i, 'streamed content cannot create executable markup');
  assert.ok(plainText(html).includes(payload));
  assert.ok(plainText(html).includes('<script>response()</script>'));
  assert.ok(preText(html, 'space.js generated code').includes('<img src=x onerror=alert(1)>'));
  assert.ok(preText(html, 'space.js generated code').includes('</code><script>unsafe()</script>'));
  assert.ok(preText(html, 'apply_change arguments').includes('<iframe'));
  assert.equal(preText(html, 'apply_change result'), payload);
});

test('native Codex patches stream verbatim once and remain inert text', () => {
  const patch = '*** Begin Patch\n*** Update File: space.js\n@@\n-old\n+<script>inert()</script>\n*** End Patch';
  for (const input of [patch.slice(0, -18), patch]) {
    const html = render([entry({ tool: 'apply_patch', inputFormat: 'patch', status: 'running', arguments: input })], { busy: true });
    assert.equal(preText(html, 'apply_patch arguments'), input);
    assert.equal(plainText(html).split('*** Begin Patch').length - 1, 1);
    assert.doesNotMatch(html, /generated code|<(?:details|script)\b/i);
  }
});

test('the compact panel retains model, tier, elapsed time, and a passive auto-scroll indicator', () => {
  const html = render([
    entry({ kind: 'request', tool: undefined, text: 'Update the tile' }),
    entry({ id: 'finished', kind: 'event', tool: undefined, time: '2026-09-21T12:00:02.500Z', title: 'Build completed', eventType: 'turn.completed' }),
  ]);
  const text = plainText(html);
  assert.ok(text.includes('gpt-6-astra'));
  assert.ok(text.includes('ultrafast'));
  assert.ok(text.includes('2.5s'));
  assert.ok(text.includes('Auto-scroll'));
  assert.doesNotMatch(html, /<button\b[^>]*>[\s\S]*?(?:Auto-scroll|Following live|Follow live)[\s\S]*?<\/button>/,
    'following the live stream cannot be disabled by an activity-panel control');
  assert.doesNotMatch(text, /Following live|Follow live/);
  for (const state of [html, render()]) {
    assert.doesNotMatch(plainText(state), /Behind the build|A look inside|A little window into the work|as your space takes shape/i);
  }
});

test('comparison streams have distinct landmarks and identifiers while default overlay keeps its target', () => {
  const props = { entries: [], busy: false, connected: true, embedded: true, onClose() {} };
  const html = renderToStaticMarkup(createElement('div', null,
    createElement(BuildActivityPanel, { ...props, label: 'Ultrafast activity' }),
    createElement(BuildActivityPanel, { ...props, label: 'Standard activity' }),
  ));
  const ids = [...html.matchAll(/<aside id="([^"]+)"/g)].map(match => match[1]);
  assert.equal(ids.length, 2);
  assert.equal(new Set(ids).size, 2, 'independent streams cannot share an element ID');
  assert.equal((html.match(/class="build-activity-panel is-embedded"/g) || []).length, 2);
  for (const lane of ['Ultrafast', 'Standard']) {
    assert.match(html, new RegExp(`aria-label="${lane} activity"`));
    assert.match(html, new RegExp(`aria-label="${lane} activity stream"`));
    assert.ok(plainText(html).includes(`${lane} activity: Ready.`));
  }
  assert.match(render(), /<aside id="build-activity-panel" class="build-activity-panel"/);
  assert.match(render([], { embedded: true, id: 'comparison-fast', label: 'Ultrafast activity' }), /<aside id="comparison-fast"/);
});

test('the third inline metric is an estimated live speedometer, not a tool counter', () => {
  const now = Date.now();
  const html = render([entry({ kind: 'event', tool: undefined, eventType: 'model.started', status: 'running',
    throughput: { tokens: 1648, durationMs: 2000, rate: 824, sampledAt: now, lastDeltaAt: now, state: 'streaming', estimated: true },
  })], { busy: true });
  assert.match(html, /data-rate="824" data-mode="streaming"/);
  assert.match(plainText(html), /≈824live tps/);
  assert.match(html, /Estimated with a local tokenizer/);
  assert.doesNotMatch(plainText(html), /tool calls/);
  assert.match(plainText(html), /elapsed/);
  assert.match(plainText(html), /output chars/);
});

test('completed speed is labelled average and missing historical telemetry has no invented speed', () => {
  const completed = render([entry({ id: 'start', kind: 'request', tool: undefined, eventType: 'turn.started' }), entry({ kind: 'event', tool: undefined, eventType: 'model.started',
    throughput: { tokens: 1200, durationMs: 2000, rate: 0, sampledAt: 50_000, lastDeltaAt: 50_000, state: 'complete', estimated: true },
  })]);
  assert.match(completed, /data-rate="600" data-mode="complete"/);
  assert.match(plainText(completed), /avg tps/);
  const missing = render([entry({ kind: 'event', tool: undefined, eventType: 'model.started' })]);
  assert.match(missing, /data-rate="" data-mode="unavailable"/);
});

test('server clock calibration keeps live readings fresh when the browser clock differs', () => {
  const serverTime = Date.now() - 60_000;
  const html = render([entry({ kind: 'event', tool: undefined, eventType: 'model.started', status: 'running',
    throughput: { tokens: 900, durationMs: 1000, rate: 900, sampledAt: serverTime, lastDeltaAt: serverTime, state: 'streaming', estimated: true },
  })], { busy: true, clockOffsetMs: -60_000 });
  assert.match(html, /data-rate="900" data-mode="streaming"/);
});

test('selecting a saved request highlights only its rows and offers a return to the live stream', () => {
  const selectedTurn = { id: 'turn-1', message: 'Update the first tile', startedAt: time, status: 'completed' };
  const html = render([
    entry({ id: 'request-1', kind: 'request', tool: undefined, eventType: 'turn.started', text: selectedTurn.message }),
    entry({ id: 'finished-1', kind: 'event', tool: undefined, time: '2026-09-21T12:00:02.500Z', title: 'Build completed', eventType: 'turn.completed' }),
    entry({ id: 'request-2', turnId: 'turn-2', kind: 'request', tool: undefined, status: 'completed', text: 'Another build is running' }),
    entry({ id: 'write-2', turnId: 'turn-2', status: 'running', text: 'Still writing the new tile' }),
  ], { busy: true, selectedTurn, onReturnToLive() {} });

  const rows = [...html.matchAll(/<li\b([^>]*)data-activity-entry="([^"]+)"([^>]*)>/g)];
  assert.equal(rows.length, 4);
  assert.ok(rows.filter(([, , id]) => id.endsWith('-1')).every(match => match[0].includes('is-selected')));
  assert.ok(rows.filter(([, , id]) => id.endsWith('-2')).every(match => !match[0].includes('is-selected')));
  assert.ok(plainText(html).includes('2.5s'), 'the metrics describe the selected request, not the running build');
  assert.match(html, /<button\b[^>]*class="build-return-live"[^>]*>[\s\S]*?Return to live<\/button>/);
  assert.doesNotMatch(plainText(html), /Auto-scroll|Full output is no longer available/);
  assert.ok(plainText(html).includes('Still writing the new tile'), 'live rows remain available while inspecting history');
});

test('uncaptured requests expose saved lifecycle details without implying their full output was kept', () => {
  const selectedTurn = { id: 'old-turn', message: 'Make the original tile blue', startedAt: time, status: 'completed' };
  const savedEvents = [
    { id: 'event-1', turnId: 'old-turn', type: 'tool.completed', time: '2026-09-21T12:00:01.000Z', title: 'Checked the tile', data: { tool: 'verify_workspace', checks: [{ name: 'Tile responds to input', ok: true }] } },
    { id: 'event-2', turnId: 'old-turn', type: 'turn.completed', time: '2026-09-21T12:00:03.500Z', title: 'The tile is ready' },
  ];
  const html = render([entry({ turnId: 'current-turn' })], { selectedTurn, savedEvents, onReturnToLive() {} });
  assert.ok(plainText(html).includes(selectedTurn.message));
  assert.ok(plainText(html).includes('Full output is no longer available. Showing saved activity.'));
  assert.ok(plainText(html).includes('Tile responds to input'));
  assert.ok(plainText(html).includes('3.5s'));
  assert.ok(plainText(html).includes('The tile is ready'));
  assert.match(html, /data-activity-turn="old-turn"[^>]*is-selected/);
  assert.doesNotMatch(html, /aria-label="space\.js generated code"/);
});

test('requests without any captured or saved events retain their prompt and honest availability state', () => {
  const selectedTurn = { id: 'missing-turn', message: 'Preserve this saved request <script>inert()</script>', startedAt: time, status: 'completed' };
  const html = render([], { selectedTurn, onReturnToLive() {} });
  assert.ok(plainText(html).includes(selectedTurn.message));
  assert.ok(plainText(html).includes('Activity output is no longer available. Showing the saved request.'));
  assert.doesNotMatch(html, /<script\b/);

  const connecting = render([], { selectedTurn, connected: false, connecting: true, onReturnToLive() {} });
  assert.ok(plainText(connecting).includes('Loading activity…'));
  assert.doesNotMatch(plainText(connecting), /no longer available/);
});

test('a partially retained turn restores its original request without duplicating its surviving output', () => {
  const selectedTurn = { id: 'turn-1', message: 'Create the original tile', startedAt: time, status: 'completed' };
  const retained = [
    entry({ id: 'write-tail', time: '2026-09-21T12:00:01.000Z', arguments: JSON.stringify({ source: 'const retained = true;' }) }),
    entry({ id: 'followup-tail', time: '2026-09-21T12:00:02.000Z', kind: 'request', tool: undefined, eventType: 'message', text: 'Also make it blue' }),
    entry({ id: 'finished-tail', time: '2026-09-21T12:00:03.000Z', kind: 'event', tool: undefined, eventType: 'turn.completed', title: 'Retained completion' }),
  ];
  const savedEvents = [{ id: 'finish', turnId: selectedTurn.id, type: 'turn.completed', time: '2026-09-21T12:00:03.000Z', title: 'Retained completion' }];
  const html = render(retained, { selectedTurn, savedEvents, onReturnToLive() {} });

  const rowIds = [...html.matchAll(/data-activity-entry="([^"]+)"/g)].map(match => match[1]);
  assert.deepEqual(rowIds, ['saved-request:turn-1', 'write-tail', 'followup-tail', 'finished-tail']);
  assert.ok(plainText(html).includes('Earlier output is no longer available. Showing the saved request and retained activity.'));
  assert.equal(plainText(html).split(selectedTurn.message).length - 1, 1);
  assert.equal(plainText(html).split('Retained completion').length - 1, 1);
  assert.ok(preText(html, 'space.js generated code').includes('const retained = true;'));
  assert.ok(plainText(html).includes('Also make it blue'), 'a surviving follow-up does not stand in for the missing initial request');

  const live = render(retained);
  assert.doesNotMatch(plainText(live), /Earlier output is no longer available|Create the original tile/);
});
