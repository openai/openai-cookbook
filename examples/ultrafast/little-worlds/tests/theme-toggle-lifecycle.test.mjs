import test from 'node:test';
import assert from 'node:assert/strict';
import vm from 'node:vm';
import { build } from 'esbuild';

const compiled = await build({
  entryPoints: [new URL('../src/ThemeToggle.tsx', import.meta.url).pathname],
  bundle: true, write: false, format: 'iife', globalName: 'ThemeToggleModule', jsx: 'automatic',
  plugins: [{ name: 'theme-toggle-lifecycle-fixture', setup(builder) {
    builder.onResolve({ filter: /^(react|react\/jsx-runtime|react-dom|lucide-react)$/ }, ({ path }) => ({ path, namespace: 'fixture' }));
    builder.onLoad({ filter: /.*/, namespace: 'fixture' }, ({ path }) => ({ contents: {
      react: 'export const { useCallback, useEffect, useLayoutEffect, useRef, useState } = globalThis.hooks;',
      'react/jsx-runtime': 'export const jsx = (type, props) => ({ type, props }); export const jsxs = jsx;',
      'react-dom': 'export const flushSync = callback => globalThis.flush(callback);',
      'lucide-react': 'export const Moon = "moon", Sun = "sun";',
    }[path] }));
  } }],
});

// Run the component and its real transition coordinator while holding native
// snapshot callbacks so storage writes can be checked before and after capture.
function fixture(initial = null, { storageBlocked = false } = {}) {
  const slots = [], transitions = [], writes = [], listeners = new Map();
  const attributes = new Map();
  const root = {
    dataset: { theme: 'dark' }, style: {},
    setAttribute: (name, value) => attributes.set(name, value),
    removeAttribute: name => attributes.delete(name),
    hasAttribute: name => attributes.has(name),
  };
  let stored = initial, cursor = 0, pending = [], dirty = false, tree;
  const changed = (before, after) => !before || before.length !== after.length || before.some((value, index) => !Object.is(value, after[index]));
  const effect = (create, deps) => {
    const index = cursor++;
    if (changed(slots[index]?.deps, deps)) pending.push({ index, create, deps });
  };
  const view = {
    localStorage: {
      getItem(key) { if (storageBlocked) throw new Error('Storage denied'); assert.equal(key, 'little-worlds-theme'); return stored; },
      setItem(key, value) { if (storageBlocked) throw new Error('Storage denied'); writes.push({ key, value }); stored = value; },
    },
    addEventListener(name, listener) {
      if (!listeners.has(name)) listeners.set(name, new Set());
      listeners.get(name).add(listener);
    },
    removeEventListener(name, listener) { listeners.get(name)?.delete(listener); },
    matchMedia: () => ({ matches: false }),
    getComputedStyle: () => ({ backgroundColor: root.dataset.theme === 'dark' ? '#000000' : '#f7f8fa' }),
  };
  const document = {
    documentElement: root, defaultView: view, visibilityState: 'visible',
    querySelector: () => null,
    dispatchEvent: () => true,
    startViewTransition(update) {
      let finish;
      const transition = {
        update, skips: 0,
        ready: Promise.resolve(),
        finished: new Promise(resolve => { finish = resolve; }),
        finish: () => finish(),
        skipTransition() { this.skips++; },
      };
      transitions.push(transition);
      return transition;
    },
  };
  const context = vm.createContext({
    document, window: view, Event,
    hooks: {
      useRef(value) { return slots[cursor++] ??= { current: value }; },
      useState(initialValue) {
        const index = cursor++;
        slots[index] ??= { value: typeof initialValue === 'function' ? initialValue() : initialValue };
        return [slots[index].value, update => {
          const next = typeof update === 'function' ? update(slots[index].value) : update;
          if (!Object.is(next, slots[index].value)) { slots[index].value = next; dirty = true; }
        }];
      },
      useCallback(callback, deps) {
        const index = cursor++;
        if (changed(slots[index]?.deps, deps)) slots[index] = { value: callback, deps };
        return slots[index].value;
      },
      useEffect: effect,
      useLayoutEffect: effect,
    },
    flush(callback) { callback(); if (dirty) render(); },
  });
  vm.runInContext(compiled.outputFiles[0].text, context);
  function render() {
    let remaining = 10;
    do {
      assert.ok(remaining--, 'theme effects settle without a render loop');
      cursor = 0; pending = []; dirty = false;
      tree = context.ThemeToggleModule.default();
      for (const { index, create, deps } of pending) {
        slots[index]?.cleanup?.();
        slots[index] = { deps, cleanup: create() };
      }
    } while (dirty);
  }
  render();
  return {
    root, writes, transitions,
    get stored() { return stored; },
    get theme() { return tree.props['data-theme']; },
    get appTheme() { return context.ThemeToggleModule.readAppTheme(); },
    get storageListeners() { return listeners.get('storage')?.size ?? 0; },
    click() { tree.props.onClick(); },
    receive(value, key = 'little-worlds-theme') {
      stored = value;
      for (const listener of listeners.get('storage') ?? []) listener({ key, newValue: value });
    },
    unmount() { slots.forEach(slot => slot?.cleanup?.()); },
  };
}

const settle = () => new Promise(resolve => setImmediate(resolve));

test('mount restores the saved appearance without publishing a storage update', () => {
  const f = fixture('light');
  assert.equal(f.theme, 'light');
  assert.equal(f.root.dataset.theme, 'light');
  assert.equal(f.root.style.colorScheme, 'light');
  assert.deepEqual(f.writes, []);
  assert.equal(f.transitions.length, 0);
});

test('a local toggle publishes once immediately and never republishes during delayed capture', async () => {
  const f = fixture('dark');
  f.click();
  assert.deepEqual(f.writes, [{ key: 'little-worlds-theme', value: 'light' }]);
  assert.equal(f.stored, 'light');
  assert.equal(f.theme, 'dark');
  assert.equal(f.root.dataset.theme, 'dark');
  const transition = f.transitions[0];
  transition.update();
  assert.equal(f.theme, 'light');
  assert.equal(f.root.dataset.theme, 'light');
  transition.update();
  transition.finish();
  await settle();
  assert.deepEqual(f.writes, [{ key: 'little-worlds-theme', value: 'light' }]);
});

test('rapid toggles publish their requested choices without delayed callbacks overwriting storage', async () => {
  const f = fixture('dark');
  f.click();
  const first = f.transitions[0];
  f.click();
  const second = f.transitions[1];
  assert.equal(first.skips, 1);
  assert.deepEqual(f.writes.map(write => write.value), ['light', 'dark']);
  assert.equal(f.stored, 'dark', 'committing the first snapshot cannot republish its old choice');
  assert.equal(f.theme, 'light', 'the pending first choice is committed before the second capture');
  second.update();
  first.update();
  first.finish();
  second.finish();
  await settle();
  assert.equal(f.theme, 'dark');
  assert.equal(f.stored, 'dark');
  assert.deepEqual(f.writes.map(write => write.value), ['light', 'dark']);
});

test('storage changes and clearing storage update the appearance without rebroadcasting', async () => {
  const f = fixture('dark');
  f.receive('light');
  assert.equal(f.transitions.length, 1);
  assert.equal(f.theme, 'dark');
  assert.deepEqual(f.writes, []);
  f.transitions[0].update();
  f.transitions[0].finish();
  await settle();
  assert.equal(f.theme, 'light');
  assert.deepEqual(f.writes, []);

  f.receive(null, null);
  f.transitions[1].update();
  f.transitions[1].finish();
  await settle();
  assert.equal(f.theme, 'dark');
  assert.equal(f.root.dataset.theme, 'dark');
  assert.equal(f.stored, null, 'cleared storage remains cleared');
  assert.deepEqual(f.writes, []);
  f.receive(null, 'unrelated-preference');
  assert.equal(f.transitions.length, 2, 'unrelated storage events do not change the theme');
});

test('a remote choice supersedes a pending local capture without writing the stale local choice again', async () => {
  const f = fixture('dark');
  f.click();
  const local = f.transitions[0];
  f.receive('dark');
  const remote = f.transitions[1];
  assert.equal(local.skips, 1);
  assert.equal(f.stored, 'dark');
  assert.deepEqual(f.writes.map(write => write.value), ['light']);
  remote.update();
  local.update();
  local.finish();
  remote.finish();
  await settle();
  assert.equal(f.theme, 'dark');
  assert.equal(f.root.dataset.theme, 'dark');
  assert.equal(f.stored, 'dark');
  assert.deepEqual(f.writes.map(write => write.value), ['light']);
});

test('unmount removes the cross-tab storage listener', () => {
  const f = fixture();
  assert.equal(f.storageListeners, 1);
  f.unmount();
  assert.equal(f.storageListeners, 0);
  f.receive('light');
  assert.equal(f.transitions.length, 0);
  assert.deepEqual(f.writes, []);
});

test('build requests capture the latest chosen theme before, during, and after a palette fade', async () => {
  for (const storageBlocked of [false, true]) {
    const f = fixture('dark', { storageBlocked });
    assert.equal(f.appTheme, 'dark');
    f.click();
    assert.equal(f.root.dataset.theme, 'dark', 'native capture has not committed the light palette yet');
    assert.equal(f.appTheme, 'light', 'new build intent uses the selected light mode immediately');
    f.click();
    assert.equal(f.root.dataset.theme, 'light', 'the older capture commits before the replacement');
    assert.equal(f.appTheme, 'dark', 'the latest pending choice wins over the painted palette and storage');
    f.transitions.at(-1).update();
    for (const transition of f.transitions) transition.finish();
    await settle();
    assert.equal(f.appTheme, 'dark');
    f.click();
    f.transitions.at(-1).update();
    f.transitions.at(-1).finish();
    await settle();
    assert.equal(f.appTheme, 'light', 'the painted preference remains available even if storage is blocked');
  }
});
