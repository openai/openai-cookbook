import test from 'node:test';
import assert from 'node:assert/strict';
import vm from 'node:vm';
import { build } from 'esbuild';

const compiled = await build({
  entryPoints: [new URL('../src/useWorkspaceFiles.ts', import.meta.url).pathname],
  bundle: true, write: false, format: 'iife', globalName: 'FilesHook',
  plugins: [{ name: 'files-hook-fixture', setup(builder) {
    builder.onResolve({ filter: /^react$/ }, () => ({ path: 'react', namespace: 'fixture' }));
    builder.onResolve({ filter: /^\.\/api$/ }, () => ({ path: 'api', namespace: 'fixture' }));
    builder.onLoad({ filter: /.*/, namespace: 'fixture' }, ({ path }) => ({
      contents: path === 'react'
        ? 'export const { useEffect, useMemo, useRef, useState } = globalThis.hooks;'
        : 'export const watchEvents = (...args) => globalThis.watchEvents(...args);',
    }));
  } }],
});

// Exercise actual hook callbacks across render/commit boundaries. The stream
// retains old callbacks deliberately, modeling network events arriving late.
function fixture() {
  const slots = []; const streams = [];
  let cursor = 0; let dirty = false; let pending = []; let latest; let props; let stateUpdates = 0;
  const changed = (before, after) => !before || before.length !== after.length || before.some((value, index) => !Object.is(value, after[index]));
  const context = vm.createContext({
    TextEncoder,
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
      latest = context.FilesHook.useWorkspaceFiles(props.path, props.expired);
      if (commit) {
        for (const { index, effect, deps } of pending) {
          slots[index]?.cleanup?.();
          slots[index] = { deps, cleanup: effect() };
        }
      }
    } while (commit && dirty);
    return latest;
  }
  return { render, streams, get stateUpdates() { return stateUpdates; }, unmount() { slots.forEach(slot => slot?.cleanup?.()); } };
}

const settings = (path = '/api/spaces/karen/files', expired = () => {}) => ({ path, expired });
const event = (content, sessionId = 'session-1', revisionId = 1) => ({
  id: 'event-1', time: '2026-09-21T12:00:00.000Z', type: 'files.snapshot', data: {
    sessionId, revisionId, status: 'streaming',
    files: ['space.js', 'tests.js'].map(path => ({ path, content, language: 'javascript', status: 'streaming', updatedAt: '2026-09-21T12:00:00.000Z' })),
  },
});

test('files receive one authoritative snapshot per batch and retain content during reconnect', () => {
  const f = fixture();
  const initial = f.render(settings());
  assert.equal(f.streams.length, 1);
  assert.equal(initial.snapshot, null);
  assert.equal(initial.connecting, true);
  const stream = f.streams[0];
  stream.connection(true);
  assert.equal(f.render().connected, true);
  const before = f.stateUpdates;
  stream.events([event('first'), event('latest')]);
  assert.equal(f.stateUpdates, before + 1);
  const snapshot = f.render().snapshot;
  assert.equal(snapshot.files[0].content, 'latest');
  stream.connection(false);
  assert.equal(f.render().snapshot, snapshot);
  assert.equal(f.render().connecting, true);
  stream.events([event('fresh reset', 'session-2', 1)]);
  assert.equal(f.render().snapshot.sessionId, 'session-2');
  assert.equal(f.render().snapshot.files[0].content, 'fresh reset');
  f.unmount();
  assert.equal(stream.stopped, true);
});

test('files never expose a prior space during navigation or accept its delayed callbacks', () => {
  const f = fixture();
  f.render(settings());
  const original = f.streams[0];
  original.events([event('Karen source')]);
  assert.equal(f.render().snapshot.files[0].content, 'Karen source');
  const next = settings('/api/spaces/james/files');
  assert.equal(f.render(next, false).snapshot, null);
  const before = f.stateUpdates;
  original.events([event('Late Karen')]); original.connection(true); original.expired();
  assert.equal(f.stateUpdates, before);
  assert.equal(f.render(next).snapshot, null);
  assert.equal(original.stopped, true);
  f.streams[1].events([event('James source')]);
  assert.equal(f.render().snapshot.files[0].content, 'James source');
  assert.equal(f.render(settings(), false).snapshot, null, 'returning to the same URL creates a new scope');
  original.events([event('Original callback')]);
  assert.equal(f.render(settings()).snapshot, null);
  f.unmount();
});

test('expiration clears files, uses the latest callback once, and unmounted accounts stay inert', () => {
  const f = fixture();
  let oldExpired = 0; let currentExpired = 0;
  f.render(settings(undefined, () => oldExpired++));
  const stream = f.streams[0];
  stream.events([event('private source')]);
  f.render(settings(undefined, () => currentExpired++));
  assert.equal(f.streams.length, 1, 'callback identity does not reconnect');
  stream.expired(); stream.expired();
  assert.equal(oldExpired, 0);
  assert.equal(currentExpired, 1);
  assert.equal(stream.stopped, true);
  const expired = f.render();
  assert.equal(expired.snapshot, null);
  assert.equal(expired.connecting, false);
  f.unmount();
  const updates = f.stateUpdates;
  stream.events([event('after sign-out')]); stream.connection(true); stream.expired();
  assert.equal(f.stateUpdates, updates);
  const replacement = fixture();
  assert.equal(replacement.render(settings()).snapshot, null);
  replacement.unmount();
});
