import test from 'node:test';
import assert from 'node:assert/strict';
import { paintingProposal } from '../server/painting/index.mjs';
import { compileModule, reduceModule, renderModule, verifyModule } from '../server/runtime.mjs';
import { validateAgentAction } from '../server/space-agent-schema.mjs';

const owner = { id: 'iris', name: 'Iris' };
const visitor = { id: 'visitor', name: 'Visitor' };
const modules = new Map();
const moduleAt = (columns, rows) => {
  const key = `${columns}x${rows}`;
  if (!modules.has(key)) modules.set(key, (async () => {
    const proposal = await paintingProposal({ columns, rows });
    return { ...proposal, ...await compileModule(proposal.source) };
  })());
  return modules.get(key);
};
const blank = () => ({ projects: [], contributions: [], extras: {} });
const artwork = () => ({
  projects: [], contributions: [],
  extras: {
    canvas: {
      iris: { actorId: 'iris', color: 2, marks: { 0: [2, 1], 800: [5, 2], 1535: [0, 3] } },
      visitor: { actorId: 'visitor', color: 4, marks: { 0: [4, 9], 49: [4, 10], 1535: [6, 11] } },
    },
    notes: { keep: { actorId: 'someone-else', text: 'Keep this unrelated participation record.' } },
  },
});
const fill = (columns, rows, color = 3) => ({ type: 'fill_canvas', columns, rows, color });
const shapes = (columns, rows, values) => ({ type: 'paint_shapes', columns, rows, shapes: values });
const shape = (kind, x1, y1, x2, y2, color, filled = true, width = 1) => ({ kind, x1, y1, x2, y2, color, filled, width });
const pixels = async (module, state, actor = owner) => {
  const html = await renderModule(module.bundle, state, actor);
  assert.ok(html.length < 180000, 'Rendered artwork remains inside the existing HTML budget');
  return html.match(/data-paint-pixels="([^"]*)"/)[1];
};

test('the published agent tool schemas accept the actual bounded painting operations', async () => {
  const module = await moduleAt(192, 128), config = module.meta.agent;
  const actions = [
    { type: 'paint_pixels', columns: 192, rows: 128, cells: [{ cell: 24575, color: 3 }] },
    fill(192, 128),
    shapes(192, 128, [shape('rect', 0, 0, 191, 127, 3), shape('ellipse', 20, 20, 30, 40, 2)]),
    { type: 'flood_fill', columns: 192, rows: 128, x: 191, y: 127, color: 3 },
  ];
  for (const { type, ...args } of actions) {
    assert.ok(config.actions.some(action => action.name === type));
    assert.deepEqual(validateAgentAction(config, type, args), args);
    assert.ok(JSON.stringify(args).length < 8000, 'The model can request the whole operation within the existing tool argument budget');
  }
});

for (const [columns, rows] of [[48, 32], [96, 64], [192, 128], [256, 256]]) {
  test(`one fill colors every pixel of a ${columns}×${rows} canvas over existing artwork`, async () => {
    const module = await moduleAt(columns, rows), state = artwork(), before = structuredClone(state);
    const next = await reduceModule(module.bundle, state, fill(columns, rows), owner);
    assert.equal(await pixels(module, next), '3'.repeat(columns * rows), 'No incomplete row, uncovered edge, or older artwork remains visible');
    assert.deepEqual(state, before, 'The reducer does not mutate its input');
    assert.deepEqual(next.extras.canvas.visitor, before.extras.canvas.visitor, 'Covering artwork leaves its original contributor record intact');
    assert.deepEqual(next.extras.notes, before.extras.notes);
    assert.ok(JSON.stringify(next).length < 500000, 'The complete fill fits the existing state budget');

    const withDetail = await reduceModule(module.bundle, next, {
      type: 'paint_pixels', columns, rows, cells: [{ cell: columns * rows - 1, color: 1 }],
    }, visitor);
    assert.equal(await pixels(module, withDetail), '3'.repeat(columns * rows - 1) + '1', 'Manual painting still wins over a prior fill');
    const refilled = await reduceModule(module.bundle, withDetail, fill(columns, rows, 6), owner);
    assert.equal(await pixels(module, refilled), '6'.repeat(columns * rows), 'A later fill replaces all visible marks, including newer visitor details');
    assert.deepEqual(refilled.extras.canvas.visitor, withDetail.extras.canvas.visitor);
    const revealed = await reduceModule(module.bundle, refilled, { type: 'clear_marks' }, owner);
    assert.equal(await pixels(module, revealed), await pixels(module, { ...withDetail, extras: { ...withDetail.extras, canvas: { visitor: withDetail.extras.canvas.visitor } } }), 'Clear my marks reveals the untouched visitor artwork');
  });
}

test('fills survive successive resolution increases and odd-sized resampling without seams', async () => {
  let state = artwork();
  for (const [columns, rows] of [[48, 32], [96, 64], [192, 128], [127, 93], [256, 256]]) {
    const module = await moduleAt(columns, rows);
    if (state.extras.canvas.iris.format === 2) assert.equal(await pixels(module, state), '3'.repeat(columns * rows));
    state = await reduceModule(module.bundle, state, fill(columns, rows), owner);
    assert.equal(await pixels(module, state), '3'.repeat(columns * rows));
    assert.deepEqual(state.extras.canvas.visitor, artwork().extras.canvas.visitor);
    assert.ok(JSON.stringify(state).length < 500000);
  }
});

test('rectangle and line batches draw inclusive, normalized bounds and apply in listed order', async () => {
  const columns = 12, rows = 10, module = await moduleAt(columns, rows);
  const next = await reduceModule(module.bundle, blank(), shapes(columns, rows, [
    shape('rect', 7, 5, 2, 2, 3),
    shape('line', 0, 3, 11, 3, 4),
    shape('line', 5, 0, 5, 9, 1),
  ]), owner);
  const expected = Array(columns * rows).fill('.');
  for (let y = 2; y <= 5; y++) for (let x = 2; x <= 7; x++) expected[y * columns + x] = '3';
  for (let x = 0; x < columns; x++) expected[3 * columns + x] = '4';
  for (let y = 0; y < rows; y++) expected[y * columns + 5] = '1';
  assert.equal(await pixels(module, next), expected.join(''));
});

test('filled and outlined ellipses stay symmetric and inside their declared bounds', async () => {
  const columns = 15, rows = 13, module = await moduleAt(columns, rows);
  for (const filled of [true, false]) {
    const next = await reduceModule(module.bundle, blank(), shapes(columns, rows, [shape('ellipse', 3, 2, 11, 10, 2, filled)]), owner);
    const result = await pixels(module, next);
    assert.ok(result.includes('2'));
    for (let y = 0; y < rows; y++) for (let x = 0; x < columns; x++) {
      const value = result[y * columns + x];
      if (x < 3 || x > 11 || y < 2 || y > 10) assert.equal(value, '.', `Nothing paints outside the ellipse at ${x},${y}`);
      else {
        assert.equal(value, result[y * columns + 14 - x], `Ellipse is horizontally symmetric at ${x},${y}`);
        assert.equal(value, result[(12 - y) * columns + x], `Ellipse is vertically symmetric at ${x},${y}`);
      }
    }
    assert.equal(result[6 * columns + 7], filled ? '2' : '.', 'Filled shapes cover their center and outlined shapes retain it');
    for (const [x, y] of [[3, 2], [11, 2], [3, 10], [11, 10]]) assert.equal(result[y * columns + x], '.', 'The bounding-box corners are not part of an ellipse');
  }
});

test('flood fill follows visible four-neighbor regions and does not cross another person’s outline', async () => {
  const columns = 12, rows = 10, module = await moduleAt(columns, rows);
  const outlined = await reduceModule(module.bundle, blank(), shapes(columns, rows, [shape('rect', 2, 2, 9, 7, 4, false)]), visitor);
  const visitorRecord = structuredClone(outlined.extras.canvas.visitor);
  const next = await reduceModule(module.bundle, outlined, { type: 'flood_fill', columns, rows, x: 5, y: 4, color: 3 }, owner);
  const outside = await reduceModule(module.bundle, next, { type: 'flood_fill', columns, rows, x: 0, y: 0, color: 0 }, owner);
  const expected = Array(columns * rows).fill('0');
  for (let y = 2; y <= 7; y++) for (let x = 2; x <= 9; x++) expected[y * columns + x] = x === 2 || x === 9 || y === 2 || y === 7 ? '4' : '3';
  assert.equal(await pixels(module, outside), expected.join(''));
  assert.deepEqual(outside.extras.canvas.visitor, visitorRecord);
  const noChange = await reduceModule(module.bundle, outside, { type: 'flood_fill', columns, rows, x: 5, y: 4, color: 3 }, owner);
  assert.equal(await pixels(module, noChange), expected.join(''), 'Flooding an already matching region is harmless');
});

test('flood fill treats opaque white and untouched background as the same visible color', async () => {
  const columns = 8, rows = 8, module = await moduleAt(columns, rows);
  const whiteLine = await reduceModule(module.bundle, blank(), shapes(columns, rows, [shape('line', 4, 0, 4, 7, 7)]), visitor);
  const next = await reduceModule(module.bundle, whiteLine, { type: 'flood_fill', columns, rows, x: 0, y: 0, color: 3 }, owner);
  assert.equal(await pixels(module, next), '3'.repeat(columns * rows));
  assert.deepEqual(next.extras.canvas.visitor, whiteLine.extras.canvas.visitor);
});

test('one-cell and narrow canvases support fill, collapsed shapes, and flood fill', async () => {
  for (const [columns, rows] of [[1, 1], [1, 19], [23, 1]]) {
    const module = await moduleAt(columns, rows);
    let state = await reduceModule(module.bundle, blank(), fill(columns, rows), owner);
    assert.equal(await pixels(module, state), '3'.repeat(columns * rows));
    state = await reduceModule(module.bundle, state, shapes(columns, rows, [shape('ellipse', 0, 0, columns - 1, rows - 1, 2)]), owner);
    assert.equal(await pixels(module, state), '2'.repeat(columns * rows));
    state = await reduceModule(module.bundle, state, shapes(columns, rows, [shape('line', 0, 0, 0, 0, 1)]), owner);
    assert.equal(await pixels(module, state), '1' + '2'.repeat(columns * rows - 1), 'A zero-length one-pixel line paints exactly its endpoint');
    state = await reduceModule(module.bundle, state, { type: 'flood_fill', columns, rows, x: 0, y: 0, color: 0 }, owner);
    assert.equal(await pixels(module, state), '0' + '2'.repeat(columns * rows - 1));
  }
});

test('diagonal thick lines preserve their footprint when their endpoints are reversed', async () => {
  const columns = 17, rows = 17, module = await moduleAt(columns, rows);
  for (const width of [1, 3, 8]) {
    const forward = await reduceModule(module.bundle, blank(), shapes(columns, rows, [shape('line', 3, 3, 13, 13, 2, false, width)]), owner);
    const reverse = await reduceModule(module.bundle, blank(), shapes(columns, rows, [shape('line', 13, 13, 3, 3, 2, false, width)]), owner);
    const result = await pixels(module, forward);
    assert.equal(result, await pixels(module, reverse));
    for (let n = 3; n <= 13; n++) assert.equal(result[n * columns + n], '2', 'Every diagonal center pixel is connected');
    if (width > 1) assert.equal(result[8 * columns + 9], '2', 'A thick line paints beside its center');
    assert.equal(result[0 * columns + 16], '.', 'A distant opposite corner remains unchanged');
  }
});

test('oblique lines retain exact boundary pixels after scanline rounding', async () => {
  const columns = 23, rows = 17, module = await moduleAt(columns, rows);
  const line = shape('line', 4, 14, 16, 5, 3, false, 4);
  const next = await reduceModule(module.bundle, blank(), shapes(columns, rows, [line]), owner);
  const expected = Array(columns * rows).fill('.');
  const dx = line.x2 - line.x1, dy = line.y2 - line.y1, length = dx * dx + dy * dy;
  for (let y = 0; y < rows; y++) for (let x = 0; x < columns; x++) {
    const px = x - line.x1, py = y - line.y1, projection = px * dx + py * dy;
    // Integer cross-products give an exact distance comparison, including
    // boundary pixels that floating point projection can place just outside.
    const inside = projection <= 0
      ? 4 * (px * px + py * py) <= line.width * line.width
      : projection >= length
        ? 4 * ((x - line.x2) ** 2 + (y - line.y2) ** 2) <= line.width * line.width
        : 4 * (px * dy - py * dx) ** 2 <= line.width * line.width * length;
    if (inside) expected[y * columns + x] = '3';
  }
  assert.equal(await pixels(module, next), expected.join(''), 'Scanline bounds must not omit pixels that satisfy the exact distance test');
  for (const [x, y] of [[14, 4], [14, 9], [6, 10]]) assert.equal(expected[y * columns + x], '3');
});

test('the maximum allowed shape work executes while excessive work rejects atomically', async () => {
  const columns = 256, rows = 256, module = await moduleAt(columns, rows), state = blank();
  const values = Array.from({ length: 8 }, (_, index) => shape('line', 0, 0, columns - 1, rows - 1, index % 7, false, 32));
  const next = await reduceModule(module.bundle, state, shapes(columns, rows, values), owner);
  const result = await pixels(module, next);
  assert.equal(result[0], '0');
  assert.equal(result.at(-1), '0');
  assert.equal(result[255], '.');
  const before = JSON.stringify(next);
  await assert.rejects(reduceModule(module.bundle, next, shapes(columns, rows, [...values, values[0]]), owner), /eight canvas areas/);
  assert.equal(JSON.stringify(next), before);
});

test('a full batch of wide vertical and near-vertical lines stays inside the reducer budget', async () => {
  const columns = 256, rows = 256, module = await moduleAt(columns, rows);
  for (const x2 of [128, 129]) {
    const values = Array.from({ length: 32 }, (_, index) => shape('line', 128, 0, x2, 255, index % 7, false, 32));
    const next = await reduceModule(module.bundle, blank(), shapes(columns, rows, values), owner);
    const result = await pixels(module, next);
    assert.equal(result[128], '3');
    assert.equal(result[255 * columns + x2], '3');
    assert.equal(result[0], '.');
    assert.equal(result.at(-1), '.');
  }
});

test('new operations reject stale geometry and malformed batches atomically', async () => {
  const columns = 48, rows = 32, module = await moduleAt(columns, rows), state = artwork(), before = structuredClone(state);
  const validShape = shape('rect', 1, 1, 4, 4, 3);
  const malformed = [
    { ...fill(columns, rows), columns: 96 }, { ...fill(columns, rows), rows: 64 },
    fill(columns, rows, -1), fill(columns, rows, 8), { ...fill(columns, rows), actorId: visitor.id },
    shapes(columns, rows, []), shapes(columns, rows, Array.from({ length: 33 }, () => validShape)),
    shapes(columns, rows, [validShape, { ...validShape, x2: columns }]),
    shapes(columns, rows, [{ ...validShape, y1: -1 }]), shapes(columns, rows, [{ ...validShape, x1: 0.5 }]),
    shapes(columns, rows, [{ ...validShape, kind: 'triangle' }]), shapes(columns, rows, [{ ...validShape, color: 8 }]),
    shapes(columns, rows, [{ ...validShape, filled: 'true' }]), shapes(columns, rows, [{ ...validShape, width: 0 }]),
    shapes(columns, rows, [{ ...validShape, width: 33 }]), shapes(columns, rows, [{ ...validShape, actorId: visitor.id }]),
    { ...shapes(columns, rows, [validShape]), rows: 64 },
    { type: 'flood_fill', columns, rows, x: columns, y: 0, color: 3 },
    { type: 'flood_fill', columns, rows, x: 0, y: -1, color: 3 },
    { type: 'flood_fill', columns, rows, x: 0, y: 0, color: 8 },
    { type: 'flood_fill', columns: 96, rows, x: 0, y: 0, color: 3 },
    { type: 'flood_fill', columns, rows, x: 0, y: 0, color: 3, actorId: visitor.id },
    { type: 'fill_canvas', columns, rows },
    { type: 'flood_fill', columns, rows, x: 0, y: 0 },
    shapes(columns, rows, [{ kind: 'rect', x1: 1, y1: 1, x2: 4, y2: 4, color: 3, filled: true }]),
    shapes(columns, rows, [{ kind: 'rect', x1: 1, y1: 1, x2: 4, y2: 4, color: 3, width: 1 }]),
    shapes(columns, rows, [{ ...validShape, x1: NaN }]),
    shapes(columns, rows, [{ ...validShape, x2: Infinity }]),
  ];
  for (const action of malformed) {
    await assert.rejects(reduceModule(module.bundle, state, action, owner), JSON.stringify(action));
    assert.deepEqual(state, before, 'Invalid operations cannot partially apply or mutate saved input');
  }
  const impostor = { ...state, extras: { ...state.extras, canvas: { ...state.extras.canvas, iris: { ...state.extras.canvas.iris, actorId: visitor.id } } } };
  for (const action of [fill(columns, rows), shapes(columns, rows, [validShape]), { type: 'flood_fill', columns, rows, x: 0, y: 0, color: 3 }]) {
    await assert.rejects(reduceModule(module.bundle, impostor, action, owner), /Not your layer/);
  }
});

function denseRawRecord(columns, rows, actorId, uniformColor) {
  const chunks = {};
  for (let cy = 0; cy < Math.ceil(rows / 16); cy++) for (let cx = 0; cx < Math.ceil(columns / 16); cx++) {
    let data = '';
    for (let i = 0; i < 256; i++) {
      const x = cx * 16 + i % 16, y = cy * 16 + Math.floor(i / 16);
      data += x < columns && y < rows ? `${uniformColor ?? (x + y) % 7}000001` : '.......';
    }
    chunks[cy * Math.ceil(columns / 16) + cx] = data;
  }
  return { actorId, format: 2, color: 0, sequence: 1, planes: [{ columns, rows, chunks }] };
}

test('a single flood fill recolors a dense 256×256 region inside the existing reducer budget', async () => {
  const columns = 256, rows = 256, module = await moduleAt(columns, rows);
  for (const contrastingPixel of [false, true]) {
    const record = denseRawRecord(columns, rows, visitor.id, 7);
    const expected = Array(columns * rows).fill('3');
    if (contrastingPixel) {
      record.planes[0].chunks[136] = '4000001' + record.planes[0].chunks[136].slice(7);
      expected[128 * columns + 128] = '4';
    }
    const state = { projects: [], contributions: [], extras: { canvas: { visitor: record } } };
    const before = JSON.stringify(state);
    const next = await reduceModule(module.bundle, state, { type: 'flood_fill', columns, rows, x: 255, y: 255, color: 3 }, owner);
    assert.equal(await pixels(module, next), expected.join(''), 'Flood traversal covers the region while preserving a contrasting obstacle');
    assert.equal(JSON.stringify(state), before);
    assert.deepEqual(next.extras.canvas.visitor, state.extras.canvas.visitor);
    assert.ok(JSON.stringify(next).length < 500000);
  }
});

test('a tiny flood region in dense multicolor 256×256 artwork stays within the reducer budget', async () => {
  const columns = 256, rows = 256, module = await moduleAt(columns, rows);
  const record = denseRawRecord(columns, rows, visitor.id);
  const state = { projects: [], contributions: [], extras: { canvas: { visitor: record } } };
  const before = JSON.stringify(state);
  const next = await reduceModule(module.bundle, state, { type: 'flood_fill', columns, rows, x: 0, y: 0, color: 3 }, owner);
  const expected = Array.from({ length: columns * rows }, (_, cell) => String((cell % columns + Math.floor(cell / columns)) % 7));
  expected[0] = '3';
  assert.equal(await pixels(module, next), expected.join(''), 'Only the connected source pixel changes despite decoding the entire multicolor canvas');
  assert.equal(JSON.stringify(state), before);
  assert.deepEqual(next.extras.canvas.visitor, record);
  assert.ok(JSON.stringify(next).length < 500000);
});

for (const [columns, rows] of [[192, 128], [256, 256]]) {
  test(`full ${columns}×${rows} fill over dense persisted artwork runs and publishes under existing sandbox limits`, { timeout: 30000 }, async () => {
    const module = await moduleAt(columns, rows);
    const state = { projects: [], contributions: [], extras: { canvas: { visitor: denseRawRecord(columns, rows, visitor.id) } } };
    const before = JSON.stringify(state);
    assert.ok(before.length < 500000);
    const next = await reduceModule(module.bundle, state, fill(columns, rows), owner);
    assert.equal(JSON.stringify(state), before);
    assert.deepEqual(next.extras.canvas.visitor, state.extras.canvas.visitor);
    assert.ok(JSON.stringify(next).length < 500000);
    assert.equal(await pixels(module, next), '3'.repeat(columns * rows));
    const result = await verifyModule(module.source, module.tests, next, { owner, visitor });
    assert.equal(result.ok, true, JSON.stringify(result.checks.filter(check => !check.ok)));
    assert.deepEqual(result.candidateState, next, 'Publication cannot flatten or rewrite another person’s dense saved layer');
  });
}
