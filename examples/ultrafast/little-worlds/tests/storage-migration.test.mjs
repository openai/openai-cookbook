import test from 'node:test';
import assert from 'node:assert/strict';
import vm from 'node:vm';
import { build } from 'esbuild';

const compiled = await build({ entryPoints: [new URL('../src/storage.ts', import.meta.url).pathname], bundle: true, write: false, format: 'esm' });
const { readAppStorage, writeAppStorage, removeAppStorage } = await import(`data:text/javascript;base64,${Buffer.from(compiled.outputFiles[0].text).toString('base64')}`);
const fixture = entries => {
  const values = new Map(entries);
  return { values, getItem: key => values.get(key) ?? null, setItem: (key, value) => values.set(key, value), removeItem: key => values.delete(key) };
};

test('current saved state wins over an older duplicate and sign-out cannot resurrect it', () => {
  const key = 'little-worlds:demo-session';
  const storage = fixture([[key, 'current'], ['living-spaces:demo-session', 'old']]);
  assert.equal(readAppStorage(storage, key), 'current');
  assert.equal(storage.values.has('living-spaces:demo-session'), false);
  writeAppStorage(storage, key, 'next');
  assert.equal(readAppStorage(storage, key), 'next');
  removeAppStorage(storage, key);
  assert.equal(readAppStorage(storage, key), null);
});

test('a storage quota failure keeps the original layout readable for the next visit', () => {
  const legacy = 'living-spaces.galaxy-layout.v1:mira';
  const value = JSON.stringify([['mira', { x: 1, y: 2, z: 3 }]]);
  const storage = fixture([[legacy, value]]);
  storage.setItem = () => { throw new Error('Quota exceeded'); };
  assert.equal(readAppStorage(storage, 'little-worlds.galaxy-layout.v1:mira'), value);
  assert.equal(storage.values.get(legacy), value);
});

const navigation = await build({
  entryPoints: [new URL('../src/navigation.ts', import.meta.url).pathname], bundle: true, write: false, format: 'iife', globalName: 'Navigation',
  plugins: [{ name: 'hooks', setup(builder) {
    builder.onResolve({ filter: /^react$/ }, () => ({ path: 'react', namespace: 'fixture' }));
    builder.onLoad({ filter: /.*/, namespace: 'fixture' }, () => ({ contents: 'export const { useCallback, useEffect, useRef, useState } = hooks;' }));
  } }],
});

test('renaming preserves browser back entries and only explicit navigation resets scroll', () => {
  const entries = [{ key: 'home', href: '/' }, { key: 'mira', href: '/?space=mira' }];
  const storage = fixture([['living-spaces:navigation:v1', JSON.stringify({ id: 'trail', entries })]]);
  const listeners = new Map(), writes = [], slots = [], scrolls = [];
  let index = 0;
  const window = {
    location: { search: '?space=mira' },
    history: {
      state: { livingSpacesNavigation: { id: 'trail', key: 'mira', index: 1 } },
      replaceState(state, _, href) { this.state = state; writes.push({ kind: 'replace', href, state }); },
      pushState(state, _, href) { this.state = state; writes.push({ kind: 'push', href, state }); window.location.search = href.slice(1); },
    },
    addEventListener: (name, callback) => listeners.set(name, callback),
    removeEventListener: name => listeners.delete(name),
    scrollTo: options => scrolls.push(options),
  };
  const hooks = {
    useState(initial) {
      const slot = index++;
      if (!(slot in slots)) slots[slot] = typeof initial === 'function' ? initial() : initial;
      return [slots[slot], value => { slots[slot] = value; }];
    },
    useRef: value => ({ current: value }), useCallback: callback => callback, useEffect: callback => callback(),
  };
  const context = vm.createContext({ hooks, window, sessionStorage: storage, URLSearchParams, crypto: { randomUUID() { throw new Error('Must restore the existing trail'); } } });
  vm.runInContext(navigation.outputFiles[0].text, context);
  const app = context.Navigation.useAppNavigation();
  assert.equal(app.route.spaceId, 'mira');
  assert.equal(writes.length, 1);
  assert.equal(writes[0].kind, 'replace');
  assert.equal(writes[0].state.littleWorldsNavigation.id, 'trail');
  assert.deepEqual(JSON.parse(storage.values.get('little-worlds:navigation:v1')).entries, entries);
  assert.equal(storage.values.has('living-spaces:navigation:v1'), false);
  window.location.search = '';
  listeners.get('popstate')({ state: { livingSpacesNavigation: { id: 'trail', key: 'home', index: 0 } } });
  assert.equal(slots[0].index, 0);
  assert.equal(slots[1].screen, 'home');
  assert.equal(writes.length, 1, 'back must not create another home entry');
  assert.equal(scrolls.length, 0, 'restoring the page and browser back preserve scroll');
  context.crypto.randomUUID = () => 'new-visit';
  app.navigate({ screen: 'space', spaceId: 'james' });
  assert.equal(scrolls.length, 1);
  assert.equal(scrolls[0].top, 0);
  assert.equal(scrolls[0].behavior, 'instant');
  assert.equal(slots[1].spaceId, 'james');
});
