import test from 'node:test';
import assert from 'node:assert/strict';
import { compileModule, paintSurfacesFromHtml, renderModule, verifyModule } from '../server/runtime.mjs';

const owner = { id: 'iris', name: 'Iris' };
const state = () => ({ projects: [], contributions: [], extras: { notes: { leo: { actorId: 'leo', text: 'Keep this' } } } });
const config = (columns = 96, rows = 64) => ({ action: 'paint_pixels', columns, rows, color: 0, colorValue: '#3153be', palette: ['#3153be', '#ffffff'], background: '#ffffff' });
const attribute = value => JSON.stringify(value).replaceAll('&', '&amp;').replaceAll("'", '&#39;');
const canvas = (value = config(), pixels = '.'.repeat(value.columns * value.rows), tag = 'canvas') => `<${tag} data-key="painting" data-paint-grid='${attribute(value)}' data-paint-pixels="${pixels}" aria-label="Shared painting"></${tag}>`;
const sourceFor = html => `export const meta={title:'Shared canvas',subtitle:'',accent:'#3153be'};
export function render(){return ${JSON.stringify(html)}}
export function reduce(state){return state}`;
const featureTests = `export function runTests(api){
 const html=api.render(api.initialState,{id:'iris',name:'Iris'});
 return [{name:'The declared surface renders',ok:html.includes('data-paint-grid')}];
}`;
const rejectHtml = async (html, pattern) => {
  const compiled = await compileModule(sourceFor(html));
  await assert.rejects(renderModule(compiled.bundle, state(), owner), pattern);
};

test('compact raster canvases publish at doubled and fine resolutions without expanding the HTML budget', async () => {
  for (const [columns, rows] of [[48, 32], [96, 64], [192, 128], [256, 256]]) {
    const value = config(columns, rows);
    const html = canvas(value, '01' + '.'.repeat(columns * rows - 2));
    assert.ok(html.length < columns * rows + 500);
    const before = state();
    const result = await verifyModule(sourceFor(html), featureTests, before, { owner });
    assert.equal(result.ok, true, `${columns} × ${rows}: ${JSON.stringify(result.checks)}`);
    assert.deepEqual(before, state());
  }
});

test('legacy indexed button grids continue to render', async () => {
  const legacy = { action: 'paint_pixels', columns: 48, rows: 32, color: 0, colorValue: '#3153be' };
  const html = `<div data-paint-grid='${attribute(legacy)}'><button data-paint-cell="0">Paint</button></div>`;
  const result = await verifyModule(sourceFor(html), featureTests, state(), { owner });
  assert.equal(result.ok, true, JSON.stringify(result.checks));
});

test('invalid raster data and oversized dimensions are rejected by the normal render path', async () => {
  const valid = config();
  for (const [html, pattern] of [
    [canvas({ ...valid, columns: 257 }), /256|dimension|column|bound/i],
    [canvas({ ...valid, rows: 0 }), /dimension|row|bound|1/i],
    [canvas({ ...valid, columns: 95.5 }, ''), /integer|whole|column|dimension/i],
    [canvas(valid, '.'.repeat(6143)), /pixel|length|cell/i],
    [canvas(valid, '.'.repeat(6145)), /pixel|length|cell/i],
    [canvas(valid, '2' + '.'.repeat(6143)), /pixel|palette|color/i],
    [canvas(valid, 'Z' + '.'.repeat(6143)), /pixel|palette|character/i],
    [canvas({ ...valid, palette: [] }), /palette/i],
    [canvas({ ...valid, background: 'url(https://example.com)' }), /background|color|hex/i],
    [canvas({ ...valid, colorValue: 'red' }), /color|hex/i],
    ['<canvas data-paint-grid="{bad}" data-paint-pixels="."></canvas>', /valid JSON/],
    [`<canvas data-paint-grid='${attribute(valid)}'></canvas>`, /data-paint-pixels/],
    ['<canvas data-paint-pixels="."></canvas>', /data-paint-grid/],
  ]) await rejectHtml(html, pattern);
});

test('raster bindings cannot hide in inert, foreign, service, game, or nested rendering contexts', async () => {
  const html = canvas();
  const legacy = { action: 'paint_pixels', columns: 1, rows: 1, color: 0, colorValue: '#3153be' };
  for (const unsafe of [
    canvas(config(), undefined, 'div'),
    `<svg>${html}</svg>`,
    `<math>${html}</math>`,
    `<template>${html}</template>`,
    `<section data-service="space-agent">${html}</section>`,
    `<section data-game="arcade">${html}</section>`,
    html.replace('data-key=', 'data-game-canvas data-key='),
    `<div data-paint-grid='${attribute(legacy)}'>${html}</div>`,
    `<canvas>${html}</canvas>`,
    `<select>${html}</select>`,
  ]) await rejectHtml(unsafe, /HTML canvas|templates|paint grids/i);
});

test('raster validation uses decoded attributes and the first duplicate, matching the HTML parser', async () => {
  const value = config(2, 1);
  const html = canvas(value, '&#48;&#x31;').replace(/"action"/, '&quot;action&quot;');
  const compiled = await compileModule(sourceFor(html));
  assert.equal(await renderModule(compiled.bundle, state(), owner), html);
  await rejectHtml(canvas(value, '2.').replace('data-paint-pixels="2."', 'data-paint-pixels="2." data-paint-pixels=".."'), /pixel|palette|color/i);
});

test('textual markup examples do not create raster surfaces', async () => {
  const invalid = '<canvas data-paint-grid="broken" data-paint-pixels="x"></canvas>';
  for (const html of [`<!-- ${invalid} -->`, `<textarea>${invalid}</textarea>`, `<pre>&lt;canvas data-paint-grid="broken"&gt;</pre>`]) {
    const compiled = await compileModule(sourceFor(html));
    assert.equal(await renderModule(compiled.bundle, state(), owner), html);
  }
});

test('bad raster markup blocks publication even when authored tests claim success', async () => {
  const result = await verifyModule(sourceFor(canvas(config(), '.')), 'export function runTests(){return [{name:"Pretend",ok:true}]}', state(), { owner });
  assert.equal(result.ok, false);
  assert.ok(result.checks.some(check => /Owner view/.test(check.name) && !check.ok && /pixel|cell/i.test(check.message)));
});

test('generated feature tests receive the same raster validation within the isolated runtime', async () => {
  const html = canvas(config(2, 1));
  const source = sourceFor(html).replace('render()', 'render(state)').replace(`return ${JSON.stringify(html)}`, `return state.extras.broken ? ${JSON.stringify(canvas(config(2, 1), '2.'))} : ${JSON.stringify(html)}`);
  const tests = `export function runTests(api){
    let rejected=false;
    try { api.render({...api.initialState,extras:{...api.initialState.extras,broken:true}}, {id:'iris',name:'Iris'}); }
    catch(error){ rejected=/pixel|palette|color/i.test(error.message); }
    return [{name:'Invalid raster output is rejected',ok:rejected}];
  }`;
  const result = await verifyModule(source, tests, state(), { owner });
  assert.equal(result.ok, true, JSON.stringify(result.checks));
});

test('host raster validation remains enforced if generated code shadows the interpreter validator', async () => {
  const source = sourceFor(canvas(config(2, 1), '2.')).replace('export function render(){', 'export function render(){globalThis.validatePaintPixels=()=>{};');
  const { bundle } = await compileModule(source);
  await assert.rejects(renderModule(bundle, state(), owner), /pixel|palette|color/i);
});

test('agent context extracts decoded authoritative raster surfaces and ignores textual examples and legacy grids', () => {
  const value = config(2, 1);
  const legacy = { action: 'paint_pixels', columns: 1, rows: 1, color: 0, colorValue: '#3153be' };
  const first = canvas(value, '&#48;&#x31;').replace('data-key="painting"', 'data-key="paint&#105;ng"');
  const second = canvas(value, '.0').replace('data-key="painting"', 'data-key="detail"');
  const html = `${first}<div data-paint-grid='${attribute(legacy)}'><button data-paint-cell="0">Paint</button></div>
    <!-- ${canvas()} --><textarea>${canvas()}</textarea><pre>&lt;canvas data-paint-pixels=".."&gt;</pre>${second}`;
  assert.deepEqual(paintSurfacesFromHtml(html), [
    { key: 'painting', config: value, pixels: '01' },
    { key: 'detail', config: value, pixels: '.0' },
  ]);
  assert.equal(paintSurfacesFromHtml(first.replace('data-key="paint&#105;ng"', ''))[0].key, '');
  assert.deepEqual(paintSurfacesFromHtml('<section>No canvas yet</section>'), []);
});

test('agent context extraction rejects malformed or inert raster surfaces instead of exposing unchecked content', () => {
  assert.throws(() => paintSurfacesFromHtml(canvas(config(2, 1), '2.')), /pixel|palette|color/i);
  assert.throws(() => paintSurfacesFromHtml(`<template>${canvas()}</template>`), /HTML canvas/);
  assert.throws(() => paintSurfacesFromHtml(`<svg>${canvas()}</svg>`), /HTML canvas/);
  assert.throws(() => paintSurfacesFromHtml('<canvas data-paint-pixels=".."></canvas>'), /data-paint-grid/);
});
