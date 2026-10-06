// Curated demo source. Concatenated with the four simulations for normal publication.
export const meta = {
  title: "Karen's arcade", subtitle: 'Good times. High scores.', accent: '#924ff7', layout: 'canvas',
  games: [
    { id: 'pacman', exportName: 'pacmanGame', tickMs: 50, saveAction: 'save_pacman' },
    { id: 'space-invaders', exportName: 'invadersGame', tickMs: 50, saveAction: 'save_invaders' },
    { id: 'snake', exportName: 'snakeGame', tickMs: 50, saveAction: 'save_snake' },
    { id: 'tetris', exportName: 'tetrisGame', tickMs: 50, saveAction: 'save_tetris' },
  ],
  suggestions: [
    { label: 'Make it mine', prompt: 'Give my arcade a new visual theme, keeping all four playable games, their controls, and everyone’s saved progress.' },
    { label: 'Add a challenge', prompt: 'Add a difficulty selector to Snake, preserving its saved progress and all other games.' },
  ],
};
function arcadeEscape(value) { return String(value).replace(/[&<>"']/g, character => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' })[character]); }
function arcadeDefinitions() {
  return [
    { id: 'pacman', name: 'PacMan', number: '01', tag: 'THE MAZE CHASE', color: '#ff8549', copy: 'A pocketful of dots. Four familiar ghosts.', keys: 'Arrow keys or WASD to steer', stat: 'lives', label: 'LIVES', game: pacmanGame },
    { id: 'space-invaders', name: 'Space Invaders', number: '02', tag: 'THE LAST LINE', color: '#924ff7', copy: 'Hold the line. Send them back to the stars.', keys: '← → or A D to move · Space to fire', stat: 'wave', label: 'WAVE', game: invadersGame },
    { id: 'snake', name: 'Snake', number: '03', tag: 'ONE MORE BITE', color: '#04b84c', copy: 'Small beginnings. Delicious complications.', keys: 'Arrow keys or WASD to steer', stat: 'length', label: 'LENGTH', game: snakeGame },
    { id: 'tetris', name: 'Tetris', number: '04', tag: 'FIND YOUR FIT', color: '#006aff', copy: 'A little order in a beautifully falling world.', keys: '← → move · ↑ rotate · ↓ lower · Space drop', stat: 'lines', label: 'LINES', game: tetrisGame },
  ];
}
function arcadePreview(scene) {
  const objects = scene.objects.map(shape => {
    const common = ' fill="' + arcadeEscape(shape.fill || (shape.stroke ? 'none' : '#ffffff')) + '"' + (shape.stroke ? ' stroke="' + arcadeEscape(shape.stroke) + '" stroke-width="' + (shape.lineWidth || 1) + '"' : '');
    const transform = ' transform="translate(' + (shape.x || 0) + ' ' + (shape.y || 0) + ') rotate(' + (shape.rotation || 0) + ')"';
    if (shape.type === 'rect') return '<rect' + transform + common + ' width="' + shape.width + '" height="' + shape.height + '" rx="' + (shape.radius || 0) + '"/>';
    if (shape.type === 'circle') return '<circle' + transform + common + ' r="' + shape.radius + '"/>';
    if (shape.type === 'path') return '<path' + transform + common + ' d="' + arcadeEscape(shape.d) + '"/>';
    return '<text' + transform + common + ' font-size="' + (shape.fontSize || 16) + '" text-anchor="' + (shape.align === 'center' ? 'middle' : shape.align === 'right' ? 'end' : 'start') + '">' + arcadeEscape(shape.text || '') + '</text>';
  }).join('');
  return '<svg class="arcade-preview" aria-hidden="true" viewBox="0 0 ' + scene.width + ' ' + scene.height + '"><rect width="100%" height="100%" fill="' + scene.background + '"/>' + objects + '</svg>';
}
function arcadeButton(name, label, symbol, action, keys, release) {
  return '<button type="button" class="arcade-key" aria-label="' + name + ' ' + label + '" data-game-action="' + arcadeEscape(JSON.stringify(action)) + '" data-game-keys="' + keys + '"' + (release ? ' data-game-release="' + arcadeEscape(JSON.stringify(release)) + '"' : '') + '><span aria-hidden="true">' + symbol + '</span></button>';
}
function arcadeControls(game) {
  if (game.id === 'pacman' || game.id === 'snake') return '<div class="arcade-dpad">' + [
    ['up', '↑', 'ArrowUp w W'], ['left', '←', 'ArrowLeft a A'], ['down', '↓', 'ArrowDown s S'], ['right', '→', 'ArrowRight d D'],
  ].map(([direction, symbol, keys]) => arcadeButton(game.name, 'move ' + direction, symbol, { type: 'direction', direction }, keys)).join('') + '</div>';
  if (game.id === 'space-invaders') return '<div class="arcade-buttons">' + [
    ['left', '←', 'ArrowLeft a A'], ['fire', 'FIRE', 'Space'], ['right', '→', 'ArrowRight d D'],
  ].map(([key, symbol, keys]) => arcadeButton(game.name, key === 'fire' ? 'fire' : 'move ' + key, symbol, { type: 'input', key, held: true }, keys, { type: 'input', key, held: false })).join('') + '</div>';
  return '<div class="arcade-buttons arcade-tetris-buttons">' + [
    arcadeButton(game.name, 'move left', '←', { type: 'move', direction: 'left' }, 'ArrowLeft a A'),
    arcadeButton(game.name, 'rotate', '↻', { type: 'rotate' }, 'ArrowUp w W'),
    arcadeButton(game.name, 'move right', '→', { type: 'move', direction: 'right' }, 'ArrowRight d D'),
    arcadeButton(game.name, 'lower', '↓', { type: 'move', direction: 'down' }, 'ArrowDown s S'),
    arcadeButton(game.name, 'drop', 'DROP', { type: 'drop' }, 'Space'),
  ].join('') + '</div>';
}
function arcadeTile(game, state, actor) {
  const saved = state.extras[game.id] && state.extras[game.id][actor.id];
  const scene = game.game.view(game.game.init(saved || null, actor));
  return '<section class="arcade-cabinet" data-game="' + game.id + '" tabindex="0" aria-label="' + game.name + ' arcade game" style="--game-color:' + game.color + '">' +
    '<div class="arcade-marquee"><span>' + game.tag + '</span><span>' + game.number + ' / 04</span></div>' +
    '<div class="arcade-title"><h2>' + game.name + '</h2><span class="arcade-token" aria-hidden="true">✦</span></div><p class="arcade-copy">' + game.copy + '</p>' +
    '<div class="arcade-score"><div><span>SCORE</span><strong data-game-value="score">' + arcadeEscape(scene.values.score) + '</strong></div><div><span>' + game.label + '</span><strong data-game-value="' + game.stat + '">' + arcadeEscape(scene.values[game.stat]) + '</strong></div></div>' +
    '<div class="arcade-screen"><canvas data-game-canvas width="' + scene.width + '" height="' + scene.height + '" aria-label="' + game.name + ' playfield"></canvas>' + arcadePreview(scene) + '</div>' +
    '<p class="arcade-play-status" data-game-value="status">' + (saved ? 'Your saved game is ready' : 'Your next high score starts here') + '</p>' +
    '<div class="arcade-command-row">' + ['start', 'pause', 'resume', 'restart'].map(command => '<button type="button" class="arcade-command' + (command === 'restart' ? ' arcade-secondary' : '') + '" data-game-command="' + command + '" aria-label="' + command[0].toUpperCase() + command.slice(1) + ' ' + game.name + '">' + (command === 'start' ? saved ? 'Continue game' : 'Let’s play' : command === 'restart' ? 'New game' : command === 'resume' ? 'Resume' : 'Pause') + '</button>').join('') + '<span class="arcade-runtime" data-game-runtime-status data-status-idle="Ready when you are" data-status-running="You’re playing" data-status-paused="Paused · progress saved" role="status"></span></div>' +
    arcadeControls(game) + '<p class="arcade-key-guide">' + game.keys + '</p></section>';
}
export function render(state, actor) {
  return `<style>
  .arcade-world{--ink:#fff;--muted:#a3a3a3;--line:#303030;--green:#04b84c;--violet:#924ff7;box-sizing:border-box;background:#080808;color:var(--ink);border-radius:4px;overflow:hidden;font-family:system-ui,Arial,Helvetica,sans-serif;padding:38px clamp(18px,4.3vw,58px) 28px;color-scheme:dark}
  .arcade-world *{box-sizing:border-box}.arcade-world button{font:inherit;cursor:pointer}.arcade-world button:focus-visible,.arcade-cabinet:focus-visible{outline:3px solid #b58cff;outline-offset:4px}.arcade-world button:disabled{cursor:default;opacity:.35}.arcade-world [hidden]{display:none!important}
  .arcade-top{display:flex;justify-content:space-between;align-items:center;gap:14px;font-size:11px;font-weight:500;line-height:1.4;letter-spacing:.12em}.arcade-brand{display:flex;align-items:center;gap:10px}.arcade-brand i{width:10px;height:10px;background:var(--green);box-shadow:4px -4px 0 var(--violet)}.arcade-open{color:#57dc8c}.arcade-open:before{content:'';display:inline-block;width:6px;height:6px;border-radius:50%;background:currentColor;margin-right:7px}
  .arcade-hero{display:flex;align-items:center;justify-content:space-between;gap:28px;padding:46px 0 35px}.arcade-hero h1{font:500 clamp(40px,6.6vw,82px)/.98 system-ui,Arial,Helvetica,sans-serif;letter-spacing:-.06em;margin:0;color:#fff}.arcade-hero h1 span{color:var(--green)}.arcade-hero p{max-width:340px;color:var(--muted);font-size:14px;line-height:1.7;margin:23px 0 0}.arcade-emblem{width:180px;flex:none}
  .arcade-divider{height:1px;background:var(--line);margin-bottom:28px}.arcade-intro{display:flex;justify-content:space-between;gap:16px;margin:0 0 18px;font-size:11px;line-height:1.6;letter-spacing:.09em;color:var(--muted)}.arcade-intro span:last-child{text-align:right}
  .arcade-grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:24px}.arcade-cabinet{min-width:0;padding:23px;background:#141414;border:1px solid var(--line);border-top:3px solid var(--game-color);border-radius:4px;transition:border-color .16s}.arcade-cabinet:focus-within{border-color:var(--game-color)}.arcade-marquee{display:flex;justify-content:space-between;color:color-mix(in srgb,var(--game-color) 75%,white);font-size:10px;font-weight:500;line-height:1.4;letter-spacing:.12em}.arcade-title{display:flex;align-items:center;justify-content:space-between;gap:10px;margin-top:13px}.arcade-title h2{font:500 clamp(25px,3vw,35px)/1.2 system-ui,Arial,Helvetica,sans-serif;letter-spacing:-.045em;margin:0}.arcade-token{font-size:27px;color:var(--game-color)}.arcade-copy{font-size:12px;line-height:1.6;color:var(--muted);margin:7px 0 20px}.arcade-score{display:flex;justify-content:space-between;padding:12px 16px;background:#080808;border:1px solid var(--line);border-bottom:0;border-radius:3px 3px 0 0;font-variant-numeric:tabular-nums}.arcade-score div{display:flex;align-items:baseline;gap:12px}.arcade-score span{font-size:10px;letter-spacing:.09em;color:var(--muted)}.arcade-score strong{font-size:20px;color:color-mix(in srgb,var(--game-color) 75%,white);font-weight:500}
  .arcade-screen{height:360px;position:relative;background:#080808;border:1px solid var(--line);border-radius:0 0 3px 3px;overflow:hidden}.arcade-screen canvas,.arcade-preview{display:block;width:100%;height:100%;object-fit:contain}.arcade-preview{position:absolute;inset:0;pointer-events:none}.arcade-cabinet[data-game-ready="true"] .arcade-preview{display:none}.arcade-play-status{font-size:11px;line-height:1.5;color:color-mix(in srgb,var(--game-color) 75%,white);min-height:30px;margin:13px 0 9px;text-align:center;letter-spacing:.025em}.arcade-command-row{display:flex;align-items:center;justify-content:center;flex-wrap:wrap;gap:10px;min-height:44px}.arcade-command{border:1px solid var(--green);border-radius:4px;background:var(--green);color:#000;padding:12px 20px;font-size:12px!important;font-weight:500!important;min-height:44px;transition:background .16s,border-color .16s}.arcade-command:hover{background:#57dc8c;border-color:#57dc8c}.arcade-secondary{background:transparent;border-color:#555;color:#fff;padding-inline:13px}.arcade-secondary:hover{background:#252525;border-color:#888}.arcade-runtime{flex-basis:100%;text-align:center;color:var(--muted);font-size:10px;line-height:1.4;min-height:14px}
  .arcade-buttons,.arcade-dpad{display:flex;align-items:center;justify-content:center;gap:9px;margin:16px auto 12px;min-height:44px}.arcade-key{min-width:44px;height:44px;padding:0 12px;border:1px solid #555;border-radius:4px;background:#202020;color:#fff;font-size:19px!important;touch-action:none;transition:background .16s,border-color .16s}.arcade-key:hover{border-color:var(--game-color);background:#2c2c2c}.arcade-key:active{background:#343434}.arcade-key-guide{font-size:10px;line-height:1.6;color:var(--muted);text-align:center;margin:0;min-height:32px}.arcade-tetris-buttons{gap:7px}.arcade-tetris-buttons .arcade-key{padding-inline:10px;min-width:40px;font-size:16px!important}
  .arcade-footer{display:flex;justify-content:space-between;gap:22px;margin-top:36px;padding-top:22px;border-top:1px solid var(--line);font-size:10px;line-height:1.7;color:var(--muted)}.arcade-footer strong{display:block;color:#fff;font-size:11px;font-weight:500;letter-spacing:.08em;margin-bottom:5px}.arcade-footer p{margin:0;max-width:350px}.arcade-footer p:last-child{text-align:right}
  @media(max-width:640px){.arcade-world{padding:24px 15px}.arcade-top{font-size:10px;flex-wrap:wrap}.arcade-hero{padding:35px 0 28px;gap:12px}.arcade-hero h1{font-size:42px}.arcade-hero p{font-size:12px;margin-top:19px}.arcade-emblem{display:none}.arcade-grid{grid-template-columns:1fr;gap:22px}.arcade-intro{font-size:10px}.arcade-cabinet{padding:19px}.arcade-screen{height:auto;aspect-ratio:320/360}.arcade-screen canvas{height:100%;position:absolute;inset:0}.arcade-footer{font-size:10px}.arcade-footer p{max-width:60%}.arcade-title h2{font-size:30px}}
  @media(prefers-reduced-motion:reduce){.arcade-cabinet,.arcade-command,.arcade-key{transition:none}}
  </style><main class="arcade-world" data-theme="devday"><div class="arcade-top"><div class="arcade-brand"><i aria-hidden="true"></i>KAREN’S ARCADE / OPENAI DEVDAY [2026]</div><span class="arcade-open">ALWAYS OPEN</span></div>
  <header class="arcade-hero"><div><h1>Good times.<br><span>High scores.</span></h1><p>A few old favorites. A little friendly competition.<br>Pick your cabinet and stay a while.</p></div><svg class="arcade-emblem" aria-hidden="true" viewBox="0 0 180 180"><path d="M34 20H18V160H34M146 20H162V160H146" fill="none" stroke="#924ff7" stroke-width="4"/><circle cx="90" cy="90" r="58" fill="none" stroke="#04b84c" stroke-width="2"/><path d="M62 106V86H70V70H78V62H102V70H110V86H118V106H106V98H98V106H82V98H74V106Z" fill="#04b84c"/><path d="M78 79H86V90H78ZM96 79H104V90H96Z" fill="#080808"/><text x="90" y="132" text-anchor="middle" font-family="monospace" font-size="10" font-weight="bold" fill="#04b84c">FREE PLAY</text></svg></header>
  <div class="arcade-divider" aria-hidden="true"></div><div class="arcade-intro"><span>CHOOSE YOUR NEXT OBSESSION</span><span>04 CABINETS · ∞ CREDITS</span></div><div class="arcade-grid">` + arcadeDefinitions().map(game => arcadeTile(game, state, actor)).join('') + '</div><footer class="arcade-footer"><p><strong>NO QUARTERS REQUIRED.</strong>Keyboard, touch, or a little help from Live.<br>Your progress stays with you. Switch games any time.</p><p>CURATED BY KAREN<br>Made for the joy of playing.</p></footer></main>';
}
export function reduce(state, action, actor) {
  const index = meta.games.findIndex(game => game.saveAction === action.type);
  if (index < 0) throw new Error('Unknown arcade action.');
  const checkpoint = action.game;
  if (!checkpoint || checkpoint.actorId !== actor.id || checkpoint.version !== 1 || !Number.isFinite(checkpoint.score) || checkpoint.score < 0 || JSON.stringify(checkpoint).length > 32768) throw new Error('Invalid arcade checkpoint.');
  // The host separately validates JSON, ownership, size and the selected game's namespace.
  arcadeDefinitions()[index].game.view(checkpoint);
  const id = meta.games[index].id;
  return { ...state, extras: { ...state.extras, [id]: { ...state.extras[id], [actor.id]: JSON.parse(JSON.stringify(checkpoint)) } } };
}
