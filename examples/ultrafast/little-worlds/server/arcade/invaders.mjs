const invadersSprites = [
  ['00011000', '00111100', '01111110', '11011011', '11111111', '00100100', '01011010', '10100101'],
  ['00100100', '00011000', '00111100', '01111110', '11011011', '11111111', '10000001', '01000010'],
  ['00011000', '01111110', '11111111', '11011011', '11111111', '00100100', '01100110', '11000011'],
];
const invadersColors = ['#ff8549', '#b58cff', '#57dc8c', '#04b84c'];

function invadersNumber(value, min, max, integer = false) {
  return typeof value === 'number' && Number.isFinite(value) && value >= min && value <= max && (!integer || Number.isInteger(value));
}

function invadersRandom(state) {
  state.seed = (Math.imul(state.seed, 1664525) + 1013904223) >>> 0;
  return state.seed / 4294967296;
}

function invadersShieldCells() {
  const cells = [];
  for (let bunker = 0; bunker < 3; bunker++) {
    for (let row = 0; row < 4; row++) {
      for (let column = 0; column < 7; column++) {
        if (row === 0 && (column === 0 || column === 6)) continue;
        if (row >= 2 && column >= 2 && column <= 4) continue;
        cells.push({ id: `b${bunker}-${row}-${column}`, x: 58 + bunker * 85 + column * 5, y: 285 + row * 5 });
      }
    }
  }
  return cells;
}

function invadersFormation(wave) {
  const aliens = [];
  for (let row = 0; row < 4; row++) {
    for (let column = 0; column < 9; column++) aliens.push({ id: row * 9 + column, row, x: 38 + column * 28, y: 53 + row * 25 + Math.min(4, wave - 1) * 6 });
  }
  return aliens;
}

function invadersFresh(actor) {
  let seed = 107;
  for (let index = 0; index < actor.id.length; index++) seed = (Math.imul(seed, 31) + actor.id.charCodeAt(index)) >>> 0;
  return {
    actorId: actor.id, version: 1, score: 0, lives: 3, wave: 1, seed,
    playerX: 160, input: { left: false, right: false, fire: false },
    aliens: invadersFormation(1), shields: invadersShieldCells(), shots: [], enemyShots: [],
    direction: 1, marchMs: 0, fireMs: 550, reloadMs: 0, invincibleMs: 0, waveMs: 0, animation: 0, finished: false,
  };
}

function invadersCopy(state) {
  return {
    ...state, input: { ...state.input }, aliens: state.aliens.map(alien => ({ ...alien })),
    shields: state.shields.map(cell => ({ ...cell })), shots: state.shots.map(shot => ({ ...shot })),
    enemyShots: state.enemyShots.map(shot => ({ ...shot })),
  };
}

function invadersSavedValid(saved, actor) {
  if (!saved || saved.actorId !== actor.id || saved.version !== 1 || typeof saved.finished !== 'boolean') return false;
  for (const key of ['score', 'lives', 'wave', 'seed', 'animation']) {
    const maximum = key === 'lives' ? 3 : key === 'seed' ? 4294967295 : 1000000000;
    if (!invadersNumber(saved[key], key === 'wave' ? 1 : 0, maximum, true)) return false;
  }
  if (!invadersNumber(saved.playerX, 18, 302) || ![-1, 1].includes(saved.direction)) return false;
  if (!saved.input || ['left', 'right', 'fire'].some(key => typeof saved.input[key] !== 'boolean')) return false;
  for (const key of ['marchMs', 'fireMs', 'reloadMs', 'invincibleMs', 'waveMs']) if (!invadersNumber(saved[key], 0, 5000)) return false;
  if (!Array.isArray(saved.aliens) || saved.aliens.length > 36 || !Array.isArray(saved.shields) || saved.shields.length > 60) return false;
  const alienIds = new Set();
  for (const alien of saved.aliens) {
    if (!alien || !invadersNumber(alien.id, 0, 35, true) || alienIds.has(alien.id) || !invadersNumber(alien.row, 0, 3, true) || !invadersNumber(alien.x, 10, 310) || !invadersNumber(alien.y, 0, 330)) return false;
    alienIds.add(alien.id);
  }
  const shieldIds = new Set();
  for (const cell of saved.shields) {
    if (!cell || typeof cell.id !== 'string' || !/^b[0-2]-[0-3]-[0-6]$/.test(cell.id) || shieldIds.has(cell.id) || !invadersNumber(cell.x, 0, 315) || !invadersNumber(cell.y, 0, 355)) return false;
    shieldIds.add(cell.id);
  }
  for (const [key, maximum] of [['shots', 3], ['enemyShots', 8]]) {
    if (!Array.isArray(saved[key]) || saved[key].length > maximum || saved[key].some(shot => !shot || !invadersNumber(shot.x, 0, 320) || !invadersNumber(shot.y, -12, 370))) return false;
  }
  return saved.finished === (saved.lives === 0);
}

function invadersShoot(state) {
  if (!state.finished && state.waveMs === 0 && state.reloadMs === 0 && state.shots.length < 3) {
    state.shots.push({ x: state.playerX, y: 315 });
    state.reloadMs = 250;
  }
}

function invadersCrosses(x, fromY, toY, left, top, width, height) {
  return x >= left && x <= left + width && Math.max(fromY, toY) >= top && Math.min(fromY, toY) <= top + height;
}

function invadersMoveShots(state, deltaMs) {
  const survivingShots = [];
  for (const shot of state.shots) {
    const nextY = shot.y - deltaMs * 0.24;
    let target = null;
    for (const cell of state.shields) {
      if (invadersCrosses(shot.x, shot.y, nextY, cell.x, cell.y, 5, 5) && (!target || cell.y > target.y)) target = { type: 'shield', id: cell.id, y: cell.y };
    }
    for (const alien of state.aliens) {
      if (invadersCrosses(shot.x, shot.y, nextY, alien.x - 10, alien.y - 8, 20, 16) && (!target || alien.y > target.y)) target = { type: 'alien', id: alien.id, y: alien.y, row: alien.row };
    }
    if (target?.type === 'shield') state.shields = state.shields.filter(cell => cell.id !== target.id);
    else if (target?.type === 'alien') {
      state.aliens = state.aliens.filter(alien => alien.id !== target.id);
      state.score += (4 - target.row) * 10;
    } else if (nextY > 22) survivingShots.push({ x: shot.x, y: nextY });
  }
  state.shots = survivingShots;
  const survivingEnemyShots = [];
  for (const shot of state.enemyShots) {
    const nextY = shot.y + deltaMs * (0.056 + Math.min(10, state.wave - 1) * 0.005);
    let target = null;
    for (const cell of state.shields) {
      if (invadersCrosses(shot.x, shot.y, nextY, cell.x, cell.y, 5, 5) && (!target || cell.y < target.y)) target = cell;
    }
    if (target) state.shields = state.shields.filter(cell => cell.id !== target.id);
    else if (state.invincibleMs === 0 && invadersCrosses(shot.x, shot.y, nextY, state.playerX - 11, 318, 22, 15)) {
      state.lives--;
      state.invincibleMs = 1500;
      state.playerX = 160;
      if (state.lives === 0) state.finished = true;
    } else if (nextY < 340) survivingEnemyShots.push({ x: shot.x, y: nextY });
  }
  state.enemyShots = survivingEnemyShots;
}

function invadersAdvance(state, deltaMs) {
  state.reloadMs = Math.max(0, state.reloadMs - deltaMs);
  state.invincibleMs = Math.max(0, state.invincibleMs - deltaMs);
  state.playerX = Math.max(18, Math.min(302, state.playerX + (Number(state.input.right) - Number(state.input.left)) * deltaMs * 0.12));
  if (state.waveMs > 0) {
    state.waveMs = Math.max(0, state.waveMs - deltaMs);
    if (state.waveMs === 0) {
      state.aliens = invadersFormation(state.wave);
      state.shields = invadersShieldCells();
      state.direction = 1;
      state.fireMs = 750;
      state.marchMs = 0;
    }
    return;
  }
  if (state.input.fire) invadersShoot(state);
  state.marchMs += deltaMs;
  const interval = Math.max(65, 420 - (36 - state.aliens.length) * 9 - Math.min(20, state.wave - 1) * 18);
  while (state.marchMs >= interval && state.aliens.length) {
    state.marchMs -= interval;
    state.animation = (state.animation + 1) % 2;
    const edge = state.aliens.some(alien => alien.x + state.direction * 5 < 20 || alien.x + state.direction * 5 > 300);
    if (edge) state.direction *= -1;
    for (const alien of state.aliens) {
      if (edge) alien.y += 10;
      else alien.x += state.direction * 5;
    }
  }
  state.shields = state.shields.filter(cell => !state.aliens.some(alien => Math.abs(alien.x - cell.x - 2.5) < 12 && Math.abs(alien.y - cell.y - 2.5) < 11));
  if (state.aliens.some(alien => alien.y >= 309)) {
    state.lives = 0;
    state.finished = true;
    return;
  }
  state.fireMs = Math.max(0, state.fireMs - deltaMs);
  if (state.fireMs === 0 && state.enemyShots.length < 8 && state.aliens.length) {
    const column = Math.floor(invadersRandom(state) * 9);
    let shooter = null;
    for (const alien of state.aliens) if (alien.id % 9 === column && (!shooter || alien.y > shooter.y)) shooter = alien;
    if (!shooter) shooter = state.aliens[Math.floor(invadersRandom(state) * state.aliens.length)];
    state.enemyShots.push({ x: shooter.x, y: shooter.y + 9 });
    state.fireMs = Math.max(230, 780 - Math.min(20, state.wave - 1) * 45) + Math.floor(invadersRandom(state) * 380);
  }
  invadersMoveShots(state, deltaMs);
  if (!state.finished && state.aliens.length === 0) {
    state.score += 100 * state.wave;
    state.wave++;
    state.waveMs = 1200;
    state.shots = [];
    state.enemyShots = [];
  }
}

function invadersPixelPath(pattern, x, y, pixel) {
  let path = '';
  for (let row = 0; row < pattern.length; row++) {
    for (let column = 0; column < pattern[row].length; column++) {
      if (pattern[row][column] === '1') path += `M${x + column * pixel} ${y + row * pixel}h${pixel}v${pixel}h-${pixel}Z`;
    }
  }
  return path;
}

export const invadersGame = {
  init(saved, actor) {
    if (!saved) return invadersFresh(actor);
    if (!invadersSavedValid(saved, actor)) throw new Error('Invalid Space Invaders checkpoint.');
    const state = invadersCopy(saved);
    state.input = { left: false, right: false, fire: false };
    return state;
  },
  step(current, action) {
    const state = invadersCopy(current);
    if (action.type === 'input') {
      if (!['left', 'right', 'fire'].includes(action.key) || typeof action.held !== 'boolean') throw new Error('Unknown Space Invaders control.');
      state.input[action.key] = action.held;
      return state;
    }
    if (action.type === 'fire') { invadersShoot(state); return state; }
    if (action.type !== 'tick' || !invadersNumber(action.deltaMs, 1, 1000)) throw new Error('Unknown Space Invaders action.');
    if (state.finished) return state;
    let remaining = action.deltaMs;
    while (remaining > 0 && !state.finished) {
      const delta = Math.min(50, remaining);
      invadersAdvance(state, delta);
      remaining -= delta;
    }
    return state;
  },
  view(state) {
    const objects = [
      { id: 'border', type: 'rect', x: 8, y: 28, width: 304, height: 311, fill: '#080808', stroke: '#3b3b3b', lineWidth: 1 },
      { id: 'score-label', type: 'text', x: 12, y: 17, text: `SCORE ${String(state.score).padStart(5, '0')}`, fontSize: 10, fill: '#57dc8c' },
      { id: 'wave-label', type: 'text', x: 308, y: 17, text: `WAVE ${String(state.wave).padStart(2, '0')}`, align: 'right', fontSize: 10, fill: '#b58cff' },
      { id: 'ground', type: 'rect', x: 9, y: 337, width: 302, height: 2, fill: '#57dc8c' },
      { id: 'lives-label', type: 'text', x: 12, y: 354, text: `LIVES ${state.lives}`, fontSize: 9, fill: '#ff8549' },
      { id: 'controls-label', type: 'text', x: 308, y: 354, text: 'MOVE + FIRE', align: 'right', fontSize: 9, fill: '#a3a3a3' },
    ];
    for (let star = 0; star < 23; star++) objects.push({ id: `star-${star}`, type: 'rect', x: 15 + (star * 71) % 290, y: 34 + (star * 53) % 276, width: 1, height: star % 3 === 0 ? 2 : 1, fill: star % 3 === 0 ? '#777777' : '#333333' });
    for (const cell of state.shields) objects.push({ id: cell.id, type: 'rect', x: cell.x, y: cell.y, width: 4.5, height: 4.5, fill: '#04b84c' });
    for (const alien of state.aliens) {
      const sprite = invadersSprites[(alien.row + state.animation) % invadersSprites.length];
      objects.push({ id: `alien-${alien.id}`, type: 'path', d: invadersPixelPath(sprite, alien.x - 8, alien.y - 8, 2), fill: invadersColors[alien.row] });
    }
    if (!state.finished && (state.invincibleMs === 0 || Math.floor(state.invincibleMs / 100) % 2 === 0)) objects.push({ id: 'cannon', type: 'path', d: `M${state.playerX - 11} 331v-8h7v-4h3v-4h2v4h3v4h7v8Z`, fill: '#57dc8c' });
    state.shots.forEach((shot, index) => objects.push({ id: `shot-${index}`, type: 'rect', x: shot.x - 1, y: shot.y - 6, width: 2, height: 8, fill: '#ffffff' }));
    state.enemyShots.forEach((shot, index) => objects.push({ id: `enemy-shot-${index}`, type: 'path', d: `M${shot.x - 2} ${shot.y - 4}l4 3l-4 3l4 3`, stroke: '#ff8549', lineWidth: 2 }));
    if (state.finished || state.waveMs > 0) {
      objects.push({ id: 'notice-bg', type: 'rect', x: 40, y: 159, width: 240, height: 52, fill: '#080808', stroke: state.finished ? '#ff8549' : '#57dc8c', lineWidth: 1 });
      objects.push({ id: 'notice', type: 'text', x: 160, y: 181, text: state.finished ? 'GAME OVER' : `WAVE ${state.wave} INCOMING`, fontSize: 17, align: 'center', fill: state.finished ? '#ff8549' : '#57dc8c' });
      objects.push({ id: 'notice-detail', type: 'text', x: 160, y: 198, text: state.finished ? 'RESTART TO DEFEND AGAIN' : 'SHIELDS RESTORED', fontSize: 9, align: 'center', fill: '#b58cff' });
    }
    return { width: 320, height: 360, background: '#080808', objects, values: { score: state.score, lives: state.lives, level: state.wave, wave: state.wave, status: state.finished ? 'Game over. Restart to defend again.' : state.waveMs > 0 ? `Wave ${state.wave} incoming. Shields restored.` : `${state.aliens.length} invaders remain. Move left or right and fire.` }, finished: state.finished };
  },
};
