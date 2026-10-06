import test from 'node:test';
import assert from 'node:assert/strict';
import vm from 'node:vm';
import { build } from 'esbuild';

const compiled = await build({
  entryPoints: [new URL('../src/useBuildActivity.ts', import.meta.url).pathname],
  bundle: true, write: false, format: 'iife', globalName: 'ActivityHook',
  plugins: [{ name: 'activity-hook-fixture', setup(builder) {
    builder.onResolve({ filter: /^react$/ }, () => ({ path: 'react', namespace: 'fixture' }));
    builder.onResolve({ filter: /^\.\/api$/ }, () => ({ path: 'api', namespace: 'fixture' }));
    builder.onLoad({ filter: /.*/, namespace: 'fixture' }, ({ path }) => ({
      contents: path === 'react'
        ? 'export const { useEffect, useMemo, useRef, useState } = globalThis.hooks;'
        : 'export const watchEvents = (...args) => globalThis.watchEvents(...args);',
    }));
  } }],
});

// Model only React's state/ref/effect lifecycle. The real hook and event merger
// execute unchanged; held callbacks stand in for network work arriving late.
function fixture(now = Date.now()) {
  const slots = []; const streams = [];
  let cursor = 0; let dirty = false; let pending = []; let latest; let props;
  let stateUpdates = 0;
  const changed = (before, after) => !before || before.length !== after.length || before.some((value, index) => !Object.is(value, after[index]));
  const context = vm.createContext({
    Date: class extends Date { static now() { return now; } },
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
  });
  vm.runInContext(compiled.outputFiles[0].text, context);
  function render(next = props, commit = true) {
    props = next;
    let remaining = 20;
    do {
      if (!remaining--) throw new Error('Unbounded hook render loop');
      cursor = 0; pending = []; dirty = false;
      latest = context.ActivityHook.useBuildActivity(props.path, props.enabled, props.expired);
      if (commit) {
        for (const { index, effect, deps } of pending) {
          slots[index]?.cleanup?.();
          slots[index] = { deps, cleanup: effect() };
        }
      }
    } while (commit && dirty);
    return latest;
  }
  return {
    render, streams,
    get stateUpdates() { return stateUpdates; },
    unmount() { slots.forEach(slot => slot?.cleanup?.()); },
  };
}

const settings = (path = '/api/spaces/karen/activity', enabled = true, expired = () => {}) => ({ path, enabled, expired });

// Filled with ordinary public activity events, not a separate hook-only format.
const event = (id, text) => ({
  id, time: '2026-09-21T12:00:00.000Z', type: 'activity.entry', title: text,
  data: { entryId: id, kind: 'tool', tool: 'apply_change', status: 'running', arguments: text },
});

test('each connection calibrates the speedometer clock from the fresh replay envelope', () => {
  const f = fixture(50_000);
  f.render(settings());
  f.streams[0].events([{ type: 'activity.reset', time: new Date(20_000).toISOString() }]);
  assert.equal(f.render().clockOffsetMs, -30_000);
  f.streams[0].events([event('tool', 'new output')]);
  assert.equal(f.render().clockOffsetMs, -30_000, 'older row timestamps do not change the clock');
  f.streams[0].events([{ type: 'activity.reset', time: new Date(60_000).toISOString() }]);
  assert.equal(f.render().clockOffsetMs, 10_000);
  assert.equal(f.render(settings('/api/spaces/another/activity'), false).clockOffsetMs, 0);
  f.unmount();
});

test('activity subscribes only while open, keeps a hidden snapshot, and merges each replay batch once', () => {
  const f = fixture();
  let state = f.render(settings(undefined, false));
  assert.equal(f.streams.length, 0);
  assert.equal(state.connected, false);
  assert.equal(state.connecting, false);
  state = f.render(settings());
  assert.equal(f.streams.length, 1);
  assert.equal(state.connecting, true);
  const stream = f.streams[0];
  stream.connection(true);
  assert.equal(f.render().connected, true);
  const before = f.stateUpdates;
  stream.events([event('a', 'First'), event('b', 'Second')]);
  assert.equal(f.stateUpdates, before + 1, 'one React update for an incoming batch');
  const entries = f.render().entries;
  assert.equal(entries.length, 2);
  state = f.render(settings(undefined, false));
  assert.equal(stream.stopped, true);
  assert.equal(state.entries, entries);
  assert.equal(state.connected, false);
  const hiddenUpdates = f.stateUpdates;
  stream.events([event('c', 'Late')]); stream.connection(true); stream.expired();
  assert.equal(f.stateUpdates, hiddenUpdates);
  state = f.render(settings());
  assert.equal(f.streams.length, 2);
  assert.equal(state.entries, entries, 'same-space content remains visible during reconnect');
  f.streams[1].events([{ type: 'activity.reset' }, event('b', 'Second replayed')]);
  assert.equal(f.render().entries.length, 1, 'the authoritative replay replaces retained history');
  f.unmount();
});

test('activity clears old-space entries immediately and ignores callbacks before and after effect cleanup', () => {
  const f = fixture();
  f.render(settings());
  const original = f.streams[0];
  original.events([event('a', 'Karen')]);
  assert.equal(f.render().entries.length, 1);
  const next = settings('/api/spaces/james/activity');
  assert.equal(f.render(next, false).entries.length, 0, 'render never exposes old entries before effects run');
  const before = f.stateUpdates;
  original.events([event('b', 'Late Karen')]); original.connection(true); original.expired();
  assert.equal(f.stateUpdates, before);
  assert.equal(f.render(next).entries.length, 0);
  assert.equal(original.stopped, true);
  f.streams[1].events([event('c', 'James')]);
  assert.equal(f.render().entries.length, 1);
  assert.equal(f.render(settings(), false).entries.length, 0, 'returning to a path gets a new scope');
  original.events([event('d', 'Old connection')]);
  assert.equal(f.render(settings()).entries.length, 0);
  f.unmount();
});

test('callback updates do not reconnect, expiration is delivered once, and unmounted sessions stay inert', () => {
  const f = fixture();
  let oldExpired = 0; let currentExpired = 0;
  f.render(settings(undefined, true, () => oldExpired++));
  const stream = f.streams[0];
  f.render(settings(undefined, true, () => currentExpired++));
  assert.equal(f.streams.length, 1);
  stream.expired(); stream.expired();
  assert.equal(oldExpired, 0);
  assert.equal(currentExpired, 1);
  assert.equal(stream.stopped, true);
  assert.equal(f.render().connecting, false);
  f.unmount();
  const updates = f.stateUpdates;
  stream.events([event('a', 'After sign-out')]); stream.connection(true); stream.expired();
  assert.equal(f.stateUpdates, updates);
  assert.equal(currentExpired, 1);
  const replacement = fixture();
  assert.equal(replacement.render(settings()).entries.length, 0, 'a new account mount starts empty');
  replacement.unmount();
});
