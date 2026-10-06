// Self-contained simulation: copied into the editable arcade space source.
const pacmanMaze = [
  '###################',
  '#o.......#.......o#',
  '#.##.###.#.###.##.#',
  '#.................#',
  '#.##.#.#####.#.##.#',
  '#....#...#...#....#',
  '####.###.#.###.####',
  '###..#.......#..###',
  '###.##.##.##.##.###',
  '#......#...#......#',
  '###.##.#...#.##.###',
  '#......#...#......#',
  '###.##.#####.##.###',
  '###..#...#...#..###',
  '####.#.#.#.#.#.####',
  '#....#.#...#.#....#',
  '#.##.#.#####.#.##.#',
  '#o.#...........#.o#',
  '##.#.###.#.###.#.##',
  '#.................#',
  '###################',
];
const pacmanVectors = { up: [0, -1], down: [0, 1], left: [-1, 0], right: [1, 0] };
const pacmanOpposite = { up: 'down', down: 'up', left: 'right', right: 'left' };
const pacmanGhostColors = ['#ff8549', '#924ff7', '#006aff', '#04b84c'];
function pacmanFloor(cell) {
  return Number.isInteger(cell) && cell >= 0 && cell < 399 && pacmanMaze[Math.floor(cell / 19)][cell % 19] !== '#';
}
function pacmanNeighbor(cell, direction) {
  const vector = pacmanVectors[direction];
  if (!vector) return -1;
  const x = cell % 19 + vector[0], y = Math.floor(cell / 19) + vector[1];
  const next = y * 19 + x;
  return x >= 0 && x < 19 && y >= 0 && y < 21 && pacmanFloor(next) ? next : -1;
}
function pacmanPellets() {
  const result = [];
  for (let cell = 0; cell < 399; cell++) if (pacmanFloor(cell) && ![180, 199, 218, 217, 332].includes(cell)) result.push(cell);
  return result;
}
function pacmanGhosts() {
  return [180, 199, 218, 217].map((cell, index) => ({ cell, next: cell, progress: 0, direction: 'up', wait: 1000 + index * 450 }));
}
function pacmanFresh(actorId) {
  return { actorId, version: 1, player: 332, playerNext: 332, playerProgress: 0, direction: 'left', queued: 'left', pellets: pacmanPellets(), ghosts: pacmanGhosts(), score: 0, lives: 3, level: 1, status: 'ready', powered: 0, combo: 0, elapsed: 0, ready: false, rng: 7319 };
}
function pacmanBound(value, low, high, fallback) {
  return Number.isInteger(value) && value >= low && value <= high ? value : fallback;
}
function pacmanRandom(state) {
  state.rng = (Math.imul(state.rng, 1664525) + 1013904223) >>> 0;
  return state.rng / 4294967296;
}
function pacmanSegment(cell, next, progress, direction) {
  return Number.isFinite(progress) && progress >= 0 && progress < 1 && next === pacmanNeighbor(cell, direction);
}
function pacmanPosition(cell, next, progress) {
  const x = cell % 19, y = Math.floor(cell / 19);
  if (!Number.isFinite(progress) || !pacmanFloor(next)) return { x, y };
  return { x: x + ((next % 19) - x) * progress,
    y: y + (Math.floor(next / 19) - y) * progress };
}
function pacmanDistances(target) {
  const distances = Array(399).fill(999), queue = [target];
  distances[target] = 0;
  for (let index = 0; index < queue.length; index++) {
    const cell = queue[index];
    for (const direction of ['up', 'left', 'down', 'right']) {
      const next = pacmanNeighbor(cell, direction);
      if (next >= 0 && distances[next] === 999) { distances[next] = distances[cell] + 1; queue.push(next); }
    }
  }
  return distances;
}
function pacmanResetActors(state) {
  state.player = 332; state.playerNext = 332; state.playerProgress = 0; state.direction = 'left'; state.queued = 'left'; state.ghosts = pacmanGhosts();
  state.powered = 0; state.combo = 0; state.ready = false;
}
function pacmanCollision(state) {
  const player = pacmanPosition(state.player, state.playerNext, state.playerProgress);
  for (let index = 0; index < state.ghosts.length; index++) {
    const ghost = state.ghosts[index];
    if (ghost.wait > 0) continue;
    const position = pacmanPosition(ghost.cell, ghost.next, ghost.progress);
    if (Math.hypot(position.x - player.x, position.y - player.y) > 0.65) continue;
    if (state.powered > 0) {
      state.score += 200 * Math.pow(2, Math.min(3, state.combo));
      state.combo = Math.min(4, state.combo + 1);
      ghost.cell = [180, 199, 218, 217][index]; ghost.next = ghost.cell; ghost.progress = 0; ghost.wait = 1800; ghost.direction = 'up';
    } else {
      state.lives--;
      state.status = state.lives === 0 ? 'over' : 'ready';
      pacmanResetActors(state);
      return true;
    }
  }
  return false;
}
function pacmanPreparePlayer(state) {
  if (pacmanSegment(state.player, state.playerNext, state.playerProgress, state.direction) && state.playerProgress > 0) return;
  state.playerProgress = 0;
  const turn = pacmanNeighbor(state.player, state.queued);
  if (turn >= 0) state.direction = state.queued;
  const next = pacmanNeighbor(state.player, state.direction);
  state.playerNext = next >= 0 ? next : state.player;
}
function pacmanArrivePlayer(state) {
  const pellet = state.pellets.indexOf(state.player);
  if (pellet >= 0) {
    state.pellets.splice(pellet, 1);
    const power = pacmanMaze[Math.floor(state.player / 19)][state.player % 19] === 'o';
    state.score += power ? 50 : 10;
    if (power) { state.powered = 6500; state.combo = 0; }
  }
  if (pacmanCollision(state)) return;
  if (state.pellets.length === 0) {
    state.level++; state.score += 500; state.pellets = pacmanPellets();
    pacmanResetActors(state); state.status = 'won';
  }
}
function pacmanAdvancePlayer(state, milliseconds) {
  const duration = Math.max(105, 150 - (state.level - 1) * 5);
  let remaining = milliseconds;
  while (remaining > 0.000001 && state.ready) {
    pacmanPreparePlayer(state);
    if (state.playerNext === state.player) return;
    const travel = Math.min(remaining, (1 - state.playerProgress) * duration);
    state.playerProgress += travel / duration;
    remaining -= travel;
    if (state.playerProgress >= 1 - 0.0000001) {
      state.player = state.playerNext; state.playerProgress = 0; state.playerNext = state.player;
      pacmanArrivePlayer(state);
    }
  }
}
function pacmanChooseGhost(state, ghost, index) {
  const chase = pacmanDistances(state.player);
  let options = ['up', 'left', 'down', 'right'].map(direction => ({ direction, cell: pacmanNeighbor(ghost.cell, direction) })).filter(option => option.cell >= 0);
  const forward = options.filter(option => option.direction !== pacmanOpposite[ghost.direction]);
  if (forward.length) options = forward;
  // A short scatter period and different target styles keep the pack escapable.
  const scatter = Math.floor(state.elapsed / 7000) % 3 === 0;
  let target = state.player;
  if (scatter || (index === 3 && chase[ghost.cell] < 6)) target = [20, 36, 362, 378][index];
  else if (index === 1) {
    for (let look = 0; look < 3; look++) { const next = pacmanNeighbor(target, state.direction); if (next >= 0) target = next; }
  } else if (index === 2 && Math.floor(state.elapsed / 1800) % 2 === 0) target = 362;
  const distances = target === state.player ? chase : pacmanDistances(target);
  options.sort((a, b) => state.powered > 0 ? chase[b.cell] - chase[a.cell] : distances[a.cell] - distances[b.cell]);
  const choice = state.powered > 0 && pacmanRandom(state) < 0.2 ? options[Math.floor(pacmanRandom(state) * options.length)] : options[0];
  ghost.next = choice ? choice.cell : ghost.cell;
  if (choice) ghost.direction = choice.direction;
}
function pacmanAdvanceGhost(state, ghost, index, milliseconds) {
  let remaining = milliseconds;
  if (ghost.wait > 0) {
    const waiting = Math.min(remaining, ghost.wait);
    ghost.wait -= waiting; remaining -= waiting;
  }
  if (!pacmanSegment(ghost.cell, ghost.next, ghost.progress, ghost.direction)) { ghost.next = ghost.cell; ghost.progress = 0; }
  const duration = state.powered > 0 ? 310 : Math.max(155, 225 - (state.level - 1) * 7);
  while (remaining > 0.000001) {
    if (ghost.next === ghost.cell) pacmanChooseGhost(state, ghost, index);
    if (ghost.next === ghost.cell) return;
    const travel = Math.min(remaining, (1 - ghost.progress) * duration);
    ghost.progress += travel / duration; remaining -= travel;
    if (ghost.progress >= 1 - 0.0000001) { ghost.cell = ghost.next; ghost.progress = 0; }
  }
}
export const pacmanGame = {
  init(saved, actor) {
    if (saved && saved.actorId !== actor.id) throw new Error('PacMan progress belongs to another participant.');
    const state = pacmanFresh(actor.id);
    if (!saved || saved.version !== 1 || !pacmanFloor(saved.player) || !Array.isArray(saved.pellets) || saved.pellets.length > 399 || !saved.pellets.every(pacmanFloor) || !Array.isArray(saved.ghosts) || saved.ghosts.length !== 4 || !saved.ghosts.every(ghost => ghost && pacmanFloor(ghost.cell))) return state;
    state.player = saved.player; state.playerNext = state.player;
    state.pellets = [...new Set(saved.pellets)];
    state.ghosts = saved.ghosts.map(ghost => {
      const direction = Object.prototype.hasOwnProperty.call(pacmanVectors, ghost.direction) ? ghost.direction : 'up';
      const moving = pacmanSegment(ghost.cell, ghost.next, ghost.progress, direction);
      return { cell: ghost.cell, next: moving ? ghost.next : ghost.cell, progress: moving ? ghost.progress : 0,
        direction, wait: pacmanBound(ghost.wait, 0, 3000, 500) };
    });
    state.score = pacmanBound(saved.score, 0, 999999999, 0); state.lives = pacmanBound(saved.lives, 0, 3, 3); state.level = pacmanBound(saved.level, 1, 9999, 1);
    state.direction = Object.prototype.hasOwnProperty.call(pacmanVectors, saved.direction) ? saved.direction : 'left'; state.queued = state.direction;
    if (pacmanSegment(state.player, saved.playerNext, saved.playerProgress, state.direction)) {
      state.playerNext = saved.playerNext; state.playerProgress = saved.playerProgress;
    }
    state.status = state.lives === 0 ? 'over' : saved.status === 'won' ? 'won' : 'ready';
    state.powered = pacmanBound(saved.powered, 0, 6500, 0); state.combo = pacmanBound(saved.combo, 0, 4, 0);
    state.elapsed = pacmanBound(saved.elapsed, 0, 2147483647, 0); state.rng = pacmanBound(saved.rng, 0, 4294967295, 7319);
    return state;
  },
  step(state, action) {
    if (state.status === 'over') return state;
    if (action.type === 'direction' && Object.prototype.hasOwnProperty.call(pacmanVectors, action.direction)) {
      state.queued = action.direction;
      // Reversing on a corridor is immediate and keeps the exact position.
      // Perpendicular turns stay buffered until the next tile center.
      if (action.direction === pacmanOpposite[state.direction] && state.playerProgress > 0 &&
        pacmanSegment(state.player, state.playerNext, state.playerProgress, state.direction)) {
        const origin = state.player; state.player = state.playerNext; state.playerNext = origin;
        state.playerProgress = 1 - state.playerProgress; state.direction = action.direction;
      }
      state.ready = true; state.status = 'playing'; pacmanPreparePlayer(state); return state;
    }
    if (action.type !== 'tick' || !Number.isFinite(action.deltaMs) || !state.ready) return state;
    let remaining = Math.max(0, Math.min(100, action.deltaMs));
    // Travel fractions advance every tick, not once per cell. Small collision
    // steps prevent characters from passing through each other between views.
    while (remaining > 0 && state.ready) {
      const elapsed = Math.min(10, remaining); remaining -= elapsed;
      state.elapsed = (state.elapsed + elapsed) % 2147483647;
      state.powered = Math.max(0, state.powered - elapsed);
      pacmanAdvancePlayer(state, elapsed);
      if (!state.ready) break;
      state.ghosts.forEach((ghost, index) => pacmanAdvanceGhost(state, ghost, index, elapsed));
      pacmanCollision(state);
    }
    return state;
  },
  view(state) {
    const objects = [], size = 15, left = 17.5, top = 22.5;
    for (let cell = 0; cell < 399; cell++) {
      const x = left + (cell % 19) * size, y = top + Math.floor(cell / 19) * size;
      if (!pacmanFloor(cell)) objects.push({ id: 'wall-' + cell, type: 'rect', x: x + 1, y: y + 1, width: 13, height: 13, radius: 3, fill: '#141414', stroke: '#924ff7', lineWidth: 1.25 });
    }
    for (const cell of state.pellets) {
      const power = pacmanMaze[Math.floor(cell / 19)][cell % 19] === 'o';
      objects.push({ id: 'pellet-' + cell, type: 'circle', x: left + (cell % 19) * size + 7.5, y: top + Math.floor(cell / 19) * size + 7.5, radius: power ? 4 : 1.6, fill: power ? '#ffffff' : '#b7b7b7' });
    }
    const position = pacmanPosition(state.player, state.playerNext, state.playerProgress);
    const px = left + position.x * size + 7.5, py = top + position.y * size + 7.5;
    objects.push({ id: 'pacman', type: 'circle', x: px, y: py, radius: 6.5, fill: '#ffe269' });
    const mouth = 0.8 + 4 * (0.5 + 0.5 * Math.sin(state.elapsed * Math.PI / 120));
    objects.push({ id: 'pacman-mouth', type: 'path', x: px, y: py,
      rotation: { right: 0, down: 90, left: 180, up: 270 }[state.direction],
      d: 'M 0 0 L 8 ' + mouth + ' L 8 ' + -mouth + ' Z', fill: '#080808' });
    state.ghosts.forEach((ghost, index) => {
      const position = pacmanPosition(ghost.cell, ghost.next, ghost.progress);
      const x = left + position.x * size + 7.5, y = top + position.y * size + 7.5;
      const frightened = state.powered > 0 && ghost.wait === 0;
      const fill = frightened ? (state.powered < 1500 && Math.floor(state.elapsed / 180) % 2 ? '#ffffff' : '#006aff') : pacmanGhostColors[index];
      objects.push({ id: 'ghost-' + index, type: 'path', d: 'M -6 6 L -6 -1 Q -6 -7 0 -7 Q 6 -7 6 -1 L 6 6 L 3 3 L 0 6 L -3 3 Z', x, y, fill });
      objects.push({ id: 'eye-left-' + index, type: 'circle', x: x - 2.4, y: y - 1.5, radius: 1.8, fill: '#ffffff' }, { id: 'eye-right-' + index, type: 'circle', x: x + 2.4, y: y - 1.5, radius: 1.8, fill: '#ffffff' });
      const look = pacmanVectors[ghost.direction];
      objects.push({ id: 'pupil-left-' + index, type: 'circle', x: x - 2.4 + look[0] * 0.7, y: y - 1.5 + look[1] * 0.7, radius: 0.85, fill: '#080808' }, { id: 'pupil-right-' + index, type: 'circle', x: x + 2.4 + look[0] * 0.7, y: y - 1.5 + look[1] * 0.7, radius: 0.85, fill: '#080808' });
    });
    return { width: 320, height: 360, background: '#080808', objects, values: { score: state.score, lives: state.lives, level: state.level, remaining: state.pellets.length, status: state.status === 'over' ? 'GAME OVER · restart to play' : state.status === 'won' ? 'MAZE CLEAR · steer for level ' + state.level : !state.ready ? 'Choose a direction to play' : state.powered > 0 ? 'POWER UP · chase the ghosts' : 'Collect every dot' }, finished: state.status === 'over' };
  },
};
