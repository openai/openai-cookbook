// Self-contained simulation: copied into the editable arcade space source.
const snakeVectors = { up: [0, -1], down: [0, 1], left: [-1, 0], right: [1, 0] };
const snakeOpposite = { up: 'down', down: 'up', left: 'right', right: 'left' };
function snakeCell(value) { return Number.isInteger(value) && value >= 0 && value < 400; }
function snakeNextRandom(state) { state.rng = (Math.imul(state.rng, 1664525) + 1013904223) >>> 0; return state.rng / 4294967296; }
function snakeFood(state) {
  const free = [];
  for (let cell = 0; cell < 400; cell++) if (!state.body.includes(cell)) free.push(cell);
  return free.length ? free[Math.floor(snakeNextRandom(state) * free.length)] : -1;
}
function snakeFresh(actorId) {
  const state = { actorId, version: 1, body: [209, 208, 207], direction: 'right', queued: 'right', food: 213, score: 0, rng: 19471, elapsed: 0, ready: false, status: 'ready' };
  return state;
}
function snakeInteger(value, low, high, fallback) { return Number.isInteger(value) && value >= low && value <= high ? value : fallback; }
export const snakeGame = {
  init(saved, actor) {
    if (saved && saved.actorId !== actor.id) throw new Error('Snake progress belongs to another participant.');
    const state = snakeFresh(actor.id);
    if (!saved || saved.version !== 1 || !Array.isArray(saved.body) || saved.body.length < 3 || saved.body.length > 400 || !saved.body.every(snakeCell) || new Set(saved.body).size !== saved.body.length) return state;
    for (let index = 1; index < saved.body.length; index++) {
      const previous = saved.body[index - 1], current = saved.body[index];
      if (Math.abs(previous % 20 - current % 20) + Math.abs(Math.floor(previous / 20) - Math.floor(current / 20)) !== 1) return state;
    }
    state.body = [...saved.body];
    const heading = state.body[0] - state.body[1];
    state.direction = heading === 1 ? 'right' : heading === -1 ? 'left' : heading === 20 ? 'down' : 'up';
    state.queued = state.direction;
    state.score = snakeInteger(saved.score, 0, 99999999, 0); state.rng = snakeInteger(saved.rng, 0, 4294967295, 19471);
    state.food = snakeCell(saved.food) && !state.body.includes(saved.food) ? saved.food : snakeFood(state);
    state.status = state.body.length === 400 ? 'won' : saved.status === 'over' ? 'over' : 'ready';
    return state;
  },
  step(state, action) {
    if (state.status === 'over' || state.status === 'won') return state;
    if (action.type === 'direction' && Object.prototype.hasOwnProperty.call(snakeVectors, action.direction)) {
      // Compare with the last actual movement, not another queued key press.
      if (action.direction !== snakeOpposite[state.direction]) { state.queued = action.direction; state.ready = true; state.status = 'playing'; }
      return state;
    }
    if (action.type !== 'tick' || !Number.isFinite(action.deltaMs) || !state.ready) return state;
    state.elapsed += Math.max(0, Math.min(100, action.deltaMs));
    const cadence = Math.max(80, 125 - Math.floor(state.score / 50) * 5);
    if (state.elapsed < cadence) return state;
    state.elapsed -= cadence; state.direction = state.queued;
    const head = state.body[0], vector = snakeVectors[state.direction], x = head % 20 + vector[0], y = Math.floor(head / 20) + vector[1], next = y * 20 + x;
    const eating = next === state.food;
    if (x < 0 || x >= 20 || y < 0 || y >= 20 || state.body.slice(0, eating ? state.body.length : -1).includes(next)) { state.status = 'over'; state.ready = false; return state; }
    state.body.unshift(next);
    if (eating) {
      state.score += 10; state.food = snakeFood(state);
      if (state.food === -1) { state.status = 'won'; state.ready = false; }
    } else state.body.pop();
    return state;
  },
  view(state) {
    const objects = [{ id: 'board', type: 'rect', x: 10, y: 30, width: 300, height: 300, radius: 5, fill: '#101010', stroke: '#04b84c', lineWidth: 1.5 }];
    for (let line = 1; line < 20; line++) {
      objects.push({ id: 'grid-v-' + line, type: 'rect', x: 10 + line * 15, y: 30, width: 0.5, height: 300, fill: '#262626' }, { id: 'grid-h-' + line, type: 'rect', x: 10, y: 30 + line * 15, width: 300, height: 0.5, fill: '#262626' });
    }
    if (state.food >= 0) {
      const x = 10 + (state.food % 20) * 15, y = 30 + Math.floor(state.food / 20) * 15;
      objects.push({ id: 'food', type: 'rect', x: x + 2.5, y: y + 3, width: 10, height: 10, radius: 3, fill: '#ff8549' }, { id: 'food-leaf', type: 'rect', x: x + 8, y, width: 4, height: 4, fill: '#04b84c' });
    }
    state.body.forEach((cell, index) => objects.push({ id: 'segment-' + index, type: 'rect', x: 10 + (cell % 20) * 15 + 1, y: 30 + Math.floor(cell / 20) * 15 + 1, width: 13, height: 13, radius: index === 0 ? 4 : 2, fill: index === 0 ? '#ffffff' : index % 2 ? '#04b84c' : '#57dc8c' }));
    const head = state.body[0], x = 17.5 + (head % 20) * 15, y = 37.5 + Math.floor(head / 20) * 15, vector = snakeVectors[state.direction];
    for (const side of [-1, 1]) objects.push({ id: 'eye-' + side, type: 'rect', x: x + vector[0] * 3 + vector[1] * side * 3 - 1, y: y + vector[1] * 3 + vector[0] * side * 3 - 1, width: 2, height: 2, fill: '#080808' });
    return { width: 320, height: 360, background: '#080808', objects, values: { score: state.score, length: state.body.length, status: state.status === 'won' ? 'PERFECT RUN · every square filled' : state.status === 'over' ? 'GAME OVER · restart to play' : !state.ready ? 'Choose a direction to play' : 'Eat, grow, find your rhythm' }, finished: state.status === 'over' || state.status === 'won' };
  },
};
