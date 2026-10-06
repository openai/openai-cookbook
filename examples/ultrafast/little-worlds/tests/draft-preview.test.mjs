import test from 'node:test';
import assert from 'node:assert/strict';
import { extractPartialSource, renderDraftSource, createDraftPreviewer } from '../server/draft-preview.mjs';
import { initialState, actors } from '../server/seed.mjs';

const source = (label = 'Three ideas') => `export const meta={title:'Draft',subtitle:'',accent:'#d6ee96'};
export function render(state,actor){return '<style>p{color:#23251f}</style><p>${label}: '+state.projects.length+'</p>'}
export function reduce(state){throw new Error('Draft actions must never run')}`;

test('partial JSON decoder only reads a root source field and preserves escapes', () => {
  const javascript = 'export const text = "Hello\\nworld";\n// café 😀 and / paths';
  const json = JSON.stringify({ summary: 'A fake "source":"ignore" property', source: javascript, tests: 'test content' });
  assert.deepEqual(extractPartialSource(json), { source: javascript, complete: true });
  assert.equal(extractPartialSource('{"summary":"fake \\"source\\":\\"text\\""'), null);
  assert.equal(extractPartialSource('{"nested":{"source":"not at root"}}'), null);
  for (let index = json.indexOf('"source":') + 10; index < json.length; index++) {
    const partial = extractPartialSource(json.slice(0, index));
    if (partial) assert.ok(javascript.startsWith(partial.source), `prefix ${index}`);
  }
});

test('decoder waits for split escape sequences without inventing characters', () => {
  assert.deepEqual(extractPartialSource('{"source":"hello\\'), { source: 'hello', complete: false });
  assert.deepEqual(extractPartialSource('{"source":"hello\\u00'), { source: 'hello', complete: false });
  assert.deepEqual(extractPartialSource('{"source":"hello\\u0061'), { source: 'helloa', complete: false });
  assert.deepEqual(extractPartialSource('{"source":"hello\\nworld'), { source: 'hello\nworld', complete: false });
  assert.equal(extractPartialSource('{"source":"bad\\x20'), null);
  assert.equal(extractPartialSource('{"source":"bad\\uXX'), null);
  assert.equal(extractPartialSource('{"source":"bad\nline'), null);
  assert.equal(extractPartialSource('{"source":42}'), null);
});

test('completed render previews from actual source before the reducer is finished', async () => {
  const full = source();
  const partial = full.slice(0, full.indexOf('export function reduce') + 31);
  const preview = await renderDraftSource(partial, initialState, actors.mira);
  assert.match(preview.html, /Three ideas: 3/);
  assert.ok(preview.renderedSourceCharacters < partial.length);
  assert.deepEqual(initialState.contributions, []);
});

test('incomplete or malformed renders fail quietly without a fabricated preview', async () => {
  assert.equal(await renderDraftSource("export const meta={title:'Draft',subtitle:'',accent:'#d6ee96'};export function render(){return '<p>unfinished", initialState, actors.mira), null);
  assert.equal(await renderDraftSource('invalid syntax { never()', initialState, actors.mira), null);
  const unsafe = source().replace("'<style>p{color:#23251f}</style><p>Three ideas: '", "'<script>alert(1)</script><p>'");
  assert.equal(await renderDraftSource(unsafe, initialState, actors.mira), null);
});

test('draft renderer never calls the reducer and keeps the host state untouched', async () => {
  const before = structuredClone(initialState);
  const preview = await renderDraftSource(source(), initialState, actors.mira);
  assert.match(preview.html, /Three ideas/);
  assert.deepEqual(initialState, before);
});

test('previews are throttled, deduplicated, bounded and suppressed after cancellation', async () => {
  let time = 0; let active = true; const events = [];
  const previewer = createDraftPreviewer({ getState: () => initialState, actor: actors.mira, emit: (event) => events.push(event), isActive: () => active, now: () => time, intervalMs: 10, minimumCharacters: 1, maxPreviews: 2 });
  const args = (label) => JSON.stringify({ source: source(label), tests: '', summary: '' });
  assert.equal(await previewer.consider(args('One')), true);
  assert.equal(await previewer.consider(args('Two')), false, 'rate limited');
  time = 20;
  assert.equal(await previewer.consider(args('One')), false, 'same source');
  assert.equal(await previewer.consider(args('Two')), true);
  time = 40;
  assert.equal(await previewer.consider(args('Three'), { force: true }), false, 'at most two frames in this test');
  assert.equal(events.length, 2);
  assert.equal(events[0].type, 'draft.preview'); assert.equal(events[0].data.actorId, 'mira');
  active = false;
  assert.equal(await previewer.consider(args('Cancelled'), { force: true }), false);
});

function gate() {
  let resolve;
  const promise = new Promise((done) => { resolve = done; });
  return { promise, resolve };
}

test('stream callbacks never wait for rendering and bursts keep only the latest queued source', async () => {
  const firstRender = gate(); const entered = gate(); const events = []; const rendered = [];
  let concurrent = 0; let peakConcurrent = 0;
  const previewer = createDraftPreviewer({
    getState: () => initialState, actor: actors.mira, emit: (event) => events.push(event), isActive: () => true,
    intervalMs: 0, minimumCharacters: 1, maxPreviews: 10,
    render: async (javascript) => {
      rendered.push(javascript); concurrent++; peakConcurrent = Math.max(peakConcurrent, concurrent);
      if (rendered.length === 1) { entered.resolve(); await firstRender.promise; }
      concurrent--;
      return { html: `<p>${javascript}</p>`, renderedSourceCharacters: javascript.length };
    },
  });
  assert.equal(previewer.schedule(JSON.stringify({ source: 'first' })), true);
  assert.equal(rendered.length, 0, 'even parsing/render startup is outside the stream callback');
  await entered.promise;
  for (let index = 0; index < 1000; index++) previewer.schedule(JSON.stringify({ source: `update-${index}` }));
  assert.deepEqual(rendered, ['first'], 'a thousand deltas do not start a thousand renders');
  const done = previewer.flush();
  firstRender.resolve();
  await done;
  assert.deepEqual(rendered, ['first', 'update-999']);
  assert.equal(peakConcurrent, 1);
  assert.equal(events.length, 2);
  assert.match(events.at(-1).data.html, /update-999/);
  assert.equal(events.at(-1).data.preview, true);
});

test('closing a previewer cancels queued work and suppresses an already running render', async () => {
  const release = gate(); const entered = gate(); const events = []; let renders = 0;
  const previewer = createDraftPreviewer({
    getState: () => initialState, actor: actors.mira, emit: (event) => events.push(event), isActive: () => true,
    intervalMs: 0, minimumCharacters: 1,
    render: async (_source, _state, _actor, { isActive }) => {
      renders++; entered.resolve(); await release.promise;
      assert.equal(isActive(), false, 'render cancellation reaches the isolated renderer');
      return { html: '<p>stale</p>' };
    },
  });
  previewer.schedule(JSON.stringify({ source: 'first' }));
  await entered.promise;
  previewer.schedule(JSON.stringify({ source: 'queued' }));
  previewer.close();
  release.resolve();
  await previewer.flush();
  assert.equal(renders, 1);
  assert.deepEqual(events, []);
  assert.equal(previewer.schedule(JSON.stringify({ source: 'after close' })), false);
});

test('discarding one model step permits a new step but never emits a stale draft', async () => {
  const release = gate(); const entered = gate(); const events = [];
  const previewer = createDraftPreviewer({
    getState: () => initialState, actor: actors.mira, emit: (event) => events.push(event), isActive: () => true,
    intervalMs: 0, minimumCharacters: 1,
    render: async (javascript) => {
      if (javascript === 'old') { entered.resolve(); await release.promise; }
      return { html: `<p>${javascript}</p>` };
    },
  });
  previewer.schedule(JSON.stringify({ source: 'old' }));
  await entered.promise;
  previewer.discard();
  previewer.schedule(JSON.stringify({ source: 'new' }));
  release.resolve();
  await previewer.flush();
  assert.deepEqual(events.map((event) => event.data.html), ['<p>new</p>']);
});

test('flush drains a throttled latest preview and renderer failures stay best effort', async () => {
  const events = [];
  const previewer = createDraftPreviewer({
    getState: () => initialState, actor: actors.mira, emit: (event) => events.push(event), isActive: () => true,
    intervalMs: 60_000, minimumCharacters: 1,
    render: async (javascript) => {
      if (javascript === 'bad') throw new Error('incomplete source');
      return { html: `<p>${javascript}</p>` };
    },
  });
  previewer.schedule(JSON.stringify({ source: 'bad' }));
  await previewer.flush();
  previewer.schedule(JSON.stringify({ source: 'latest' }));
  await previewer.flush();
  assert.deepEqual(events.map((event) => event.data.html), ['<p>latest</p>']);
  previewer.close();
});

test('coalesced previews remove slow rendering from the token consumption critical path', async (t) => {
  const delayMs = 20; const updates = 12;
  const make = (counter) => createDraftPreviewer({
    getState: () => initialState, actor: actors.mira, emit: () => {}, isActive: () => true,
    intervalMs: 0, minimumCharacters: 1, maxPreviews: updates,
    render: async (javascript) => {
      counter.renders++;
      await new Promise((resolve) => setTimeout(resolve, delayMs));
      return { html: `<p>${javascript}</p>` };
    },
  });
  const blocking = { renders: 0 }; const scheduled = { renders: 0 };
  const before = make(blocking); const after = make(scheduled);
  const started = performance.now();
  for (let index = 0; index < updates; index++) await before.consider(JSON.stringify({ source: `update-${index}` }));
  const blockingMs = performance.now() - started;
  const streamingStarted = performance.now();
  for (let index = 0; index < updates; index++) {
    after.schedule(JSON.stringify({ source: `update-${index}` }));
    await Promise.resolve();
  }
  const consumptionMs = performance.now() - streamingStarted;
  assert.equal(scheduled.renders, 1, 'all tokens are consumed while the first slow render is pending');
  await after.flush();
  const drainedMs = performance.now() - streamingStarted;
  assert.equal(blocking.renders, updates);
  assert.equal(scheduled.renders, 2, 'only the first and latest snapshots render');
  t.diagnostic(`12 deltas, ${delayMs} ms renderer: awaited=${blockingMs.toFixed(1)} ms; scheduled token consumption=${consumptionMs.toFixed(1)} ms; all previews drained=${drainedMs.toFixed(1)} ms`);
});
