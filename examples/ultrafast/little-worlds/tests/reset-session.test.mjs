import test from 'node:test';
import assert from 'node:assert/strict';
import vm from 'node:vm';
import { fileURLToPath } from 'node:url';
import { build } from 'esbuild';

const compiled = await build({
  stdin: {
    contents: "export * from './reset-session'; export { setSessionToken, hasSessionToken, resetDemo } from './api';",
    resolveDir: fileURLToPath(new URL('../src/', import.meta.url)),
    loader: 'ts',
  },
  bundle: true, write: false, format: 'iife', globalName: 'resetTools', platform: 'browser',
});

function storage(initial = {}) {
  const values = new Map(Object.entries(initial));
  return {
    get length() { return values.size; },
    key: index => [...values.keys()][index] ?? null,
    getItem: key => values.get(key) ?? null,
    setItem: (key, value) => values.set(key, String(value)),
    removeItem: key => values.delete(key),
    values,
  };
}

function fixture({ broadcast = true, deniedStorage = false } = {}) {
  const channels = [], navigations = [], requests = [];
  const sessionStorage = storage({ 'little-worlds:demo-session': 'old-token', 'other-app:session': 'keep-session' });
  const localStorage = storage({ 'living-spaces.galaxy-position': 'old-position', 'little-worlds.galaxy-layout.v1:mira': 'layout', 'little-worlds:other': 'old-setting', 'other-app': 'keep-local' });
  const context = {
    setTimeout, clearTimeout,
    sessionStorage, localStorage,
    window: { location: { replace: url => navigations.push(url) } },
    fetch: async (url, init) => { requests.push({ url, init }); return { ok: true, json: async () => ({ ok: true, users: [] }) }; },
  };
  if (broadcast) context.BroadcastChannel = class {
    constructor(name) { this.name = name; this.messages = []; this.closed = false; channels.push(this); }
    postMessage(message) { this.messages.push(message); }
    close() { this.closed = true; }
  };
  if (deniedStorage) {
    for (const name of ['sessionStorage', 'localStorage']) Object.defineProperty(context, name, { get() { throw new Error('Storage denied'); } });
  }
  vm.runInNewContext(compiled.outputFiles[0].text, context);
  return { api: context.resetTools, sessionStorage, localStorage, channels, navigations, requests };
}

test('completed reset clears app credentials and galaxy storage while preserving other apps', () => {
  const { api, sessionStorage, localStorage, channels, navigations } = fixture();
  assert.equal(api.hasSessionToken(), true);
  api.returnToWelcomeAfterReset();
  assert.equal(api.hasSessionToken(), false);
  assert.deepEqual([...sessionStorage.values], [['other-app:session', 'keep-session']]);
  assert.deepEqual([...localStorage.values], [['other-app', 'keep-local']]);
  assert.deepEqual(navigations, ['/']);
  assert.deepEqual(channels.map(channel => channel.name), ['little-worlds:demo-reset', 'living-spaces:demo-reset']);
  assert.deepEqual(channels[0].messages, ['completed']);
  assert.equal(channels[0].closed, true);
});

test('sibling tab reset returns home without rebroadcasting or looping', () => {
  const { api, channels, navigations } = fixture();
  const stop = api.listenForDemoReset();
  channels[0].onmessage({ data: 'unrelated' });
  assert.deepEqual(navigations, []);
  channels[0].onmessage({ data: 'completed' });
  assert.deepEqual(navigations, ['/']);
  assert.equal(api.hasSessionToken(), false);
  assert.equal(channels.length, 2);
  channels[1].onmessage({ data: 'completed' });
  assert.deepEqual(navigations, ['/'], 'the other name must not repeat a completed reset');
  assert.deepEqual(channels[0].messages, []);
  stop();
  assert.equal(channels[0].closed, true);
});

test('an older open tab can still notify the renamed app of a completed reset', () => {
  const { api, channels, navigations } = fixture();
  const stop = api.listenForDemoReset();
  channels.find(channel => channel.name === 'living-spaces:demo-reset').onmessage({ data: 'completed' });
  assert.deepEqual(navigations, ['/']);
  assert.equal(api.hasSessionToken(), false);
  assert.equal(channels.every(channel => channel.messages.length === 0), true);
  stop();
  assert.equal(channels.every(channel => channel.closed), true);
});

test('reset still clears in-memory auth and returns home if storage or broadcasting is unavailable', () => {
  const { api, navigations } = fixture({ broadcast: false, deniedStorage: true });
  api.setSessionToken('memory-only-token');
  assert.equal(api.hasSessionToken(), true);
  const stop = api.listenForDemoReset();
  api.returnToWelcomeAfterReset();
  assert.equal(api.hasSessionToken(), false);
  assert.deepEqual(navigations, ['/']);
  stop();
});

test('the welcome-screen reset request carries explicit confirmation without old bearer credentials', async () => {
  const { api, requests } = fixture();
  assert.equal(api.hasSessionToken(), true);
  await api.resetDemo();
  assert.equal(requests[0].url, '/api/demo/reset');
  assert.equal(requests[0].init.method, 'POST');
  assert.equal(requests[0].init.headers.Authorization, undefined);
  assert.equal(requests[0].init.headers['Content-Type'], 'application/json');
  assert.deepEqual(JSON.parse(requests[0].init.body), { confirmation: 'reset-demo' });
});
