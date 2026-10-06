import { randomUUID } from 'node:crypto';
import { createOutputThroughput } from './output-throughput.mjs';

const TOOLS = new Set(['inspect_space', 'read_file', 'write_file', 'verify_workspace', 'publish_revision', 'apply_change', 'apply_patch']);
const LIFECYCLE = new Set(['turn.started', 'turn.completed', 'turn.failed', 'turn.cancelled', 'message', 'model.started', 'model.completed', 'tool.started', 'tool.completed', 'tool.failed', 'revision.published', 'draft.preview']);
const RESULT_KEYS = ['tool', 'files', 'file', 'characters', 'sourceCharacters', 'testCharacters', 'checks', 'revisionId', 'preservedContributions', 'model', 'requestedTier', 'servedTier', 'iteration', 'durationMs', 'ttftMs', 'headersMs', 'outputTokens', 'inputTokens', 'cachedInputTokens', 'reasoningTokens', 'transport', 'transportFallback'];
const safeText = value => String(value).replace(/sk-[A-Za-z0-9_-]+/g, '[redacted]').replace(/\bBearer\s+[^\s"'<>]+/gi, 'Bearer [redacted]');

// This feed deliberately never receives model input/instructions, raw Responses
// objects, reasoning items, or headers. It is a transient owner-only projection.
export function createBuildActivity({ intervalMs = 90, maxEntries = 120, maxTextBytes = 192 * 1024, maxBytes = 2 * 1024 * 1024, now = () => Date.now(), countTokens } = {}) {
  const generation = randomUUID();
  const entries = new Map();
  const calls = new Map();
  const throughput = new Map();
  const listeners = new Set();
  const closeListeners = new Set();
  const dirty = new Set();
  let sequence = 0;
  let bytes = 0;
  let timer;
  let closed = false;

  function notify(event) {
    for (const listener of listeners) {
      try { listener(structuredClone(event)); } catch { /* A viewer cannot interrupt the builder. */ }
    }
  }
  function removeOldest() {
    const key = entries.keys().next().value;
    if (key === undefined) return;
    const entry = entries.get(key);
    bytes -= entry.bytes;
    entries.delete(key); dirty.delete(key);
    for (const [callId, entryId] of calls) if (entryId === key) calls.delete(callId);
    for (const [responseId, response] of throughput) if (response.entryKey === key) throughput.delete(responseId);
  }
  function enforceBounds() {
    while (entries.size > maxEntries || bytes > maxBytes && entries.size > 1) removeOldest();
  }
  function schedule() {
    if (timer || closed) return;
    timer = setTimeout(flush, intervalMs);
    timer.unref?.();
  }
  function update(key, properties, fields = {}, append = false) {
    if (closed) return;
    let entry = entries.get(key);
    if (!entry) {
      entry = { key, time: new Date(now()).toISOString(), properties: {}, fields: {}, omitted: {}, bytes: 0 };
      entries.set(key, entry);
    }
    Object.assign(entry.properties, properties);
    for (const [field, value] of Object.entries(fields)) {
      if (typeof value !== 'string') continue;
      const previous = entry.fields[field] || '';
      const previousBytes = Buffer.byteLength(previous);
      const incoming = Buffer.from(value);
      const remaining = append && entry.omitted[field] ? 0 : Math.max(0, Math.min(maxTextBytes - (append ? previousBytes : 0), maxBytes - entry.bytes + (append ? 0 : previousBytes)));
      let end = Math.min(incoming.length, remaining);
      // Truncate at a UTF-8 boundary instead of creating a replacement character.
      while (end > 0 && end < incoming.length && (incoming[end] & 0xc0) === 0x80) end--;
      const accepted = incoming.subarray(0, end).toString();
      entry.fields[field] = (append ? previous : '') + accepted;
      entry.omitted[field] = (append ? entry.omitted[field] || 0 : 0) + incoming.length - end;
      const difference = Buffer.byteLength(entry.fields[field]) - previousBytes;
      entry.bytes += difference; bytes += difference;
    }
    dirty.add(key);
    enforceBounds();
    schedule();
    return key;
  }
  function flush() {
    if (timer) clearTimeout(timer);
    timer = undefined;
    if (closed) return;
    for (const response of throughput.values()) {
      const entry = entries.get(response.entryKey);
      if (!entry || !response.meter.dirty) continue;
      entry.properties.throughput = response.meter.sample();
      dirty.add(response.entryKey);
    }
    for (const key of dirty) {
      const entry = entries.get(key);
      if (!entry) continue;
      const fields = Object.fromEntries(Object.entries(entry.fields).map(([name, value]) => [name, safeText(value)]));
      const omittedBytes = Object.values(entry.omitted).reduce((sum, value) => sum + value, 0);
      const { title, turnId, ...properties } = entry.properties;
      entry.event = { id: String(++sequence), type: 'activity.entry', time: entry.time, ...(turnId ? { turnId } : {}), title: safeText(title || 'Build activity'), data: { entryId: `${generation}:${key}`, ...properties, ...fields, ...(omittedBytes ? { truncated: true, omittedBytes } : {}) } };
      notify(entry.event);
    }
    dirty.clear();
  }
  function reset() {
    if (closed) return;
    if (timer) clearTimeout(timer);
    timer = undefined;
    entries.clear(); calls.clear(); throughput.clear(); dirty.clear(); bytes = 0;
    notify({ id: String(++sequence), type: 'activity.reset', time: new Date(now()).toISOString(), title: 'Build activity cleared', data: { reason: 'space-reset' } });
  }
  function finishTurn(turnId, status) {
    for (const response of throughput.values()) if (response.turnId === turnId) response.meter.finish();
    for (const [key, entry] of entries) {
      if (entry.properties.turnId === turnId && entry.properties.status === 'running') update(key, { status });
    }
  }
  function lifecycle(event) {
    if (event.type === 'space.reset' || event.type === 'space.updated' && event.data?.reset) { reset(); return; }
    if (!LIFECYCLE.has(event.type)) return;
    const status = event.type.endsWith('.failed') ? 'failed' : event.type.endsWith('.cancelled') ? 'cancelled' : event.type.endsWith('.started') ? 'running' : 'completed';
    const request = event.type === 'turn.started' || event.type === 'message' && event.data?.steering;
    const result = Object.fromEntries(RESULT_KEYS.filter(key => event.data?.[key] !== undefined).map(key => [key, event.data[key]]));
    update(`event:${event.id}`, { title: event.title, turnId: event.turnId, kind: request ? 'request' : 'event', status: request ? 'completed' : status, eventType: event.type, ...(TOOLS.has(event.data?.tool) ? { tool: event.data.tool } : {}), ...(Number.isFinite(event.durationMs) ? { durationMs: event.durationMs } : {}) }, { ...(typeof event.detail === 'string' ? { text: event.detail } : {}), ...(Object.keys(result).length ? { result: JSON.stringify(result, null, 2) } : {}) });
    if (event.type === 'model.started' && typeof event.turnId === 'string' && Number.isInteger(event.data?.iteration) && event.data.iteration > 0) {
      const entryKey = `event:${event.id}`;
      const responseKey = `${event.turnId}:response:${event.data.iteration - 1}`;
      if (entries.has(entryKey) && !throughput.has(responseKey)) throughput.set(responseKey, {
        entryKey, turnId: event.turnId, meter: createOutputThroughput({ now, ...(countTokens ? { countTokens } : {}) }),
      });
    }
    // A lifecycle span resolves its own start row as well as adding its result.
    if (event.type === 'model.completed' || event.type === 'tool.completed' || event.type === 'tool.failed') {
      const startType = event.type.startsWith('model.') ? 'model.started' : 'tool.started';
      for (const [key, entry] of entries) {
        if (entry.properties.turnId === event.turnId && entry.properties.eventType === startType && entry.properties.status === 'running' && (startType === 'model.started' || entry.properties.tool === event.data?.tool)) {
          update(key, { status });
          if (startType === 'model.started') for (const response of throughput.values()) if (response.entryKey === key) response.meter.finish();
        }
      }
    }
    if (['turn.completed', 'turn.failed', 'turn.cancelled'].includes(event.type)) { finishTurn(event.turnId, status); flush(); }
  }
  const itemKey = (turnId, iteration, outputIndex) => `${turnId}:response:${iteration}:item:${outputIndex}`;
  function outputItem(turnId, iteration, outputIndex, item, complete = false) {
    const key = itemKey(turnId, iteration, outputIndex);
    if (['function_call', 'custom_tool_call'].includes(item?.type) && TOOLS.has(item.name)) {
      if (typeof item.call_id === 'string') calls.set(`${turnId}:${item.call_id}`, key);
      const input = item.type === 'custom_tool_call' ? item.input : item.arguments;
      update(key, { turnId, kind: 'tool', title: item.name, tool: item.name, status: 'running', inputFormat: item.type === 'custom_tool_call' ? 'patch' : 'json' }, { arguments: typeof input === 'string' ? input : '' });
    } else if (item?.type === 'message') {
      for (const [contentIndex, content] of (Array.isArray(item.content) ? item.content : []).entries()) {
        if (content.type === 'output_text' && typeof content.text === 'string') update(`${key}:text:${contentIndex}`, { turnId, kind: 'message', title: 'Agent response', status: complete ? 'completed' : 'running' }, { text: content.text });
      }
    }
  }
  function providerEvent(turnId, iteration, event) {
    if (closed || !event || !Number.isInteger(event.output_index)) return;
    const key = itemKey(turnId, iteration, event.output_index);
    if (event.type === 'response.output_item.added' || event.type === 'response.output_item.done') outputItem(turnId, iteration, event.output_index, event.item, event.type.endsWith('.done'));
    else if (event.type === 'response.function_call_arguments.delta' && entries.get(key)?.properties.inputFormat === 'json') {
      update(key, {}, { arguments: event.delta }, true);
      throughput.get(`${turnId}:response:${iteration}`)?.meter.append(key, event.delta);
    }
    else if (event.type === 'response.function_call_arguments.done' && entries.get(key)?.properties.inputFormat === 'json') update(key, {}, { arguments: event.arguments });
    else if (event.type === 'response.custom_tool_call_input.delta' && entries.get(key)?.properties.inputFormat === 'patch') {
      update(key, {}, { arguments: event.delta }, true);
      throughput.get(`${turnId}:response:${iteration}`)?.meter.append(key, event.delta);
    }
    else if (event.type === 'response.custom_tool_call_input.done' && entries.get(key)?.properties.inputFormat === 'patch') update(key, {}, { arguments: event.input });
    else if ((event.type === 'response.output_text.delta' || event.type === 'response.output_text.done') && Number.isInteger(event.content_index)) {
      update(`${key}:text:${event.content_index}`, { turnId, kind: 'message', title: 'Agent response', status: event.type.endsWith('.done') ? 'completed' : 'running' }, { text: event.type.endsWith('.done') ? event.text : event.delta }, event.type.endsWith('.delta'));
      if (event.type.endsWith('.delta')) throughput.get(`${turnId}:response:${iteration}`)?.meter.append(`${key}:text:${event.content_index}`, event.delta);
    }
  }
  function providerOutput(turnId, iteration, output) {
    for (const [index, item] of (Array.isArray(output) ? output : []).entries()) outputItem(turnId, iteration, index, item, true);
    flush();
  }
  function toolStarted(turnId, call) {
    if (!TOOLS.has(call.name)) return;
    const key = calls.get(`${turnId}:${call.call_id}`) || `${turnId}:call:${call.call_id}`;
    calls.set(`${turnId}:${call.call_id}`, key);
    update(key, { turnId, kind: 'tool', title: call.name, tool: call.name, status: 'running', inputFormat: call.type === 'custom_tool_call' ? 'patch' : 'json' }, { arguments: (call.type === 'custom_tool_call' ? call.input : call.arguments) || '' });
    flush();
  }
  function toolFinished(turnId, call, result, durationMs) {
    const key = calls.get(`${turnId}:${call.call_id}`);
    if (!key) return;
    update(key, { status: result?.ok === false || result?.error ? 'failed' : 'completed', durationMs }, { result: JSON.stringify(result, null, 2) });
    flush();
  }
  return {
    lifecycle, providerEvent, providerOutput, toolStarted, toolFinished, reset, flush,
    read() { flush(); return [...entries.values()].map(entry => structuredClone(entry.event)).filter(Boolean); },
    subscribe(listener, onClose) {
      if (closed) { onClose?.(); return () => {}; }
      listeners.add(listener); if (onClose) closeListeners.add(onClose);
      return () => { listeners.delete(listener); if (onClose) closeListeners.delete(onClose); };
    },
    close() {
      if (closed) return;
      flush(); closed = true;
      if (timer) clearTimeout(timer);
      for (const listener of closeListeners) { try { listener(); } catch { /* Ignore disconnected clients. */ } }
      listeners.clear(); closeListeners.clear(); entries.clear(); calls.clear(); throughput.clear(); dirty.clear(); bytes = 0;
    },
  };
}
