import test from 'node:test';
import assert from 'node:assert/strict';
import { createRequire } from 'node:module';
import { createElement } from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { build } from 'esbuild';

const compiled = await build({
  entryPoints: [new URL('../src/ThemeToggle.tsx', import.meta.url).pathname],
  bundle: true, write: false, platform: 'node', format: 'cjs', packages: 'external', jsx: 'automatic',
});
const module = { exports: {} };
new Function('module', 'exports', 'require', compiled.outputFiles[0].text)(module, module.exports, createRequire(import.meta.url));
const { default: ThemeToggle, readSavedTheme, applyTheme, THEME_STORAGE_KEY } = module.exports;

test('appearance starts dark and restores only a recognized saved preference', () => {
  assert.equal(readSavedTheme(null), 'dark');
  for (const stored of ['dark', null, '', 'system', 'invalid']) {
    assert.equal(readSavedTheme({ getItem: () => stored }), 'dark');
  }
  assert.equal(readSavedTheme({ getItem(key) { assert.equal(key, THEME_STORAGE_KEY); return 'light'; } }), 'light');
});

test('appearance works when local storage is blocked or the browser is absent', () => {
  assert.equal(readSavedTheme({ getItem() { throw new Error('Storage denied'); } }), 'dark');
  assert.equal(readSavedTheme(), 'dark');
});

test('remounted controls retain the session appearance when browser storage is blocked', t => {
  const originalWindow = Object.getOwnPropertyDescriptor(globalThis, 'window');
  const originalDocument = Object.getOwnPropertyDescriptor(globalThis, 'document');
  t.after(() => {
    for (const [key, descriptor] of [['window', originalWindow], ['document', originalDocument]]) {
      if (descriptor) Object.defineProperty(globalThis, key, descriptor);
      else delete globalThis[key];
    }
  });
  const document = { documentElement: { dataset: {}, style: {} }, querySelector: () => null };
  Object.defineProperty(globalThis, 'document', { configurable: true, value: document });
  for (const browser of [
    { get localStorage() { throw new Error('Storage access denied'); } },
    { localStorage: { getItem() { throw new Error('Storage reads denied'); } } },
  ]) {
    Object.defineProperty(globalThis, 'window', { configurable: true, value: browser });
    applyTheme('light');
    assert.equal(readSavedTheme(), 'light');
    assert.match(renderToStaticMarkup(createElement(ThemeToggle)), /aria-label="Switch to dark mode"/);
    applyTheme('dark');
    assert.equal(readSavedTheme(), 'dark');
  }
  applyTheme('light');
  assert.equal(readSavedTheme({ getItem() { throw new Error('Injected failure'); } }), 'dark', 'explicit storage keeps its deterministic default');
  Object.defineProperty(globalThis, 'window', { configurable: true, value: { localStorage: { getItem: () => null } } });
  assert.equal(readSavedTheme(), 'dark', 'available storage remains authoritative even if its preference was cleared');
});

test('theme updates the host, native controls, and browser chrome only', () => {
  const attrs = {};
  const document = {
    documentElement: { dataset: {}, style: {} },
    querySelector(selector) {
      assert.equal(selector, 'meta[name="theme-color"]', 'must not access authored iframe contents');
      return { setAttribute(key, value) { attrs[key] = value; } };
    },
  };
  applyTheme('light', document);
  assert.equal(document.documentElement.dataset.theme, 'light');
  assert.equal(document.documentElement.style.colorScheme, 'light');
  assert.equal(attrs.content, '#f7f8fa');
  applyTheme('dark', document);
  assert.equal(document.documentElement.dataset.theme, 'dark');
  assert.equal(document.documentElement.style.colorScheme, 'dark');
  assert.equal(attrs.content, '#000000');
});

test('theme also applies when browser chrome metadata is absent', () => {
  const document = { documentElement: { dataset: {}, style: {} }, querySelector: () => null };
  assert.doesNotThrow(() => applyTheme('light', document));
  assert.equal(document.documentElement.dataset.theme, 'light');
});

test('appearance control has an actionable accessible name and decorative icons', () => {
  const html = renderToStaticMarkup(createElement(ThemeToggle));
  assert.match(html, /type="button"/);
  assert.match(html, /aria-label="Switch to light mode"/);
  assert.match(html, /<svg[^>]*aria-hidden="true"/);
  assert.match(html, /data-theme="dark"/);
});
