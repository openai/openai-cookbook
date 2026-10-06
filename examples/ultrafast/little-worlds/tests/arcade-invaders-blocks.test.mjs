import test from 'node:test';
import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import { invadersGame } from '../server/arcade/invaders.mjs';
import { validateGameState, validateGameView } from '../shared/game-schema.mjs';
import { compileGameModule, gameInit, gameStep, gameView } from '../server/runtime.mjs';

const actor = { id: 'arcade_player', name: 'Arcade player' };
const tick = (state, deltaMs = 50) => invadersGame.step(state, { type: 'tick', deltaMs });

test('Space Invaders begins with four formations, destructible bunkers, three lives, and a bounded scene', () => {
  const state = invadersGame.init(null, actor);
  assert.equal(state.aliens.length, 36);
  assert.equal(state.shields.length, 60);
  assert.equal(state.lives, 3);
  assert.equal(state.wave, 1);
  assert.equal(validateGameState(state, actor), state);
  const before = JSON.stringify(state);
  const scene = validateGameView(invadersGame.view(state));
  assert.equal(scene.width, 320);
  assert.equal(scene.height, 360);
  assert.equal(scene.finished, false);
  assert.match(scene.values.status, /36 invaders/);
  assert.ok(scene.objects.length < 200);
  assert.equal(JSON.stringify(state), before, 'drawing does not change progress');
});

test('Space Invaders held controls move continuously, stop on release, and stay inside the arena', () => {
  const original = invadersGame.init(null, actor);
  let state = invadersGame.step(original, { type: 'input', key: 'right', held: true });
  state = tick(state, 1000);
  assert.equal(state.playerX, 280);
  state = tick(state, 1000);
  assert.equal(state.playerX, 302);
  state = invadersGame.step(state, { type: 'input', key: 'right', held: false });
  state = tick(state, 300);
  assert.equal(state.playerX, 302);
  state = invadersGame.step(state, { type: 'input', key: 'left', held: true });
  state = tick(tick(tick(state, 1000), 1000), 1000);
  assert.equal(state.playerX, 18);
  assert.equal(original.playerX, 160);
  assert.equal(original.input.right, false);
});

test('Space Invaders held and tapped fire share a bounded cooldown', () => {
  let state = invadersGame.init(null, actor);
  state.shields = [];
  state = invadersGame.step(state, { type: 'fire' });
  state = invadersGame.step(state, { type: 'fire' });
  assert.equal(state.shots.length, 1);
  state = invadersGame.step(state, { type: 'input', key: 'fire', held: true });
  for (let frame = 0; frame < 40; frame++) {
    state = tick(state);
    assert.ok(state.shots.length <= 3);
  }
  assert.ok(state.shots.length > 0);
  state = invadersGame.step(state, { type: 'input', key: 'fire', held: false });
  for (let frame = 0; frame < 30; frame++) state = tick(state);
  assert.equal(state.shots.length, 0);
});

test('Space Invaders collisions remove only the hit invader and award its row score', () => {
  const state = invadersGame.init(null, actor);
  const target = state.aliens[0];
  state.shots = [{ x: target.x, y: target.y + 12 }];
  const next = tick(state);
  assert.equal(next.aliens.length, 35);
  assert.ok(!next.aliens.some(alien => alien.id === target.id));
  assert.equal(next.score, 40);
  assert.equal(next.shots.length, 0);
  assert.equal(state.aliens.length, 36, 'steps preserve their input snapshot');
});

test('Space Invaders bunkers erode from player and enemy shots and protect the cannon', () => {
  let state = invadersGame.init(null, actor);
  const target = state.shields.at(-1);
  state.shots = [{ x: target.x + 2, y: target.y + 8 }];
  state = tick(state);
  assert.equal(state.shields.length, 59);
  assert.ok(!state.shields.some(cell => cell.id === target.id));
  state.playerX = 160;
  state.shields = [{ id: 'b1-0-1', x: 158, y: 310 }];
  state.enemyShots = [{ x: 160, y: 309 }];
  state = tick(state);
  assert.equal(state.shields.length, 0);
  assert.equal(state.enemyShots.length, 0);
  assert.equal(state.lives, 3);
});

test('Space Invaders uses temporary hit protection and a terminal loss after three hits', () => {
  let state = invadersGame.init(null, actor);
  state.enemyShots = [{ x: 160, y: 318 }, { x: 160, y: 318 }];
  state = tick(state);
  assert.equal(state.lives, 2);
  assert.equal(state.invincibleMs, 1500);
  state = tick(state);
  assert.equal(state.lives, 2, 'overlapping bullets do not cost several lives at once');
  for (let lives = 1; lives >= 0; lives--) {
    state.invincibleMs = 0;
    state.enemyShots = [{ x: 160, y: 318 }];
    state = tick(state);
    assert.equal(state.lives, lives);
  }
  assert.equal(state.finished, true);
  assert.equal(invadersGame.view(state).finished, true);
  const score = state.score;
  state = tick(state, 1000);
  assert.equal(state.score, score);
  assert.equal(state.lives, 0);
});

test('Space Invaders formation reverses and descends at an edge and loses on reaching the cannon', () => {
  let state = invadersGame.init(null, actor);
  state.aliens = [{ id: 0, row: 0, x: 300, y: 100 }];
  state.marchMs = 104;
  state = tick(state);
  assert.equal(state.direction, -1);
  assert.equal(state.aliens[0].y, 110);
  state.aliens[0].y = 310;
  state = tick(state);
  assert.equal(state.lives, 0);
  assert.equal(state.finished, true);
});

test('Space Invaders final kill awards a wave bonus and restores the next formation and bunkers', () => {
  let state = invadersGame.init(null, actor);
  state.aliens = [{ id: 0, row: 0, x: 100, y: 100 }];
  state.shields = [];
  state.shots = [{ x: 100, y: 112 }];
  state = tick(state);
  assert.equal(state.score, 140);
  assert.equal(state.wave, 2);
  assert.equal(state.waveMs, 1200);
  assert.equal(state.aliens.length, 0);
  assert.equal(invadersGame.view(state).finished, false);
  state = tick(tick(state, 1000), 200);
  assert.equal(state.aliens.length, 36);
  assert.equal(state.shields.length, 60);
  assert.equal(state.score, 140);
});

test('Space Invaders validates checkpoints, copies progress, and never restores held inputs', () => {
  let saved = invadersGame.init(null, actor);
  saved = invadersGame.step(saved, { type: 'input', key: 'fire', held: true });
  saved = tick(saved, 200);
  const before = JSON.stringify(saved);
  const resumed = invadersGame.init(saved, actor);
  assert.equal(resumed.playerX, saved.playerX);
  assert.equal(resumed.seed, saved.seed);
  assert.deepEqual(resumed.input, { left: false, right: false, fire: false });
  assert.notEqual(resumed.aliens[0], saved.aliens[0]);
  assert.equal(JSON.stringify(saved), before);
  for (const bad of [
    { ...saved, actorId: 'someone_else' }, { ...saved, score: NaN },
    { ...saved, aliens: [saved.aliens[0], saved.aliens[0]] },
    { ...saved, shots: Array(4).fill({ x: 10, y: 20 }) },
    { ...saved, finished: true }, { ...saved, reloadMs: -10 },
  ]) assert.throws(() => invadersGame.init(bad, actor), /checkpoint/);
  assert.throws(() => invadersGame.step(saved, { type: 'input', key: 'laser', held: true }), /control/);
  assert.throws(() => invadersGame.step(saved, { type: 'tick', deltaMs: Infinity }), /action/);
  assert.throws(() => invadersGame.step(saved, { type: 'cheat' }), /action/);
});

test('Space Invaders runs its actual public dependency bundle in the isolated game interpreter', async () => {
  const source = await readFile(new URL('../server/arcade/invaders.mjs', import.meta.url), 'utf8');
  const bundle = await compileGameModule(`${source}\nexport const game = invadersGame;`);
  let state = await gameInit(bundle, null, actor);
  state = await gameStep(bundle, state, { type: 'input', key: 'right', held: true }, actor);
  state = await gameStep(bundle, state, { type: 'input', key: 'fire', held: true }, actor);
  for (let frame = 0; frame < 12; frame++) state = await gameStep(bundle, state, { type: 'tick', deltaMs: 50 }, actor);
  assert.equal(state.playerX, 232);
  assert.equal(validateGameState(state, actor), state);
  const scene = validateGameView(await gameView(bundle, state, actor));
  assert.equal(scene.width, 320);
  assert.equal(scene.values.lives, state.lives);
  const resumed = await gameInit(bundle, state, actor);
  assert.deepEqual(resumed.input, { left: false, right: false, fire: false });
});

test('Space Invaders remains within state and scene budgets through sustained play', () => {
  let state = invadersGame.init(null, actor);
  state = invadersGame.step(state, { type: 'input', key: 'fire', held: true });
  for (let frame = 0; frame < 1200 && !state.finished; frame++) {
    if (frame % 60 === 0) {
      state = invadersGame.step(state, { type: 'input', key: 'right', held: frame % 120 === 0 });
      state = invadersGame.step(state, { type: 'input', key: 'left', held: frame % 120 !== 0 });
    }
    state = tick(state);
    if (frame % 50 === 0) {
      validateGameState(state, actor);
      validateGameView(invadersGame.view(state));
      invadersGame.init(state, actor);
    }
  }
  validateGameState(state, actor);
  validateGameView(invadersGame.view(state));
  assert.ok(Buffer.byteLength(JSON.stringify(state)) < 8000);
});
