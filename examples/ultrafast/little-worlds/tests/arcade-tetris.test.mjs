import test from 'node:test';
import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import { tetrisGame } from '../server/arcade/tetris.mjs';
import { validateGameState, validateGameView } from '../shared/game-schema.mjs';
import { compileGameModule, gameInit, gameStep, gameView } from '../server/runtime.mjs';

const actor = { id: 'arcade-player', name: 'Arcade player' };
const fresh = () => tetrisGame.init(null, actor);

test('Tetris uses a deterministic seven-piece bag and resumes its random sequence', () => {
  let state = fresh();
  const sequence = [];
  for (let index = 0; index < 21; index++) {
    sequence.push(state.piece.type);
    const checkpoint = tetrisGame.init(state, actor);
    const next = tetrisGame.step(state, { type: 'drop' });
    assert.deepEqual(tetrisGame.step(checkpoint, { type: 'drop' }), next);
    state = { ...next, board: Array(200).fill(0), over: false };
  }
  for (let offset = 0; offset < sequence.length; offset += 7) assert.equal(new Set(sequence.slice(offset, offset + 7)).size, 7);
  assert.deepEqual(fresh(), fresh());
  assert.notEqual(fresh().rng, tetrisGame.init(null, { id: 'other-player', name: 'Other' }).rng);
});

test('Tetris gravity advances with elapsed time, soft drop scores, and inputs are immutable', () => {
  const initial = fresh(), initialCopy = structuredClone(initial);
  let state = initial;
  for (let tick = 0; tick < 13; tick++) state = tetrisGame.step(state, { type: 'tick' });
  assert.equal(state.piece.y, 0);
  state = tetrisGame.step(state, { type: 'tick', deltaMs: 50 });
  assert.equal(state.piece.y, 1);
  state = tetrisGame.step(state, { type: 'move', direction: 'down' });
  assert.equal(state.piece.y, 2);
  assert.equal(state.score, 1);
  assert.deepEqual(initial, initialCopy);
  assert.throws(() => tetrisGame.step(initial, { type: 'tick', deltaMs: Infinity }), /delta/);
  assert.throws(() => tetrisGame.step(initial, { type: 'move', direction: 'up' }), /left, right, or down/);
});

test('Tetris boundaries, collision, and wall kicks keep each tetromino on the board', () => {
  for (const type of ['I', 'O', 'T', 'S', 'Z', 'J', 'L']) {
    let state = { ...fresh(), piece: { type, rotation: 0, x: 3, y: 5 } };
    for (let turn = 0; turn < 4; turn++) state = tetrisGame.step(state, { type: 'rotate' });
    assert.deepEqual(state.piece, { type, rotation: 0, x: 3, y: 5 });
    for (let step = 0; step < 20; step++) state = tetrisGame.step(state, { type: 'move', direction: 'left' });
    const atWall = structuredClone(state.piece);
    state = tetrisGame.step(state, { type: 'move', direction: 'left' });
    assert.deepEqual(state.piece, atWall);
    assert.doesNotThrow(() => tetrisGame.init(state, actor));
  }
  const wall = { ...fresh(), piece: { type: 'I', rotation: 1, x: -2, y: 5 } };
  const kicked = tetrisGame.step(wall, { type: 'rotate' });
  assert.deepEqual(kicked.piece, { type: 'I', rotation: 2, x: 0, y: 5 });
  const blocked = { ...fresh(), piece: { type: 'O', rotation: 0, x: 3, y: 5 } };
  blocked.board[5 * 10 + 3] = 2;
  assert.deepEqual(tetrisGame.step(blocked, { type: 'move', direction: 'left' }).piece, blocked.piece);
});

test('Tetris clears four completed lines, awards score, and advances the level at ten lines', () => {
  const state = { ...fresh(), piece: { type: 'I', rotation: 1, x: 2, y: 0 }, lines: 6 };
  for (let row = 16; row < 20; row++) {
    for (let column = 0; column < 10; column++) state.board[row * 10 + column] = column === 4 ? 0 : 5;
  }
  const next = tetrisGame.step(state, { type: 'drop' });
  assert.equal(next.lines, 10);
  assert.equal(next.level, 2);
  assert.equal(next.score, 832);
  assert.equal(next.board.filter(Boolean).length, 0);
  assert.equal(next.pieces, 1);
  assert.equal(next.piece.type, state.next);
  assert.equal(next.over, false);
});

test('Tetris ends when a new piece cannot spawn and terminal controls do not mutate play', () => {
  const state = { ...fresh(), piece: { type: 'O', rotation: 0, x: 3, y: 18 }, next: 'O' };
  state.board[4] = 1;
  const finished = tetrisGame.step(state, { type: 'drop' });
  assert.equal(finished.over, true);
  assert.equal(tetrisGame.view(finished).finished, true);
  assert.equal(tetrisGame.view(finished).values.status, 'Game over');
  for (const action of [{ type: 'drop' }, { type: 'rotate' }, { type: 'tick' }, { type: 'move', direction: 'left' }]) {
    assert.deepEqual(tetrisGame.step(finished, action), finished);
  }
  assert.deepEqual(tetrisGame.init(finished, actor), finished);
});

test('Tetris checkpoints validate ownership and state, copy inputs, and remain below runtime bounds', () => {
  const state = fresh(), checkpoint = tetrisGame.init(state, actor);
  checkpoint.board[199] = 3;
  checkpoint.piece.x++;
  assert.equal(state.board[199], 0);
  assert.equal(state.piece.x, 3);
  const mutations = [
    item => { item.actorId = 'someone-else'; }, item => { item.board[0] = 8; },
    item => { delete item.board[2]; }, item => { item.piece.type = 'X'; },
    item => { item.bag = ['I', 'I']; }, item => { item.rng = 0; },
    item => { item.level = 9; }, item => { item.elapsed = NaN; },
    item => { item.piece.x = 20; }, item => { item.over = 'false'; },
    item => { item.board.fill(1, 190); },
  ];
  for (const mutate of mutations) {
    const invalid = structuredClone(state); mutate(invalid);
    assert.throws(() => tetrisGame.init(invalid, actor), /Invalid Tetris checkpoint/);
  }
  assert.doesNotThrow(() => validateGameState(state, actor));
  assert.ok(JSON.stringify(state).length < 32000);
  const view = tetrisGame.view(state);
  assert.doesNotThrow(() => validateGameView(view));
  assert.ok(view.objects.some(object => object.id === 'ghost-0'));
  assert.ok(view.objects.some(object => object.id === 'preview-0'));
  const full = { ...state, board: Array(200).fill(1), over: true };
  assert.doesNotThrow(() => validateGameView(tetrisGame.view(full)));
  assert.ok(tetrisGame.view(full).objects.length < 1000);
});

test('Tetris runs inside the production QuickJS game runtime without outside dependencies', async () => {
  const source = await readFile(new URL('../server/arcade/tetris.mjs', import.meta.url), 'utf8');
  const bundle = await compileGameModule(source, 'tetrisGame');
  const state = await gameInit(bundle, null, actor);
  const next = await gameStep(bundle, state, { type: 'drop' }, actor);
  assert.equal(next.pieces, 1);
  assert.ok(next.score > 0);
  const view = await gameView(bundle, next, actor);
  assert.equal(view.width, 320);
  assert.equal(view.height, 480);
  assert.deepEqual(view.values, tetrisGame.view(next).values);
  assert.deepEqual(await gameInit(bundle, next, actor), next);
});
