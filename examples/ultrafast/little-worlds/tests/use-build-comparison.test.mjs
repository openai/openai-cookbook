import test from 'node:test';
import assert from 'node:assert/strict';
import vm from 'node:vm';
import { build } from 'esbuild';

const compiled = await build({
  entryPoints: [new URL('../src/useBuildComparison.ts', import.meta.url).pathname],
  bundle: true, write: false, format: 'iife', globalName: 'ComparisonHook',
  plugins: [{ name: 'comparison-hook-fixture', setup(builder) {
    builder.onResolve({ filter: /^react$/ }, () => ({ path: 'react', namespace: 'fixture' }));
    builder.onResolve({ filter: /^\.\/api$/ }, () => ({ path: 'api', namespace: 'fixture' }));
    builder.onLoad({ filter: /.*/, namespace: 'fixture' }, ({ path }) => ({
      contents: path === 'react'
        ? 'export const { useEffect, useMemo, useRef, useState } = globalThis.hooks;'
        : 'export const watchEvents = (...args) => globalThis.watchEvents(...args); export const captureSessionApi = () => (...args) => globalThis.request(...args); export const ApiError = globalThis.ApiError;',
    }));
  } }],
});

// Exercise the production hook through render/commit/cleanup boundaries. Held
// transport callbacks represent already queued network events, including events
// arriving after navigation, permission changes, sign-out, or unmount.
function fixture(document) {
  const slots = [], streams = [], requests = [], timers = new Map();
  let nextTimer = 0;
  let cursor = 0, dirty = false, pending = [], latest, props, stateUpdates = 0;
  const changed = (before, after) => !before || before.length !== after.length || before.some((value, index) => !Object.is(value, after[index]));
  const context = vm.createContext({
    ...(document ? { document } : {}),
    ApiError: class ApiError extends Error { constructor(message, status) { super(message); this.status = status; } },
    setTimeout(callback, delay) { const id = ++nextTimer; timers.set(id, { callback, delay }); return id; },
    clearTimeout(id) { timers.delete(id); },
    hooks: {
      useRef(value) { const index = cursor++; return slots[index] ??= { current: value }; },
      useMemo(create, deps) {
        const index = cursor++;
        if (changed(slots[index]?.deps, deps)) slots[index] = { deps, value: create() };
        return slots[index].value;
      },
      useState(initial) {
        const index = cursor++;
        slots[index] ??= { value: typeof initial === 'function' ? initial() : initial };
        return [slots[index].value, update => {
          stateUpdates++;
          const value = typeof update === 'function' ? update(slots[index].value) : update;
          if (!Object.is(value, slots[index].value)) { slots[index].value = value; dirty = true; }
        }];
      },
      useEffect(effect, deps) {
        const index = cursor++;
        if (changed(slots[index]?.deps, deps)) pending.push({ index, effect, deps });
      },
    },
    watchEvents(path, events, connection, expired) {
      const stream = { path, events, connection, expired, stopped: false };
      streams.push(stream);
      return () => { stream.stopped = true; };
    },
    request(path) {
      return new Promise((resolve, reject) => requests.push({ path, resolve, reject }));
    },
  });
  vm.runInContext(compiled.outputFiles[0].text, context);
  function render(next = props, commit = true) {
    props = next;
    let remaining = 20;
    do {
      if (!remaining--) throw new Error('Unbounded hook render loop');
      cursor = 0; pending = []; dirty = false;
      latest = context.ComparisonHook.useBuildComparison(props.base, props.enabled, props.expired);
      if (commit) for (const { index, effect, deps } of pending) {
        slots[index]?.cleanup?.();
        slots[index] = { deps, cleanup: effect() };
      }
    } while (commit && dirty);
    return latest;
  }
  return {
    render, streams, requests, timers, ApiError: context.ApiError,
    watchPending: (...args) => context.ComparisonHook.watchPendingComparison(...args),
    tick() { for (const [id, timer] of [...timers]) { timers.delete(id); timer.callback(); } },
    get stateUpdates() { return stateUpdates; }, unmount() { slots.forEach(slot => slot?.cleanup?.()); },
  };
}

const settle = () => new Promise(resolve => setImmediate(resolve));

const settings = (base = '/api/spaces/karen', enabled = true, expired = () => {}) => ({ base, enabled, expired });
const comparison = (id, fields = {}) => ({
  id, primaryTurnId: `turn-${id}`, model: 'fixture-astra', reasoningEffort: 'low', startedAt: '2026-09-25T12:00:00Z', finished: false,
  ultrafast: { turnId: `ultrafast-${id}`, status: 'running', startedAt: '2026-09-25T12:00:00Z', outputTokens: 100 },
  standard: { turnId: `standard-${id}`, status: 'running', startedAt: '2026-09-25T12:00:00Z', outputTokens: 20 }, ...fields,
});
const event = value => ({ type: 'comparison.state', data: { comparison: value } });
const compactEvent = value => ({ type: 'comparison.state', data: { comparison: value, retainPreviews: true } });
const withPreviews = (id) => {
  const value = comparison(id);
  value.ultrafast.html = '<main>Ultrafast preview</main>';
  value.standard.html = '<main>Standard preview</main>';
  return value;
};

test('pending acceptance retries a failed refresh and resolves an authoritative null once', async () => {
  const f = fixture(), requests = [];
  let resolved = 0;
  const stop = f.watchPending('accepted', () => new Promise((resolve, reject) => requests.push({ resolve, reject })), () => resolved++);
  assert.equal(requests.length, 1, 'the first post-acceptance read starts immediately');
  assert.equal(f.timers.size, 0, 'no poll overlaps a pending read');
  requests[0].reject(new Error('offline')); await settle();
  assert.equal([...f.timers.values()][0].delay, 1500);
  f.tick();
  assert.equal(requests.length, 2);
  requests[1].resolve(null); await settle();
  assert.equal(resolved, 1);
  assert.equal(f.timers.size, 0);
  f.tick();
  assert.equal(requests.length, 2, 'successful reconciliation stops healthy polling');
  stop();
});

test('pending acceptance retries a mismatched comparison until the accepted id arrives', async () => {
  const f = fixture(), requests = [];
  let resolved = 0;
  const stop = f.watchPending('accepted', () => new Promise(resolve => requests.push(resolve)), () => resolved++);
  requests[0]({ id: 'previous' }); await settle();
  assert.equal(resolved, 0);
  assert.equal(f.timers.size, 1);
  f.tick(); requests[1]({ id: 'accepted' }); await settle();
  assert.equal(resolved, 1);
  assert.equal(f.timers.size, 0);
  stop();
});

test('changing the pending id or unmounting ignores late reads and clears retry timers', async () => {
  const f = fixture(), oldRequests = [], newRequests = [];
  let current = 'old';
  const stopOld = f.watchPending('old', () => new Promise(resolve => oldRequests.push(resolve)), () => { current = null; });
  stopOld(); current = 'new';
  const stopNew = f.watchPending('new', () => new Promise((resolve, reject) => newRequests.push({ resolve, reject })), () => { current = null; });
  oldRequests[0](null); await settle();
  assert.equal(current, 'new', 'late old-id resolution cannot clear a newer accepted build');
  assert.equal(f.timers.size, 0);
  newRequests[0].reject(new Error('offline')); await settle();
  assert.equal(f.timers.size, 1);
  stopNew();
  assert.equal(f.timers.size, 0, 'effect cleanup removes its pending retry');
  f.tick(); assert.equal(newRequests.length, 1);
});

test('an unmounted pending resolver never reschedules an in-flight failed read', async () => {
  const f = fixture(); let reject, resolved = 0;
  const stop = f.watchPending('accepted', () => new Promise((_, fail) => { reject = fail; }), () => resolved++);
  stop(); reject(new Error('late failure')); await settle();
  assert.equal(resolved, 0);
  assert.equal(f.timers.size, 0);
});

test('disabled visitors never connect and owners subscribe to the selected world only', () => {
  const f = fixture();
  const visitor = f.render(settings(undefined, false));
  assert.equal(visitor.comparison, null);
  assert.equal(visitor.connected, false);
  assert.equal(f.streams.length, 0);
  assert.equal(f.render(settings()).connected, false);
  assert.equal(f.streams.length, 1);
  assert.equal(f.streams[0].path, '/api/spaces/karen/comparison/events');
  f.streams[0].connection(true);
  assert.equal(f.render().connected, true);
  f.unmount();
});

test('each replay batch applies its latest comparison once and ignores unrelated events', () => {
  const f = fixture(); f.render(settings());
  const stream = f.streams[0];
  stream.connection(true);
  const before = f.stateUpdates;
  const latest = comparison('current', { standard: { status: 'completed', outputTokens: 120 } });
  stream.events([event(comparison('previous')), { type: 'keepalive' }, event(latest)]);
  assert.equal(f.stateUpdates, before + 1);
  assert.equal(f.render().comparison, latest);
  assert.equal(f.render().connected, true);
  const after = f.stateUpdates;
  stream.events([{ type: 'activity.reset' }, { type: 'comparison.state', data: {} }]);
  assert.equal(f.stateUpdates, after);
  assert.equal(f.render().comparison, latest);
  f.unmount();
});

test('compact telemetry preserves matching previews while replacing lane metadata', () => {
  const f = fixture(); f.render(settings());
  const initial = withPreviews('current');
  f.streams[0].events([event(initial)]);
  const next = comparison('current');
  next.ultrafast.outputTokens = 400;
  next.ultrafast.status = 'completed';
  next.standard.outputTokens = 95;
  f.streams[0].events([compactEvent(next)]);
  const value = f.render().comparison;
  assert.equal(value.ultrafast.html, initial.ultrafast.html);
  assert.equal(value.standard.html, initial.standard.html);
  assert.equal(value.ultrafast.outputTokens, 400);
  assert.equal(value.ultrafast.status, 'completed');
  assert.equal(value.standard.outputTokens, 95);
  assert.equal(Object.hasOwn(next.ultrafast, 'html'), false, 'incoming transport state is not mutated');
  f.unmount();
});

test('full previews and following compact updates in one batch render the newest preview once', () => {
  const f = fixture(); f.render(settings());
  f.streams[0].events([event(withPreviews('current'))]);
  const full = withPreviews('current');
  full.standard.html = '<main>Updated standard preview</main>';
  const compact = comparison('current');
  compact.standard.outputTokens = 220;
  const before = f.stateUpdates;
  f.streams[0].events([compactEvent(comparison('current')), event(full), { type: 'keepalive' }, compactEvent(compact)]);
  assert.equal(f.stateUpdates, before + 1);
  const value = f.render().comparison;
  assert.equal(value.ultrafast.html, full.ultrafast.html);
  assert.equal(value.standard.html, full.standard.html);
  assert.equal(value.standard.outputTokens, 220);
  f.unmount();
});

test('full snapshots clear omitted previews and explicit compact html takes precedence', () => {
  const f = fixture(); f.render(settings());
  f.streams[0].events([event(withPreviews('current')), event(comparison('current'))]);
  assert.equal(f.render().comparison.ultrafast.html, undefined);
  assert.equal(f.render().comparison.standard.html, undefined);
  f.streams[0].events([event(withPreviews('current'))]);
  const explicit = comparison('current');
  explicit.ultrafast.html = '';
  explicit.standard.html = '<main>Explicit replacement</main>';
  f.streams[0].events([compactEvent(explicit)]);
  assert.equal(f.render().comparison.ultrafast.html, '');
  assert.equal(f.render().comparison.standard.html, explicit.standard.html);
  f.unmount();
});

test('compact updates cannot retain previews across comparisons, lane turns, or absent IDs', () => {
  const f = fixture(); f.render(settings());
  const initial = withPreviews('current');
  const another = comparison('another');
  // Even a matching turn cannot carry a preview into another comparison.
  another.ultrafast.turnId = initial.ultrafast.turnId;
  f.streams[0].events([event(initial), compactEvent(another)]);
  assert.equal(f.render().comparison.ultrafast.html, undefined);
  assert.equal(f.render().comparison.standard.html, undefined);
  const changedTurn = comparison('current');
  changedTurn.standard.turnId = 'replacement-standard-turn';
  f.streams[0].events([event(initial), compactEvent(changedTurn)]);
  assert.equal(f.render().comparison.ultrafast.html, initial.ultrafast.html);
  assert.equal(f.render().comparison.standard.html, undefined);
  const withoutIds = withPreviews('current');
  delete withoutIds.ultrafast.turnId;
  const nextWithoutId = comparison('current');
  delete nextWithoutId.ultrafast.turnId;
  f.streams[0].events([event(withoutIds), compactEvent(nextWithoutId)]);
  assert.equal(f.render().comparison.ultrafast.html, undefined);
  assert.equal(f.render().comparison.standard.html, initial.standard.html);
  f.unmount();
});

test('failed or cancelled lanes never inherit previews from compact telemetry', () => {
  const f = fixture(); f.render(settings());
  const stopped = comparison('current');
  stopped.ultrafast.status = 'failed';
  stopped.standard.status = 'cancelled';
  f.streams[0].events([event(withPreviews('current')), compactEvent(stopped)]);
  assert.equal(f.render().comparison.ultrafast.html, undefined);
  assert.equal(f.render().comparison.standard.html, undefined);
  f.unmount();
});

test('null resets clear previews before later compact telemetry, including within one batch', () => {
  const f = fixture(); f.render(settings());
  f.streams[0].events([event(withPreviews('current')), compactEvent(null)]);
  assert.equal(f.render().comparison, null);
  f.streams[0].events([compactEvent(comparison('current'))]);
  assert.equal(f.render().comparison.ultrafast.html, undefined);
  f.streams[0].events([event(withPreviews('current')), event(null), compactEvent(comparison('current'))]);
  assert.equal(f.render().comparison.ultrafast.html, undefined);
  assert.equal(f.render().comparison.standard.html, undefined);
  f.unmount();
});

test('GET snapshots replace compact previews and stale GETs cannot override merged SSE', async () => {
  const f = fixture(); f.render(settings());
  f.requests[0].resolve({ comparison: withPreviews('current') }); await settle();
  f.streams[0].events([compactEvent(comparison('current'))]);
  assert.equal(f.render().comparison.standard.html, '<main>Standard preview</main>');
  let refresh = f.render().refreshComparison();
  f.requests[1].resolve({ comparison: comparison('current') }); await refresh;
  assert.equal(f.render().comparison.ultrafast.html, undefined);
  refresh = f.render().refreshComparison();
  const fresh = withPreviews('current');
  fresh.ultrafast.html = '<main>New preview</main>';
  f.streams[0].events([event(fresh), compactEvent(comparison('current'))]);
  f.requests[2].resolve({ comparison: null }); await refresh;
  assert.equal(f.render().comparison.ultrafast.html, fresh.ultrafast.html);
  f.unmount();
});

test('disconnect preserves the last comparison until reconnect replay replaces or clears it', () => {
  const f = fixture(); f.render(settings());
  const stream = f.streams[0], initial = comparison('initial');
  stream.connection(true); stream.events([event(initial)]);
  stream.connection(false);
  assert.equal(f.render().connected, false);
  assert.equal(f.render().comparison, initial);
  const completed = comparison('initial', { finished: true });
  stream.connection(true); stream.events([event(completed)]);
  assert.equal(f.render().connected, true);
  assert.equal(f.render().comparison, completed);
  stream.events([event(null)]);
  assert.equal(f.render().comparison, null, 'reset replay removes stale lanes');
  assert.equal(f.render().connected, true);
  f.unmount();
});

test('progress budgets and streamed counts survive reconnect without an older pending read resetting them', async () => {
  const f = fixture(); f.render(settings());
  const initial = withPreviews('progress');
  initial.progress = { status: 'pending' };
  f.requests[0].resolve({ comparison: initial }); await settle();
  const refresh = f.render().refreshComparison();
  const latest = comparison('progress', { progress: { status: 'ready', expectedOutputTokens: 4000 } });
  latest.ultrafast.outputTokens = 2000;
  latest.standard.outputTokens = 500;
  f.streams[0].events([compactEvent(latest)]);
  f.requests[1].resolve({ comparison: initial }); await refresh;
  let value = f.render().comparison;
  assert.equal(value.progress.expectedOutputTokens, 4000);
  assert.equal(value.ultrafast.outputTokens, 2000);
  assert.equal(value.standard.outputTokens, 500);
  assert.equal(value.standard.html, initial.standard.html);
  f.streams[0].connection(false);
  assert.equal(f.render().comparison.progress.status, 'ready');
  const replay = { ...latest, progress: { ...latest.progress }, standard: { ...latest.standard, outputTokens: 1400 } };
  f.streams[0].connection(true);
  f.streams[0].events([event(replay)]);
  value = f.render().comparison;
  assert.equal(value.progress.expectedOutputTokens, 4000);
  assert.equal(value.standard.outputTokens, 1400);
  const delayed = comparison('progress', { progress: { status: 'fallback', expectedOutputTokens: 9000 } });
  f.streams[0].events([compactEvent(delayed)]);
  value = f.render().comparison;
  assert.equal(value.progress.expectedOutputTokens, 4000, 'late budget changes cannot move the bars backwards');
  assert.equal(value.progress.status, 'ready');
  assert.equal(value.ultrafast.outputTokens, 2000, 'older telemetry cannot reduce cumulative output');
  assert.equal(value.standard.outputTokens, 1400);
  f.streams[0].events([compactEvent(comparison('progress', { progress: { status: 'pending' } }))]);
  assert.equal(f.render().comparison.progress.expectedOutputTokens, 4000, 'pending replay cannot discard an accepted budget');
  f.streams[0].events([event(comparison('next', { progress: { status: 'pending' } }))]);
  assert.equal(f.render().comparison.progress.expectedOutputTokens, undefined, 'a new build never inherits the previous budget');
  f.unmount();
});

test('same-turn active replays retain terminal outcomes and accept late cumulative output', () => {
  for (const status of ['completed', 'failed', 'cancelled']) {
    const f = fixture(); f.render(settings());
    const finished = comparison('finished');
    Object.assign(finished.ultrafast, { status, outputTokens: 0, endedAt: '2026-09-25T12:00:03Z' }, status === 'completed'
      ? { html: '<main>Finished world</main>' } : { error: 'Final outcome' });
    f.streams[0].events([event(finished)]);
    for (const activeStatus of ['preparing', 'running']) {
      const replay = withPreviews('finished');
      Object.assign(replay.ultrafast, { status: activeStatus, outputTokens: 800 });
      f.streams[0].events([compactEvent(replay)]);
      const lane = f.render().comparison.ultrafast;
      assert.equal(lane.status, status);
      assert.equal(lane.endedAt, finished.ultrafast.endedAt);
      assert.equal(lane.outputTokens, 800, 'late positive output survives an initially empty terminal snapshot');
      assert.equal(lane.html, finished.ultrafast.html, 'stale drafts cannot replace a published world or restore a failed draft');
      assert.equal(lane.error, finished.ultrafast.error);
      assert.equal(replay.ultrafast.status, activeStatus, 'incoming snapshots are not mutated');
    }
    const later = comparison('finished');
    Object.assign(later.ultrafast, { status, outputTokens: 1200 });
    f.streams[0].events([event(later)]);
    assert.equal(f.render().comparison.ultrafast.outputTokens, 1200, 'new terminal telemetry remains eligible');
    f.unmount();
  }
});

test('terminal outcome retention never crosses comparison or turn boundaries', () => {
  const f = fixture(); f.render(settings());
  const finished = comparison('finished');
  Object.assign(finished.standard, { status: 'completed', outputTokens: 1200, html: '<main>Old world</main>' });
  f.streams[0].events([event(finished)]);
  const otherTurn = comparison('finished');
  Object.assign(otherTurn.standard, { turnId: 'new-standard-turn', status: 'preparing', outputTokens: 0 });
  f.streams[0].events([compactEvent(otherTurn)]);
  assert.equal(f.render().comparison.standard.status, 'preparing');
  assert.equal(f.render().comparison.standard.outputTokens, 0);
  assert.equal(f.render().comparison.standard.html, undefined);
  f.streams[0].events([event(finished)]);
  const otherComparison = comparison('new');
  f.streams[0].events([compactEvent(otherComparison)]);
  assert.equal(f.render().comparison.standard.status, 'running');
  assert.equal(f.render().comparison.standard.outputTokens, 20);
  assert.equal(f.render().comparison.standard.html, undefined);
  f.unmount();
});

test('navigation hides old-world state before cleanup and ignores queued callbacks on both sides of commit', () => {
  const f = fixture(); let expired = 0;
  f.render(settings(undefined, true, () => expired++));
  const old = f.streams[0];
  old.connection(true); old.events([event(comparison('karen'))]);
  assert.equal(f.render().comparison.id, 'karen');
  const destination = settings('/api/spaces/james', true, () => expired++);
  const pending = f.render(destination, false);
  assert.equal(pending.comparison, null);
  assert.equal(pending.connected, false);
  const before = f.stateUpdates;
  old.events([event(comparison('late-karen'))]); old.connection(true); old.expired();
  assert.equal(f.stateUpdates, before);
  assert.equal(expired, 0);
  assert.equal(f.render(destination).comparison, null);
  assert.equal(old.stopped, true);
  f.streams[1].events([event(comparison('james'))]);
  assert.equal(f.render().comparison.id, 'james');
  assert.equal(f.render(settings(), false).comparison, null, 'returning to an old URL starts a new scope');
  old.events([event(comparison('very-late-karen'))]);
  assert.equal(f.render(settings()).comparison, null);
  assert.equal(f.streams.length, 3);
  f.unmount();
});

test('losing permission immediately hides state, stops the stream, and reconnects empty when restored', () => {
  const f = fixture(); let expired = 0;
  f.render(settings(undefined, true, () => expired++));
  const old = f.streams[0]; old.connection(true); old.events([event(comparison('owner'))]);
  assert.equal(f.render().comparison.id, 'owner');
  const hidden = f.render(settings(undefined, false), false);
  assert.equal(hidden.comparison, null);
  assert.equal(hidden.connected, false);
  const before = f.stateUpdates;
  old.events([event(comparison('late-owner'))]); old.connection(true); old.expired();
  assert.equal(f.stateUpdates, before);
  assert.equal(expired, 0);
  f.render(settings(undefined, false));
  assert.equal(old.stopped, true);
  assert.equal(f.render(settings()).comparison, null);
  assert.equal(f.streams.length, 2);
  f.unmount();
});

test('expiration uses the current callback once, stops connection, and ignores later events', () => {
  const f = fixture(); let oldExpired = 0, currentExpired = 0;
  f.render(settings(undefined, true, () => oldExpired++));
  const stream = f.streams[0];
  stream.connection(true);
  f.render(settings(undefined, true, () => currentExpired++));
  assert.equal(f.streams.length, 1, 'a new callback does not reconnect');
  stream.expired(); stream.expired();
  assert.equal(oldExpired, 0);
  assert.equal(currentExpired, 1);
  assert.equal(stream.stopped, true);
  assert.equal(f.render().connected, false);
  const before = f.stateUpdates;
  stream.events([event(comparison('after-expiry'))]); stream.connection(true); stream.expired();
  assert.equal(f.stateUpdates, before);
  assert.equal(currentExpired, 1);
  f.unmount();
});

test('unmounted streams stay inert and a new mount starts with no retained comparison', () => {
  const f = fixture(); let expired = 0;
  f.render(settings(undefined, true, () => expired++));
  const stream = f.streams[0]; stream.events([event(comparison('before-unmount'))]);
  f.unmount();
  assert.equal(stream.stopped, true);
  const before = f.stateUpdates;
  stream.events([event(comparison('after-unmount'))]); stream.connection(true); stream.expired();
  assert.equal(f.stateUpdates, before);
  assert.equal(expired, 0);
  const replacement = fixture();
  assert.equal(replacement.render(settings()).comparison, null);
  replacement.unmount();
});

test('initial and disconnected polling recovers state without overlapping GET requests', async () => {
  const f = fixture();
  f.render(settings());
  assert.equal(f.requests.length, 1);
  assert.equal(f.requests[0].path, '/api/spaces/karen/comparison');
  f.streams[0].connection(false);
  f.tick();
  assert.equal(f.requests.length, 1, 'a pending GET is shared with a scheduled poll');
  const initial = comparison('initial');
  f.requests[0].resolve({ comparison: initial });
  await settle();
  assert.equal(f.render().comparison, initial);
  assert.equal(f.render().connected, false, 'GET recovery does not pretend SSE is connected');
  assert.equal(f.timers.size, 1);
  assert.equal([...f.timers.values()][0].delay, 1500);
  f.tick();
  assert.equal(f.requests.length, 2);
  const complete = comparison('initial', { finished: true });
  f.requests[1].resolve({ comparison: complete });
  await settle();
  assert.equal(f.render().comparison, complete);
  f.streams[0].connection(true);
  assert.equal(f.timers.size, 0, 'connected SSE stops polling');
  f.unmount();
});

test('hidden comparison tabs do not replace paused event streams with background polling', async () => {
  const document = new EventTarget(); document.hidden = true;
  const f = fixture(document);
  f.render(settings());
  assert.equal(f.requests.length, 0);
  f.streams[0].connection(false);
  assert.equal(f.timers.size, 0);
  document.hidden = false; document.dispatchEvent(new Event('visibilitychange'));
  f.tick();
  assert.equal(f.requests.length, 1);
  f.requests[0].resolve({ comparison: comparison('visible') });
  await settle();
  assert.equal(f.timers.size, 1);
  document.hidden = true; document.dispatchEvent(new Event('visibilitychange'));
  assert.equal(f.timers.size, 0);
  assert.equal(f.render().comparison.id, 'visible', 'Retain the last visible snapshot while suspended');
  f.unmount();
  document.hidden = false; document.dispatchEvent(new Event('visibilitychange'));
  assert.equal(f.timers.size, 0, 'Unmount removes the visibility listener');
});

test('fresh SSE cannot be replaced by a delayed GET snapshot', async () => {
  const f = fixture(); f.render(settings());
  const fresh = comparison('fresh');
  f.streams[0].connection(true);
  f.streams[0].events([event(fresh)]);
  const observation = f.render().observation;
  f.requests[0].resolve({ comparison: comparison('stale') });
  await settle();
  assert.equal(f.render().comparison, fresh);
  assert.equal(f.render().observation, observation, 'ignored GET is not an authoritative observation');
  assert.equal(f.timers.size, 0);
  f.unmount();
});

test('explicit post-mutation refresh waits for earlier GET then requests a fresh snapshot', async () => {
  const f = fixture(); const state = f.render(settings());
  const refresh = state.refreshComparison();
  f.requests[0].resolve({ comparison: null });
  await settle();
  assert.equal(f.requests.length, 2, 'pre-mutation null is not returned as post-mutation state');
  const fresh = comparison('accepted');
  f.requests[1].resolve({ comparison: fresh });
  assert.equal(await refresh, fresh);
  assert.equal(f.render().comparison, fresh);
  assert.equal(f.render().observation, 2);
  f.unmount();
});

test('explicit refresh returns newer SSE when its own GET becomes stale', async () => {
  const f = fixture(); let state = f.render(settings());
  f.requests[0].resolve({ comparison: null }); await settle();
  f.streams[0].connection(true); state = f.render();
  const refresh = state.refreshComparison();
  const fresh = comparison('streamed');
  f.streams[0].events([event(fresh)]);
  f.requests[1].resolve({ comparison: null });
  assert.equal(await refresh, fresh);
  assert.equal(f.render().comparison, fresh);
  f.unmount();
});

test('polling retries transient failures and a null replay clears reset state', async () => {
  const f = fixture(); f.render(settings());
  f.requests[0].reject(new Error('offline')); await settle();
  assert.equal(f.timers.size, 1);
  f.tick();
  f.requests[1].resolve({ comparison: comparison('before-reset') }); await settle();
  assert.equal(f.render().comparison.id, 'before-reset');
  f.tick(); f.requests[2].resolve({ comparison: null }); await settle();
  assert.equal(f.render().comparison, null);
  f.unmount();
  assert.equal(f.timers.size, 0);
});

test('GET expiration stops both transports and only calls the latest expiry handler once', async () => {
  const f = fixture(); let count = 0;
  f.render(settings(undefined, true, () => count++));
  f.requests[0].reject(new f.ApiError('expired', 401)); await settle();
  assert.equal(count, 1);
  assert.equal(f.streams[0].stopped, true);
  assert.equal(f.timers.size, 0);
  f.streams[0].expired();
  assert.equal(count, 1);
  await assert.rejects(f.render().refreshComparison(), /no longer open/);
  f.unmount();
});

test('late GET and explicit refresh cannot update a navigated or unmounted scope', async () => {
  const f = fixture(); const first = f.render(settings());
  const refresh = first.refreshComparison();
  const rejected = assert.rejects(refresh, /no longer open/);
  f.render(settings('/api/spaces/james'));
  const before = f.stateUpdates;
  f.requests[0].resolve({ comparison: comparison('stale-karen') });
  await rejected; await settle();
  assert.equal(f.stateUpdates, before);
  assert.equal(f.render().comparison, null);
  f.unmount();
  f.requests[1].resolve({ comparison: comparison('late-james') }); await settle();
  assert.equal(f.stateUpdates, before);
  assert.equal(f.timers.size, 0);
});
