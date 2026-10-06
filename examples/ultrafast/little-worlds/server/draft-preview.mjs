import { compileModule, renderModule, projectStateForPublication } from './runtime.mjs';

// Decode only complete JSON escape sequences. An unfinished string is useful
// while arguments stream; an invalid escape is not. No generated JS is evaluated
// by the host, and a source-like substring inside another value is never a key.
function readJsonString(text, start) {
  if (text[start] !== '"') return null;
  let value = '';
  for (let index = start + 1; index < text.length; index++) {
    const character = text[index];
    if (character === '"') return { value, complete: true, end: index + 1 };
    if (character.charCodeAt(0) < 32) return null;
    if (character !== '\\') { value += character; continue; }
    if (++index >= text.length) return { value, complete: false, end: text.length };
    const escaped = text[index];
    const simple = { '"': '"', '\\': '\\', '/': '/', b: '\b', f: '\f', n: '\n', r: '\r', t: '\t' };
    if (Object.hasOwn(simple, escaped)) { value += simple[escaped]; continue; }
    if (escaped !== 'u') return null;
    const hex = text.slice(index + 1, index + 5);
    if (!/^[0-9a-f]*$/i.test(hex)) return null;
    if (hex.length < 4) return { value, complete: false, end: text.length };
    value += String.fromCharCode(Number.parseInt(hex, 16)); index += 4;
  }
  return { value, complete: false, end: text.length };
}

export function extractPartialSource(argumentsText) {
  if (typeof argumentsText !== 'string' || argumentsText.length > 240_000) return null;
  let index = 0;
  const whitespace = () => { while (/\s/.test(argumentsText[index] || '') && index < argumentsText.length) index++; };
  whitespace(); if (argumentsText[index++] !== '{') return null;
  while (index < argumentsText.length) {
    whitespace();
    const key = readJsonString(argumentsText, index);
    if (!key?.complete) return null;
    index = key.end; whitespace(); if (argumentsText[index++] !== ':') return null;
    whitespace();
    const value = readJsonString(argumentsText, index);
    if (!value) return null;
    if (key.value === 'source') return value.value.length <= 80_000 ? { source: value.value, complete: value.complete } : null;
    if (!value.complete) return null;
    index = value.end; whitespace(); if (argumentsText[index++] !== ',') return null;
  }
  return null;
}

function sourceCandidates(source) {
  const candidates = [source];
  // The requested source order is meta, render, reduce. This boundary permits a
  // valid render to preview while the model is still writing behavior and tests.
  const reducers = [...source.matchAll(/\bexport\s+(?:(?:async\s+)?function\s+reduce\b|(?:const|let|var)\s+reduce\b)/g)];
  for (const marker of reducers.reverse()) candidates.push(source.slice(0, marker.index));
  // Only completed syntax is accepted below. Candidate boundaries may include
  // punctuation in strings or comments; esbuild rejects those incomplete slices.
  let count = 0;
  for (let index = source.length - 1; index >= 0 && count < 16; index--) {
    if (source[index] === '}' || source[index] === ';') { candidates.push(source.slice(0, index + 1)); count++; }
  }
  return [...new Set(candidates.map((candidate) => candidate.trim()))].filter((candidate) => candidate.length >= 80);
}

export async function renderDraftSource(source, state, actor, { isActive = () => true } = {}) {
  const deadline = performance.now() + 300;
  for (const candidate of sourceCandidates(source)) {
    for (const withStub of [false, true]) {
      if (!isActive() || performance.now() > deadline) return null;
      // The stub only satisfies the module shape for an inert preview. It is
      // never saved, verified, published or called to handle a visitor action.
      const previewSource = withStub ? `${candidate}\nexport function reduce(state) { return state; }` : candidate;
      try {
        const { bundle, meta } = await compileModule(previewSource);
        if (!isActive() || performance.now() > deadline) return null;
        const html = await renderModule(bundle, projectStateForPublication(meta, state), actor);
        if (!isActive()) return null;
        if (html.length > 40_000) continue;
        return { html, layout: meta.layout, renderedSourceCharacters: candidate.length };
      } catch { /* A partial or invalid source must not interrupt the real turn. */ }
    }
  }
  return null;
}

export function createDraftPreviewer({ getState, actor, emit, isActive, now = () => performance.now(), intervalMs = 700, minimumCharacters = 700, maxPreviews = 4, render = renderDraftSource }) {
  let lastAttempt = -Infinity;
  let lastAttemptSource = '';
  let lastHtml = null;
  let published = 0;
  let pending = null;
  let running = null;
  let timer = null;
  let scheduled = false;
  let closed = false;
  let generation = 0;
  const idleWaiters = new Set();
  const active = () => !closed && published < maxPreviews && isActive();
  const clearTimer = () => { if (timer !== null) clearTimeout(timer); timer = null; };
  const notifyIdle = () => {
    if (running || pending || scheduled || timer !== null) return;
    for (const resolve of idleWaiters) resolve();
    idleWaiters.clear();
  };

  function kick() {
    if (running || scheduled || timer !== null || !pending) { notifyIdle(); return; }
    if (!active()) { pending = null; notifyIdle(); return; }
    const remaining = pending.force ? 0 : intervalMs - (now() - lastAttempt);
    if (remaining > 0) {
      timer = setTimeout(() => { timer = null; kick(); }, remaining);
      // A best-effort animation must never keep the server process alive.
      timer.unref?.();
      return;
    }
    scheduled = true;
    queueMicrotask(() => {
      scheduled = false;
      if (!pending || !active()) { pending = null; notifyIdle(); return; }
      if (running) return; // An explicit consider() may have started meanwhile.
      const next = pending; pending = null;
      start(next.argumentsText, next);
    });
  }

  function start(argumentsText, { force = false } = {}) {
    if (running || !active() || (!force && now() - lastAttempt < intervalMs)) { notifyIdle(); return Promise.resolve(false); }
    const decoded = extractPartialSource(argumentsText);
    if (!decoded || decoded.source === lastAttemptSource || (!decoded.complete && decoded.source.length < minimumCharacters)) { notifyIdle(); return Promise.resolve(false); }
    lastAttempt = now(); lastAttemptSource = decoded.source;
    const attemptGeneration = generation;
    const current = () => generation === attemptGeneration && active();
    const work = async () => {
      try {
        const preview = await render(decoded.source, getState(), actor, { isActive: current });
        if (!preview || preview.html === lastHtml || !current()) return false;
        await emit({ type: 'draft.preview', stage: 'build', title: 'Your new page is taking shape', detail: 'A live preview of generated source. Checks are still running.', data: { html: preview.html, layout: preview.layout, sourceCharacters: decoded.source.length, renderedSourceCharacters: preview.renderedSourceCharacters, actorId: actor.id, preview: true } }, current);
        lastHtml = preview.html; published++;
        return true;
      } catch { return false; /* A preview cannot fail the owner's actual turn. */ }
    };
    running = work().finally(() => {
      running = null;
      kick();
      notifyIdle();
    });
    return running;
  }

  const previewer = {
    // Kept for callers explicitly requesting a completed preview. Model stream
    // callbacks use schedule instead so compilation never stalls SSE parsing.
    consider(argumentsText, options) { return start(argumentsText, options); },
    schedule(argumentsText, { force = false } = {}) {
      if (!active() || typeof argumentsText !== 'string' || argumentsText.length > 240_000) return false;
      // There is at most one active render and one latest snapshot. Parsing also
      // happens after coalescing, rather than re-decoding all source per token.
      pending = { argumentsText, force: force || Boolean(pending?.force) };
      if (force) clearTimer();
      kick();
      return true;
    },
    flush() {
      if (pending) { pending.force = true; clearTimer(); }
      return new Promise((resolve) => { idleWaiters.add(resolve); kick(); notifyIdle(); });
    },
    discard() {
      generation++;
      pending = null;
      lastAttempt = -Infinity;
      lastAttemptSource = '';
      clearTimer();
      notifyIdle();
    },
    close() { closed = true; previewer.discard(); },
  };
  return previewer;
}
