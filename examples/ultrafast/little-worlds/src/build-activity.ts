import type { RuntimeEvent } from './types';

export interface OutputThroughput {
  tokens: number;
  durationMs: number;
  rate: number;
  sampledAt: number;
  lastDeltaAt: number | null;
  state: 'waiting' | 'streaming' | 'complete';
  estimated: true;
}

export interface ActivityEntry {
  id: string;
  time: string;
  turnId?: string;
  kind: 'request' | 'message' | 'tool' | 'event';
  title: string;
  status?: 'running' | 'completed' | 'failed' | 'cancelled';
  text?: string;
  tool?: string;
  arguments?: string;
  inputFormat?: 'json' | 'patch';
  result?: string;
  eventType?: string;
  durationMs?: number;
  truncated?: boolean;
  throughput?: OutputThroughput;
}

// Match the server's transient replay bounds. Character limits are a final
// client safeguard; the server applies the stricter UTF-8 byte limits.
export const ACTIVITY_MAX_ENTRIES = 120;
export const ACTIVITY_MAX_FIELD = 192 * 1024;
export const ACTIVITY_MAX_CONTENT = 2 * 1024 * 1024;
const kinds = new Set(['request', 'message', 'tool', 'event']);
const statuses = new Set(['running', 'completed', 'failed', 'cancelled']);
const record = (value: unknown): value is Record<string, unknown> => !!value && typeof value === 'object' && !Array.isArray(value);

function safeSlice(value: string, limit: number) {
  let end = Math.min(value.length, limit);
  if (end < value.length && /[\uD800-\uDBFF]/.test(value.charAt(end - 1))) end--;
  return value.slice(0, end);
}

function activityEntry(event: Record<string, unknown>): ActivityEntry | null {
  const data = event.data;
  if (!record(data) || typeof data.entryId !== 'string' || !data.entryId || data.entryId.length > 256
    || typeof data.kind !== 'string' || !kinds.has(data.kind)) return null;
  const entry: ActivityEntry = {
    id: data.entryId,
    time: typeof event.time === 'string' ? safeSlice(event.time, 80) : '',
    kind: data.kind as ActivityEntry['kind'],
    title: typeof event.title === 'string' ? safeSlice(event.title, 240) : 'Build activity',
  };
  if (typeof event.turnId === 'string') entry.turnId = safeSlice(event.turnId, 256);
  if (typeof data.status === 'string' && statuses.has(data.status)) entry.status = data.status as ActivityEntry['status'];
  if (typeof data.durationMs === 'number' && Number.isFinite(data.durationMs) && data.durationMs >= 0) entry.durationMs = data.durationMs;
  if (data.truncated === true) entry.truncated = true;
  if (data.inputFormat === 'json' || data.inputFormat === 'patch') entry.inputFormat = data.inputFormat;
  for (const field of ['text', 'tool', 'arguments', 'result', 'eventType'] as const) {
    if (typeof data[field] !== 'string') continue;
    const limit = field === 'tool' || field === 'eventType' ? 160 : ACTIVITY_MAX_FIELD;
    entry[field] = safeSlice(data[field], limit);
    if (entry[field].length < data[field].length) entry.truncated = true;
  }
  const speed = data.throughput;
  if (entry.eventType === 'model.started' && record(speed) && speed.estimated === true
    && ['waiting', 'streaming', 'complete'].includes(String(speed.state))
    && ['tokens', 'durationMs', 'rate', 'sampledAt'].every(key => typeof speed[key] === 'number' && Number.isFinite(speed[key]) && speed[key] >= 0)
    && Number(speed.tokens) <= 1e9 && Number(speed.durationMs) <= 1e9 && Number(speed.rate) <= 1e9 && Number(speed.sampledAt) <= 8.64e15
    && (speed.lastDeltaAt === null || typeof speed.lastDeltaAt === 'number' && Number.isFinite(speed.lastDeltaAt) && speed.lastDeltaAt >= 0)) {
    entry.throughput = {
      tokens: speed.tokens as number, durationMs: speed.durationMs as number, rate: speed.rate as number,
      sampledAt: speed.sampledAt as number, lastDeltaAt: speed.lastDeltaAt as number | null,
      state: speed.state as OutputThroughput['state'], estimated: true,
    };
  }
  return entry;
}

function sameEntry(left: ActivityEntry, right: ActivityEntry) {
  const keys = Object.keys(left) as Array<keyof ActivityEntry>;
  return keys.length === Object.keys(right).length && keys.every(key => key === 'throughput'
    ? JSON.stringify(left.throughput) === JSON.stringify(right.throughput) : left[key] === right[key]);
}

/** Upsert cumulative snapshots once per transport batch, retaining first-seen order. */
export function mergeActivityEvents(current: ActivityEntry[], events: readonly (RuntimeEvent | unknown)[]): ActivityEntry[] {
  let next = current;
  for (const event of events) {
    if (!record(event)) continue;
    if (event.type === 'activity.reset') {
      if (next.length) next = [];
      continue;
    }
    if (event.type !== 'activity.entry') continue;
    const incoming = activityEntry(event);
    if (!incoming) continue;
    const index = next.findIndex(entry => entry.id === incoming.id);
    if (index === -1) next = [...next, incoming];
    else {
      // An update replaces the full cumulative payload, but never moves its row
      // or changes when that row first appeared.
      incoming.time = next[index].time;
      if (sameEntry(next[index], incoming)) continue;
      next = next.slice();
      next[index] = incoming;
    }
  }
  if (next === current) return current;
  let content = 0;
  let start = next.length;
  while (start > 0 && next.length - start < ACTIVITY_MAX_ENTRIES) {
    const entry = next[start - 1];
    const length = (entry.text?.length || 0) + (entry.arguments?.length || 0) + (entry.result?.length || 0);
    if (content + length > ACTIVITY_MAX_CONTENT) break;
    content += length;
    start--;
  }
  return start ? next.slice(start) : next;
}

type Parsed = { value?: unknown; end: number; complete: boolean; invalid?: boolean };

/** Read a JSON prefix without evaluating code or inventing unfinished escapes. */
export function parseActivityArguments(input: string | undefined): Record<string, unknown> | null {
  if (typeof input !== 'string' || input.length > ACTIVITY_MAX_FIELD) return null;
  const raw = input;
  let nodes = 0;
  const whitespace = (index: number) => { while (/\s/.test(raw.charAt(index)) && index < raw.length) index++; return index; };
  function string(index: number): Parsed {
    let value = '';
    let cursor = index + 1;
    while (cursor < raw.length) {
      const character = raw[cursor++];
      if (character === '"') return { value, end: cursor, complete: true };
      if (character.charCodeAt(0) < 32) return { end: cursor, complete: false, invalid: true };
      if (character !== '\\') { value += character; continue; }
      if (cursor >= raw.length) break;
      const escape = raw[cursor++];
      if (escape === 'u') {
        const digits = raw.slice(cursor, cursor + 4);
        if (!/^[0-9a-f]*$/i.test(digits)) return { end: cursor, complete: false, invalid: true };
        if (digits.length < 4) break;
        value += String.fromCharCode(parseInt(digits, 16));
        cursor += 4;
      } else {
        const escapes: Record<string, string> = { '"': '"', '\\': '\\', '/': '/', b: '\b', f: '\f', n: '\n', r: '\r', t: '\t' };
        if (!Object.hasOwn(escapes, escape)) return { end: cursor, complete: false, invalid: true };
        value += escapes[escape];
      }
    }
    // A surrogate pair may arrive in separate deltas. Wait for its second half.
    if (/[\uD800-\uDBFF]/.test(value.charAt(value.length - 1))) value = value.slice(0, -1);
    return { value, end: raw.length, complete: false };
  }
  function parse(index: number, depth = 0): Parsed {
    if (++nodes > 2048 || depth > 16) return { end: index, complete: false, invalid: true };
    index = whitespace(index);
    if (index >= raw.length) return { end: index, complete: false };
    if (raw[index] === '"') return string(index);
    if (raw[index] === '{' || raw[index] === '[') {
      const array = raw[index] === '[';
      const value: unknown[] | Record<string, unknown> = array ? [] : Object.create(null);
      const close = array ? ']' : '}';
      let cursor = whitespace(index + 1);
      if (raw[cursor] === close) return { value, end: cursor + 1, complete: true };
      while (cursor < raw.length) {
        let key = '';
        if (!array) {
          if (raw[cursor] !== '"') return { end: cursor, complete: false, invalid: true };
          const name = string(cursor);
          if (name.invalid) return name;
          if (!name.complete) return { value, end: name.end, complete: false };
          key = name.value as string;
          cursor = whitespace(name.end);
          if (cursor === raw.length) return { value, end: cursor, complete: false };
          if (raw[cursor] !== ':') return { end: cursor, complete: false, invalid: true };
          cursor++;
        }
        const child = parse(cursor, depth + 1);
        if (child.invalid) return child;
        if (child.value !== undefined) {
          if (Array.isArray(value)) value.push(child.value);
          else value[key] = child.value;
        }
        if (!child.complete) return { value, end: child.end, complete: false };
        cursor = whitespace(child.end);
        if (raw[cursor] === close) return { value, end: cursor + 1, complete: true };
        if (cursor === raw.length) return { value, end: cursor, complete: false };
        if (raw[cursor] !== ',') return { end: cursor, complete: false, invalid: true };
        cursor = whitespace(cursor + 1);
      }
      return { value, end: cursor, complete: false };
    }
    let end = index;
    while (end < raw.length && !/[\s,}\]]/.test(raw[end])) end++;
    const primitive = raw.slice(index, end);
    try {
      const value: unknown = JSON.parse(primitive);
      return { value, end, complete: true };
    } catch {
      const prefix = ['true', 'false', 'null'].some(value => value.startsWith(primitive)) || /^-?(?:\d+(?:\.\d*)?)?(?:[eE][+-]?\d*)?$/.test(primitive);
      return { end, complete: false, invalid: end < raw.length || !prefix };
    }
  }
  const parsed = parse(0);
  if (parsed.invalid || !record(parsed.value) || parsed.complete && whitespace(parsed.end) !== raw.length) return null;
  return parsed.value;
}

/** Display source as text only; it is never loaded or executed by this panel. */
export function activityCode(entry: ActivityEntry): Array<{ path: string; code: string }> {
  if (entry.kind !== 'tool') return [];
  // Freeform patches are shown verbatim once by the existing wrapped Arguments
  // view. Legacy saved function calls still decode into their source blocks.
  if (entry.inputFormat === 'patch') return [];
  const arguments_ = parseActivityArguments(entry.arguments);
  if (!arguments_) return [];
  if (entry.tool === 'apply_change') return [
    ...(typeof arguments_.source === 'string' ? [{ path: 'space.js', code: arguments_.source }] : []),
    ...(typeof arguments_.tests === 'string' ? [{ path: 'tests.js', code: arguments_.tests }] : []),
  ];
  if (entry.tool === 'write_file' && typeof arguments_.content === 'string') return [{
    path: typeof arguments_.path === 'string' ? safeSlice(arguments_.path, 160) : 'file', code: arguments_.content,
  }];
  if (entry.tool === 'apply_patch' && Array.isArray(arguments_.edits)) return arguments_.edits.flatMap((edit, index) => {
    if (!record(edit) || typeof edit.replace !== 'string') return [];
    return [{ path: `${typeof edit.path === 'string' ? safeSlice(edit.path, 160) : 'file'} · edit ${index + 1}`, code: edit.replace }];
  });
  return [];
}

export function prettyActivityJson(value: string | undefined, limit = 16_000): string {
  if (typeof value !== 'string') return '';
  let formatted = value;
  if (value.length <= ACTIVITY_MAX_FIELD) {
    try { formatted = JSON.stringify(JSON.parse(value), null, 2); } catch { /* Streaming arguments may still be incomplete. */ }
  }
  const bound = Number.isFinite(limit) ? Math.max(0, Math.min(ACTIVITY_MAX_FIELD, Math.floor(limit))) : 16_000;
  return formatted.length > bound ? `${safeSlice(formatted, bound)}\n…` : formatted;
}
