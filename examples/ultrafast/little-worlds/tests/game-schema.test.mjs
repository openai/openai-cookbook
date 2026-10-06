import test from 'node:test';
import assert from 'node:assert/strict';
import { build } from 'esbuild';
import { getQuickJS } from 'quickjs-emscripten';
import { gameValidationCode, validateGameConfig, validateGameState, validateGameView } from '../shared/game-schema.mjs';

const actor = { id: 'player_1', name: 'Player' };
const view = objects => ({ width: 260, height: 260, objects });
const bytes = value => Buffer.byteLength(JSON.stringify(value), 'utf8');

async function evaluate(code, expression) {
  const quickjs = await getQuickJS();
  const runtime = quickjs.newRuntime();
  runtime.setMemoryLimit(16 * 1024 * 1024);
  const deadline = Date.now() + 1000;
  runtime.setInterruptHandler(() => Date.now() > deadline);
  const context = runtime.newContext();
  try {
    const result = context.evalCode(`${code}\n${expression}`);
    if (result.error) {
      const error = context.dump(result.error);
      result.error.dispose();
      throw new Error(error.message || String(error));
    }
    try { return context.dump(result.value); }
    finally { result.value.dispose(); }
  } finally {
    context.dispose();
    runtime.dispose();
  }
}

test('game schema accepts bounded scenes and preserves inputs and omitted defaults', () => {
  const config = { id: 'maze-1', saveAction: 'save_maze' };
  const state = { actorId: actor.id, score: 4, position: { x: 1, y: 2 }, pellets: [1, 3, 5] };
  const scene = {
    ...view([
      { id: 'wall:1', type: 'rect', width: 12, height: 12, radius: 2, fill: '#174b9a' },
      { id: 'player', type: 'circle', x: 50, y: 60, radius: 8, fill: 'gold', rotation: -90 },
      { id: 'path', type: 'path', d: 'M0 0L12 12Z', stroke: 'rgb(10, 20, 30)', lineWidth: 1 },
      { id: 'label', type: 'text', text: '<Ready & steady>', fontSize: 18, align: 'center' },
    ]),
    background: '#050c24', values: { score: 4, status: 'Ready' }, finished: false,
  };
  const before = JSON.stringify({ config, state, scene });
  assert.equal(validateGameConfig(config), config);
  assert.equal(validateGameState(state, actor), state);
  assert.equal(validateGameView(scene), scene);
  assert.equal(JSON.stringify({ config, state, scene }), before);
  assert.equal(Object.hasOwn(config, 'tickMs'), false);
  assert.equal(Object.hasOwn(scene.objects[0], 'x'), false);
  const nullPrototypeState = Object.assign(Object.create(null), { actorId: actor.id });
  assert.equal(validateGameState(nullPrototypeState, actor), nullPrototypeState);
});

test('game config rejects reserved namespaces, unsupported keys, and out-of-range ticks', () => {
  for (const config of [
    {}, { id: '' }, { id: '0maze' }, { id: '__proto__' }, { id: 'constructor' },
    { id: 'prototype' }, { id: 'x'.repeat(65) }, { id: 'maze', tickMs: 15 },
    { id: 'maze', tickMs: 101 }, { id: 'maze', tickMs: 16.5 }, { id: 'maze', tickMs: NaN },
    { id: 'maze', saveAction: 'constructor' }, { id: 'maze', saveAction: 'bad action' },
    { id: 'maze', unexpected: true }, { id: 'maze', tickMs: undefined },
  ]) assert.throws(() => validateGameConfig(config));
  for (const tickMs of [16, 50, 100]) assert.equal(validateGameConfig({ id: 'maze', tickMs }).tickMs, tickMs);
});

test('game state requires its own matching actor and plain JSON data without executing accessors', () => {
  let reads = 0;
  const accessor = Object.defineProperty({ actorId: actor.id }, 'score', { enumerable: true, get() { reads++; return 1; } });
  const actorAccessor = Object.defineProperty({ name: 'Player' }, 'id', { enumerable: true, get() { reads++; return actor.id; } });
  const nonenumerable = Object.defineProperty({ actorId: actor.id }, 'score', { value: 1 });
  const symbol = { actorId: actor.id, [Symbol('score')]: 1 };
  const sparse = [1, , 3];
  const extraArray = Object.assign([1, 2], { extra: 3 });
  const customArray = Object.setPrototypeOf([1], {});
  const cycle = { actorId: actor.id }; cycle.self = cycle;
  for (const state of [
    {}, { actorId: 'someone_else' }, Object.create({ actorId: actor.id }),
    accessor, nonenumerable, symbol, cycle,
    ...[new Date(), new Map(), new Set(), new Number(1), new Uint8Array(2), sparse, extraArray, customArray, undefined, Infinity, NaN, 1n, () => 1]
      .map(value => ({ actorId: actor.id, value })),
    ...['__proto__', 'constructor', 'prototype'].map(key => ({ actorId: actor.id, nested: JSON.parse(`{"${key}":1}`) })),
  ]) assert.throws(() => validateGameState(state, actor));
  assert.throws(() => validateGameState({ actorId: actor.id }, actorAccessor));
  assert.equal(reads, 0, 'validation must inspect descriptors before reading values');
  const shared = { score: 1 };
  assert.doesNotThrow(() => validateGameState({ actorId: actor.id, first: shared, second: shared }, actor));
});

test('game state enforces depth 16 and exact UTF-8 JSON byte limits', () => {
  let nested = 1;
  for (let depth = 0; depth < 15; depth++) nested = { next: nested };
  assert.doesNotThrow(() => validateGameState({ actorId: actor.id, nested }, actor));
  assert.throws(() => validateGameState({ actorId: actor.id, nested: { next: nested } }, actor), /deeply/);
  for (const prefix of ['', 'é', '€', '🎮', '\ud800', '\udc00', '\u0001', '"\\\n', '\b\t\n\f\r', '\u0000\u001f', '\u007f\u0080\u07ff\u0800']) {
    const state = { actorId: actor.id, text: prefix };
    state.text += 'a'.repeat(32_000 - bytes(state));
    assert.equal(bytes(state), 32_000);
    assert.equal(validateGameState(state, actor), state);
    assert.throws(() => validateGameState({ ...state, text: state.text + 'a' }, actor), /32000 JSON bytes/);
  }
});

test('game view rejects ambiguous shapes, nonfinite geometry, unsafe colors and oversized collections', () => {
  const rect = { id: 'wall', type: 'rect', width: 12, height: 12 };
  const invalidShapes = [
    { ...rect, type: 'image' }, { id: 'wall', type: 'rect', width: 12 },
    { ...rect, id: '' }, { ...rect, id: 'x'.repeat(101) },
    { ...rect, x: Infinity }, { ...rect, y: NaN }, { ...rect, x: 10_001 },
    { ...rect, rotation: -10_001 }, { ...rect, width: -1 }, { ...rect, radius: -1 },
    { ...rect, lineWidth: -1 }, { ...rect, fill: 'url(https://example.com)' },
    { ...rect, fill: 'URL (asset)' }, { ...rect, stroke: 'x'.repeat(41) },
    { ...rect, onclick: 'doSomething()' },
    { id: 'dot', type: 'circle', radius: -1 },
    { id: 'line', type: 'path', d: 'M'.repeat(6001) },
    { id: 'label', type: 'text', text: 'x'.repeat(301) },
    { id: 'label', type: 'text', text: 'Hello', fontSize: 7 },
    { id: 'label', type: 'text', text: 'Hello', fontSize: 121 },
    { id: 'label', type: 'text', text: 'Hello', align: 'start' },
  ];
  for (const shape of invalidShapes) assert.throws(() => validateGameView(view([shape])));
  for (const scene of [
    { ...view([]), width: 63 }, { ...view([]), height: 2049 }, { ...view([]), finished: 'true' },
    view([rect, { ...rect }]), view(Array.from({ length: 1001 }, (_, id) => ({ ...rect, id: String(id) }))),
    { ...view([]), values: { score: true } }, { ...view([]), values: { 'bad key': 1 } },
    { ...view([]), values: { status: 'x'.repeat(501) } },
    { ...view([]), values: Object.fromEntries(Array.from({ length: 31 }, (_, index) => [`score${index}`, index])) },
  ]) assert.throws(() => validateGameView(scene));
  assert.doesNotThrow(() => validateGameView(view(Array.from({ length: 1000 }, (_, id) => ({ ...rect, id: String(id) })))));
});

test('game view enforces the exact 200000-byte serialized limit', () => {
  const scene = view(Array.from({ length: 34 }, (_, index) => ({ id: `path:${index}`, type: 'path', d: '' })));
  let remaining = 200_000 - bytes(scene);
  for (const shape of scene.objects) {
    const size = Math.min(remaining, 6000);
    shape.d = ' '.repeat(size);
    remaining -= size;
  }
  assert.equal(remaining, 0);
  assert.equal(bytes(scene), 200_000);
  assert.equal(validateGameView(scene), scene);
  scene.objects.at(-1).d += ' ';
  assert.throws(() => validateGameView(scene), /200000 JSON bytes/);
});

test('game paths bound numeric geometry while accepting SVG commands and exponent notation', () => {
  const path = d => view([{ id: 'line', type: 'path', d }]);
  for (const d of [
    '', 'M0 0L10000 -10000Z', 'm.5-.5 h+1e2 v-1E-2 z',
    'M0,0 C1 2 3 4 5 6 S7 8 9 10 Q11 12 13 14 T15 16',
    'M0 0 A10 20 45 0 1 40 50 a5 5 0 1 0 -10 -10',
  ]) assert.doesNotThrow(() => validateGameView(path(d)), d);
  for (const d of [
    'M10001 0', 'M-10001 0', 'M1e999 0', 'MNaN 0', 'MInfinity 0',
    'M0 0R1 2', 'M0 0<script>', 'M0 0;L1 1',
  ]) assert.throws(() => validateGameView(path(d)), /path/, d);
});

test('serialized game policy works in QuickJS without TextEncoder and preserves rejection rules', async () => {
  const result = await evaluate(gameValidationCode, `(() => {
    const actor = { id: 'player_1', name: 'Player' };
    const state = { actorId: actor.id, text: '🎮' };
    let reads = 0;
    const getter = Object.defineProperty({ actorId: actor.id }, 'score', { enumerable: true, get() { reads++; return 1; } });
    let rejected = false;
    try { validateGameState(getter, actor); } catch { rejected = true; }
    const oversized = { actorId: actor.id, text: '🎮'.repeat(8000) };
    let largeRejected = false;
    try { validateGameState(oversized, actor); } catch { largeRejected = true; }
    return {
      noEncoder: typeof TextEncoder === 'undefined',
      identity: validateGameState(state, actor) === state,
      tick: validateGameConfig({ id: 'maze' }).tickMs === undefined,
      scene: validateGameView({ width: 64, height: 64, objects: [] }).width,
      rejected, largeRejected, reads
    };
  })()`);
  assert.deepEqual(result, { noEncoder: true, identity: true, tick: true, scene: 64, rejected: true, largeRejected: true, reads: 0 });
});

test('minified browser builds preserve serialized validator names and dependencies', async () => {
  const output = await build({
    entryPoints: [new URL('../shared/game-schema.mjs', import.meta.url).pathname],
    bundle: true, write: false, format: 'iife', globalName: 'GameSchema', platform: 'browser',
    minify: true, target: 'es2020', logLevel: 'silent',
  });
  const serialized = await evaluate(output.outputFiles[0].text, 'GameSchema.gameValidationCode');
  const result = await evaluate(serialized, `(() => {
    const actor = { id: 'player_1', name: 'Player' };
    const state = validateGameState({ actorId: actor.id, score: 7 }, actor);
    const config = gameValidators.validateGameConfig({ id: 'maze', tickMs: 20 });
    const view = validateGameView({ width: 64, height: 64, objects: [{ id: 'p', type: 'circle', radius: 2 }] });
    let rejected = false;
    try { validateGameState({ actorId: 'other' }, actor); } catch { rejected = true; }
    return { score: state.score, tick: config.tickMs, radius: view.objects[0].radius, rejected };
  })()`);
  assert.deepEqual(result, { score: 7, tick: 20, radius: 2, rejected: true });
});
