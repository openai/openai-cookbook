import test from 'node:test';
import assert from 'node:assert/strict';
import { compileGameModule, gameInit, gameStep, gameView } from '../server/runtime.mjs';

const actor = { id: 'game-reviewer', name: 'Reviewer' };
const game = `{
  init(saved, actor) { return saved || { actorId: actor.id, count: 0 }; },
  step(state) { return { ...state, count: state.count + 1 }; },
  view(state) { return { width: 260, height: 260, objects: [], values: { count: state.count } }; }
}`;

test('public game bundles exclude unrelated effectful private initializers and statements', async () => {
  const privateCases = [
    `const privateNotes = Object.freeze({ text: 'PRIVATE_FREEZE' });`,
    `const privateNotes = {}; Object.assign(privateNotes, { text: 'PRIVATE_ASSIGN' });`,
    `const privateNotes = (() => { throw new Error('PRIVATE_IIFE'); })();`,
    `const privateNotes = ['PRIVATE_MAP'].map(text => ({ text }));`,
    `export const meta = Object.freeze({ title: 'PRIVATE_META' });`,
  ];
  for (const privateSource of privateCases) {
    const bundle = await compileGameModule(`${privateSource}\nexport const game = ${game};`);
    assert.doesNotMatch(bundle, /PRIVATE_|privateNotes/);
    assert.equal((await gameInit(bundle, null, actor)).count, 0);
  }
});

test('public game dependency closure retains transitive constants and functions', async () => {
  const bundle = await compileGameModule(`
    const settings = Object.freeze({ initial: 4, increment: 3 });
    function advance(value) { return value + settings.increment; }
    const makeState = actor => ({ actorId: actor.id, count: settings.initial });
    const privateNotes = Object.freeze({ text: 'PRIVATE_UNRELATED' });
    export const game = {
      init(saved, actor) { return saved || makeState(actor); },
      step(state) { return { ...state, count: advance(state.count) }; },
      view(state) { return { width: 260, height: 260, objects: [], values: { count: state.count } }; }
    };
  `);
  assert.doesNotMatch(bundle, /PRIVATE_UNRELATED/);
  const initial = await gameInit(bundle, null, actor);
  assert.equal(initial.count, 4);
  const next = await gameStep(bundle, initial, { type: 'tick', deltaMs: 50 }, actor);
  assert.equal(next.count, 7);
  assert.equal((await gameView(bundle, next, actor)).values.count, 7);
});

test('comma declaration splitting excludes private siblings of required bindings', async () => {
  const bundle = await compileGameModule(`
    const privateBefore = (() => { throw Error('PRIVATE_BEFORE'); })(),
      initial = 8,
      privateAfter = Object.freeze({ text: 'PRIVATE_AFTER' });
    export const game = ${game.replace('count: 0', 'count: initial')};
  `);
  assert.doesNotMatch(bundle, /PRIVATE_BEFORE|PRIVATE_AFTER/);
  assert.equal((await gameInit(bundle, null, actor)).count, 8);
});

test('nested lexical shadowing does not expose similarly named private bindings', async () => {
  const bundle = await compileGameModule(`
    const settings = Object.freeze({ text: 'PRIVATE_SHADOWED' });
    function initialCount(settings) {
      function add(value) { const settings = 3; return value + settings; }
      return add(settings);
    }
    export const game = ${game.replace('count: 0', 'count: initialCount(5)')};
  `);
  assert.doesNotMatch(bundle, /PRIVATE_SHADOWED/);
  assert.equal((await gameInit(bundle, null, actor)).count, 8);
});

test('an explicit alias export selects the correct public game binding', async () => {
  const bundle = await compileGameModule(`
    const privateNotes = Object.freeze({ text: 'PRIVATE_ALIAS' });
    const arcade = ${game};
    export { arcade as game };
  `);
  assert.doesNotMatch(bundle, /PRIVATE_ALIAS/);
  assert.equal((await gameInit(bundle, null, actor)).count, 0);
});

test('an exported function parameter does not make a local game public', async () => {
  await assert.rejects(compileGameModule(`
    const game = ${game};
    export function render(game) { return game; }
  `), /Export game/);
});

test('reachable destructured and reassigned bindings reject with an actionable explanation', async () => {
  await assert.rejects(compileGameModule(`
    const { initial } = { initial: 2 };
    export const game = ${game.replace('count: 0', 'count: initial')};
  `), /individual named initializers|destructuring/);
  await assert.rejects(compileGameModule(`
    let initial = 2;
    initial = 3;
    export const game = ${game.replace('count: 0', 'count: initial')};
  `), /must not be reassigned/);
});

test('separate module statements cannot silently mutate required game dependencies', async () => {
  await assert.rejects(compileGameModule(`
    const settings = { initial: 2 };
    settings.initial = 3;
    export const game = ${game.replace('count: 0', 'count: settings.initial')};
  `), /inside their declarations|separate module statements/);
});

test('excluded initializers cannot silently mutate a required game dependency', async () => {
  for (const initializer of [
    'const unused = Object.assign(settings, { initial: 3 });',
    'function configure() { settings.initial = 3; } const unused = configure();',
  ]) {
    await assert.rejects(compileGameModule(`
      const settings = { initial: 2 };
      ${initializer}
      export const game = ${game.replace('count: 0', 'count: settings.initial')};
    `), /inside their declarations|separate module statements|outside|initializer/i);
  }
});
