import test from 'node:test';
import assert from 'node:assert/strict';
import { createRequire } from 'node:module';
import { readFile } from 'node:fs/promises';
import { createElement } from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { build } from 'esbuild';

const compiled = await build({
  stdin: {
    contents: "export { BuildSpeedometer } from './src/BuildSpeedometer'; export { BUILD_SPEEDOMETER_MAX_TPS } from './src/build-speedometer-geometry';",
    resolveDir: new URL('..', import.meta.url).pathname,
  },
  bundle: true, write: false, platform: 'node', format: 'cjs', packages: 'external', jsx: 'automatic',
});
const module = { exports: {} };
new Function('module', 'exports', 'require', compiled.outputFiles[0].text)(module, module.exports, createRequire(import.meta.url));
const { BuildSpeedometer, BUILD_SPEEDOMETER_MAX_TPS: maximum } = module.exports;
const css = await readFile(new URL('../src/build-activity.css', import.meta.url), 'utf8');
const render = (rate, mode = 'streaming') => renderToStaticMarkup(createElement(BuildSpeedometer, { rate, mode }));

function geometry(html) {
  const fill = html.match(/<path class="build-speed-fill"[^>]+>/)?.[0];
  const needle = html.match(/<g class="build-speed-needle"[^>]+>([\s\S]*?)<\/g>/);
  assert.ok(fill && needle, 'the real component renders a fill and needle');
  const arc = fill.match(/d="M ([\d.]+) ([\d.]+) A ([\d.]+) ([\d.]+) 0 0 1 ([\d.]+) ([\d.]+)"/).slice(1).map(Number);
  const origin = needle[0].match(/transform-origin:([\d.]+)px ([\d.]+)px/).slice(1).map(Number);
  const tip = needle[1].match(/ L ([\d.]+) ([\d.]+) L /).slice(1).map(Number);
  const rotation = Number(needle[0].match(/rotate\(([-\d.]+)deg\)/)[1]);
  const dashOffset = Number(fill.match(/stroke-dashoffset="([\d.]+)"/)[1]);
  const center = [(arc[0] + arc[4]) / 2, arc[1]];
  assert.equal(arc[1], arc[5], 'arc endpoints share a baseline');
  assert.equal(arc[2], arc[3], 'the arc is circular');
  assert.equal(arc[4] - arc[0], arc[2] * 2, 'the arc is a semicircle');
  assert.deepEqual(origin, center, 'the needle must pivot around the actual arc center');
  assert.match(needle[1], new RegExp(`<circle cx="${center[0]}" cy="${center[1]}"`));
  assert.match(fill, /pathLength="100" stroke-dasharray="100 100"/);
  return { center, radius: arc[2], origin, tip, rotation, dashOffset };
}

function assertAligned({ center, radius, origin, tip, rotation, dashOffset }, expectedFraction) {
  const fraction = 1 - dashOffset / 100;
  assert.ok(Math.abs(fraction - expectedFraction) < 1e-10);
  const arcAngle = Math.PI * (1 + fraction);
  const fillEnd = [center[0] + radius * Math.cos(arcAngle), center[1] + radius * Math.sin(arcAngle)];
  const radians = rotation * Math.PI / 180;
  const dx = tip[0] - origin[0];
  const dy = tip[1] - origin[1];
  const needleEnd = [origin[0] + dx * Math.cos(radians) - dy * Math.sin(radians), origin[1] + dx * Math.sin(radians) + dy * Math.cos(radians)];
  const needleVector = needleEnd.map((coordinate, index) => coordinate - center[index]);
  const fillVector = fillEnd.map((coordinate, index) => coordinate - center[index]);
  const crossProduct = needleVector[0] * fillVector[1] - needleVector[1] * fillVector[0];
  const dotProduct = needleVector[0] * fillVector[0] + needleVector[1] * fillVector[1];
  assert.ok(Math.abs(crossProduct) < 1e-7, 'the needle points exactly toward the visible fill endpoint');
  assert.ok(dotProduct > 0, 'the needle points toward the fill endpoint, not its opposite');
}

test('the dial fill and needle agree at zero, every quadrant, the maximum, and beyond it', () => {
  for (const fraction of [0, 0.25, 0.5, 0.75, 1, 1.5]) {
    const rate = maximum * fraction;
    const html = render(rate);
    assertAligned(geometry(html), Math.min(1, fraction));
    assert.match(html, new RegExp(`data-rate="${Math.round(rate)}"`), 'the rounded numeric reading is not capped by the visual scale');
    assert.match(html, new RegExp(`data-max-rate="${maximum}"`));
  }
});

test('fill and needle stay aligned between readings in both directions', () => {
  // Browser CSS interpolates these two properties from their current values.
  // They must describe the same angle at every intermediate animation frame.
  for (const [fromRate, toRate] of [[0, maximum], [maximum, maximum / 4], [maximum / 3, maximum * 2]]) {
    const from = geometry(render(fromRate));
    const to = geometry(render(toRate));
    for (const progress of [0.1, 0.25, 0.5, 0.9]) {
      const current = {
        ...from,
        rotation: from.rotation + (to.rotation - from.rotation) * progress,
        dashOffset: from.dashOffset + (to.dashOffset - from.dashOffset) * progress,
      };
      const expectedFraction = Math.min(1, fromRate / maximum) * (1 - progress) + Math.min(1, toRate / maximum) * progress;
      assertAligned(current, expectedFraction);
    }
  }
  assert.match(css, /\.build-speedometer\s*\{[^}]*--speedometer-transition:\s*\.22s linear/);
  assert.match(css, /\.build-speed-fill\s*\{[^}]*stroke-linecap:\s*butt;[^}]*transition:\s*stroke-dashoffset var\(--speedometer-transition\)/,
    'the fill has no rounded cap protruding beyond its indicated angle');
  assert.match(css, /\.build-speed-needle\s*\{[^}]*transition:\s*transform var\(--speedometer-transition\)/);
  assert.match(css, /@media\(prefers-reduced-motion:reduce\)\s*\{\s*\.build-speed-fill,\.build-speed-needle\s*\{\s*transition:\s*none/);
});

test('live and average readings describe their scale and preserve unavailable states', () => {
  for (const mode of ['streaming', 'complete']) {
    const html = render(maximum / 2, mode);
    assert.match(html, new RegExp(`The needle scale is 0 to ${maximum.toLocaleString()} tokens per second`));
    assert.match(html, /Estimated with a local tokenizer/);
    assert.match(html, mode === 'complete' ? /Average visible output/ : /Live visible output/);
    assert.match(html, mode === 'complete' ? />avg tps<\/span>/ : />live tps<\/span>/);
  }
  for (const mode of ['unavailable', 'disconnected']) {
    const html = render(null, mode);
    assert.match(html, /data-rate=""/);
    assert.match(html, /unavailable/);
    assertAligned(geometry(html), 0);
  }
});
