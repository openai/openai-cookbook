import test from 'node:test';
import assert from 'node:assert/strict';
import vm from 'node:vm';
import { build } from 'esbuild';

const compiled = await build({
  entryPoints: [new URL('../src/BuildComparison.tsx', import.meta.url).pathname],
  bundle: true, write: false, format: 'iife', globalName: 'Comparison', jsx: 'automatic',
  loader: { '.css': 'empty' },
  plugins: [{ name: 'comparison-lifecycle-fixture', setup(builder) {
    builder.onResolve({ filter: /^(react|react\/jsx-runtime|react-dom|gsap|lucide-react)$/ }, ({ path }) => ({ path, namespace: 'fixture' }));
    builder.onLoad({ filter: /.*/, namespace: 'fixture' }, ({ path }) => ({ contents: {
      react: 'export const { useId, useRef, useState, useLayoutEffect } = globalThis.hooks;',
      'react/jsx-runtime': 'export const jsx = (type, props) => ({type, props}); export const jsxs = jsx;',
      'react-dom': 'export const flushSync = callback => globalThis.flush(callback);',
      gsap: 'export const gsap = globalThis.motion;',
      'lucide-react': 'export const ChevronLeft = "left", ChevronRight = "right", LoaderCircle = "spinner";',
    }[path] }));
  } }],
});

const BEFORE_THEME_CHANGE = 'little-worlds:before-theme-change';

// Exercise the real component's update/cleanup logic while independently holding
// browser snapshot callbacks. DOM geometry and visuals are covered in the browser
// fixture; these tests target races that are difficult to reproduce by clicking.
function fixture({ active = false, native = true, reduce = false, narrow = false } = {}) {
  const slots = [], nodes = new Map(), microtasks = [], frames = [];
  const transitions = [], tweens = [], layouts = [], phases = [], scrolls = [];
  const listeners = new Map(), documentListeners = new Map(), preferenceListeners = new Set();
  let cursor = 0, pending = [], dirty = false, tree, reduced = reduce, mounted = true;
  let stateUpdates = 0;
  const props = {
    active, ultrafast: { status: 'running' }, standard: { status: 'running' },
    children: { type: 'iframe', props: { id: 'primary' } },
    onLayoutChange: split => layouts.push(split), onTransitionChange: busy => phases.push(busy),
  };
  const changed = (before, after) => !before || before.length !== after.length || before.some((value, index) => !Object.is(value, after[index]));
  const makeNode = () => ({
    attributes: new Map(), style: {}, inertAncestor: false,
    setAttribute(name, value) { this.attributes.set(name, value); },
    removeAttribute(name) { this.attributes.delete(name); },
    closest() { return this.inertAncestor ? {} : null; },
  });
  const document = {
    documentElement: makeNode(),
    addEventListener(name, listener) {
      if (!documentListeners.has(name)) documentListeners.set(name, new Set());
      documentListeners.get(name).add(listener);
    },
    removeEventListener(name, listener) { documentListeners.get(name)?.delete(listener); },
    dispatchEvent(event) {
      for (const listener of [...documentListeners.get(event.type) ?? []]) listener(event);
      return true;
    },
  };
  if (native) document.startViewTransition = update => {
    if (native === 'throws') throw new Error('Snapshot capture could not start');
    let done;
    const transition = {
      started: false, skipped: 0,
      ready: Promise.resolve(), finished: new Promise(resolve => { done = resolve; }),
      invoke() {
        if (!this.started) { this.started = true; this.updated = Promise.resolve(update()); }
        return this.updated;
      },
      complete() { return this.invoke().then(() => done()); },
      skipTransition() { this.skipped++; void this.complete(); },
    };
    transitions.push(transition);
    return transition;
  };
  const clearStyle = (node, fields) => fields?.split(',').forEach(field => {
    delete node.style[field];
    if (field === 'transform') delete node.style.y;
  });
  const context = vm.createContext({
    document,
    window: {
      matchMedia: query => ({ get matches() { return query === '(prefers-reduced-motion: reduce)' ? reduced : query === '(max-width: 700px)' ? narrow : false; }, addEventListener: (_, fn) => preferenceListeners.add(fn), removeEventListener: (_, fn) => preferenceListeners.delete(fn) }),
      addEventListener: (name, fn) => listeners.set(name, fn),
      removeEventListener: (name, fn) => { if (listeners.get(name) === fn) listeners.delete(name); },
      scrollTo: position => scrolls.push(position),
    },
    queueMicrotask: fn => microtasks.push(fn),
    requestAnimationFrame: fn => frames.push(fn),
    setTimeout, clearTimeout,
    hooks: {
      useId() { return 'lifecycle'; },
      useRef(initial) { return slots[cursor++] ??= { current: initial }; },
      useState(initial) {
        const index = cursor++;
        slots[index] ??= { value: typeof initial === 'function' ? initial() : initial };
        return [slots[index].value, update => {
          stateUpdates++;
          const next = typeof update === 'function' ? update(slots[index].value) : update;
          if (!Object.is(next, slots[index].value)) { slots[index].value = next; dirty = true; }
        }];
      },
      useLayoutEffect(effect, deps) {
        const index = cursor++;
        if (changed(slots[index]?.deps, deps)) pending.push({ index, effect, deps });
      },
    },
    flush(callback) { callback(); if (dirty && mounted) render(); },
    motion: {
      fromTo(node, from, to) {
        Object.assign(node.style, from);
        const tween = {
          killed: false,
          kill() { this.killed = true; },
          progress(value) { if (value === 1 && !this.killed) { clearStyle(node, to.clearProps); to.onComplete?.(); } },
        };
        tweens.push(tween);
        return tween;
      },
      set(node, values) { clearStyle(node, values.clearProps); },
    },
  });
  vm.runInContext(compiled.outputFiles[0].text, context);
  function commitRefs(element) {
    if (!element || typeof element !== 'object') return;
    if (Array.isArray(element)) { element.forEach(commitRefs); return; }
    const { props: properties } = element;
    if (!properties) return;
    if (properties.ref) {
      const name = properties.className;
      const node = nodes.get(name) || makeNode();
      nodes.set(name, node);
      properties.ref.current = node;
      for (const [key, value] of Object.entries(properties)) if (key.startsWith('data-')) node.attributes.set(key, value);
    }
    commitRefs(properties.children);
  }
  function render(changes = {}) {
    Object.assign(props, changes);
    let remaining = 15;
    do {
      assert.ok(remaining--, 'component does not loop while committing');
      cursor = 0; pending = []; dirty = false;
      tree = context.Comparison.default(props);
      commitRefs(tree);
      for (const { index, effect, deps } of pending) {
        slots[index]?.cleanup?.();
        slots[index] = { deps, effect, cleanup: effect() };
      }
    } while (dirty);
    return tree;
  }
  render();
  return {
    render, transitions, tweens, layouts, phases, scrolls, nodes, frames,
    get split() { return tree.props['data-comparing']; },
    get stateUpdates() { return stateUpdates; },
    get marker() { return document.documentElement.attributes.get('data-world-transition'); },
    get themeListenerCount() { return documentListeners.get(BEFORE_THEME_CHANGE)?.size ?? 0; },
    runQueued() { while (microtasks.length) microtasks.shift()(); },
    reduceSilently() { reduced = true; },
    resize() { listeners.get('resize')?.(); },
    themeChange() { document.dispatchEvent({ type: BEFORE_THEME_CHANGE }); },
    replayMountEffects() { slots.forEach(slot => slot?.cleanup?.()); slots.forEach(slot => { if (slot?.effect) slot.cleanup = slot.effect(); }); },
    unmount() { mounted = false; slots.forEach(slot => slot?.cleanup?.()); },
  };
}

const settle = () => new Promise(resolve => setImmediate(resolve));

test('initial comparison and StrictMode effect replay synchronize the host without starting a transition', () => {
  const f = fixture({ active: true });
  f.replayMountEffects();
  f.runQueued();
  assert.equal(f.split, 'true');
  assert.deepEqual(f.layouts, [true, true]);
  assert.equal(f.transitions.length, 0);
  assert.deepEqual(f.phases, []);
});

test('native snapshot update commits host and world together without waiting on suppressed animation frames', async () => {
  const f = fixture();
  f.render({ active: true }); f.runQueued();
  assert.equal(f.split, 'false', 'old layout remains until the browser has captured it');
  assert.deepEqual(f.layouts, [false]);
  assert.deepEqual(f.phases, [true]);
  const t = f.transitions[0];
  let updated = false;
  void t.invoke().then(() => { updated = true; });
  await settle();
  assert.equal(updated, true, 'update callback must not depend on a rendering opportunity');
  assert.equal(f.frames.length, 0);
  assert.equal(f.split, 'true');
  assert.deepEqual(f.layouts, [false, true]);
  assert.equal(f.scrolls.length, 1);
  await t.complete(); await settle();
  assert.equal(f.marker, undefined);
  assert.deepEqual(f.phases, [true, false]);
});

test('rapid requests before capture commit only the newest target', async () => {
  const f = fixture();
  f.render({ active: true }); f.render({ active: false }); f.runQueued();
  assert.equal(f.transitions.length, 1);
  await f.transitions[0].complete(); await settle();
  assert.equal(f.split, 'false');
  assert.deepEqual(f.layouts, [false, false]);
  assert.equal(f.scrolls.length, 1);
});

test('skipped old snapshot callbacks cannot overwrite a newer target or finish its animation', async () => {
  const f = fixture();
  f.render({ active: true }); f.runQueued();
  const old = f.transitions[0];
  f.render({ active: false }); f.runQueued();
  await settle();
  assert.equal(old.skipped, 1);
  assert.deepEqual(f.layouts, [false], 'old callback skipped without committing its stale target');
  assert.equal(f.marker, 'closing', 'old completion cannot clear the new transition marker');
  await f.transitions[1].complete(); await settle();
  assert.equal(f.split, 'false');
  assert.deepEqual(f.phases, [true, true, false]);
});

test('unmount invalidates queued updates and native completion callbacks', async () => {
  const f = fixture();
  f.render({ active: true }); f.runQueued();
  const updates = f.stateUpdates;
  f.unmount(); await settle();
  assert.equal(f.stateUpdates, updates);
  assert.deepEqual(f.layouts, [false]);
  assert.equal(f.marker, undefined);
  assert.deepEqual(f.phases, [true], 'unmounted component cannot mutate its former host');
});

test('resize skips animation while preserving the requested layout update', async () => {
  const f = fixture();
  f.render({ active: true }); f.runQueued();
  f.resize(); await settle();
  assert.equal(f.transitions[0].skipped, 1);
  assert.equal(f.split, 'true');
  assert.equal(f.marker, undefined);
  assert.deepEqual(f.phases, [true, false]);
});

test('a theme change synchronously commits a pending native layout and clears its snapshots', async () => {
  const f = fixture();
  f.render({ active: true }); f.runQueued();
  const transition = f.transitions[0];
  assert.equal(transition.started, false);
  assert.equal(f.split, 'false');
  assert.equal(f.marker, 'opening');

  f.themeChange();
  assert.equal(f.split, 'true', 'the new palette must capture the requested layout immediately');
  assert.deepEqual(f.layouts, [false, true]);
  assert.equal(transition.skipped, 1);
  assert.equal(f.scrolls.length, 1);
  assert.equal(f.marker, undefined);
  assert.equal(f.nodes.get('build-comparison').attributes.has('data-morphing'), false);
  assert.deepEqual(f.phases, [true, false]);

  const updates = f.stateUpdates;
  await transition.complete(); await settle();
  assert.equal(f.stateUpdates, updates, 'late snapshot callbacks cannot recommit the layout');
  assert.deepEqual(f.layouts, [false, true]);
  assert.deepEqual(f.phases, [true, false], 'late completion cannot finish the same animation twice');
});

test('a theme change after the native layout commit only finishes the remaining animation', async () => {
  const f = fixture();
  f.render({ active: true }); f.runQueued();
  const transition = f.transitions[0];
  await transition.invoke();
  assert.equal(f.split, 'true');
  assert.equal(f.marker, 'opening');
  const updates = f.stateUpdates;

  f.themeChange();
  assert.equal(f.stateUpdates, updates);
  assert.deepEqual(f.layouts, [false, true]);
  assert.equal(f.scrolls.length, 1);
  assert.equal(transition.skipped, 1);
  assert.equal(f.marker, undefined);
  assert.equal(f.nodes.get('build-comparison').attributes.has('data-morphing'), false);
  assert.deepEqual(f.phases, [true, false]);
  await settle();
  f.themeChange();
  assert.equal(transition.skipped, 1, 'later theme changes have no finished snapshot to skip');
  assert.equal(f.stateUpdates, updates);
  assert.deepEqual(f.phases, [true, false]);
});

test('theme event listeners survive effect replay once and are removed on unmount', async () => {
  const f = fixture();
  assert.equal(f.themeListenerCount, 1);
  f.replayMountEffects();
  assert.equal(f.themeListenerCount, 1, 'StrictMode replay does not duplicate the listener');
  f.render({ active: true }); f.runQueued();
  const transition = f.transitions[0];
  f.unmount();
  assert.equal(f.themeListenerCount, 0);
  const updates = f.stateUpdates, skips = transition.skipped;
  f.themeChange();
  await settle();
  assert.equal(f.stateUpdates, updates);
  assert.equal(transition.skipped, skips, 'a theme event cannot reach an unmounted comparison');
  assert.deepEqual(f.layouts, [false, false]);
  assert.deepEqual(f.phases, [true]);
});

test('reduced motion commits both layouts synchronously without snapshots or tweens', () => {
  const f = fixture({ reduce: true });
  f.render({ active: true }); f.runQueued();
  assert.equal(f.split, 'true');
  assert.deepEqual(f.layouts, [false, true]);
  assert.deepEqual(f.phases, [true, false]);
  assert.equal(f.transitions.length, 0);
  assert.equal(f.tweens.length, 0);
});

test('stacked mobile layouts use the short fade without capturing tall world snapshots', () => {
  const f = fixture({ narrow: true });
  f.render({ active: true }); f.runQueued();
  assert.equal(f.split, 'true');
  assert.deepEqual(f.layouts, [false, true]);
  assert.equal(f.transitions.length, 0, 'native support must not trigger a tall mobile capture');
  assert.equal(f.marker, undefined);
  assert.equal(f.tweens.length, 1);
  assert.deepEqual(f.phases, [true]);
  f.tweens[0].progress(1);
  assert.deepEqual(f.phases, [true, false]);

  f.render({ active: false }); f.runQueued();
  assert.equal(f.split, 'false');
  assert.equal(f.transitions.length, 0);
  f.tweens[1].progress(1);
  assert.deepEqual(f.phases, [true, false, true, false]);
  assert.equal(f.nodes.get('build-comparison-grid').style.opacity, undefined);
});

test('an interrupted fallback clears its transforms when the new target uses reduced motion', () => {
  const f = fixture({ native: false });
  f.render({ active: true }); f.runQueued();
  const grid = f.nodes.get('build-comparison-grid');
  assert.equal(grid.style.opacity, .65);
  f.reduceSilently();
  f.render({ active: false }); f.runQueued();
  assert.equal(f.tweens[0].killed, true);
  assert.equal(f.split, 'false');
  assert.equal(grid.style.opacity, undefined, 'the finished world must not remain dimmed');
  assert.equal(grid.style.y, undefined, 'the finished world must not retain its transition offset');
});

test('synchronous snapshot failure commits the requested layout through the fade fallback', () => {
  const f = fixture({ native: 'throws' });
  f.render({ active: true });
  assert.doesNotThrow(() => f.runQueued());
  assert.equal(f.split, 'true');
  assert.deepEqual(f.layouts, [false, true]);
  assert.equal(f.marker, undefined, 'failed capture leaves no global snapshot styling');
  assert.equal(f.tweens.length, 1);
  assert.deepEqual(f.phases, [true]);
  f.tweens[0].progress(1);
  assert.deepEqual(f.phases, [true, false]);
  assert.equal(f.nodes.get('build-comparison').attributes.has('data-morphing'), false);
  assert.equal(f.nodes.get('build-comparison-grid').style.opacity, undefined);

  f.render({ active: false }); f.runQueued();
  assert.equal(f.split, 'false', 'later return to the world still works after a rejected capture');
  f.tweens[1].progress(1);
  assert.deepEqual(f.phases, [true, false, true, false]);
});
