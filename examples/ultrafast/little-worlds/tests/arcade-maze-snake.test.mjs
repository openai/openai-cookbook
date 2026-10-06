import test from 'node:test';
import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import { pacmanGame } from '../server/arcade/pacman.mjs';
import { snakeGame } from '../server/arcade/snake.mjs';
import { validateGameState, validateGameView } from '../shared/game-schema.mjs';
import { compileGameModule, gameInit, gameStep, gameView } from '../server/runtime.mjs';

const actor = { id: 'arcade-player', name: 'Player' };
const tick = (game, state, count = 1) => { for (let i = 0; i < count; i++) state = game.step(state, { type: 'tick', deltaMs: 50 }); return state; };
const steer = (game, state, direction) => game.step(state, { type: 'direction', direction });
const walls = state => new Set(pacmanGame.view(state).objects.filter(shape => shape.id.startsWith('wall-')).map(shape => Number(shape.id.slice(5))));
const directions = { up: -19, down: 19, left: -1, right: 1 };

function safePacmanMove(state, direction) {
  for (const ghost of state.ghosts) ghost.wait = 3000;
  steer(pacmanGame, state, direction);
  return tick(pacmanGame, state, 3);
}

for (const [name, game] of [['PacMan', pacmanGame], ['Snake', snakeGame]]) {
  test(`${name} waits for input, renders a valid scene, and sanitizes saved progress`, () => {
    const fresh = game.init(null, actor), before = structuredClone(fresh);
    tick(game, fresh, 1000);
    assert.deepEqual(fresh, before, 'The player should not lose a life before choosing a direction');
    validateGameState(fresh, actor);
    const scene = game.view(fresh);
    validateGameView(scene);
    assert.equal(scene.width, 320); assert.equal(scene.height, 360);
    assert.ok(scene.objects.length < 1000);
    assert.deepEqual(fresh, before, 'Rendering must not alter progress');
    assert.deepEqual(game.init({ actorId: actor.id, version: 1 }, actor), before);
    assert.throws(() => game.init({ ...fresh, actorId: 'somebody-else' }, actor), /another participant/);
    assert.equal(game.init({ ...fresh, direction: '__proto__' }, actor).direction, name === 'Snake' ? 'right' : 'left');
    assert.equal(game.init({ ...fresh, direction: 'constructor' }, actor).direction, name === 'Snake' ? 'right' : 'left');
  });

  test(`${name} compiles and simulates inside the real public QuickJS game runtime`, async () => {
    const path = name === 'Snake' ? 'snake' : 'pacman';
    const source = (await readFile(new URL(`../server/arcade/${path}.mjs`, import.meta.url), 'utf8')).replace(`export const ${path}Game`, 'export const game');
    const bundle = await compileGameModule(source);
    let state = await gameInit(bundle, null, actor);
    const before = structuredClone(state);
    state = await gameStep(bundle, state, { type: 'direction', direction: name === 'Snake' ? 'right' : 'left' }, actor);
    for (let i = 0; i < 3; i++) state = await gameStep(bundle, state, { type: 'tick', deltaMs: 50 }, actor);
    assert.notDeepEqual(state, before);
    const scene = await gameView(bundle, state, actor);
    validateGameView(scene);
    const resumed = await gameInit(bundle, state, actor);
    assert.equal(resumed.score, state.score);
    assert.equal(resumed.ready, false, 'Reload must not replay a held steering input');
    assert.equal(resumed.actorId, actor.id);
    assert.equal(resumed.queued, resumed.direction);
    assert.ok(JSON.stringify(resumed).length < 32000);
  });
}

test('PacMan has one connected maze, reachable pellets, and four distinct ghost colors', () => {
  const state = pacmanGame.init(null, actor), blocked = walls(state), visited = new Set([state.player]), queue = [state.player];
  for (let index = 0; index < queue.length; index++) {
    const cell = queue[index];
    for (const offset of Object.values(directions)) {
      const next = cell + offset;
      if (next >= 0 && next < 399 && !blocked.has(next) && !visited.has(next)) { visited.add(next); queue.push(next); }
    }
  }
  assert.ok(state.pellets.length > 150);
  assert.ok(state.pellets.every(cell => visited.has(cell)));
  assert.ok(state.ghosts.every(ghost => visited.has(ghost.cell)));
  const colors = pacmanGame.view(state).objects.filter(shape => /^ghost-\d$/.test(shape.id)).map(shape => shape.fill);
  assert.equal(new Set(colors).size, 4);
});

test('PacMan eats pellets, obeys walls, and queues turns until the corridor permits them', () => {
  const state = pacmanGame.init(null, actor);
  const start = state.player;
  safePacmanMove(state, 'left');
  assert.equal(state.player, start - 1); assert.equal(state.score, 10);
  assert.ok(!state.pellets.includes(state.player));
  safePacmanMove(state, 'left');
  assert.equal(state.player, start - 2);
  safePacmanMove(state, 'up');
  assert.equal(state.player, start - 3, 'A blocked upward turn should keep moving along the corridor');
  tick(pacmanGame, state, 3);
  assert.equal(state.player, start - 3 - 19, 'The queued turn should fire at the next open junction');
  const blocked = walls(state);
  for (let i = 0; i < 20; i++) { safePacmanMove(state, 'up'); assert.ok(!blocked.has(state.player)); }
});

test('PacMan power pellets turn collisions into points and normal collisions consume exactly one life', () => {
  const powered = pacmanGame.init(null, actor);
  powered.player = 21; powered.direction = 'left'; powered.ghosts.forEach(ghost => { ghost.wait = 3000; });
  tick(pacmanGame, steer(pacmanGame, powered, 'left'), 3);
  assert.equal(powered.player, 20); assert.equal(powered.score, 50); assert.ok(powered.powered > 0);
  powered.ghosts[0] = { cell: 21, direction: 'left', wait: 0 };
  tick(pacmanGame, steer(pacmanGame, powered, 'right'), 3);
  assert.equal(powered.lives, 3); assert.equal(powered.score, 260); assert.ok(powered.ghosts[0].wait > 0);
  const hit = pacmanGame.init(null, actor);
  hit.ghosts[0] = { cell: hit.player - 1, direction: 'right', wait: 0 };
  tick(pacmanGame, steer(pacmanGame, hit, 'left'), 3);
  assert.equal(hit.lives, 2); assert.equal(hit.ready, false); assert.equal(hit.player, 332);
  tick(pacmanGame, hit, 100); assert.equal(hit.lives, 2, 'Waiting after a hit cannot consume more lives');
  hit.lives = 1; hit.ghosts[0] = { cell: hit.player - 1, direction: 'right', wait: 0 };
  tick(pacmanGame, steer(pacmanGame, hit, 'left'), 3);
  assert.equal(hit.lives, 0); assert.equal(pacmanGame.view(hit).finished, true);
  assert.equal(pacmanGame.init(hit, actor).status, 'over');
});

test('PacMan clearing the last pellet advances the level and waits before beginning another maze', () => {
  const state = pacmanGame.init(null, actor);
  state.pellets = [state.player - 1];
  safePacmanMove(state, 'left');
  assert.equal(state.level, 2); assert.equal(state.score, 510); assert.equal(state.status, 'won'); assert.equal(state.ready, false);
  assert.ok(state.pellets.length > 150); assert.equal(pacmanGame.view(state).finished, false);
  assert.match(pacmanGame.view(state).values.status, /MAZE CLEAR/);
  tick(pacmanGame, state, 20); assert.equal(state.status, 'won');
  steer(pacmanGame, state, 'left'); assert.equal(state.status, 'playing');
});

test('Snake moves at a playable cadence, grows, and deterministically places food outside its body', () => {
  const state = snakeGame.init(null, actor), originalHead = state.body[0];
  steer(snakeGame, state, 'right'); tick(snakeGame, state, 2); assert.equal(state.body[0], originalHead);
  tick(snakeGame, state); assert.equal(state.body[0], originalHead + 1);
  const twin = structuredClone(state);
  tick(snakeGame, state, 7); tick(snakeGame, twin, 7);
  assert.equal(state.score, 10); assert.equal(state.body.length, 4); assert.ok(!state.body.includes(state.food));
  assert.deepEqual(state, twin);
  const saved = structuredClone(state), resumed = snakeGame.init(saved, actor);
  assert.deepEqual(resumed.body, saved.body); assert.equal(resumed.food, saved.food); assert.deepEqual(state, saved);
});

test('Snake prevents both direct and rapid queued reversals and stops at the wall', () => {
  const state = snakeGame.init(null, actor), head = state.body[0];
  steer(snakeGame, state, 'left'); tick(snakeGame, state, 3);
  assert.equal(state.body[0], head, 'A reversed first input must not start into the body');
  steer(snakeGame, state, 'up'); steer(snakeGame, state, 'left'); tick(snakeGame, state, 3);
  assert.equal(state.body[0], head - 20, 'The second key must not reverse the actual rightward heading');
  tick(snakeGame, state, 30);
  assert.equal(state.status, 'over'); assert.equal(snakeGame.view(state).finished, true);
  const before = structuredClone(state); steer(snakeGame, state, 'down'); tick(snakeGame, state, 20); assert.deepEqual(state, before);
});

test('Snake allows entering the departing tail but catches a real body collision', () => {
  const loop = { ...snakeGame.init(null, actor), body: [21, 22, 42, 41], direction: 'left', queued: 'left', food: 200, ready: true, status: 'playing' };
  steer(snakeGame, loop, 'down'); tick(snakeGame, loop, 3);
  assert.equal(loop.status, 'playing'); assert.equal(loop.body[0], 41);
  const collision = { ...snakeGame.init(null, actor), body: [21, 22, 42, 41, 61], direction: 'left', queued: 'left', food: 200, ready: true, status: 'playing' };
  steer(snakeGame, collision, 'down'); tick(snakeGame, collision, 3);
  assert.equal(collision.status, 'over'); assert.equal(collision.body[0], 21);
});

test('Snake reaches a valid finished board when the last free square is eaten', () => {
  const body = [];
  for (let row = 0; row < 20; row++) for (let column = 0; column < 20; column++) body.push(row * 20 + (row % 2 ? 19 - column : column));
  const state = { ...snakeGame.init(null, actor), body: body.slice(1), direction: 'left', queued: 'left', food: 0, ready: true, status: 'playing' };
  tick(snakeGame, state, 3);
  assert.equal(state.body.length, 400); assert.equal(state.food, -1); assert.equal(state.status, 'won');
  validateGameState(state, actor); validateGameView(snakeGame.view(state));
  assert.equal(snakeGame.view(state).finished, true); assert.equal(snakeGame.init(state, actor).status, 'won');
});

test('Snake reload derives its heading from the body instead of accepting a direction into its neck', () => {
  const saved = { ...snakeGame.init(null, actor), direction: 'left', queued: 'left', ready: true };
  const resumed = snakeGame.init(saved, actor);
  assert.equal(resumed.direction, 'right'); assert.equal(resumed.queued, 'right');
  steer(snakeGame, resumed, 'right'); tick(snakeGame, resumed, 3);
  assert.equal(resumed.status, 'playing'); assert.equal(resumed.body[0], 210);
});

test('PacMan ghosts leave their pen deterministically and threaten an unattended player', () => {
  const state = pacmanGame.init(null, actor), replay = pacmanGame.init(null, actor);
  steer(pacmanGame, state, 'left'); steer(pacmanGame, replay, 'left');
  const initialCells = state.ghosts.map(ghost => ghost.cell);
  tick(pacmanGame, state, 50); tick(pacmanGame, replay, 50);
  assert.notDeepEqual(state.ghosts.map(ghost => ghost.cell), initialCells);
  assert.deepEqual(state, replay);
  for (let frame = 0; frame < 200 && state.ready; frame++) {
    tick(pacmanGame, state); validateGameState(state, actor); validateGameView(pacmanGame.view(state));
  }
  assert.equal(state.lives, 2, 'Ghosts must be active opponents, rather than static decorations');
  assert.equal(state.ready, false);
});
