import test from 'node:test';
import assert from 'node:assert/strict';
import { createRequire } from 'node:module';
import { createElement } from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { build } from 'esbuild';

const compiled = await build({
  entryPoints: [new URL('../src/BuildComparison.tsx', import.meta.url).pathname],
  bundle: true, write: false, platform: 'node', format: 'cjs', packages: 'external',
  jsx: 'automatic', loader: { '.css': 'empty' },
});
const module = { exports: {} };
new Function('module', 'exports', 'require', compiled.outputFiles[0].text)(module, module.exports, createRequire(import.meta.url));
const BuildComparison = module.exports.default;
const lane = { status: 'running', model: 'gpt-6-astra', elapsedMs: 1250 };
const render = (props = {}) => renderToStaticMarkup(createElement(BuildComparison, {
  active: true, ultrafast: lane, standard: lane,
  ultrafastActivity: createElement('div', null, 'Fast stream'),
  standardActivity: createElement('div', null, 'Standard stream'),
  standardPreview: createElement('div', null, 'Standard preview'),
  ...props,
}, createElement('div', { id: 'primary-world' }, 'The world')));

test('comparison shows independent lane status and time without output percentages', () => {
  const html = render();
  assert.match(html, /Ultrafast build/);
  assert.match(html, /Standard build/);
  assert.doesNotMatch(html, /42%|100%|output vs ultrafast|build-comparison-ratio/);
  assert.match(html, /1\.3s/);
  assert.equal((html.match(/id="primary-world"/g) || []).length, 1);
  assert.match(html, /build-comparison-world" inert=""/);
  assert.match(html, /Fast stream/);
  assert.match(html, /Standard stream/);
});

test('single world is interactive while inactive comparison chrome is hidden', () => {
  const html = render({ active: false });
  assert.match(html, /data-comparing="false"/);
  assert.match(html, /build-comparison-world"><div id="primary-world"/);
  assert.match(html, /aria-label="Standard build" inert="" aria-hidden="true"/);
  assert.match(html, /build-comparison-activity" inert="" aria-hidden="true"/);
});

test('both Activity sidebars open automatically with independently labelled controls', () => {
  const html = render();
  const buttons = html.match(/<button\b[^>]*>/g) || [];
  const controls = ['Ultrafast', 'Standard'].map(name => {
    const button = buttons.find(tag => tag.includes(`aria-label="Hide ${name} activity"`));
    assert.ok(button, `${name} has its own accessible Activity control`);
    assert.match(button, /aria-expanded="true"/);
    const id = button.match(/aria-controls="([^"]+)"/)?.[1];
    assert.ok(id, `${name} control identifies its sidebar`);
    assert.ok(html.includes(`id="${id}"`), `${name} controls an existing sidebar`);
    return id;
  });
  assert.equal(new Set(controls).size, 2, 'each button controls only its own lane');
});

test('output telemetry never becomes a completion indicator', () => {
  // Older callers may still supply the removed field; it must stay invisible.
  for (const outputRatio of [null, undefined, NaN, Infinity, -1, .79, 1.25]) {
    const html = render({ standard: { ...lane, outputRatio } });
    assert.doesNotMatch(html, /NaN|Infinity|%|output vs ultrafast/);
    assert.match(html, /is-running/);
    assert.doesNotMatch(html, /is-completed/);
  }
});

test('only a completed and published primary world becomes interactive during comparison', () => {
  for (const status of ['waiting', 'running', 'failed', 'cancelled']) {
    const html = render({ primaryInteractive: true, ultrafast: { ...lane, status } });
    assert.match(html, /build-comparison-world" inert=""><div id="primary-world"/);
  }
  assert.match(render({ ultrafast: { ...lane, status: 'completed' } }), /build-comparison-world" inert=""><div id="primary-world"/);
  const html = render({ primaryInteractive: true, ultrafast: { ...lane, status: 'completed' }, standard: { ...lane, status: 'completed' } });
  assert.match(html, /data-comparing="true"/);
  assert.match(html, /build-comparison-world"><div id="primary-world"/);
  assert.match(html, /build-comparison-world" inert=""><div>Standard preview/);
});

test('activity arrows point toward their respective outer lane edge to collapse', () => {
  const html = render();
  assert.match(html, /aria-label="Hide Ultrafast activity"[^>]*>[\s\S]*?lucide-chevron-right/);
  assert.match(html, /aria-label="Hide Standard activity"[^>]*>[\s\S]*?lucide-chevron-left/);
});

test('failure and stopped status remain distinct from successful completion', () => {
  const html = render({ ultrafast: { ...lane, status: 'completed' }, standard: { ...lane, status: 'failed' } });
  assert.match(html, /is-completed">[\s\S]*?<span>Complete/);
  assert.match(html, /is-failed">[\s\S]*?<span>Failed/);
  assert.match(render({ standard: { ...lane, status: 'cancelled' } }), /is-cancelled">[\s\S]*?<span>Stopped/);
});

test('active lanes show a decorative spinner without suggesting completed work is still running', () => {
  for (const status of ['running', 'waiting']) {
    const html = render({ ultrafast: { ...lane, status }, standard: { ...lane, status } });
    assert.equal((html.match(/class="[^"]*build-comparison-spinner/g) || []).length, 2);
    assert.match(html, /build-comparison-spinner"[^>]*aria-hidden="true"/);
  }
  for (const status of ['completed', 'failed', 'cancelled']) {
    assert.doesNotMatch(render({ ultrafast: { ...lane, status }, standard: { ...lane, status } }), /build-comparison-spinner/);
  }
});
