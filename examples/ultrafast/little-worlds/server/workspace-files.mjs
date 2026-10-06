import { applySourceEdits } from './source-edits.mjs';
import { projectCodexPatch } from './codex-patch-preview.mjs';

const FILES = [['space.js', 'source'], ['tests.js', 'tests']];
const WRITERS = new Set(['apply_change', 'apply_patch', 'write_file']);
const MAX_ARGUMENTS = 2 * 1024 * 1024;
const validContent = value => typeof value === 'string' && Buffer.byteLength(value) <= 80_000;

// Read only the JSON prefix received so far. Nodes retain completeness so a
// partial path/search can never choose a file or replace the wrong source.
// This parser evaluates neither JavaScript nor the model's arbitrary output.
function partialArguments(text) {
  let at = 0;
  let nodes = 0;
  const whitespace = () => { while (at < text.length && /\s/.test(text[at])) at++; };
  function read(depth = 0) {
    if (++nodes > 200 || depth > 5) throw new Error('Arguments are too complex.');
    whitespace();
    if (text[at] === '"') {
      at++;
      let value = '';
      while (at < text.length) {
        let next = text[at++];
        if (next === '"') return { kind: 'string', value, complete: true };
        if (next.charCodeAt(0) < 32) throw new Error('Invalid string.');
        if (next === '\\') {
          if (at === text.length) break;
          next = text[at++];
          if (next === 'u') {
            const hex = text.slice(at, at + 4);
            if (!/^[0-9a-f]*$/i.test(hex)) throw new Error('Invalid escape.');
            if (hex.length < 4) { at = text.length; break; }
            value += String.fromCharCode(Number.parseInt(hex, 16)); at += 4;
            continue;
          }
          const escapes = { '"': '"', '\\': '\\', '/': '/', b: '\b', f: '\f', n: '\n', r: '\r', t: '\t' };
          if (!Object.hasOwn(escapes, next)) throw new Error('Invalid escape.');
          value += escapes[next];
        } else value += next;
      }
      return { kind: 'string', value, complete: false };
    }
    const array = text[at] === '[';
    if (!array && text[at] !== '{') throw new Error('Expected an object, array, or string.');
    at++;
    const value = array ? [] : Object.create(null);
    const close = array ? ']' : '}';
    while (at < text.length) {
      whitespace();
      if (at === text.length) break;
      if (text[at] === close) { at++; return { kind: array ? 'array' : 'object', value, complete: true }; }
      let key;
      if (!array) {
        const field = read(depth + 1);
        if (field.kind !== 'string') throw new Error('Invalid property.');
        if (!field.complete) break;
        key = field.value;
        if (Object.hasOwn(value, key)) throw new Error('Duplicate property.');
        whitespace();
        if (at === text.length) break;
        if (text[at++] !== ':') throw new Error('Expected a colon.');
        whitespace();
        if (at === text.length) break;
      }
      if (at === text.length) break;
      const item = read(depth + 1);
      if (array) value.push(item); else value[key] = item;
      if (!item.complete) break;
      whitespace();
      if (text[at] === close) { at++; return { kind: array ? 'array' : 'object', value, complete: true }; }
      if (at === text.length) break;
      if (text[at++] !== ',') throw new Error('Expected a comma.');
    }
    return { kind: array ? 'array' : 'object', value, complete: false };
  }
  try {
    const node = read();
    whitespace();
    return node.kind === 'object' && at === text.length ? node.value : null;
  } catch { return null; }
}

function projectCall(workspace, call) {
  if (call.type === 'custom_tool_call') return call.name === 'apply_patch'
    ? projectCodexPatch(workspace, call.arguments, { complete: call.complete }) : workspace;
  const fields = partialArguments(call.arguments);
  if (!fields) return workspace;
  const text = node => node?.kind === 'string' ? node.value : undefined;
  if (call.name === 'apply_change') {
    const next = { ...workspace };
    for (const key of ['source', 'tests']) if (validContent(text(fields[key]))) next[key] = text(fields[key]);
    return next;
  }
  if (call.name === 'write_file') {
    const path = fields.path?.complete && text(fields.path);
    if (!FILES.some(([file]) => file === path) || !validContent(text(fields.content))) return workspace;
    return { ...workspace, [path === 'space.js' ? 'source' : 'tests']: text(fields.content) };
  }
  if (call.name === 'apply_patch' && fields.edits?.kind === 'array') {
    const edits = [];
    for (const node of fields.edits.value) {
      if (node.kind !== 'object') return workspace;
      const { path, search, replace } = node.value;
      if (!path?.complete || !search?.complete || text(replace) === undefined) break;
      edits.push({ path: text(path), search: text(search), replace: text(replace) });
      if (!node.complete) break;
    }
    if (edits.length) {
      try { return applySourceEdits(workspace, edits); } catch { /* Invalid or ambiguous edits never alter the preview. */ }
    }
  }
  return workspace;
}

// The files inspector is a bounded in-memory view of the two permitted source
// files. Provisional text never reaches the disk, runtime, or publication path.
export function createWorkspaceFiles({ getPublished, intervalMs = 90, now = () => Date.now() }) {
  const listeners = new Set();
  const closeListeners = new Set();
  const calls = new Map();
  let base;
  let snapshot;
  let sequence = 0;
  let turnId;
  let timer;
  let closed = false;
  let phase = 'published';

  function update(projected = base, streaming = false) {
    const previous = snapshot?.data;
    const time = new Date(now()).toISOString();
    const files = FILES.map(([path, key]) => {
      const content = projected[key];
      const last = previous?.files.find(file => file.path === path);
      const status = streaming && content !== base[key] ? 'streaming' : phase;
      return { path, content, language: 'javascript', status, updatedAt: last?.content === content ? last.updatedAt : time };
    });
    const data = { sessionId: base.sessionId, revisionId: base.revisionId, ...(turnId ? { turnId } : {}), status: files.some(file => file.status === 'streaming') ? 'streaming' : phase, files };
    if (JSON.stringify(data) === JSON.stringify(previous)) return;
    snapshot = { id: String(++sequence), type: 'files.snapshot', time, data };
    for (const listener of listeners) {
      try { listener(structuredClone(snapshot)); } catch { /* An inspector cannot interrupt generation. */ }
    }
  }
  function flush() {
    if (timer) clearTimeout(timer);
    timer = undefined;
    if (closed) return;
    let projected = base;
    for (const call of calls.values()) projected = projectCall(projected, call);
    update(projected, calls.size > 0);
  }
  function schedule() {
    if (timer || closed) return;
    timer = setTimeout(flush, intervalMs);
    timer.unref?.();
  }
  function published() {
    if (closed) return;
    calls.clear(); turnId = undefined; phase = 'published';
    base = getPublished();
    flush();
  }
  function outputItem(index, item, complete = false) {
    if (!WRITERS.has(item?.name) || !['function_call', 'custom_tool_call'].includes(item.type)) return;
    if (item.type === 'custom_tool_call' && item.name !== 'apply_patch') return;
    if (!calls.has(index) && calls.size >= 24) return;
    const input = item.type === 'custom_tool_call' ? item.input : item.arguments;
    const args = typeof input === 'string' ? input : '';
    calls.set(index, { type: item.type, name: item.name, arguments: args.length <= MAX_ARGUMENTS ? args : '', overflow: args.length > MAX_ARGUMENTS, complete });
    schedule();
  }
  published();
  return {
    flush,
    published,
    begin(id) { if (closed) return; calls.clear(); turnId = id; phase = 'working'; base = getPublished(); flush(); },
    beginResponse() { if (closed || !turnId) return; calls.clear(); flush(); },
    working(workspace) {
      if (closed || !turnId) return;
      calls.clear();
      base = { ...base, source: workspace.source, tests: workspace.tests };
      flush();
    },
    providerEvent(event) {
      if (closed || !turnId || !Number.isInteger(event.output_index)) return;
      if (['response.output_item.added', 'response.output_item.done'].includes(event.type)) outputItem(event.output_index, event.item, event.type.endsWith('.done'));
      else if (['response.function_call_arguments.delta', 'response.function_call_arguments.done', 'response.custom_tool_call_input.delta', 'response.custom_tool_call_input.done'].includes(event.type)) {
        const call = calls.get(event.output_index);
        if (!call || call.overflow) return;
        const custom = event.type.startsWith('response.custom_tool_call_input.');
        if (custom !== (call.type === 'custom_tool_call')) return;
        const value = event.type.endsWith('.done') ? custom ? event.input : event.arguments : event.delta;
        if (typeof value !== 'string') return;
        call.arguments = event.type.endsWith('.done') ? value : call.arguments + value;
        call.complete = event.type.endsWith('.done');
        if (call.arguments.length > MAX_ARGUMENTS) { call.arguments = ''; call.overflow = true; }
        schedule();
      }
    },
    providerOutput(output) { if (closed || !turnId) return; output.forEach((item, index) => outputItem(index, item, true)); flush(); },
    read() { flush(); return structuredClone(snapshot); },
    subscribe(listener, onClose) {
      if (closed) { onClose?.(); return () => {}; }
      listeners.add(listener); if (onClose) closeListeners.add(onClose);
      return () => { listeners.delete(listener); if (onClose) closeListeners.delete(onClose); };
    },
    close() {
      if (closed) return;
      closed = true;
      if (timer) clearTimeout(timer);
      for (const listener of closeListeners) { try { listener(); } catch { /* Already disconnected. */ } }
      calls.clear(); listeners.clear(); closeListeners.clear();
    },
  };
}
