import { build } from 'esbuild';
import { parse } from '@babel/parser';
import babelTraverse from '@babel/traverse';
import { getQuickJS } from 'quickjs-emscripten';
import { Worker, isMainThread, parentPort, workerData } from 'node:worker_threads';
import { validateAgentConfig } from './space-agent-schema.mjs';
import { validateGameConfig, gameConfigs, validateGameState, validateGameView, gameValidationCode } from '../shared/game-schema.mjs';
import { validatePaintConfig, validatePaintPixels, paintValidationCode } from '../shared/paint-schema.mjs';

const SOURCE_LIMIT = 96_000;
const TESTS_LIMIT = 64_000;
const HTML_LIMIT = 180_000;
const MEMORY_LIMIT = 16 * 1024 * 1024;
const RUN_TIMEOUT = 120;
const RENDER_TIMEOUT = 250;
const GAME_TIMEOUT = 250;
const VERIFICATION_TIMEOUT = 500;

// These pure functions run both here and inside the isolated interpreter. No
// host function, credential, filesystem object, or network API crosses the seam.
function isRecord(value) {
  return value !== null && typeof value === 'object' && !Array.isArray(value);
}

function assertJson(value, depth = 0, seen = new Set()) {
  if (depth > 32) throw new Error('State is nested too deeply.');
  if (value === null || typeof value === 'string' || typeof value === 'boolean') return;
  if (typeof value === 'number' && Number.isFinite(value)) return;
  if (typeof value !== 'object') throw new Error('State must contain only JSON values.');
  if (seen.has(value)) throw new Error('State must not contain cycles.');
  seen.add(value);
  const entries = Object.entries(value);
  if (entries.length > 10_000) throw new Error('State contains too many entries.');
  for (const [key, child] of entries) {
    if (key === '__proto__' || key === 'constructor' || key === 'prototype') {
      throw new Error('State contains a reserved property.');
    }
    assertJson(child, depth + 1, seen);
  }
  seen.delete(value);
}

function stableJson(value) {
  if (Array.isArray(value)) return '[' + value.map(stableJson).join(',') + ']';
  if (isRecord(value)) {
    return '{' + Object.keys(value).sort().map(key => JSON.stringify(key) + ':' + stableJson(value[key])).join(',') + '}';
  }
  return JSON.stringify(value);
}

function validateActor(actor) {
  if (!isRecord(actor) || typeof actor.id !== 'string' || !/^[a-zA-Z0-9_-]{1,64}$/.test(actor.id)) {
    throw new Error('A valid participant is required.');
  }
  if (typeof actor.name !== 'string' || !actor.name.trim() || actor.name.length > 100) {
    throw new Error('A valid participant name is required.');
  }
}

function validateAction(action, limit = 16_000) {
  if (!isRecord(action) || typeof action.type !== 'string' || action.type.length > 100) throw new Error('A valid action is required.');
  assertJson(action);
  if (JSON.stringify(action).length > limit) throw new Error('This action is too large.');
}

function validateState(state) {
  assertJson(state);
  if (!isRecord(state) || !Array.isArray(state.projects) || !Array.isArray(state.contributions) || !isRecord(state.extras)) {
    throw new Error('State requires projects, contributions, and extras.');
  }
  if (JSON.stringify(state).length > 500_000) throw new Error('State is too large.');
  const projects = new Set();
  for (const project of state.projects) {
    if (!isRecord(project) || typeof project.id !== 'string' || !project.id || projects.has(project.id)) {
      throw new Error('Each project needs a unique id.');
    }
    for (const key of ['title', 'description', 'color']) {
      if (typeof project[key] !== 'string') throw new Error('Projects must retain their title, description, and color.');
    }
    projects.add(project.id);
  }
  const ids = new Set();
  for (const contribution of state.contributions) {
    if (!isRecord(contribution) || typeof contribution.id !== 'string' || !contribution.id || ids.has(contribution.id)) {
      throw new Error('Each contribution needs a unique id.');
    }
    if (typeof contribution.actorId !== 'string' || !/^[a-zA-Z0-9_-]{1,64}$/.test(contribution.actorId)) {
      throw new Error('Each contribution needs a valid participant.');
    }
    if (!projects.has(contribution.projectId)) throw new Error('A contribution refers to an unknown project.');
    if (!Number.isInteger(contribution.points) || contribution.points < 1 || contribution.points > 100_000) {
      throw new Error('Contribution points must be positive whole numbers.');
    }
    ids.add(contribution.id);
  }
}

// Generated reducers may define new feature collections, but they do not gain
// authority over another participant's records. An unchanged legacy namespace
// may pass through; all mutations use feature -> record id -> { actorId, ... }.
function validateExtraTransition(before, after, actor) {
  for (const namespace of new Set([...Object.keys(before), ...Object.keys(after)])) {
    const previous = before[namespace];
    const next = after[namespace];
    if (stableJson(previous) === stableJson(next)) continue;
    if ((previous !== undefined && !isRecord(previous)) || (next !== undefined && !isRecord(next))) {
      throw new Error('Space features must store participant-owned records in a collection.');
    }
    const oldRecords = previous || {};
    const newRecords = next || {};
    for (const id of new Set([...Object.keys(oldRecords), ...Object.keys(newRecords)])) {
      const oldRecord = oldRecords[id];
      const newRecord = newRecords[id];
      if (stableJson(oldRecord) === stableJson(newRecord)) continue;
      for (const record of [oldRecord, newRecord]) {
        if (record !== undefined && (!isRecord(record) || record.actorId !== actor.id)) {
          throw new Error('You can only change your own space records.');
        }
      }
    }
  }
}

function validateTransition(before, after, actor) {
  validateState(after);
  const managed = new Set(['projects', 'contributions', 'extras']);
  for (const field of new Set([...Object.keys(before), ...Object.keys(after)])) {
    if (!managed.has(field) && stableJson(before[field]) !== stableJson(after[field])) {
      throw new Error('Store new feature data in participant-owned extras records.');
    }
  }
  if (stableJson(before.projects) !== stableJson(after.projects)) throw new Error('Existing projects must be preserved.');
  const previous = new Map(before.contributions.map(item => [item.id, item]));
  const next = new Map(after.contributions.map(item => [item.id, item]));
  for (const old of before.contributions) {
    if (old.actorId !== actor.id && stableJson(next.get(old.id)) !== stableJson(old)) {
      throw new Error('You can only change your own contributions.');
    }
  }
  for (const item of after.contributions) {
    const old = previous.get(item.id);
    if (item.actorId !== actor.id && (!old || stableJson(old) !== stableJson(item))) {
      throw new Error('You can only change your own contributions.');
    }
    if (old && old.actorId !== item.actorId) throw new Error('Contribution ownership cannot change.');
  }
  validateExtraTransition(before.extras, after.extras, actor);
}

function validateGameCheckpoint(before, after, action, actor, config) {
  validateGameState(after.extras[config.id]?.[actor.id], actor);
  const expected = JSON.parse(JSON.stringify(before));
  expected.extras[config.id] = { ...expected.extras[config.id], [actor.id]: action.game };
  if (stableJson(after) !== stableJson(expected)) {
    throw new Error('A game checkpoint must save its complete game record and preserve every other record, project, and contribution.');
  }
}

function decodeHtmlAttribute(value) {
  const named = { quot: '"', apos: "'", lt: '<', gt: '>', amp: '&', colon: ':', sol: '/', tab: '\t', newline: '\n', nbsp: '\u00a0' };
  return value.replace(/&#(x[0-9a-f]+|[0-9]+);?|&(quot|apos|lt|gt|amp|colon|sol|tab|newline|nbsp);/gi, (_match, code, name) => {
    if (name) return named[name.toLowerCase()];
    const point = code[0].toLowerCase() === 'x' ? parseInt(code.slice(1), 16) : parseInt(code, 10);
    return point > 0 && point <= 0x10ffff ? String.fromCodePoint(point) : '\ufffd';
  });
}

function validateHtml(html, collectElements = false) {
  if (typeof html !== 'string') throw new Error('render must return an HTML string.');
  if (html.length > 180_000) throw new Error('Rendered content is too large.');
  // Check markup, not text. Escaped user content, data-action JSON, and a label
  // such as "onboarding=done" must not be mistaken for executable attributes.
  // This is a restrictive content policy, not an HTML sanitizer; the trusted
  // browser host still supplies an opaque iframe origin and nonce-only CSP.
  const forbidden = new Set(['script', 'iframe', 'object', 'embed', 'base', 'meta', 'link']);
  const urls = new Set(['src', 'href', 'action', 'formaction', 'xlink:href', 'poster', 'background', 'srcset']);
  const rawText = new Set(['style', 'textarea', 'title', 'xmp', 'noembed', 'noframes', 'noscript']);
  const space = character => character !== undefined && /[\t\n\f\r ]/.test(character);
  const voidTags = new Set(['area', 'base', 'br', 'col', 'embed', 'hr', 'img', 'input', 'link', 'meta', 'param', 'source', 'track', 'wbr']);
  const closesParagraph = new Set(['address', 'article', 'aside', 'blockquote', 'details', 'div', 'dl', 'fieldset', 'figcaption', 'figure', 'footer', 'form', 'h1', 'h2', 'h3', 'h4', 'h5', 'h6', 'header', 'hgroup', 'hr', 'main', 'menu', 'nav', 'ol', 'p', 'pre', 'section', 'table', 'ul']);
  const elements = [], ancestors = [];
  const lower = html.toLowerCase();
  // Raster painting is a trusted host capability. Validate its declarative
  // inputs before publication, including in generated feature-test renders.
  const inspectPaint = lower.includes('data-paint-grid') || lower.includes('data-paint-pixels');
  const inspectElements = collectElements || inspectPaint;
  let cursor = 0;
  let templates = 0;
  let foreignDepth = 0;
  while (true) {
    const nextTag = html.indexOf('<', cursor);
    if (inspectElements && ancestors.length) ancestors[ancestors.length - 1].text += decodeHtmlAttribute(html.slice(cursor, nextTag === -1 ? html.length : nextTag));
    if (nextTag === -1) break;
    cursor = nextTag;
    if (html.startsWith('<!--', cursor)) {
      const end = /--!?>/.exec(html.slice(cursor + 4));
      if (!end || /^<!---?>/.test(html.slice(cursor))) throw new Error('Generated markup contains an incomplete comment.');
      cursor += 4 + end.index + end[0].length;
      continue;
    }
    if (foreignDepth && html.startsWith('<![CDATA[', cursor)) {
      const end = html.indexOf(']]>', cursor + 9);
      if (end === -1) throw new Error('Generated markup contains an incomplete CDATA section.');
      // Keep inspecting foreign content conservatively, including CDATA.
      cursor += 9;
      continue;
    }
    if (html[cursor + 1] === '!' || html[cursor + 1] === '?') {
      // Even quoted DOCTYPE identifiers terminate abruptly at >. Treating
      // quotes as protection here could conceal executable markup after it.
      const end = html.indexOf('>', cursor + 2);
      if (end === -1) throw new Error('Generated markup contains an incomplete declaration.');
      cursor++;
      continue;
    }
    let index = cursor + 1;
    const closing = html[index] === '/';
    if (closing) index++;
    if (!/[a-z]/i.test(html[index] || '')) {
      if (closing) {
        const end = html.indexOf('>', index);
        if (end === -1) throw new Error('Generated markup contains an incomplete closing tag.');
      }
      cursor++;
      continue;
    }
    const nameStart = index;
    while (index < html.length && !space(html[index]) && html[index] !== '/' && html[index] !== '>') index++;
    const tag = lower.slice(nameStart, index);
    if (forbidden.has(tag)) throw new Error('Generated markup cannot contain executable or embedded documents.');
    if (tag === 'plaintext') throw new Error('Generated markup cannot contain plaintext elements.');
    let selfClosing = false;
    let complete = false;
    const attributes = inspectElements ? Object.create(null) : undefined;
    // Attribute values have their own lexical context. A quote in an unquoted
    // value is data (an HTML parse error), not the start of a quoted value.
    while (index < html.length) {
      while (space(html[index]) || html[index] === '/') {
        if (html[index] === '/' && html[index + 1] === '>') selfClosing = true;
        index++;
      }
      if (html[index] === '>') { index++; complete = true; break; }
      if (index >= html.length) break;
      const attributeStart = index;
      while (index < html.length && !space(html[index]) && !['/', '>', '='].includes(html[index])) index++;
      const attribute = lower.slice(attributeStart, index);
      if (!attribute) { index++; continue; }
      while (space(html[index])) index++;
      let value = '';
      if (html[index] === '=') {
        index++;
        while (space(html[index])) index++;
        if (html[index] === '"' || html[index] === "'") {
          const quote = html[index++];
          const valueStart = index;
          while (index < html.length && html[index] !== quote) index++;
          value = html.slice(valueStart, index);
          if (html[index] !== quote) throw new Error('Generated markup contains an incomplete quoted attribute.');
          index++;
        } else {
          const valueStart = index;
          while (index < html.length && !space(html[index]) && html[index] !== '>') index++;
          value = html.slice(valueStart, index);
        }
      }
      if (!closing && /^on[a-z]/.test(attribute)) throw new Error('Use data-action controls instead of inline JavaScript.');
      // HTML keeps the first duplicate attribute, including data-game hooks.
      if (attributes && !Object.hasOwn(attributes, attribute)) attributes[attribute] = decodeHtmlAttribute(value);
      if (!closing && urls.has(attribute)) {
        const named = { colon: ':', sol: '/', tab: '\t', newline: '\n', amp: '&' };
        const decoded = value.replace(/&#(x[0-9a-f]+|[0-9]+);?/gi, (_match, code) => {
          const point = code[0].toLowerCase() === 'x' ? parseInt(code.slice(1), 16) : parseInt(code, 10);
          return point > 0 && point <= 0x10ffff ? String.fromCodePoint(point) : '\ufffd';
        }).replace(/&(colon|sol|tab|newline|amp);/gi, (_match, name) => named[name.toLowerCase()]);
        const normalized = decoded.replace(/[\u0000-\u0020\u007f]/g, '').toLowerCase();
        if (/^(?:javascript|vbscript):/.test(normalized)) throw new Error('Use data-action controls instead of inline JavaScript.');
        if (/^(?:https?:|\/\/)/.test(normalized) || (attribute === 'srcset' && /(?:https?:|\/\/)/.test(normalized))) {
          throw new Error('Generated content cannot load or navigate to external resources.');
        }
      }
    }
    if (!complete) throw new Error('Generated markup contains an incomplete tag.');
    cursor = index;
    if (closing) {
      if (inspectElements) {
        const open = ancestors.map(node => node.tag).lastIndexOf(tag);
        if (open !== -1) ancestors.length = open;
      }
      if (tag === 'svg' || tag === 'math') foreignDepth = Math.max(0, foreignDepth - 1);
      if (tag === 'template') templates = Math.max(0, templates - 1);
      continue;
    }
    if (inspectElements) {
      // Account for common implicit HTML closures that can move controls out
      // of an authored root. This does not change the markup safety policy.
      if (!foreignDepth && closesParagraph.has(tag)) {
        const paragraph = ancestors.map(node => node.tag).lastIndexOf('p');
        if (paragraph !== -1) ancestors.length = paragraph;
      }
      if (!foreignDepth && ['li', 'dt', 'dd', 'button', 'option', 'optgroup'].includes(tag)) {
        const group = tag === 'dt' || tag === 'dd' ? ['dt', 'dd'] : tag === 'optgroup' ? ['option', 'optgroup'] : [tag];
        const scope = tag === 'li' ? ['ul', 'ol', 'menu'] : tag === 'dt' || tag === 'dd' ? ['dl'] : tag === 'option' || tag === 'optgroup' ? ['select'] : [];
        const boundary = ancestors.findLastIndex(node => scope.includes(node.tag));
        const previous = ancestors.findLastIndex((node, index) => index > boundary && group.includes(node.tag));
        if (previous !== -1) ancestors.length = previous;
      }
      const parent = ancestors[ancestors.length - 1];
      const node = { tag, attributes, parent, text: '', template: templates > 0 || tag === 'template', foreign: foreignDepth > 0 || tag === 'svg' || tag === 'math' };
      elements.push(node);
      // In HTML, a trailing slash does not close a non-void element. In SVG it does.
      if (!voidTags.has(tag) && !(node.foreign && selfClosing)) ancestors.push(node);
    }
    if (!selfClosing && (tag === 'svg' || tag === 'math')) foreignDepth++;
    if (tag === 'template' && !(foreignDepth && selfClosing)) templates++;
    if (rawText.has(tag) && !(foreignDepth && selfClosing)) {
      const close = new RegExp('</' + tag + '(?=[\\t\\n\\f\\r />])', 'g');
      close.lastIndex = cursor;
      const end = close.exec(lower);
      if (!end) throw new Error('Generated markup contains an incomplete <' + tag + '> element.');
      if (!foreignDepth) cursor = end.index;
    }
  }
  if (templates) throw new Error('Generated markup contains an incomplete <template> element.');
  if (inspectPaint) validatePaintElements(elements);
  if (collectElements) return elements;
}

// The same HTML tokenizer supplies both safety checks and painting bindings.
// Looking only for matching strings would accept a surface inside a template,
// SVG, or service region even though the browser cannot bind it as a canvas.
function validatePaintElements(elements) {
  const has = (node, name) => Object.hasOwn(node.attributes, name);
  const closest = (node, predicate) => {
    for (let current = node; current; current = current.parent) if (predicate(current)) return current;
  };
  for (const node of elements) {
    const grid = has(node, 'data-paint-grid');
    const pixels = has(node, 'data-paint-pixels');
    if (!grid && !pixels) continue;
    if (!grid) throw new Error('data-paint-pixels requires data-paint-grid on the same canvas.');
    const raster = pixels || node.tag === 'canvas';
    let config;
    const raw = node.attributes['data-paint-grid'];
    if (raw.length > 4000) throw new Error('data-paint-grid configuration exceeds 4000 characters.');
    try { config = JSON.parse(raw); }
    catch { throw new Error('data-paint-grid must contain valid JSON.'); }
    validatePaintConfig(config, raster);
    if (!raster) continue;
    if (node.tag !== 'canvas' || node.foreign || node.template
      || closest(node, item => has(item, 'data-service') || has(item, 'data-game') || has(item, 'data-game-canvas'))
      || closest(node.parent, item => has(item, 'data-paint-grid') || ['canvas', 'select', 'option', 'optgroup'].includes(item.tag))) {
      throw new Error('Raster painting requires an HTML canvas outside templates, SVG, service regions, games, and other paint grids.');
    }
    if (!pixels) throw new Error('A raster paint canvas requires data-paint-pixels with one character per cell.');
    validatePaintPixels(node.attributes['data-paint-pixels'], config);
  }
}

// Agent context uses the authoritative visible raster instead of replaying a
// potentially much larger edit history. Reuse publication's tokenizer and
// validation so escaped examples and invalid bindings cannot become context.
export function paintSurfacesFromHtml(html) {
  return validateHtml(html, true)
    .filter(node => node.tag === 'canvas' && Object.hasOwn(node.attributes, 'data-paint-pixels'))
    .map(node => ({
      key: node.attributes['data-key'] || '',
      config: validatePaintConfig(JSON.parse(node.attributes['data-paint-grid']), true),
      pixels: node.attributes['data-paint-pixels'],
    }));
}

// Check the hooks that the trusted frame actually binds before publishing a
// generated game. This uses the same tokenizer as the HTML boundary, so examples
// in comments, textareas, styles, or inert templates cannot satisfy the contract.
export function validateGameBindings(html, config, configs = [config]) {
  validateGameConfig(config);
  const elements = validateHtml(html, true).filter(node => !node.template);
  const has = (node, name) => Object.hasOwn(node.attributes, name);
  const closest = (node, predicate) => {
    for (let current = node; current; current = current.parent) if (predicate(current)) return current;
  };
  const roots = elements.filter(node => has(node, 'data-game'));
  const allowedIds = new Set(configs.map(item => item.id));
  const matching = roots.filter(node => node.attributes['data-game'] === config.id);
  if (matching.length !== 1 || roots.length !== configs.length || roots.some(node => !allowedIds.has(node.attributes['data-game']))
    || new Set(roots.map(node => node.attributes['data-game'])).size !== roots.length) {
    throw new Error(`Game ${config.id} requires exactly one rendered data-game="${config.id}" root; remove or correct unmatched game roots.`);
  }
  const root = matching[0];
  if (root.foreign || ['button', 'input', 'textarea', 'select', 'option'].includes(root.tag)
    || closest(root, node => has(node, 'data-service'))
    || closest(root.parent, node => has(node, 'data-game'))
    || closest(root.parent, node => ['select', 'option', 'optgroup', 'canvas'].includes(node.tag))) {
    throw new Error(`Game ${config.id} must use an HTML container outside data-service regions.`);
  }
  // Missing tabindex is supported: the trusted frame adds tabindex="0".
  if (has(root, 'tabindex') && !/^-?\d+$/.test(root.attributes.tabindex.trim())) {
    throw new Error(`Game ${config.id} needs a numeric tabindex so Start can focus its keyboard controls, or omit tabindex to use the default.`);
  }
  const hiddenStyle = node => /(?:^|;)\s*(?:display\s*:\s*none|visibility\s*:\s*(?:hidden|collapse))\s*(?:!important\s*)?(?:;|$)/i.test(node.attributes.style || '');
  const hidden = node => closest(node, item => has(item, 'hidden') || has(item, 'inert') || item.attributes['aria-hidden'] === 'true' || hiddenStyle(item));
  if (hidden(root)) throw new Error(`Game ${config.id} root must be available to players, without hidden, inert, or aria-hidden ancestors.`);
  const allBindings = elements.filter(node => ['data-game-canvas', 'data-game-command', 'data-game-action', 'data-game-release', 'data-game-keys', 'data-game-value', 'data-game-runtime-status'].some(name => has(node, name)));
  for (const node of allBindings) {
    const owner = closest(node, item => has(item, 'data-game'));
    if (!owner || node === owner || node.foreign || !allowedIds.has(owner.attributes['data-game'])) {
      throw new Error(`Game ${config.id} bindings must be HTML descendants of its data-game root; move orphan canvas, controls, and readouts inside it.`);
    }
  }
  const bound = allBindings.filter(node => closest(node, item => has(item, 'data-game')) === root);
  if (!bound.some(node => node.tag === 'canvas' && has(node, 'data-game-canvas'))) {
    throw new Error(`Game ${config.id} requires a <canvas data-game-canvas> inside its data-game root.`);
  }
  for (const node of bound.filter(node => has(node, 'data-game-canvas'))) {
    if (node.tag !== 'canvas') throw new Error('data-game-canvas must be placed on a canvas element.');
  }
  const native = node => node.tag === 'button' || node.tag === 'input';
  const controls = bound.filter(node => has(node, 'data-game-command') || has(node, 'data-game-action'));
  const textFor = node => elements.filter(item => closest(item, candidate => candidate === node)).map(item => item.text).join(' ').trim();
  const label = node => {
    if (node.attributes['aria-label']?.trim()) return node.attributes['aria-label'].trim();
    if (node.attributes['aria-labelledby']) {
      const names = node.attributes['aria-labelledby'].trim().split(/\s+/);
      const text = elements.filter(item => names.includes(item.attributes.id)).map(textFor).join(' ').trim();
      if (text) return text;
    }
    const nativeLabels = elements.filter(item => item.tag === 'label' && (node.attributes.id && item.attributes.for === node.attributes.id || closest(node.parent, parent => parent === item))).map(textFor).join(' ').trim();
    if (nativeLabels) return nativeLabels;
    if (node.tag === 'input' && node.attributes.value?.trim()) return node.attributes.value.trim();
    return textFor(node) || node.attributes.title?.trim() || '';
  };
  const actions = [], seen = new Set();
  const parseAction = (node, attribute) => {
    const raw = node.attributes[attribute];
    let action;
    try { action = JSON.parse(raw); }
    catch { throw new Error(`${attribute} must contain valid JSON such as {"type":"jump"}.`); }
    if (raw.length > 4096 || !isRecord(action) || typeof action.type !== 'string' || !/^[A-Za-z][A-Za-z0-9_-]{0,63}$/.test(action.type) || action.type === 'tick') {
      throw new Error(`${attribute} needs an object with a safe type other than tick and at most 4096 characters; ticks are supplied by the game runtime.`);
    }
    const safe = (value, depth = 0) => {
      if (depth > 12) throw new Error(`${attribute} must not be nested more than 12 levels.`);
      if (typeof value === 'number' && !Number.isFinite(value)) throw new Error(`${attribute} requires finite JSON numbers.`);
      if (value && typeof value === 'object') for (const [key, child] of Object.entries(value)) {
        if (['constructor', 'prototype', '__proto__'].includes(key)) throw new Error(`${attribute} must not contain reserved property names.`);
        safe(child, depth + 1);
      }
    };
    safe(action);
    return action;
  };
  for (const node of bound.filter(node => has(node, 'data-game-release'))) {
    if (!has(node, 'data-game-action') || has(node, 'data-game-command')) throw new Error('data-game-release requires a data-game-action control, not a lifecycle command.');
  }
  for (const node of controls) {
    if (!native(node)) throw new Error('Game commands and actions require native button or input controls so touch, keyboard, and voice can activate them.');
    if (has(node, 'data-game-command') && has(node, 'data-game-action')) throw new Error('A game control must use either data-game-command or data-game-action, not both.');
    if (has(node, 'data-game-command')) {
      if (!['start', 'pause', 'resume', 'restart'].includes(node.attributes['data-game-command'])) {
        throw new Error('data-game-command supports only start, pause, resume, or restart; use data-game-action JSON for game-specific input.');
      }
    } else {
      const action = parseAction(node, 'data-game-action');
      const release = has(node, 'data-game-release') ? parseAction(node, 'data-game-release') : undefined;
      const key = stableJson([action, release ?? null]);
      if (!seen.has(key)) { actions.push({ action, label: label(node), ...(release ? { release } : {}) }); seen.add(key); }
    }
  }
  for (const node of bound.filter(node => has(node, 'data-game-keys'))) {
    if (!has(node, 'data-game-action') || !node.attributes['data-game-keys'].trim()) throw new Error('data-game-keys requires a game action control and at least one KeyboardEvent key.');
  }
  const disabledFieldset = node => closest(node.parent, fieldset => {
    if (fieldset.tag !== 'fieldset' || !has(fieldset, 'disabled')) return false;
    // Native controls in a disabled fieldset's first legend remain enabled.
    const legend = elements.find(item => item.parent === fieldset && item.tag === 'legend');
    return !legend || !closest(node, item => item === legend);
  });
  const start = controls.some(node => node.attributes['data-game-command'] === 'start'
    && !has(node, 'disabled') && node.attributes['aria-disabled'] !== 'true'
    && !hidden(node.parent) && !disabledFieldset(node)
    && !has(node, 'inert') && !hiddenStyle(node) && node.attributes['aria-hidden'] !== 'true' && label(node));
  // A Start button's own hidden attribute is reset by the runtime's idle state.
  if (!start) throw new Error(`Game ${config.id} requires a labeled, enabled native Start control inside its root, using data-game-command="start".`);
  return { actions };
}

function validateMeta(meta) {
  if (!isRecord(meta) || typeof meta.title !== 'string' || !meta.title.trim() || meta.title.length > 120) {
    throw new Error('meta.title must be a short title.');
  }
  if (typeof meta.subtitle !== 'string' || meta.subtitle.length > 240) throw new Error('meta.subtitle must be a short string.');
  if (typeof meta.accent !== 'string' || !/^#[a-f0-9]{3,8}$/i.test(meta.accent)) throw new Error('meta.accent must be a hex color.');
  if (meta.budget !== undefined && (!Number.isInteger(meta.budget) || meta.budget < 1 || meta.budget > 1000)) {
    throw new Error('meta.budget must be a positive whole number up to 1000.');
  }
  if (meta.layout !== undefined && meta.layout !== 'canvas') throw new Error('meta.layout must be canvas when supplied.');
  if (meta.capabilities !== undefined && (!Array.isArray(meta.capabilities) || meta.capabilities.length > 3 || new Set(meta.capabilities).size !== meta.capabilities.length || meta.capabilities.some(name => !['health-chat', 'finance-news', 'space-agent'].includes(name)))) {
    throw new Error('meta.capabilities may contain only health-chat, finance-news, and space-agent, without duplicates.');
  }
  validateAgentConfig(meta);
  gameConfigs(meta);
  if (meta.suggestions !== undefined && (!Array.isArray(meta.suggestions) || meta.suggestions.length > 3 || meta.suggestions.some(item => !isRecord(item) || typeof item.label !== 'string' || !item.label.trim() || item.label.length > 60 || typeof item.prompt !== 'string' || !item.prompt.trim() || item.prompt.length > 1500))) {
    throw new Error('meta.suggestions may contain up to three short labels and editing prompts.');
  }
  if (meta.projects !== undefined) {
    if (meta.layout !== 'canvas' || !Array.isArray(meta.projects) || meta.projects.length > 60) {
      throw new Error('A canvas may declare up to 60 projects in meta.projects.');
    }
    const ids = new Set();
    for (const project of meta.projects) {
      if (!isRecord(project) || typeof project.id !== 'string' || !/^[a-zA-Z0-9_-]{1,64}$/.test(project.id) || ids.has(project.id)) {
        throw new Error('Each declared project needs a unique stable id.');
      }
      if (Object.keys(project).some(key => !['id', 'title', 'description', 'color'].includes(key))) throw new Error('Declared projects may contain only id, title, description, and color.');
      if (typeof project.title !== 'string' || !project.title.trim() || project.title.length > 120) throw new Error('Each declared project needs a short title.');
      if (typeof project.description !== 'string' || project.description.length > 400) throw new Error('Each declared project needs a short description.');
      if (typeof project.color !== 'string' || !/^#(?:[a-f0-9]{3}|[a-f0-9]{4}|[a-f0-9]{6}|[a-f0-9]{8})$/i.test(project.color)) throw new Error('Each declared project needs a hex color.');
      ids.add(project.id);
    }
  }
  assertJson(meta);
}

// Only the trusted publication path calls this. Generated reducers never gain
// project write authority: they still pass through validateTransition unchanged.
// An omitted project remains in the catalog, including all referenced ids. This
// lets an owner add/relabel tiles without deleting participation or extra data.
export function projectStateForPublication(meta, liveState) {
  validateMeta(meta);
  validateState(liveState);
  const next = structuredClone(liveState);
  const catalog = new Map((meta.projects || []).map(project => [project.id, project]));
  next.projects = next.projects.map(project => {
    const update = catalog.get(project.id);
    catalog.delete(project.id);
    return update ? { ...project, ...structuredClone(update) } : project;
  });
  next.projects.push(...structuredClone([...catalog.values()]));
  validateState(next);
  return next;
}

function withoutGameClock(operation) {
  const date = globalThis.Date;
  const performance = globalThis.performance;
  globalThis.Date = undefined;
  globalThis.performance = undefined;
  try { return operation(); }
  finally { globalThis.Date = date; globalThis.performance = performance; }
}

function gameInitChecked(game, saved, actor) {
  validateActor(actor);
  if (saved !== null) validateGameState(saved, actor);
  const input = JSON.parse(JSON.stringify(saved));
  const before = stableJson(input);
  const next = withoutGameClock(() => game.init(input, JSON.parse(JSON.stringify(actor))));
  if (stableJson(input) !== before) throw new Error('Game initialization must not change saved input.');
  validateGameState(next, actor);
  return next;
}

function gameStepChecked(game, state, action, actor) {
  validateActor(actor);
  validateGameState(state, actor);
  validateAction(action);
  const next = withoutGameClock(() => game.step(JSON.parse(JSON.stringify(state)), JSON.parse(JSON.stringify(action)), JSON.parse(JSON.stringify(actor))));
  validateGameState(next, actor);
  return next;
}

function gameViewChecked(game, state, actor, serialize = false) {
  validateActor(actor);
  validateGameState(state, actor);
  const input = JSON.parse(JSON.stringify(state));
  const before = stableJson(input);
  const view = withoutGameClock(() => game.view(input, JSON.parse(JSON.stringify(actor))));
  if (serialize) {
    // Standalone calls validate the canonical JSON in the trusted host. Avoid
    // another full scene traversal in WASM; serialization stays sandboxed.
    const result = withoutGameClock(() => JSON.stringify(view));
    if (stableJson(input) !== before) throw new Error('Game rendering must not change its state.');
    if (typeof result !== 'string' || result.length > 200_000) throw new Error('Game view exceeds 200000 JSON bytes.');
    return result;
  }
  if (stableJson(input) !== before) throw new Error('Game rendering must not change its state.');
  validateGameView(view);
  return view;
}

const validationCode = gameValidationCode + '\n' + paintValidationCode + '\n' + [isRecord, assertJson, stableJson, validateActor, validateAction, validateState, validateExtraTransition, validateTransition, validateGameCheckpoint, decodeHtmlAttribute, validateHtml, validatePaintElements, validateAgentConfig, validateMeta, withoutGameClock, gameInitChecked, gameStepChecked, gameViewChecked]
  .map(fn => fn.toString()).join('\n');

function encoded(value) {
  assertJson(value);
  return `JSON.parse(${JSON.stringify(JSON.stringify(value))})`;
}

async function evaluateIsolated(bundle, body, { timeout = RUN_TIMEOUT, game = false } = {}) {
  const quickjs = await getQuickJS();
  const runtime = quickjs.newRuntime();
  runtime.setMemoryLimit(MEMORY_LIMIT);
  runtime.setMaxStackSize(512 * 1024);
  const deadline = Date.now() + timeout;
  let interruptCycles = 0;
  // A feature suite makes many validated calls in one context. Its larger time
  // allowance must carry a proportional instruction allowance as well.
  const interruptLimit = Math.ceil(3000 * timeout / RUN_TIMEOUT);
  runtime.setInterruptHandler(() => Date.now() > deadline || ++interruptCycles > interruptLimit);
  const context = runtime.newContext();
  try {
    const prelude = game ? 'globalThis.Date = undefined; globalThis.performance = undefined;' : '';
    const result = context.evalCode(`${prelude}\n${bundle}\n${validationCode}\n(() => {\n${body}\n})()`, 'living-space.js');
    if (result.error) {
      const details = context.dump(result.error);
      result.error.dispose();
      const message = details && typeof details === 'object' ? details.message : details;
      if (/interrupted/i.test(String(message))) throw new Error('This feature exceeded the execution time limit.');
      if (/out of memory/i.test(String(message))) throw new Error('This feature exceeded the memory limit.');
      throw new Error(String(message || 'The generated feature could not run.').slice(0, 600));
    }
    try {
      const serialized = context.dump(result.value);
      if (typeof serialized !== 'string') throw new Error('The isolated runtime returned an invalid result.');
      return JSON.parse(serialized);
    } finally {
      result.value.dispose();
    }
  } finally {
    context.dispose();
    runtime.dispose();
  }
}

// QuickJS interruption is cooperative. A large allocation can spend time in its
// native allocator before another bytecode interrupt. A credential-free worker
// adds a hard wall-clock boundary and keeps the HTTP event loop responsive.
let executionWorker;
let activeExecution;
const executionQueue = [];
let executionId = 0;

function nextExecution() {
  if (activeExecution || executionQueue.length === 0) return;
  const job = executionQueue.shift();
  if (!executionWorker) {
    const worker = new Worker(new URL(import.meta.url), {
      workerData: { littleWorldsRuntime: true },
      env: {},
      resourceLimits: { maxOldGenerationSizeMb: 48, maxYoungGenerationSizeMb: 8, stackSizeMb: 2 },
    });
    executionWorker = worker;
    worker.on('message', message => {
      if (executionWorker !== worker || !activeExecution || message.id !== activeExecution.id) return;
      const current = activeExecution;
      clearTimeout(current.watchdog);
      activeExecution = undefined;
      worker.unref();
      if (message.error) current.reject(new Error(message.error));
      else current.resolve(message.value);
      nextExecution();
    });
    const failed = error => {
      if (executionWorker !== worker) return;
      executionWorker = undefined;
      if (activeExecution) {
        clearTimeout(activeExecution.watchdog);
        activeExecution.reject(new Error(`The isolated feature runtime stopped: ${error.message || error}`));
        activeExecution = undefined;
      }
      nextExecution();
    };
    worker.on('error', failed);
    worker.on('exit', code => {
      if (executionWorker === worker) failed(new Error(`worker exited (${code})`));
    });
  }
  activeExecution = job;
  executionWorker.ref();
  job.watchdog = setTimeout(() => {
    if (activeExecution !== job) return;
    const stopped = executionWorker;
    executionWorker = undefined;
    activeExecution = undefined;
    void stopped.terminate();
    job.reject(new Error('This feature exceeded the execution time limit.'));
    nextExecution();
  }, Math.max(750, job.options.timeout + 300));
  executionWorker.postMessage({ id: job.id, bundle: job.bundle, body: job.body, options: job.options });
}

async function evaluate(bundle, body, { timeout = RUN_TIMEOUT, game = false } = {}) {
  return new Promise((resolve, reject) => {
    executionQueue.push({ id: ++executionId, bundle, body, options: { timeout, game }, resolve, reject });
    nextExecution();
  });
}

if (!isMainThread && workerData?.littleWorldsRuntime) {
  parentPort.on('message', async ({ id, bundle, body, options }) => {
    try {
      parentPort.postMessage({ id, value: await evaluateIsolated(bundle, body, options) });
    } catch (error) {
      parentPort.postMessage({ id, error: error.message });
    }
  });
}

async function compile(source, globalName, limit) {
  if (typeof source !== 'string' || !source.trim()) throw new Error('A JavaScript source file is required.');
  if (source.length > limit) throw new Error('The source file is too large.');
  // esbuild resolves static imports through the deny plugin. Non-literal dynamic
  // imports are otherwise left in the bundle, so reject that syntax explicitly.
  if (/\bimport\s*(?:\(|\.)/.test(source)) throw new Error('Imports are unavailable in generated features.');
  try {
    const result = await build({
      stdin: { contents: source, loader: 'js', sourcefile: globalName === 'LivingModule' ? 'space.js' : 'tests.js' },
      bundle: true,
      write: false,
      format: 'iife',
      globalName,
      platform: 'neutral',
      target: 'es2020',
      logLevel: 'silent',
      legalComments: 'none',
      plugins: [{
        name: 'no-generated-imports',
        setup(builder) {
          builder.onResolve({ filter: /.*/ }, () => ({ errors: [{ text: 'Imports are unavailable in generated features.' }] }));
        },
      }],
    });
    return result.outputFiles[0].text;
  } catch (error) {
    const detail = error.errors?.map(item => item.text).join(' ') || error.message;
    throw new Error(`Could not compile ${globalName === 'LivingModule' ? 'space.js' : 'tests.js'}: ${detail}`.slice(0, 1000));
  }
}

export async function compileModule(source) {
  const bundle = await compile(source, 'LivingModule', SOURCE_LIMIT);
  const meta = await evaluate(bundle, `
    if (typeof LivingModule.render !== 'function' || typeof LivingModule.reduce !== 'function') {
      throw new Error('Export render(state, actor) and reduce(state, action, actor).');
    }
    validateMeta(LivingModule.meta);
    const games = gameConfigs(LivingModule.meta);
    if (LivingModule.meta.games === undefined && (games.length > 0) !== (LivingModule[LivingModule.meta.game?.exportName || 'game'] !== undefined)) {
      throw new Error('Declare meta.game and export game together.');
    }
    for (const config of games) {
      const name = config.exportName || 'game';
      if (!isRecord(LivingModule[name]) || ['init', 'step', 'view'].some(method => typeof LivingModule[name][method] !== 'function')) {
        throw new Error('Export the game ' + name + ' with init, step, and view.');
      }
    }
    return JSON.stringify(LivingModule.meta);
  `);
  validateMeta(meta);
  const configs = gameConfigs(meta);
  const gameBundles = Object.fromEntries(await Promise.all(configs.map(async config => [config.id, await compileGameModule(source, config.exportName || 'game')])));
  const gameBundle = meta.game === undefined ? undefined : gameBundles[meta.game.id];
  return { bundle, meta, ...(configs.length ? { gameBundles } : {}), ...(gameBundle ? { gameBundle } : {}) };
}

// Tree shaking alone retains unused initializers when they might have effects.
// Select the public lexical dependency closure before esbuild sees any source;
// private page declarations and executable statements cannot enter the artifact.
function publicGameSource(source, exportName) {
  const ast = parse(source, { sourceType: 'module' });
  let program;
  babelTraverse.default(ast, {
    Program(path) { program = path; },
    enter(path) {
      if (path.isImportDeclaration() || path.isImport() || path.node.type === 'ImportExpression'
        || (path.isMetaProperty() && path.node.meta.name === 'import')
        || ((path.isExportNamedDeclaration() || path.isExportAllDeclaration()) && path.node.source)) {
        throw new Error('Imports are unavailable in generated features.');
      }
    },
  });
  let exportedName;
  for (const statement of program.get('body')) {
    if (!statement.isExportNamedDeclaration()) continue;
    const declaration = statement.get('declaration');
    if ((declaration.isVariableDeclaration() && Object.hasOwn(declaration.getBindingIdentifiers(), exportName))
      || ((declaration.isFunctionDeclaration() || declaration.isClassDeclaration()) && declaration.node.id?.name === exportName)) exportedName = exportName;
    for (const specifier of statement.get('specifiers')) {
      if (specifier.isExportSpecifier() && (specifier.node.exported.name || specifier.node.exported.value) === exportName) {
        exportedName = specifier.node.local.name;
      }
    }
  }
  if (!exportedName) throw new Error(`Export ${exportName} with init, step, and view.`);
  const selected = new Set();
  const include = binding => {
    if (!binding || binding.scope !== program.scope) throw new Error('Public game helpers must be declared in this module.');
    if (selected.has(binding)) return;
    const path = binding.path;
    if (path.isVariableDeclarator()) {
      if (!path.get('id').isIdentifier() || !path.node.init) {
        throw new Error('Public game helpers need individual named initializers; avoid destructuring.');
      }
    } else if (!path.isFunctionDeclaration() && !path.isClassDeclaration()) {
      throw new Error('Public game helpers must use named variable, function, or class declarations.');
    }
    if (!binding.constant) throw new Error('Public game bindings must not be reassigned; keep changing values in game state.');
    selected.add(binding);
    path.traverse({ ReferencedIdentifier(reference) {
      const dependency = reference.scope.getBinding(reference.node.name);
      if (dependency?.scope === program.scope) include(dependency);
    } });
  };
  include(program.scope.getBinding(exportedName));
  // Dropping an initializer that configures a public helper would silently
  // change its meaning. Conservatively refuse outside initialization that
  // reaches the public dependency chain, including calls through a helper.
  const referencesPublic = (path, seen = new Set()) => {
    let found = false;
    // A separately declared game's ordinary object methods do not execute
    // while its object is initialized. They may share helpers without making
    // that other game's source part of this public artifact. Calls and
    // computed properties still require the conservative side-effect check.
    const deferredObject = path.isObjectExpression();
    const inspect = reference => {
      if (found) return;
      const binding = reference.scope.getBinding(reference.node.name);
      if (selected.has(binding)) { found = true; return; }
      if (binding?.scope === program.scope && !seen.has(binding)) {
        seen.add(binding);
        found = referencesPublic(binding.path, seen);
      }
    };
    if (path.isReferencedIdentifier()) inspect(path);
    if (!found) path.traverse({
      Function(fn) {
        if (deferredObject && (fn.isObjectMethod() && fn.parentPath === path && !fn.node.computed
          || (fn.isFunctionExpression() || fn.isArrowFunctionExpression()) && fn.parentPath.isObjectProperty()
          && fn.parentPath.parentPath === path && fn.key === 'value')) fn.skip();
      },
      ReferencedIdentifier: inspect,
    });
    return found;
  };
  const selectedPaths = new Set([...selected].map(binding => binding.path));
  for (const statement of program.get('body')) {
    const declaration = statement.isExportNamedDeclaration() || statement.isExportDefaultDeclaration() ? statement.get('declaration') : statement;
    if (!declaration.node || declaration.isFunction() || selectedPaths.has(declaration)) continue;
    if (declaration.isVariableDeclaration()) {
      for (const declarator of declaration.get('declarations')) {
        const initial = declarator.get('init');
        if (!selectedPaths.has(declarator) && initial.node && !initial.isFunction() && referencesPublic(initial)) {
          throw new Error('Initialize public game helpers inside their declarations, not outside initializers.');
        }
      }
    } else if (referencesPublic(declaration)) {
      throw new Error('Initialize public game helpers inside their declarations, not separate module statements.');
    }
  }
  return [...selected].sort((a, b) => a.path.node.start - b.path.node.start).map(({ path }) => {
    const text = source.slice(path.node.start, path.node.end);
    return path.isVariableDeclarator() ? `${path.parentPath.node.kind} ${text};` : text;
  }).join('\n') + `\nexport { ${exportedName} as game };`;
}

export async function compileGameModule(source, exportName = 'game') {
  validateGameConfig({ id: 'publicGame', exportName });
  if (typeof source !== 'string' || !source.trim() || source.length > SOURCE_LIMIT) throw new Error('A bounded game source file is required.');
  if (/\bimport\s*(?:\(|\.)/.test(source)) throw new Error('Imports are unavailable in generated features.');
  let bundle;
  try {
    const publicSource = publicGameSource(source, exportName);
    const result = await build({
      entryPoints: ['public-game-entry'], bundle: true, write: false, format: 'iife', globalName: 'GameModule',
      platform: 'neutral', target: 'es2020', treeShaking: true, minifySyntax: true, legalComments: 'none', logLevel: 'silent',
      plugins: [{ name: 'public-game-only', setup(builder) {
        builder.onResolve({ filter: /.*/ }, args => {
          if (args.kind === 'entry-point' && args.path === 'public-game-entry') return { path: args.path, namespace: 'game-entry' };
          if (args.namespace === 'game-entry' && args.path === 'authored-game-source') return { path: 'space.js', namespace: 'game-source' };
          return { errors: [{ text: 'Imports are unavailable in generated features.' }] };
        });
        builder.onLoad({ filter: /.*/, namespace: 'game-entry' }, () => ({ contents: 'export { game } from "authored-game-source";', loader: 'js' }));
        builder.onLoad({ filter: /.*/, namespace: 'game-source' }, () => ({ contents: publicSource, loader: 'js' }));
      } }],
    });
    bundle = result.outputFiles[0].text;
  } catch (error) {
    const detail = error.errors?.map(item => item.text).join(' ') || error.message;
    throw new Error(`Could not compile the public game: ${detail}`.slice(0, 1000));
  }
  await evaluate(bundle, `
    if (!isRecord(GameModule.game) || ['init', 'step', 'view'].some(name => typeof GameModule.game[name] !== 'function')) {
      throw new Error('Export game with init(saved, actor), step(state, action, actor), and view(state, actor).');
    }
    return 'true';
  `, { game: true, timeout: GAME_TIMEOUT });
  return bundle;
}

export async function gameInit(bundle, saved, actor) {
  validateActor(actor);
  if (saved !== null) validateGameState(saved, actor);
  const state = await evaluate(bundle, `return JSON.stringify(gameInitChecked(GameModule.game, ${encoded(saved)}, ${encoded(actor)}));`, { game: true, timeout: GAME_TIMEOUT });
  return validateGameState(state, actor);
}

export async function gameStep(bundle, state, action, actor) {
  validateActor(actor);
  validateGameState(state, actor);
  validateAction(action);
  const next = await evaluate(bundle, `return JSON.stringify(gameStepChecked(GameModule.game, ${encoded(state)}, ${encoded(action)}, ${encoded(actor)}));`, { game: true, timeout: GAME_TIMEOUT });
  return validateGameState(next, actor);
}

export async function gameView(bundle, state, actor) {
  validateActor(actor);
  validateGameState(state, actor);
  const view = await evaluate(bundle, `return gameViewChecked(GameModule.game, ${encoded(state)}, ${encoded(actor)}, true);`, { game: true, timeout: GAME_TIMEOUT });
  return validateGameView(view);
}

export async function renderModule(bundle, state, actor) {
  validateState(state);
  validateActor(actor);
  const html = await evaluate(bundle, `
    const state = ${encoded(state)};
    const before = stableJson(state);
    const html = LivingModule.render(state, ${encoded(actor)});
    if (typeof html !== 'string') throw new Error('render must return an HTML string.');
    if (html.length > ${HTML_LIMIT}) throw new Error('Rendered content is too large.');
    if (stableJson(state) !== before) throw new Error('Rendering must not change the saved state.');
    return JSON.stringify(html);
  `, { timeout: RENDER_TIMEOUT });
  // Validate the bounded, immutable string in the trusted host. Repeating the
  // full markup scan in QuickJS charges host validation against the generated
  // render's execution budget and can reject valid, detailed pages on cold runs.
  validateHtml(html);
  if (html.length > HTML_LIMIT) throw new Error('Rendered content is too large.');
  return html;
}

export async function reduceModule(bundle, state, action, actor, { gameCheckpoint = false } = {}) {
  validateState(state);
  validateActor(actor);
  validateAction(action, gameCheckpoint ? 34_000 : 16_000);
  if (gameCheckpoint) {
    validateGameConfig(gameCheckpoint);
    validateGameState(action.game, actor);
  }
  const next = await evaluate(bundle, `
    const before = ${encoded(state)};
    const input = JSON.parse(JSON.stringify(before));
    const actor = ${encoded(actor)};
    const action = ${encoded(action)};
    validateAction(action, ${gameCheckpoint ? 34_000 : 16_000});
    const next = LivingModule.reduce(input, action, actor);
    validateTransition(before, next, actor);
    return JSON.stringify(next);
  `);
  // Enforce again outside the interpreter. Generated code cannot weaken these
  // checks even if it shadows or changes built-ins in its own context.
  validateTransition(state, next, actor);
  if (gameCheckpoint) validateGameCheckpoint(state, next, action, actor, gameCheckpoint);
  return next;
}

export async function verifyModule(source, testsSource, state, {
  owner = { id: 'mira', name: 'Mira' },
  visitor = { id: 'leo', name: 'Leo' },
  projectCatalog = false,
} = {}) {
  const checks = [];
  let compiled;
  const check = async (name, fn) => {
    try {
      await fn();
      checks.push({ name, ok: true });
      return true;
    } catch (error) {
      checks.push({ name, ok: false, message: error.message });
      return false;
    }
  };
  if (!await check('Source compiles in the isolated runtime', async () => { compiled = await compileModule(source); })) {
    return { ok: false, checks };
  }
  const liveState = state;
  const original = stableJson(liveState);
  if (projectCatalog && !await check('Owner project catalog preserves live participation', () => {
    state = projectStateForPublication(compiled.meta, liveState);
  })) return { ok: false, checks, ...compiled };
  const candidateState = structuredClone(state);
  await check('Saved projects and contributions are valid', () => validateState(state));
  const rendered = new Map();
  await check('Owner view renders without changing saved data', async () => { rendered.set(owner.id, await renderModule(compiled.bundle, state, owner)); });
  await check('Visitor view renders without changing saved data', async () => { rendered.set(visitor.id, await renderModule(compiled.bundle, state, visitor)); });
  const configs = gameConfigs(compiled.meta);
  const gameActions = {};
  for (const config of configs) {
    const gameBundle = compiled.gameBundles[config.id];
    for (const [role, actor] of [['Owner', owner], ['Visitor', visitor]]) {
      const name = configs.length === 1 ? role : `${role} ${config.id}`;
      await check(`${name} game controls are connected`, () => {
        const bindings = validateGameBindings(rendered.get(actor.id), config, configs);
        if (actor.id === owner.id) gameActions[config.id] = bindings.actions;
      });
      let fresh, next;
      const simulated = await check(`${name} game initializes, advances, and renders safely`, async () => {
        fresh = await gameInit(gameBundle, null, actor);
        await gameView(gameBundle, fresh, actor);
        const saved = state.extras[config.id]?.[actor.id] ?? null;
        next = await gameInit(gameBundle, saved, actor);
        let view = await gameView(gameBundle, next, actor);
        // A valid first frame is not enough: initialization mistakes often
        // surface only after a timer or position advances on later frames.
        for (let tick = 0; tick < 5 && !view.finished; tick++) {
          next = await gameStep(gameBundle, next, { type: 'tick', deltaMs: config.tickMs ?? 50 }, actor);
          view = await gameView(gameBundle, next, actor);
        }
      });
      if (simulated && config.saveAction) {
        await check(`${name} game checkpoints preserve progress and unrelated data`, async () => {
          for (const progress of [fresh, next]) {
            const saved = await reduceModule(compiled.bundle, state, { type: config.saveAction, game: progress }, actor, { gameCheckpoint: config });
            const resumed = await gameInit(gameBundle, saved.extras[config.id][actor.id], actor);
            await gameView(gameBundle, resumed, actor);
          }
        });
      }
    }
  }
  await check('Invalid participants cannot act', async () => {
    try {
      await reduceModule(compiled.bundle, state, { type: 'support', projectId: 'tidepool' }, { id: '', name: '' });
    } catch (error) {
      if (/participant/i.test(error.message)) return;
      throw error;
    }
    throw new Error('An invalid participant was accepted.');
  });
  await check('Publication preserves the current data', () => {
    if (stableJson(liveState) !== original) throw new Error('Verification changed the current data.');
    if (stableJson(state.contributions) !== stableJson(liveState.contributions) || stableJson(state.extras) !== stableJson(liveState.extras)) {
      throw new Error('Publication must preserve contributions and extra data.');
    }
  });
  await check('Feature behavior tests pass', async () => {
    const testsBundle = await compile(testsSource, 'LivingTests', TESTS_LIMIT);
    const publicGame = `const PublicGames = {${configs.map(config => `${JSON.stringify(config.id)}: (${withoutGameClock.toString()})(() => { ${compiled.gameBundles[config.id]}\nreturn GameModule.game; })`).join(',')}};`;
    const gameApi = configs.map(config => `${JSON.stringify(config.id)}: Object.freeze({
      config: ${encoded(config)}, actions: ${encoded(gameActions[config.id] || [])},
      init(saved, actor) { return gameInitChecked(PublicGames[${JSON.stringify(config.id)}], saved, actor); },
      step(state, action, actor) { return gameStepChecked(PublicGames[${JSON.stringify(config.id)}], state, action, actor); },
      view(state, actor) { return gameViewChecked(PublicGames[${JSON.stringify(config.id)}], state, actor); }
    })`).join(',');
    // One suite exercises every independent game in the same interpreter.
    // Keep a finite allowance per game (at most four) without extending the
    // individual action or simulation-step budgets.
    const generated = await evaluate(`${compiled.bundle}\n${publicGame}\n${testsBundle}`, `
      if (typeof LivingTests.runTests !== 'function') throw new Error('tests.js must export runTests(api).');
      const api = Object.freeze({
        initialState: ${encoded(state)},
        meta: LivingModule.meta,
        reduce(state, action, actor) {
          validateState(state);
          validateActor(actor);
          const checkpoint = gameConfigs(LivingModule.meta).find(config => config.saveAction !== undefined && config.saveAction === action.type);
          validateAction(action, checkpoint ? 34000 : 16000);
          if (checkpoint) validateGameState(action.game, actor);
          const before = JSON.parse(JSON.stringify(state));
          const next = LivingModule.reduce(JSON.parse(JSON.stringify(state)), action, actor);
          validateTransition(before, next, actor);
          if (checkpoint) validateGameCheckpoint(before, next, action, actor, checkpoint);
          return next;
        },
        render(state, actor) {
          validateState(state);
          validateActor(actor);
          const input = JSON.parse(JSON.stringify(state));
          const before = stableJson(input);
          const html = LivingModule.render(input, actor);
          validateHtml(html);
          if (stableJson(input) !== before) throw new Error('Rendering must not change saved data.');
          return html;
        },
        games: Object.freeze({${gameApi}}),
        ${compiled.meta.game ? `gameActions: ${encoded(gameActions[compiled.meta.game.id] || [])},
        gameInit(saved, actor) { return gameInitChecked(PublicGames[${JSON.stringify(compiled.meta.game.id)}], saved, actor); },
        gameStep(state, action, actor) { return gameStepChecked(PublicGames[${JSON.stringify(compiled.meta.game.id)}], state, action, actor); },
        gameView(state, actor) { return gameViewChecked(PublicGames[${JSON.stringify(compiled.meta.game.id)}], state, actor); },` : ''}
      });
      const results = LivingTests.runTests(api);
      if (!Array.isArray(results) || results.length < 1 || results.length > 60) {
        throw new Error('runTests(api) must return a non-empty array of checks.');
      }
      for (const item of results) {
        if (!isRecord(item) || typeof item.name !== 'string' || typeof item.ok !== 'boolean') {
          throw new Error('Every feature check needs a name and a boolean ok.');
        }
      }
      assertJson(results);
      return JSON.stringify(results);
    `, { timeout: VERIFICATION_TIMEOUT * Math.max(1, configs.length) });
    for (const result of generated) {
      checks.push({
        name: String(result.name).slice(0, 200),
        ok: result.ok === true,
        ...(result.message ? { message: String(result.message).slice(0, 600) } : {}),
      });
    }
    if (generated.some(result => result.ok !== true)) throw new Error('One or more feature behavior checks failed.');
  });
  return { ok: checks.every(result => result.ok), checks, ...compiled, candidateState };
}
