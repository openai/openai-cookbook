// These functions also run inside QuickJS. Keep their dependencies explicit in
// gameValidationCode and do not depend on browser, Node, or encoding globals.
function gameOwn(value, key) {
  return Object.prototype.hasOwnProperty.call(value, key);
}

function gameRecord(value) {
  if (value === null || typeof value !== 'object' || Array.isArray(value)) return false;
  const prototype = Object.getPrototypeOf(value);
  return prototype === Object.prototype || prototype === null;
}

function gameFail(message) {
  throw new Error(message);
}

function gameReserved(key) {
  return key === '__proto__' || key === 'prototype' || key === 'constructor';
}

// Byte length of the JSON string representation, including quotes and escapes.
// Lone surrogates are escaped by well-formed JSON.stringify; a pair is UTF-8.
function gameStringBytes(value) {
  let bytes = 2;
  for (let index = 0; index < value.length; index++) {
    const code = value.charCodeAt(index);
    if (code === 34 || code === 92 || code === 8 || code === 9 || code === 10 || code === 12 || code === 13) bytes += 2;
    else if (code < 32) bytes += 6;
    else if (code < 128) bytes++;
    else if (code < 2048) bytes += 2;
    else if (code >= 0xd800 && code <= 0xdbff) {
      const next = value.charCodeAt(index + 1);
      if (next >= 0xdc00 && next <= 0xdfff) { bytes += 4; index++; }
      else bytes += 6;
    } else bytes += code >= 0xdc00 && code <= 0xdfff ? 6 : 3;
  }
  return bytes;
}

function gameJson(value, maximumBytes, maximumDepth, label) {
  let bytes = 0;
  const ancestors = new Set();
  const add = count => {
    bytes += count;
    if (bytes > maximumBytes) gameFail(`${label} exceeds ${maximumBytes} JSON bytes.`);
  };
  function visit(item, depth) {
    if (depth > maximumDepth) gameFail(`${label} is nested too deeply (maximum ${maximumDepth}).`);
    if (item === null) { add(4); return; }
    if (typeof item === 'string') {
      if (item.length > maximumBytes) gameFail(`${label} exceeds ${maximumBytes} JSON bytes.`);
      add(gameStringBytes(item)); return;
    }
    if (typeof item === 'boolean') { add(item ? 4 : 5); return; }
    if (typeof item === 'number' && Number.isFinite(item)) { add(String(item).length); return; }
    const array = Array.isArray(item);
    if ((!array && !gameRecord(item)) || (array && Object.getPrototypeOf(item) !== Array.prototype)) {
      gameFail(`${label} must contain only plain JSON values.`);
    }
    if (array && item.length > maximumBytes) gameFail(`${label} exceeds ${maximumBytes} JSON bytes.`);
    if (ancestors.has(item)) gameFail(`${label} must not contain cycles.`);
    ancestors.add(item);
    const keys = Reflect.ownKeys(item);
    if (keys.length > maximumBytes) gameFail(`${label} exceeds ${maximumBytes} JSON bytes.`);
    add(2);
    let count = 0;
    for (const key of keys) {
      if (array && key === 'length') continue;
      if (typeof key !== 'string' || gameReserved(key)) gameFail(`${label} contains a reserved or non-JSON property.`);
      const property = Object.getOwnPropertyDescriptor(item, key);
      if (!property || !gameOwn(property, 'value') || !property.enumerable) {
        gameFail(`${label} requires enumerable data properties, without accessors.`);
      }
      if (array) {
        if (key !== String(count) || count >= item.length) {
          gameFail(`${label} arrays must be dense and contain no extra properties.`);
        }
      } else {
        if (key.length > maximumBytes) gameFail(`${label} exceeds ${maximumBytes} JSON bytes.`);
        add(gameStringBytes(key) + 1);
      }
      if (count++) add(1);
      visit(property.value, depth + 1);
    }
    if (array && count !== item.length) gameFail(`${label} arrays must be dense and contain no extra properties.`);
    ancestors.delete(item);
  }
  visit(value, 0);
  return value;
}

function gameFields(value, allowed, required, label) {
  if (!gameRecord(value)) gameFail(`${label} must be a plain object.`);
  for (const key of Object.keys(value)) {
    if (!allowed.includes(key)) gameFail(`${label} contains an unsupported field.`);
  }
  for (const key of required) {
    if (!gameOwn(value, key)) gameFail(`${label} is missing a required field.`);
  }
}

function gameIdentifier(value, label) {
  if (typeof value !== 'string' || !/^[a-zA-Z][a-zA-Z0-9_-]{0,63}$/.test(value) || gameReserved(value)) {
    gameFail(`${label} must be a safe identifier of 1 to 64 characters.`);
  }
}

function gameNumber(value, minimum, maximum, label) {
  if (typeof value !== 'number' || !Number.isFinite(value) || value < minimum || value > maximum) {
    gameFail(`${label} must be a finite number from ${minimum} to ${maximum}.`);
  }
}

function gameColor(value, label) {
  if (typeof value !== 'string' || !value.trim() || value.length > 40 || /url\s*\(/i.test(value) || value.includes('\0')) {
    gameFail(`${label} must be a color of up to 40 characters without url().`);
  }
}

function gamePath(value) {
  if (typeof value !== 'string' || value.length > 6000) gameFail('Game path data must be a string of up to 6000 characters.');
  // Path2D remains responsible for path grammar. Bound every supplied numeric
  // token and allow only SVG path commands, numbers, and their separators.
  const tokens = /[a-zA-Z]|[-+]?(?:[0-9]+\.?[0-9]*|\.[0-9]+)(?:[eE][-+]?[0-9]+)?/g;
  const separators = /^[\t\n\r ,]*$/;
  const letter = /^[a-zA-Z]$/;
  const commands = /^[MmZzLlHhVvCcSsQqTtAa]$/;
  let end = 0;
  let token;
  while ((token = tokens.exec(value)) !== null) {
    if (!separators.test(value.slice(end, token.index))) gameFail('Game path data contains an unsupported character.');
    if (letter.test(token[0])) {
      if (!commands.test(token[0])) gameFail('Game path data contains an unsupported command.');
    } else gameNumber(Number(token[0]), -10_000, 10_000, 'Game path coordinate');
    end = tokens.lastIndex;
  }
  if (!separators.test(value.slice(end))) gameFail('Game path data contains an unsupported character.');
}

function gameActor(actor) {
  gameJson(actor, 1024, 2, 'Game actor');
  gameFields(actor, ['id', 'name'], ['id', 'name'], 'Game actor');
  if (typeof actor.id !== 'string' || !/^[a-zA-Z0-9_-]{1,64}$/.test(actor.id) || gameReserved(actor.id)) {
    gameFail('Game actor requires a valid participant id.');
  }
  if (typeof actor.name !== 'string' || !actor.name.trim() || actor.name.length > 100) {
    gameFail('Game actor requires a participant name of up to 100 characters.');
  }
}

export function validateGameConfig(config) {
  gameJson(config, 1024, 2, 'Game configuration');
  gameFields(config, ['id', 'tickMs', 'saveAction', 'exportName'], ['id'], 'Game configuration');
  gameIdentifier(config.id, 'Game id');
  if (gameOwn(config, 'tickMs')) {
    gameNumber(config.tickMs, 16, 100, 'Game tickMs');
    if (!Number.isInteger(config.tickMs)) gameFail('Game tickMs must be a whole number.');
  }
  if (gameOwn(config, 'saveAction')) gameIdentifier(config.saveAction, 'Game saveAction');
  if (gameOwn(config, 'exportName') && (typeof config.exportName !== 'string'
    || !/^[A-Za-z_$][A-Za-z0-9_$]{0,63}$/.test(config.exportName) || gameReserved(config.exportName))) {
    gameFail('Game exportName must name a safe JavaScript export of 1 to 64 characters.');
  }
  return config;
}

/** Normalize legacy single-game metadata and independently configured arcades. */
export function gameConfigs(meta) {
  if (!meta || typeof meta !== 'object') return [];
  if (meta.game !== undefined && meta.games !== undefined) gameFail('Declare meta.game or meta.games, not both.');
  if (meta.games === undefined) return meta.game === undefined ? [] : [validateGameConfig(meta.game)];
  if (!Array.isArray(meta.games) || meta.games.length < 1 || meta.games.length > 4) gameFail('meta.games must declare between one and four games.');
  const ids = new Set(), saves = new Set();
  for (const config of meta.games) {
    validateGameConfig(config);
    if (!gameOwn(config, 'exportName')) gameFail('Each meta.games entry requires an exportName.');
    if (ids.has(config.id)) gameFail('Game ids must be unique within a space.');
    ids.add(config.id);
    if (config.saveAction !== undefined) {
      if (saves.has(config.saveAction)) gameFail('Game saveAction names must be unique within a space.');
      saves.add(config.saveAction);
    }
  }
  return meta.games;
}

export function validateGameState(state, actor) {
  gameActor(actor);
  gameJson(state, 32_000, 16, 'Game state');
  if (!gameRecord(state) || !gameOwn(state, 'actorId') || state.actorId !== actor.id) {
    gameFail('Game state actorId must match the current participant.');
  }
  return state;
}

export function validateGameView(view) {
  gameJson(view, 200_000, 16, 'Game view');
  gameFields(view, ['width', 'height', 'background', 'objects', 'values', 'finished'], ['width', 'height', 'objects'], 'Game view');
  gameNumber(view.width, 64, 2048, 'Game view width');
  gameNumber(view.height, 64, 2048, 'Game view height');
  if (gameOwn(view, 'background')) gameColor(view.background, 'Game background');
  if (gameOwn(view, 'finished') && typeof view.finished !== 'boolean') gameFail('Game finished must be a boolean.');
  if (!Array.isArray(view.objects) || view.objects.length > 1000) gameFail('Game view supports at most 1000 objects.');
  const common = ['id', 'type', 'x', 'y', 'rotation', 'fill', 'stroke', 'lineWidth'];
  const rectFields = [...common, 'width', 'height', 'radius'];
  const circleFields = [...common, 'radius'];
  const pathFields = [...common, 'd'];
  const textFields = [...common, 'text', 'fontSize', 'align'];
  const rectRequired = ['id', 'type', 'width', 'height'];
  const circleRequired = ['id', 'type', 'radius'];
  const pathRequired = ['id', 'type', 'd'];
  const textRequired = ['id', 'type', 'text'];
  const positionFields = ['x', 'y', 'rotation'];
  const sizeFields = ['width', 'height', 'radius', 'lineWidth'];
  const colorFields = ['fill', 'stroke'];
  const alignments = ['left', 'center', 'right'];
  const ids = new Set();
  for (const shape of view.objects) {
    if (!gameRecord(shape)) gameFail('Each game shape must be a plain object.');
    let required;
    let fields;
    if (shape.type === 'rect') { fields = rectFields; required = rectRequired; }
    else if (shape.type === 'circle') { fields = circleFields; required = circleRequired; }
    else if (shape.type === 'path') { fields = pathFields; required = pathRequired; }
    else if (shape.type === 'text') { fields = textFields; required = textRequired; }
    else gameFail('Game shapes must use rect, circle, path, or text.');
    gameFields(shape, fields, required, 'Game shape');
    if (typeof shape.id !== 'string' || !shape.id.trim() || shape.id.length > 100 || ids.has(shape.id)) {
      gameFail('Game shapes require unique nonempty ids of up to 100 characters.');
    }
    ids.add(shape.id);
    for (const key of positionFields) if (gameOwn(shape, key)) gameNumber(shape[key], -10_000, 10_000, `Game shape ${key}`);
    for (const key of sizeFields) if (gameOwn(shape, key)) gameNumber(shape[key], 0, 10_000, `Game shape ${key}`);
    for (const key of colorFields) if (gameOwn(shape, key)) gameColor(shape[key], `Game shape ${key}`);
    if (shape.type === 'path') gamePath(shape.d);
    if (shape.type === 'text') {
      if (typeof shape.text !== 'string' || shape.text.length > 300) gameFail('Game text must be a string of up to 300 characters.');
      if (gameOwn(shape, 'fontSize')) gameNumber(shape.fontSize, 8, 120, 'Game text fontSize');
      if (gameOwn(shape, 'align') && !alignments.includes(shape.align)) gameFail('Game text align must be left, center, or right.');
    }
  }
  if (gameOwn(view, 'values')) {
    if (!gameRecord(view.values) || Object.keys(view.values).length > 30) gameFail('Game values must be an object with at most 30 entries.');
    for (const [key, value] of Object.entries(view.values)) {
      gameIdentifier(key, 'Game value key');
      if (!(typeof value === 'string' && value.length <= 500) && !(typeof value === 'number' && Number.isFinite(value))) {
        gameFail('Game values must be finite numbers or strings of up to 500 characters.');
      }
    }
  }
  return view;
}

const gameValidationFunctions = [
  gameOwn, gameRecord, gameFail, gameReserved, gameStringBytes, gameJson,
  gameFields, gameIdentifier, gameNumber, gameColor, gamePath, gameActor,
  validateGameConfig, gameConfigs, validateGameState, validateGameView,
];

// A production bundle can rename the functions. Capture their actual names in
// an isolated closure, then expose the stable interface used by every runtime.
export const gameValidationCode = `const gameValidators = (() => {
${gameValidationFunctions.map(fn => fn.toString()).join('\n')}
return {
  validateGameConfig: ${validateGameConfig.name},
  gameConfigs: ${gameConfigs.name},
  validateGameState: ${validateGameState.name},
  validateGameView: ${validateGameView.name}
};
})();
const { validateGameConfig, gameConfigs, validateGameState, validateGameView } = gameValidators;`;
