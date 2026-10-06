import test from 'node:test';
import assert from 'node:assert/strict';
import { pacmanGame as game } from '../server/arcade/pacman.mjs';

const actor = { id: 'motion-player', name: 'Motion player' };
const close = (actual, expected, message) => assert.ok(Math.abs(actual - expected) < 1e-8, `${message}: ${actual} versus ${expected}`);
const shape = (state, id = 'pacman') => game.view(state).objects.find(object => object.id === id);
const tick = (state, deltaMs = 50) => game.step(state, { type: 'tick', deltaMs });
const steer = (state, direction) => game.step(state, { type: 'direction', direction });
function start() {
  const state = game.init(null, actor);
  state.ghosts.forEach(ghost => { ghost.wait = 3000; });
  return steer(state, 'left');
}

test('PacMan advances the same distance on every frame, including cell boundaries', () => {
  const state = start();
  let previous = shape(state);
  for (let frame = 0; frame < 12; frame++) {
    tick(state);
    const current = shape(state);
    close(previous.x - current.x, 5, `Frame ${frame} must travel five pixels`);
    close(current.y, previous.y, 'Corridor heading is stable');
    previous = current;
  }
  assert.equal(state.score, 40);
});

for (const powered of [false, true]) {
  test(`Ghosts advance uniformly ${powered ? 'while frightened' : 'at normal speed'}, without waiting for whole cells`, () => {
    const state = start();
    state.ghosts[0] = { cell: 21, next: 21, progress: 0, direction: 'right', wait: 0 };
    if (powered) state.powered = 6500;
    let previous = shape(state, 'ghost-0');
    for (let frame = 0; frame < 6; frame++) {
      tick(state);
      const current = shape(state, 'ghost-0');
      close(current.x - previous.x, 15 * 50 / (powered ? 310 : 225), `Ghost frame ${frame}`);
      close(current.y, previous.y, 'Ghost heading is stable');
      previous = current;
    }
  });
}

test('A reversal preserves the exact position and responds on the next frame', () => {
  const state = start();
  tick(state);
  const before = shape(state);
  steer(state, 'right');
  assert.deepEqual(shape(state), before, 'Turning cannot teleport the body to a cell center');
  tick(state);
  close(shape(state).x - before.x, 5, 'The first reversed frame has normal speed');
  assert.equal(state.player, 332);
  assert.equal(state.playerProgress, 0);
});

test('Early turns stay queued through blocked cells and turn at the junction without a pause', () => {
  const state = start();
  tick(state);
  const before = shape(state);
  steer(state, 'up');
  assert.deepEqual(shape(state), before);
  for (let frame = 1; frame < 9; frame++) tick(state);
  assert.equal(state.player, 329);
  const corner = shape(state);
  tick(state);
  close(shape(state).x, corner.x, 'Turn stays on the corridor');
  close(corner.y - shape(state).y, 5, 'Queued turn begins immediately at normal speed');
});

test('Repeated direction inputs cannot reset travel progress or change speed', () => {
  const quiet = start(), repeated = start();
  for (let frame = 0; frame < 10; frame++) {
    for (let repeat = 0; repeat < 6; repeat++) steer(repeated, 'left');
    tick(quiet); tick(repeated);
    assert.deepEqual(repeated, quiet);
  }
});

test('Fractional checkpoints preserve positions and progress while legacy checkpoints remain compatible', () => {
  const state = start();
  state.ghosts[0] = { cell: 21, next: 21, progress: 0, direction: 'right', wait: 0 };
  tick(state); tick(state);
  const saved = structuredClone(state), resumed = game.init(saved, actor);
  assert.deepEqual(shape(resumed), shape(state));
  assert.deepEqual(shape(resumed, 'ghost-0'), shape(state, 'ghost-0'));
  assert.equal(resumed.ready, false, 'Restoration waits for intentional input');
  assert.deepEqual(saved, state, 'Restoration must not mutate the checkpoint');
  for (const key of ['score', 'lives', 'level', 'pellets', 'powered', 'rng']) assert.deepEqual(resumed[key], saved[key]);
  steer(resumed, 'left'); tick(resumed); tick(state);
  assert.deepEqual(resumed, state);

  const legacy = structuredClone(saved);
  delete legacy.playerNext; delete legacy.playerProgress;
  legacy.playerTime = 100; legacy.ghostTime = 100;
  legacy.ghosts.forEach(ghost => { delete ghost.next; delete ghost.progress; });
  const migrated = game.init(legacy, actor);
  assert.equal(migrated.player, legacy.player);
  assert.equal(migrated.playerProgress, 0);
  assert.deepEqual(migrated.pellets, legacy.pellets);
  assert.equal(migrated.score, legacy.score);
  const before = shape(migrated);
  steer(migrated, 'left'); tick(migrated);
  close(before.x - shape(migrated).x, 5, 'Legacy restoration starts at uniform speed');
});

test('Malformed saved movement cannot send characters through walls or beyond their segment', () => {
  const saved = start();
  saved.playerNext = saved.player - 19; saved.playerProgress = 0.5;
  saved.ghosts[0].next = 0; saved.ghosts[0].progress = 0.8;
  saved.ghosts[1].progress = Infinity;
  const resumed = game.init(saved, actor);
  assert.equal(resumed.playerNext, resumed.player);
  assert.equal(resumed.playerProgress, 0);
  for (const ghost of resumed.ghosts) {
    assert.equal(ghost.next, ghost.cell);
    assert.equal(ghost.progress, 0);
  }
});

test('The mouth and ghost details remain anchored to continuously moving bodies', () => {
  const state = start();
  state.ghosts.forEach(ghost => { ghost.wait = 0; });
  for (let frame = 0; frame < 12; frame++) {
    tick(state);
    const body = shape(state), mouth = shape(state, 'pacman-mouth');
    assert.ok(mouth, 'The mouth must not disappear between animation frames');
    assert.equal(mouth.x, body.x); assert.equal(mouth.y, body.y);
    assert.match(mouth.d, /^M 0 0 /, 'The path must move with its local origin');
    for (let index = 0; index < 4; index++) {
      const ghost = shape(state, `ghost-${index}`), eye = shape(state, `eye-left-${index}`);
      close(ghost.x - eye.x, 2.4, 'Eye follows horizontal motion');
      close(ghost.y - eye.y, 1.5, 'Eye follows vertical motion');
    }
  }
});

test('Tick batching preserves simulation pace and collisions are detected between cell centers', () => {
  const one = start(), two = structuredClone(one);
  tick(one, 100); tick(two); tick(two);
  assert.deepEqual(one, two);
  const hit = start();
  hit.ghosts[0] = { cell: 330, next: 331, progress: 0.9, direction: 'right', wait: 0 };
  tick(hit, 100);
  assert.equal(hit.lives, 2);
  assert.equal(hit.ready, false, 'A head-on collision stops both actors rather than allowing them to pass through');
});
