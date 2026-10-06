function tetrisKinds() {
  return ['I', 'O', 'T', 'S', 'Z', 'J', 'L'];
}

function tetrisCells(type, rotation) {
  const shapes = {
    I: [[0, 1], [1, 1], [2, 1], [3, 1]],
    O: [[1, 0], [2, 0], [1, 1], [2, 1]],
    T: [[1, 0], [0, 1], [1, 1], [2, 1]],
    S: [[1, 0], [2, 0], [0, 1], [1, 1]],
    Z: [[0, 0], [1, 0], [1, 1], [2, 1]],
    J: [[0, 0], [0, 1], [1, 1], [2, 1]],
    L: [[2, 0], [0, 1], [1, 1], [2, 1]],
  };
  let cells = shapes[type];
  if (type === 'O') return cells;
  const edge = type === 'I' ? 3 : 2;
  for (let turn = 0; turn < rotation; turn++) cells = cells.map(([x, y]) => [edge - y, x]);
  return cells;
}

function tetrisFits(board, piece) {
  return tetrisCells(piece.type, piece.rotation).every(([dx, dy]) => {
    const x = piece.x + dx, y = piece.y + dy;
    return x >= 0 && x < 10 && y < 20 && (y < 0 || board[y * 10 + x] === 0);
  });
}

function tetrisCopy(state) {
  return {
    version: 1, actorId: state.actorId, board: state.board.slice(), piece: { ...state.piece },
    next: state.next, bag: state.bag.slice(), rng: state.rng, score: state.score,
    lines: state.lines, level: state.level, pieces: state.pieces, elapsed: state.elapsed, over: state.over,
  };
}

function tetrisRandom(state) {
  let value = state.rng;
  value ^= value << 13;
  value ^= value >>> 17;
  value ^= value << 5;
  state.rng = value >>> 0;
  return state.rng / 4294967296;
}

function tetrisTake(state) {
  if (!state.bag.length) {
    state.bag = tetrisKinds();
    for (let index = state.bag.length - 1; index > 0; index--) {
      const other = Math.floor(tetrisRandom(state) * (index + 1));
      const held = state.bag[index];
      state.bag[index] = state.bag[other];
      state.bag[other] = held;
    }
  }
  return state.bag.pop();
}

function tetrisValid(saved, actor) {
  const integer = (value, maximum) => Number.isInteger(value) && value >= 0 && value <= maximum;
  if (!saved || typeof saved !== 'object' || saved.version !== 1 || saved.actorId !== actor.id
    || !Array.isArray(saved.board) || saved.board.length !== 200 || Object.keys(saved.board).length !== 200
    || !saved.board.every(value => integer(value, 7))
    || !saved.piece || !tetrisKinds().includes(saved.piece.type)
    || !integer(saved.piece.rotation, 3)
    || !Number.isInteger(saved.piece.x) || saved.piece.x < -3 || saved.piece.x > 9
    || !Number.isInteger(saved.piece.y) || saved.piece.y < -4 || saved.piece.y > 19
    || !tetrisKinds().includes(saved.next)
    || !Array.isArray(saved.bag) || saved.bag.length > 7 || Object.keys(saved.bag).length !== saved.bag.length
    || !saved.bag.every(type => tetrisKinds().includes(type))
    || new Set(saved.bag).size !== saved.bag.length
    || !integer(saved.rng, 4294967295) || saved.rng === 0
    || !integer(saved.score, Number.MAX_SAFE_INTEGER)
    || !integer(saved.lines, Number.MAX_SAFE_INTEGER)
    || saved.level !== Math.floor(saved.lines / 10) + 1
    || !integer(saved.pieces, Number.MAX_SAFE_INTEGER)
    || typeof saved.elapsed !== 'number' || !Number.isFinite(saved.elapsed) || saved.elapsed < 0 || saved.elapsed >= 700
    || typeof saved.over !== 'boolean'
    || (!saved.over && !tetrisFits(saved.board, saved.piece))) {
    throw new Error('Invalid Tetris checkpoint for this player.');
  }
  // A completed row is removed in the same step that locks its final piece.
  // Reject impossible saved rows instead of letting a fabricated checkpoint
  // clear more than four rows and escape the scoring table on its next lock.
  for (let row = 0; row < 20; row++) {
    if (saved.board.slice(row * 10, row * 10 + 10).every(Boolean)) {
      throw new Error('Invalid Tetris checkpoint for this player.');
    }
  }
}

function tetrisLock(state) {
  const cells = tetrisCells(state.piece.type, state.piece.rotation);
  if (cells.some(([, dy]) => state.piece.y + dy < 0)) {
    state.over = true;
    return;
  }
  const color = tetrisKinds().indexOf(state.piece.type) + 1;
  for (const [dx, dy] of cells) state.board[(state.piece.y + dy) * 10 + state.piece.x + dx] = color;
  const remaining = [], empty = [];
  let cleared = 0;
  for (let row = 0; row < 20; row++) {
    const cellsInRow = state.board.slice(row * 10, row * 10 + 10);
    if (cellsInRow.every(Boolean)) { cleared++; empty.push(...Array(10).fill(0)); }
    else remaining.push(...cellsInRow);
  }
  state.board = empty.concat(remaining);
  state.score += [0, 100, 300, 500, 800][cleared] * state.level;
  state.lines += cleared;
  state.level = Math.floor(state.lines / 10) + 1;
  state.pieces++;
  state.piece = { type: state.next, rotation: 0, x: 3, y: 0 };
  state.next = tetrisTake(state);
  state.elapsed = 0;
  if (!tetrisFits(state.board, state.piece)) state.over = true;
}

function tetrisDown(state, reward) {
  const next = { ...state.piece, y: state.piece.y + 1 };
  if (tetrisFits(state.board, next)) {
    state.piece = next;
    state.score += reward;
    return true;
  }
  tetrisLock(state);
  return false;
}

function tetrisPaintBlock(objects, id, x, y, size, color, ghost) {
  objects.push({ id, type: 'rect', x: x + 1, y: y + 1, width: size - 2, height: size - 2,
    radius: 1, fill: ghost ? '#141414' : color, stroke: ghost ? '#777777' : '#ffffff30', lineWidth: 1 });
  if (!ghost) objects.push({ id: id + '-light', type: 'rect', x: x + 3, y: y + 3,
    width: size - 6, height: 2, fill: '#ffffff55' });
}

export const tetrisGame = {
  init(saved, actor) {
    if (saved !== null && saved !== undefined) {
      tetrisValid(saved, actor);
      return tetrisCopy(saved);
    }
    let seed = 2166136261;
    for (let index = 0; index < actor.id.length; index++) seed = Math.imul(seed ^ actor.id.charCodeAt(index), 16777619) >>> 0;
    const state = {
      version: 1, actorId: actor.id, board: Array(200).fill(0), piece: null, next: '', bag: [],
      rng: seed || 1, score: 0, lines: 0, level: 1, pieces: 0, elapsed: 0, over: false,
    };
    state.piece = { type: tetrisTake(state), rotation: 0, x: 3, y: 0 };
    state.next = tetrisTake(state);
    return state;
  },

  step(previous, action) {
    const state = tetrisCopy(previous);
    if (state.over) return state;
    if (action.type === 'move') {
      if (action.direction === 'down') tetrisDown(state, 1);
      else if (action.direction === 'left' || action.direction === 'right') {
        const next = { ...state.piece, x: state.piece.x + (action.direction === 'left' ? -1 : 1) };
        if (tetrisFits(state.board, next)) state.piece = next;
      } else throw new Error('Choose left, right, or down to move a Tetris piece.');
    } else if (action.type === 'rotate') {
      const rotation = (state.piece.rotation + 1) % 4;
      for (const [dx, dy] of [[0, 0], [-1, 0], [1, 0], [-2, 0], [2, 0], [0, -1], [0, -2]]) {
        const next = { ...state.piece, rotation, x: state.piece.x + dx, y: state.piece.y + dy };
        if (tetrisFits(state.board, next)) { state.piece = next; break; }
      }
    } else if (action.type === 'drop') {
      while (tetrisFits(state.board, { ...state.piece, y: state.piece.y + 1 })) {
        state.piece.y++;
        state.score += 2;
      }
      tetrisLock(state);
    } else if (action.type === 'tick') {
      const deltaMs = action.deltaMs === undefined ? 50 : action.deltaMs;
      if (typeof deltaMs !== 'number' || !Number.isFinite(deltaMs) || deltaMs < 0 || deltaMs > 1000) {
        throw new Error('Tetris tick delta must be between 0 and 1000 milliseconds.');
      }
      state.elapsed += deltaMs;
      const interval = Math.max(80, 700 - (state.level - 1) * 55);
      while (!state.over && state.elapsed >= interval) {
        state.elapsed -= interval;
        if (!tetrisDown(state, 0)) break;
      }
    } else throw new Error('Unknown Tetris action.');
    return state;
  },

  view(state) {
    const colors = ['#57dbef', '#f4d76b', '#b890f6', '#80dda0', '#f47b94', '#789cf6', '#f4ae70'];
    const objects = [
      { id: 'name', type: 'text', x: 16, y: 23, text: 'TETRIS', fontSize: 16, fill: '#ffffff' },
      { id: 'edition', type: 'text', x: 302, y: 22, text: '04 / STACK', fontSize: 10, align: 'right', fill: '#a3a3a3' },
      { id: 'well', type: 'rect', x: 14, y: 40, width: 204, height: 404, fill: '#080808', stroke: '#924ff7', lineWidth: 2 },
      { id: 'side-rule', type: 'rect', x: 227, y: 42, width: 1, height: 399, fill: '#3b3b3b' },
    ];
    for (let row = 1; row < 20; row++) objects.push({ id: 'grid-y-' + row, type: 'rect', x: 16,
      y: 42 + row * 20, width: 200, height: 1, fill: '#202020' });
    for (let column = 1; column < 10; column++) objects.push({ id: 'grid-x-' + column, type: 'rect',
      x: 16 + column * 20, y: 42, width: 1, height: 400, fill: '#202020' });
    for (let index = 0; index < state.board.length; index++) {
      if (state.board[index]) tetrisPaintBlock(objects, 'settled-' + index, 16 + (index % 10) * 20,
        42 + Math.floor(index / 10) * 20, 20, colors[state.board[index] - 1], false);
    }
    if (!state.over) {
      const ghost = { ...state.piece };
      while (tetrisFits(state.board, { ...ghost, y: ghost.y + 1 })) ghost.y++;
      if (ghost.y > state.piece.y) tetrisCells(ghost.type, ghost.rotation).forEach(([dx, dy], index) => {
        if (ghost.y + dy >= 0) tetrisPaintBlock(objects, 'ghost-' + index, 16 + (ghost.x + dx) * 20,
          42 + (ghost.y + dy) * 20, 20, '', true);
      });
      tetrisCells(state.piece.type, state.piece.rotation).forEach(([dx, dy], index) => {
        if (state.piece.y + dy >= 0) tetrisPaintBlock(objects, 'piece-' + index, 16 + (state.piece.x + dx) * 20,
          42 + (state.piece.y + dy) * 20, 20, colors[tetrisKinds().indexOf(state.piece.type)], false);
      });
    }
    const label = (id, text, y, color, fontSize) => objects.push({ id, type: 'text', x: 239, y,
      text, fill: color || '#a3a3a3', fontSize: fontSize || 10 });
    label('next-label', 'NEXT', 58);
    objects.push({ id: 'next-box', type: 'rect', x: 237, y: 69, width: 68, height: 67, fill: '#141414', stroke: '#3b3b3b', lineWidth: 1 });
    const preview = tetrisCells(state.next, 0);
    const minX = Math.min(...preview.map(([x]) => x)), maxX = Math.max(...preview.map(([x]) => x));
    const minY = Math.min(...preview.map(([, y]) => y)), maxY = Math.max(...preview.map(([, y]) => y));
    preview.forEach(([x, y], index) => tetrisPaintBlock(objects, 'preview-' + index,
      271 - (maxX - minX + 1) * 7 + (x - minX) * 14,
      103 - (maxY - minY + 1) * 7 + (y - minY) * 14, 14, colors[tetrisKinds().indexOf(state.next)], false));
    label('score-label', 'SCORE', 167);
    label('score', String(state.score), 188, '#f4d76b', state.score > 999999 ? 11 : 14);
    label('lines-label', 'LINES', 227);
    label('lines', String(state.lines), 249, '#ffffff', 16);
    label('level-label', 'LEVEL', 288);
    label('level', String(state.level).padStart(2, '0'), 310, '#b890f6', 18);
    label('goal-a', 'FILL ROWS.', 371, '#a3a3a3', 9);
    label('goal-b', 'MAKE ROOM.', 387, '#a3a3a3', 9);
    objects.push({ id: 'footer', type: 'text', x: 16, y: 466, text: 'ARROWS MOVE · UP ROTATES · SPACE DROPS', fontSize: 9, fill: '#a3a3a3' });
    if (state.over) {
      objects.push({ id: 'over-shade', type: 'rect', x: 16, y: 185, width: 200, height: 101, fill: '#080808ee', stroke: '#b890f6', lineWidth: 1 });
      objects.push({ id: 'over-title', type: 'text', x: 116, y: 223, text: 'GAME OVER', align: 'center', fontSize: 20, fill: '#f4d76b' });
      objects.push({ id: 'over-hint', type: 'text', x: 116, y: 253, text: 'ONE MORE ROUND?', align: 'center', fontSize: 11, fill: '#ffffff' });
    }
    return { width: 320, height: 480, background: '#080808', objects, finished: state.over,
      values: { score: state.score, level: state.level, lines: state.lines, next: state.next, status: state.over ? 'Game over' : 'Playing' } };
  },
};
