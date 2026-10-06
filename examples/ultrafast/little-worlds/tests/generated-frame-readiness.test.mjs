import test from 'node:test';
import assert from 'node:assert/strict';
import vm from 'node:vm';
import { build } from 'esbuild';

// Exercise the real host bridge and React lifecycle while keeping game workers,
// the opaque child document, network, and the microphone outside this test.
const compiled = await build({
  entryPoints: [new URL('../src/GeneratedFrame.tsx', import.meta.url).pathname],
  bundle: true, write: false, format: 'iife', globalName: 'FrameModule',
  plugins: [{ name: 'host-frame-fixture', setup(builder) {
    builder.onResolve({ filter: /^(react(?:\/jsx-runtime)?|\.\/game-controller|\.\/voice-frame-registry|\.\/frame-theme)$/ }, ({ path }) => ({ path, namespace: 'fixture' }));
    builder.onLoad({ filter: /.*/, namespace: 'fixture' }, ({ path }) => ({ contents:
      path === 'react' ? 'export const {useEffect,useMemo,useRef,useState}=h;'
      : path === 'react/jsx-runtime' ? 'export const jsx=h.jsx,jsxs=h.jsx;'
      : path === './game-controller' ? 'export const createGameController=h.createGameController;'
      : path === './frame-theme' ? 'export const frameTheme="";'
      : 'export const registerVoiceFrame=h.registerVoiceFrame;',
    }));
  } }],
});

function fixture() {
  const slots = [], effects = [], messages = [], listeners = new Map();
  let cursor = 0, actions = 0, controllers = 0, commands = 0, disposed = 0, voice = null;
  const equal = (before, after) => before && after && before.length === after.length && before.every((value, i) => Object.is(value, after[i]));
  const h = {
    jsx: (type, props) => ({ type, props }),
    useRef(value) { const i = cursor++; return slots[i] ??= { current: value }; },
    useState(value) { const i = cursor++; slots[i] ??= { value }; return [slots[i].value, next => { slots[i].value = typeof next === 'function' ? next(slots[i].value) : next; }]; },
    useMemo(create, deps) { const i = cursor++; if (!equal(slots[i]?.deps, deps)) slots[i] = { deps, value: create() }; return slots[i].value; },
    useEffect(create, deps) { const i = cursor++; if (!equal(slots[i]?.deps, deps)) effects.push(() => { slots[i]?.cleanup?.(); slots[i] = { deps, cleanup: create() }; }); },
    createGameController() { controllers++; return { async handle() { commands++; return true; }, dispose() { disposed++; } }; },
    registerVoiceFrame(value) { voice = value; return () => { if (voice === value) voice = null; }; },
  };
  const frameWindow = { postMessage: message => messages.push(message) };
  const frameElement = { contentWindow: frameWindow };
  const context = vm.createContext({ h, crypto: { randomUUID: () => 'fixture-nonce' },
    window: { location: { origin: 'http://127.0.0.1' }, addEventListener: (type, callback) => listeners.set(type, callback), removeEventListener: type => listeners.delete(type) },
    setTimeout, clearTimeout,
  });
  vm.runInContext(compiled.outputFiles[0].text, context);
  const props = { html: '<canvas></canvas>', renderVersion: 1, revisionId: 1,
    capabilities: ['chat'], services: { request() {}, cancel() {} },
    games: [{ id: 'arcade', load() {}, save() {} }], onAction: async () => { actions++; return { ok: true }; },
  };
  return {
    render(extra) {
      cursor = 0;
      const tree = context.FrameModule.default({ ...props, ...extra });
      tree.props.ref.current = frameElement;
      while (effects.length) effects.shift()();
      return tree.props;
    },
    emit(data) { listeners.get('message')({ source: frameWindow, data: { channel: 'living-space', bridgeKey: 'fixturenonce', ...data } }); },
    messages,
    stats: () => ({ actions, controllers, commands, disposed, voice }),
    dispose() { for (const slot of slots) slot?.cleanup?.(); },
  };
}

test('full-brightness read-only previews cannot dispatch actions, start games, or register voice', async t => {
  const app = fixture(); t.after(() => app.dispose());
  const frame = app.render({ pending: true, dimmed: false });
  assert.equal(frame.style.opacity, 1);
  assert.equal(frame.inert, true);
  assert.equal(frame.tabIndex, -1);
  app.emit({ type: 'ready' });
  app.render({ pending: true, dimmed: false });
  app.emit({ type: 'action', requestId: 1, action: { type: 'save' } });
  app.emit({ type: 'game.command', requestId: 2, gameId: 'arcade', command: 'start' });
  await new Promise(resolve => setImmediate(resolve));
  assert.deepEqual(app.stats(), { actions: 0, controllers: 0, commands: 0, disposed: 0, voice: null });
  assert.ok(app.messages.filter(message => message.type === 'service.configure').every(message => !message.active));
  assert.ok(app.messages.filter(message => message.type === 'game.configure').every(message => !message.configs.length));
});

test('publishing a ready primary frame enables games, actions, and voice without recreating it when brightness changes', async t => {
  const app = fixture(); t.after(() => app.dispose());
  app.render({ pending: true });
  app.emit({ type: 'ready' });
  const ready = app.render({ pending: false });
  assert.equal(ready.inert, false);
  assert.equal(ready.tabIndex, 0);
  assert.equal(app.stats().controllers, 1);
  assert.ok(app.stats().voice);
  app.emit({ type: 'action', requestId: 1, action: { type: 'save' } });
  app.emit({ type: 'game.command', requestId: 2, gameId: 'arcade', command: 'start' });
  await new Promise(resolve => setImmediate(resolve));
  assert.equal(app.stats().actions, 1);
  assert.equal(app.stats().commands, 1);
  const voice = app.stats().voice;
  const updated = app.render({ pending: false, dimmed: true });
  assert.equal(updated.srcDoc, ready.srcDoc);
  assert.equal(app.stats().controllers, 1);
  assert.equal(app.stats().disposed, 0);
  assert.equal(app.stats().voice, voice);
});

test('curated appearance survives initial render, updates and actions without replacing the game context', async t => {
  const app = fixture(); t.after(() => app.dispose());
  const appearance = { lightCss: 'html,body{background:#fff;color:#123}' };
  const initial = app.render({ pending: false, appearance });
  assert.equal(initial['data-space-appearance'], '');
  assert.match(initial.srcDoc, /@media\(prefers-color-scheme:light\)/);
  app.emit({ type: 'ready' });
  app.render({ pending: false, appearance });
  const controllers = app.stats().controllers;
  const updated = app.render({ pending: false, appearance, html: '<p>Updated state</p>', renderVersion: 2,
    onAction: async () => ({ ok: true, html: '<p>Saved state</p>', version: 3 }),
  });
  assert.equal(updated.srcDoc, initial.srcDoc, 'ordinary state updates retain the iframe document');
  assert.equal(app.stats().controllers, controllers);
  assert.equal(app.stats().disposed, 0);
  assert.match(app.messages.filter(message => message.type === 'render').at(-1).html, /Updated state.*data-space-appearance/);
  app.emit({ type: 'action', requestId: 1, action: { type: 'save' } });
  await new Promise(resolve => setImmediate(resolve));
  const result = app.messages.find(message => message.type === 'action.result');
  assert.match(result.html, /Saved state.*data-space-appearance/);
  assert.equal(result.version, 3);
  const count = app.messages.length;
  app.render({ pending: false, appearance, html: '<p>Updated state</p>', renderVersion: 2 });
  assert.equal(app.messages.length, count, 'unchanged appearance sends no extra render or configure');
});

test('custom worlds do not inherit a curated appearance', t => {
  const app = fixture(); t.after(() => app.dispose());
  const frame = app.render({ pending: false });
  assert.equal(frame['data-space-appearance'], undefined);
  assert.doesNotMatch(frame.srcDoc, /data-space-appearance|prefers-color-scheme:light/);
});
