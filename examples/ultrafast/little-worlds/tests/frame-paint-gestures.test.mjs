import test from 'node:test';
import assert from 'node:assert/strict';
import vm from 'node:vm';
import { build } from 'esbuild';
import { validatePaintConfig, validatePaintPixels } from '../shared/paint-schema.mjs';

const compiled = await build({ entryPoints: [new URL('../src/frame-paint-gestures.ts', import.meta.url).pathname], bundle: true, format: 'esm', write: false, minify: true, target: 'es2020' });
const { installPaintGestures } = await import(`data:text/javascript;base64,${Buffer.from(compiled.outputFiles[0].text).toString('base64')}`);
const tick = () => new Promise(resolve => setImmediate(resolve));

function frame({ columns = 8, rows = 8, svg = false } = {}) {
  const handlers = new Map();
  let active = true;
  class Element {
    attrs = {}; style = { backgroundColor: '', fill: '' }; isConnected = true; id = ''; capture = null;
    getAttribute(name) { return this.attrs[name] ?? null; }
    closest(selector) {
      if (selector === '[data-service]') return null;
      if (selector === '[data-paint-grid]') return root;
      if (selector === '[data-paint-cell]') return this === root ? null : this;
      return null;
    }
    querySelector(selector) { return cells[Number(selector.match(/"(\d+)"/)?.[1])] || null; }
    getBoundingClientRect() { return { left: 0, top: 0, right: columns * 10, bottom: rows * 10, width: columns * 10, height: rows * 10 }; }
    setPointerCapture(id) { this.capture = id; }
    hasPointerCapture(id) { return this.capture === id; }
    releasePointerCapture() { this.capture = null; }
    contains(node) { return node === this || cells.includes(node); }
  }
  class HTMLElement extends Element {}
  class SVGElement extends Element {}
  const root = new HTMLElement();
  const cells = Array.from({ length: columns * rows }, (_, index) => {
    const node = svg ? new SVGElement() : new HTMLElement();
    node.attrs['data-paint-cell'] = String(index);
    return node;
  });
  const property = svg ? 'fill' : 'backgroundColor';
  const setColor = (color, colorValue) => { root.attrs['data-paint-grid'] = JSON.stringify({ action: 'paint_pixels', columns, rows, color, colorValue }); };
  setColor(0, '#3153be');
  const saved = Array(cells.length).fill('#ffffff');
  const jobs = [];
  const document = {
    querySelectorAll: () => [root],
    elementFromPoint: (x, y) => cells[Math.floor(y / 10) * columns + Math.floor(x / 10)] || null,
    addEventListener: (name, handler) => { if (!handlers.has(name)) handlers.set(name, []); handlers.get(name).push(handler); },
  };
  const options = { isActive: () => active, dispatch: action => new Promise(resolve => jobs.push({ action: JSON.parse(JSON.stringify(action)), resolve })) };
  const installed = vm.runInNewContext(`(${installPaintGestures.toString()})(options, validatePaintConfig, validatePaintPixels)`, { options, validatePaintConfig, validatePaintPixels, document, Element, HTMLElement, SVGElement, Date, setTimeout, clearTimeout });
  function authoritative() { cells.forEach((node, index) => { node.style[property] = saved[index]; }); installed.reapply(); }
  authoritative();
  function fire(name, cell = 0, extra = {}) {
    const event = { target: cells[cell], button: 0, buttons: 1, isPrimary: true, pointerId: 1, pointerType: 'mouse', clientX: cell % columns * 10 + 5, clientY: Math.floor(cell / columns) * 10 + 5, detail: 1, defaultPrevented: false, stopped: false, preventDefault() { this.defaultPrevented = true; }, stopImmediatePropagation() { this.stopped = true; }, ...extra };
    for (const handler of handlers.get(name) || []) { handler(event); if (event.stopped) break; }
    return event;
  }
  async function complete(job, ok = true) {
    if (ok) for (const item of job.action.cells) saved[item.cell] = item.color === 0 ? '#3153be' : '#e06050';
    authoritative();
    job.resolve(ok);
    await tick();
  }
  return { root, cells, jobs, fire, complete, saved, authoritative, setColor, installed, property, setActive: value => { active = value; } };
}

test('fast drag fills intervening cells immediately and saves without duplicate pointer click', async () => {
  const f = frame();
  f.fire('pointerdown', 0);
  f.fire('pointermove', 63);
  f.fire('pointerup', 63);
  assert.equal(f.root.capture, null);
  assert.equal(f.fire('click', 63).defaultPrevented, true);
  const expected = [0, 9, 18, 27, 36, 45, 54, 63];
  assert.deepEqual(expected.map(index => f.cells[index].style.backgroundColor), expected.map(() => '#3153be'));
  await tick();
  assert.equal(f.jobs.length, 1);
  assert.deepEqual(f.jobs[0].action, { type: 'paint_pixels', cells: expected.map(cell => ({ cell, color: 0 })) });
  await f.complete(f.jobs[0]);
  assert.deepEqual(expected.map(index => f.cells[index].style.backgroundColor), expected.map(() => '#3153be'));
});

test('large strokes batch serially and preserve the frozen color across later strokes', async () => {
  const f = frame({ columns: 16, rows: 16 });
  f.fire('pointerdown', 0);
  for (let row = 0; row < 16; row++) {
    f.fire('pointermove', row * 16 + (row % 2 ? 15 : 0));
    f.fire('pointermove', row * 16 + (row % 2 ? 0 : 15));
  }
  f.setColor(1, '#e06050');
  f.fire('pointerup', 240);
  f.fire('pointerdown', 0);
  f.fire('pointerup', 0);
  await tick();
  assert.equal(f.jobs.length, 1, 'only one batch may be in flight');
  assert.equal(f.jobs[0].action.cells.length, 120);
  f.saved[200] = '#00aa00';
  f.authoritative();
  assert.equal(f.cells[0].style.backgroundColor, '#e06050', 'newer pending paint survives a public update');
  let completed = 0;
  while (completed < f.jobs.length) await f.complete(f.jobs[completed++]);
  const all = f.jobs.flatMap(job => job.action.cells);
  assert.equal(all.length, 257);
  assert.ok(all.slice(0, 256).every(item => item.color === 0));
  assert.deepEqual(all.at(-1), { cell: 0, color: 1 });
  assert.ok(f.jobs.every(job => job.action.cells.length <= 120));
  assert.equal(f.cells[0].style.backgroundColor, '#e06050');
});

test('failed save rolls back pending paint to the last authoritative colors', async () => {
  const f = frame({ svg: true });
  f.fire('pointerdown', 0);
  f.fire('pointerup', 7);
  await tick();
  f.fire('pointerdown', 8);
  f.fire('pointermove', 15);
  f.saved[3] = '#00aa00';
  await f.complete(f.jobs[0], false);
  assert.equal(f.jobs.length, 1, 'a failure discards unsaved buffered actions');
  assert.equal(f.cells[3].style.fill, '#00aa00');
  assert.equal(f.cells[8].style.fill, '#ffffff');
  assert.equal(f.root.capture, null);
});

test('keyboard activation works without data-action while invalid, secondary and disabled gestures do not dispatch', async () => {
  const f = frame();
  f.fire('pointerdown', 0, { button: 2 });
  f.fire('pointerdown', 0, { isPrimary: false });
  f.setActive(false);
  f.fire('pointerdown', 0);
  f.fire('click', 0, { detail: 0 });
  await tick();
  assert.equal(f.jobs.length, 0);
  f.setActive(true);
  assert.equal(f.fire('click', 14, { detail: 0 }).defaultPrevented, true);
  await tick();
  assert.deepEqual(f.jobs[0].action.cells, [{ cell: 14, color: 0 }]);
  await f.complete(f.jobs[0]);
  f.root.attrs['data-paint-grid'] = JSON.stringify({ action: 'paint_pixels', columns: 999, rows: 1, color: 0, colorValue: '#3153be' });
  f.fire('pointerdown', 0);
  f.fire('click', 0, { detail: 0 });
  await tick();
  assert.equal(f.jobs.length, 1);
});

test('lost capture flushes the final marks and cancellation prevents buffered or late work', async () => {
  const f = frame();
  f.fire('pointerdown', 0, { pointerType: 'touch' });
  f.fire('pointermove', 7, { pointerType: 'touch', buttons: 0 });
  f.fire('lostpointercapture', 7);
  await tick();
  assert.equal(f.jobs[0].action.cells.length, 8);
  f.fire('pointerdown', 8);
  f.fire('pointermove', 15);
  f.installed.cancel();
  f.jobs[0].resolve(true);
  await tick();
  assert.equal(f.jobs.length, 1);
  assert.ok(f.cells.every(node => node.style.backgroundColor === '#ffffff'));
});

function rasterFrame({ columns = 96, rows = 64, active = true, palette = ['#123456', '#e06050', '#00aa00'] } = {}) {
  const handlers = new Map(), jobs = [];
  let config = { action: 'paint_pixels', columns, rows, color: 0, colorValue: palette[0], palette, background: '#ffffff' };
  let saved = Array(columns * rows).fill('.');
  const rgb = value => {
    const hex = value.length === 4 ? [...value.slice(1)].map(char => char + char).join('') : value.slice(1);
    return [parseInt(hex.slice(0, 2), 16), parseInt(hex.slice(2, 4), 16), parseInt(hex.slice(4, 6), 16), 255];
  };
  class Element {
    attrs = {}; style = {}; isConnected = true; id = 'painting'; parentElement = null; capture = null;
    getAttribute(name) { return this.attrs[name] ?? null; }
    hasAttribute(name) { return Object.hasOwn(this.attrs, name); }
    setAttribute(name, value) { this.attrs[name] = String(value); }
    closest(selector) { return selector === '[data-paint-grid]' ? this : null; }
    getBoundingClientRect() { return { left: 20, top: 30, right: 980, bottom: 670, width: 960, height: 640 }; }
    setPointerCapture(id) { this.capture = id; }
    hasPointerCapture(id) { return this.capture === id; }
    releasePointerCapture() { this.capture = null; }
    contains(node) { return node === this; }
    focus() { document.activeElement = this; }
  }
  class HTMLElement extends Element {}
  class SVGElement extends Element {}
  class HTMLCanvasElement extends HTMLElement {
    width = 300; height = 150; tabIndex = -1; bitmap = new Uint8ClampedArray(300 * 150 * 4);
    context = {
      fillStyle: '#000', imageSmoothingEnabled: true,
      createImageData: (width, height) => ({ width, height, data: new Uint8ClampedArray(width * height * 4) }),
      putImageData: image => { this.bitmap = Uint8ClampedArray.from(image.data); },
      fillRect: (x, y) => { this.bitmap.set(rgb(this.context.fillStyle), (y * this.width + x) * 4); },
      strokeRect() {}, save() {}, restore() {},
    };
    getContext() { return this.context; }
  }
  const root = new HTMLCanvasElement();
  root.setAttribute('aria-label', 'Shared artwork');
  const document = { activeElement: null, querySelectorAll: () => root.isConnected ? [root] : [],
    addEventListener(name, handler) { if (!handlers.has(name)) handlers.set(name, []); handlers.get(name).push(handler); } };
  const write = () => { root.setAttribute('data-paint-grid', JSON.stringify(config)); root.setAttribute('data-paint-pixels', saved.join('')); };
  write();
  const options = { isActive: () => active, dispatch: action => new Promise(resolve => jobs.push({ action: JSON.parse(JSON.stringify(action)), resolve })) };
  const installed = vm.runInNewContext(`(${installPaintGestures.toString()})(options, validatePaintConfig, validatePaintPixels)`, { options, validatePaintConfig, validatePaintPixels, document, Element, HTMLElement, SVGElement, HTMLCanvasElement, Date, setTimeout, clearTimeout });
  function fire(name, cell = 0, extra = {}) {
    const event = { target: root, button: 0, buttons: 1, isPrimary: true, pointerId: 1, pointerType: 'mouse', clientX: 20 + (cell % config.columns + .5) / config.columns * 960, clientY: 30 + (Math.floor(cell / config.columns) + .5) / config.rows * 640, detail: 1, defaultPrevented: false, stopped: false,
      preventDefault() { this.defaultPrevented = true; }, stopImmediatePropagation() { this.stopped = true; }, ...extra };
    for (const handler of handlers.get(name) || []) { handler(event); if (event.stopped) break; }
    return event;
  }
  function authoritative() { write(); installed.reapply(); }
  async function complete(job, ok = true) {
    if (ok) for (const item of job.action.cells) saved[item.cell] = item.color.toString(32);
    authoritative(); job.resolve(ok); await tick();
  }
  return { root, jobs, fire, complete, installed, authoritative,
    pixel: cell => [...root.bitmap.slice(cell * 4, cell * 4 + 4)],
    saved: () => saved,
    setSaved(cell, color) { saved[cell] = color.toString(32); },
    setColor(color) { config = { ...config, color, colorValue: palette[color] }; authoritative(); },
    resize(columns, rows) { config = { ...config, columns, rows }; saved = Array(columns * rows).fill('.'); authoritative(); },
    focus() { root.focus(); fire('focusin'); },
    setActive(value) { active = value; },
  };
}

test('raster surface draws high-resolution previews while inactive using native backing dimensions', () => {
  for (const [columns, rows] of [[96, 64], [192, 128], [256, 256]]) {
    const f = rasterFrame({ columns, rows, active: false });
    assert.equal(f.root.width, columns);
    assert.equal(f.root.height, rows);
    assert.equal(f.root.style.aspectRatio, `${columns} / ${rows}`);
    assert.equal(f.root.style.imageRendering, 'pixelated');
    assert.equal(f.root.context.imageSmoothingEnabled, false);
    assert.deepEqual(f.pixel(columns * rows - 1), [255, 255, 255, 255]);
    f.setSaved(columns * rows - 1, 2); f.authoritative();
    assert.deepEqual(f.pixel(columns * rows - 1), [0, 170, 0, 255]);
    f.fire('pointerdown', 0); f.fire('pointerup', 0);
    assert.equal(f.jobs.length, 0);
  }
});

test('raster strokes interpolate at scaled coordinates and serialize bounded geometry-aware batches', async () => {
  const f = rasterFrame({ columns: 256, rows: 256 });
  f.fire('pointerdown', 0); f.fire('pointerup', 65535);
  for (const cell of [0, 257, 32896, 65535]) assert.deepEqual(f.pixel(cell), [18, 52, 86, 255]);
  await tick();
  assert.equal(f.jobs.length, 1);
  assert.equal(f.jobs[0].action.columns, 256);
  assert.equal(f.jobs[0].action.rows, 256);
  let complete = 0;
  while (complete < f.jobs.length) await f.complete(f.jobs[complete++]);
  assert.deepEqual(f.jobs.map(job => job.action.cells.length), [120, 120, 16]);
  assert.deepEqual(f.jobs.flatMap(job => job.action.cells.map(item => item.cell)), Array.from({ length: 256 }, (_, index) => index * 257));
  assert.equal(f.fire('click', 65535).defaultPrevented, true);
});

test('raster keyboard cursor uses arrows, row/document edges and explicit painting', async () => {
  const f = rasterFrame(); f.focus();
  for (const key of ['ArrowRight', 'ArrowDown', 'End', 'Enter']) assert.equal(f.fire('keydown', 0, { key }).defaultPrevented, true);
  await tick();
  assert.deepEqual(f.jobs[0].action.cells, [{ cell: 191, color: 0 }]);
  assert.match(f.root.getAttribute('aria-label'), /Column 96 of 96, row 2 of 64/);
  await f.complete(f.jobs[0]);
  f.fire('keydown', 0, { key: 'End', ctrlKey: true });
  f.fire('keydown', 0, { key: 'ArrowRight' });
  f.fire('keydown', 0, { key: ' ' });
  await tick();
  assert.deepEqual(f.jobs[1].action.cells, [{ cell: 6143, color: 0 }]);
  await f.complete(f.jobs[1]);
  f.fire('keydown', 0, { key: 'Home', ctrlKey: true });
  f.fire('keydown', 0, { key: 'ArrowLeft' });
  assert.match(f.root.getAttribute('aria-label'), /Column 1 of 96, row 1 of 64/);
  f.setActive(false); f.fire('keydown', 0, { key: 'Enter' }); await tick();
  assert.equal(f.jobs.length, 2);
});

test('raster optimistic marks survive public updates and rejected saves reveal latest authoritative pixels', async () => {
  const f = rasterFrame();
  f.fire('pointerdown', 0); f.fire('pointerup', 95); await tick();
  f.setSaved(0, 2); f.authoritative();
  assert.deepEqual(f.pixel(0), [18, 52, 86, 255]);
  f.setColor(1); f.fire('pointerdown', 96); f.fire('pointerup', 191);
  assert.deepEqual(f.pixel(96), [224, 96, 80, 255]);
  await f.complete(f.jobs[0], false);
  assert.deepEqual(f.pixel(0), [0, 170, 0, 255]);
  assert.deepEqual(f.pixel(96), [255, 255, 255, 255]);
  assert.equal(f.jobs.length, 1);
});

test('raster palette selections freeze per stroke without losing newer overlays on the same pixel', async () => {
  const f = rasterFrame();
  f.fire('pointerdown', 0); f.fire('pointermove', 95);
  f.setColor(1); f.fire('pointerup', 95); await tick();
  f.fire('pointerdown', 0); f.fire('pointerup', 0);
  await f.complete(f.jobs[0]);
  assert.deepEqual(f.pixel(0), [224, 96, 80, 255]);
  assert.ok(f.jobs[0].action.cells.every(item => item.color === 0));
  await f.complete(f.jobs[1]);
  assert.deepEqual(f.pixel(0), [224, 96, 80, 255]);
});

test('same-revision raster resize cancels buffered geometry and permits new geometry only after in-flight completion', async () => {
  const f = rasterFrame({ columns: 256, rows: 256 });
  f.fire('pointerdown', 0); f.fire('pointerup', 65535); await tick();
  f.resize(96, 64);
  assert.equal(f.root.capture, null);
  assert.equal(f.root.width, 96);
  assert.deepEqual(f.pixel(0), [255, 255, 255, 255]);
  f.fire('pointerdown', 6143); f.fire('pointerup', 6143);
  await tick(); assert.equal(f.jobs.length, 1);
  await f.complete(f.jobs[0], false);
  assert.equal(f.jobs.length, 2);
  assert.deepEqual(f.jobs[1].action, { type: 'paint_pixels', columns: 96, rows: 64, cells: [{ cell: 6143, color: 0 }] });
  await f.complete(f.jobs[1]);
  assert.deepEqual(f.pixel(6143), [18, 52, 86, 255]);
});

test('invalid raster markup is inert and cancellation before dispatch makes no request', async () => {
  const f = rasterFrame();
  f.root.setAttribute('data-paint-pixels', 'not enough pixels'); f.installed.reapply();
  f.fire('pointerdown', 0); f.fire('pointerup', 0); f.fire('keydown', 0, { key: 'Enter' });
  await tick(); assert.equal(f.jobs.length, 0);
  f.authoritative();
  f.fire('pointerdown', 0); f.fire('pointerup', 0); f.installed.cancel();
  await tick(); assert.equal(f.jobs.length, 0);
});
