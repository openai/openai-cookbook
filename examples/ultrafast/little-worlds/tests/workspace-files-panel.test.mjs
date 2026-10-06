import test from 'node:test';
import assert from 'node:assert/strict';
import { createRequire } from 'node:module';
import { createElement } from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { build } from 'esbuild';

const compiled = await build({
  entryPoints: [new URL('../src/FilesPanel.tsx', import.meta.url).pathname],
  bundle: true, write: false, platform: 'node', format: 'cjs', packages: 'external',
  jsx: 'automatic', loader: { '.css': 'empty' },
});
const module = { exports: {} };
new Function('module', 'exports', 'require', compiled.outputFiles[0].text)(module, module.exports, createRequire(import.meta.url));
const { FilesPanel } = module.exports;
const snapshot = (content = 'export const meta = {};\nexport function render() { return "<section>hello</section>"; }', status = 'published') => ({
  sessionId: 'session-1', revisionId: 2, status,
  files: ['space.js', 'tests.js'].map(path => ({ path, content: path === 'space.js' ? content : 'assert.equal(1, 1);', language: 'javascript', status, updatedAt: '2026-09-21T12:00:00.000Z' })),
});
const render = (value = snapshot(), props = {}) => renderToStaticMarkup(createElement(FilesPanel, { snapshot: value, connected: true, connecting: false, onClose() {}, ...props }));
const plainText = html => html.replace(/<[^>]+>/g, '').replace(/&(?:amp|lt|gt|quot|#x27|#39);/g, entity => ({
  '&amp;': '&', '&lt;': '<', '&gt;': '>', '&quot;': '"', '&#x27;': "'", '&#39;': "'",
}[entity]));

test('file controls remain voice-accessible while the full line-numbered source is inert', () => {
  const source = 'const html = "<img src=x onerror=alert(1)>";\n// </code><script>unsafe()</script>';
  const html = render(snapshot(source));
  assert.match(html, /id="workspace-files-panel"/);
  assert.match(html, /<nav[^>]*aria-label="Workspace files"/);
  assert.match(html, /<button[^>]*aria-label="Open space\.js"[^>]*aria-pressed="true"/);
  assert.match(html, /<button[^>]*aria-label="Open tests\.js"[^>]*aria-pressed="false"/);
  assert.match(html, /aria-label="Close files"/);
  assert.match(html, /aria-label="space\.js source"[^>]*data-voice-ignore/);
  assert.match(html, /data-file-line="1"/);
  assert.match(html, /data-file-line="2"/);
  assert.doesNotMatch(html, /<(?:script|iframe|img|details|textarea)\b/i);
  for (const line of source.split('\n')) assert.ok(plainText(html).includes(line));
  assert.ok(plainText(html).includes('2 lines'));
  assert.ok(plainText(html).includes('r2'));
});

test('source updates replace the selected file without repeating versions or collapsing content', () => {
  const lines = Array.from({ length: 175 }, (_, index) => `const line_${index} = ${index};`);
  const html = render(snapshot(lines.join('\n'), 'streaming'));
  for (const line of lines) assert.ok(plainText(html).includes(line));
  assert.equal((html.match(/data-file-line=/g) || []).length, lines.length);
  assert.ok(plainText(html).includes('Writing'));
  assert.ok(plainText(html).includes('175 lines'));
  const after = plainText(render(snapshot('const updated = true;', 'working')));
  assert.ok(after.includes('const updated = true;'));
  assert.ok(after.includes('Working'));
  assert.ok(!after.includes('const line_0'));
});

test('loading, reconnecting, and disconnected states keep useful content and controls clear', () => {
  assert.ok(plainText(render(null, { connected: false, connecting: true })).includes('Connecting'));
  assert.ok(plainText(render(null)).includes('Loading files…'));
  const reconnecting = plainText(render(snapshot('retained content'), { connected: false, connecting: true }));
  assert.ok(reconnecting.includes('Reconnecting'));
  assert.ok(reconnecting.includes('retained content'));
  const disconnected = render(null, { connected: false, connecting: false });
  assert.ok(plainText(disconnected).includes('Files unavailable.'));
  assert.match(disconnected, /aria-label="Close files"/);
});
