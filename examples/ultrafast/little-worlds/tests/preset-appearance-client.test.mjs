import test from 'node:test';
import assert from 'node:assert/strict';
import { createRequire } from 'node:module';
import { createElement } from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { build } from 'esbuild';

const require = createRequire(import.meta.url);
async function load(path, react) {
  const compiled = await build({
    entryPoints: [new URL(path, import.meta.url).pathname],
    bundle: true, write: false, platform: 'node', format: 'cjs', packages: 'external',
    jsx: 'automatic', loader: { '.css': 'empty' },
  });
  const module = { exports: {} };
  new Function('module', 'exports', 'require', compiled.outputFiles[0].text)(module, module.exports,
    name => name === 'react' && react ? react : require(name));
  return module.exports;
}

const { withSpaceAppearance } = await load('../src/space-appearance.ts');
const { default: SpaceIcon } = await load('../src/SpaceIcon.tsx');
const { default: Avatar } = await load('../src/Avatar.tsx');

test('appearance is an opt-in stylesheet and does not rewrite authored markup or active controls', () => {
  const html = '<form><input value="Kept"><canvas data-game-canvas></canvas></form>';
  assert.equal(withSpaceAppearance(html), html);
  assert.equal(withSpaceAppearance(html, { lightCss: '' }), html);
  const themed = withSpaceAppearance(html, { lightCss: 'body{background:#fff}' });
  assert.ok(themed.startsWith(html));
  assert.match(themed, /@media\(prefers-color-scheme:light\)\{body\{background:#fff\}\}/);
  assert.match(themed, /transition-property:transform,opacity,filter!important/);
  assert.equal((themed.match(/<style/g) || []).length, 1);
});

test('accidental style closing tags cannot break out of a curated stylesheet', () => {
  const themed = withSpaceAppearance('<p>World</p>', { lightCss: 'p{content:"</STYLE><script>oops</script>"}' });
  assert.equal((themed.match(/<\/style>/gi) || []).length, 1);
  assert.match(themed, /<\\\/style>/i);
});

test('reviewed typography applies in both themes and keeps the original markup intact', () => {
  const html = '<button data-action=\'{"type":"start"}\'>Start</button><canvas data-game-canvas></canvas>';
  const presentationCss = '.square p{font-size:22px}';
  const result = withSpaceAppearance(html, { lightCss: 'body{color:#222}', presentationCss });
  assert.ok(result.startsWith(html));
  assert.ok(result.indexOf(presentationCss) < result.indexOf('@media(prefers-color-scheme:light)'));
  assert.equal((result.match(/<style/g) || []).length, 1);
  const escaped = withSpaceAppearance(html, { lightCss: '', presentationCss: 'p{content:"</STYLE><script>oops</script>"}' });
  assert.equal((escaped.match(/<\/style>/gi) || []).length, 1);
  assert.match(escaped, /<\\\/style>/i);
});

for (const [name, Component, baseProps, lightClass] of [
  ['world icons', SpaceIcon, { name: 'Mira' }, 'space-icon-light'],
  ['profile avatars', Avatar, { personId: 'mira', name: 'Mira' }, 'person-avatar-light'],
]) {
  test(`${name} preload both variants with a single accessible label`, () => {
    const html = renderToStaticMarkup(createElement(Component, { ...baseProps,
      icon: { status: 'ready', dataUrl: 'data:image/webp;base64,ZGFyaw==', lightDataUrl: 'data:image/webp;base64,bGlnaHQ=' },
    }));
    assert.equal((html.match(/<img /g) || []).length, 2);
    assert.equal((html.match(/aria-label=/g) || []).length, 1);
    assert.match(html, /has-light-icon/);
    assert.ok(html.includes(lightClass));
    assert.doesNotMatch(html, /loading="lazy"/);
  });

  test(`${name} leave custom uploads and ordinary generated artwork unchanged`, () => {
    const html = renderToStaticMarkup(createElement(Component, { ...baseProps,
      icon: { status: 'ready', source: 'upload', dataUrl: 'data:image/webp;base64,b3duZXI=' },
    }));
    assert.equal((html.match(/<img /g) || []).length, 1);
    assert.doesNotMatch(html, /has-light-icon/);
  });
}
