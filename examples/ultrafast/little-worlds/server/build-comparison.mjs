import { randomUUID } from 'node:crypto';
import { publicError } from './responses.mjs';
import { validBuildOutputTokens } from './build-progress-estimate.mjs';

const terminal = new Set(['completed', 'failed', 'cancelled']);
const MAX_HTML = 180_000;

// Preserve the sanitized standard feed independently of its temporary harness.
// Early subscribers can connect before that harness finishes preparing.
export function createComparisonActivity() {
  const entries = new Map();
  const listeners = new Set();
  const closeListeners = new Set();
  let bytes = 0;
  let closed = false;
  return {
    accept(event) {
      if (closed) return;
      if (event.type === 'activity.reset') { entries.clear(); bytes = 0; }
      else if (event.type === 'activity.entry' && typeof event.data?.entryId === 'string') {
        const key = event.data.entryId;
        const size = Buffer.byteLength(JSON.stringify(event));
        bytes += size - (entries.get(key)?.size || 0);
        entries.set(key, { event: structuredClone(event), size });
        while (entries.size > 120 || bytes > 3 * 1024 * 1024 && entries.size > 1) {
          const first = entries.keys().next().value;
          bytes -= entries.get(first).size; entries.delete(first);
        }
      } else return;
      for (const listener of listeners) { try { listener(structuredClone(event)); } catch { /* Disconnected viewer. */ } }
    },
    read: () => [...entries.values()].map(({ event }) => structuredClone(event)),
    subscribe(listener, onClose) {
      if (closed) { onClose?.(); return () => {}; }
      listeners.add(listener); if (onClose) closeListeners.add(onClose);
      return () => { listeners.delete(listener); if (onClose) closeListeners.delete(onClose); };
    },
    close() {
      closed = true;
      for (const listener of closeListeners) { try { listener(); } catch { /* Disconnected viewer. */ } }
      listeners.clear(); closeListeners.clear(); entries.clear(); bytes = 0;
    },
  };
}

// One transient comparison per space. This projection contains only owner-safe
// display data, never model inputs, credentials, or the companion's saved store.
export function createBuildComparison({ intervalMs = 90 } = {}) {
  const listeners = new Set();
  const closeListeners = new Set();
  const tokens = { ultrafast: new Map(), standard: new Map() };
  let current = null;
  let timer;
  let sequence = 0;
  let closed = false;
  let previewsDirty = true;
  const read = () => current ? structuredClone(current) : null;
  const event = (includePreviews = true) => {
    const state = read();
    if (!includePreviews && state) { delete state.ultrafast.html; delete state.standard.html; }
    return { id: String(++sequence), type: 'comparison.state', time: new Date().toISOString(),
      data: { comparison: state, ...(!includePreviews ? { retainPreviews: true } : {}) } };
  };
  function flush() {
    clearTimeout(timer); timer = undefined;
    if (closed) return;
    const next = event(previewsDirty);
    previewsDirty = false;
    for (const listener of listeners) { try { listener(next); } catch { /* Observers cannot interrupt builds. */ } }
  }
  function changed(immediate = false) {
    if (immediate) { flush(); return; }
    if (!timer && !closed) { timer = setTimeout(flush, intervalMs); timer.unref?.(); }
  }
  function laneFor(id, lane, turnId) {
    if (!current || current.id !== id || !current[lane] || current[lane].turnId !== turnId) return null;
    return current[lane];
  }
  return {
    read,
    snapshot: event,
    begin({ model, reasoningEffort = 'low', primaryTurnId, standardTurnId }) {
      tokens.ultrafast.clear(); tokens.standard.clear();
      const startedAt = new Date().toISOString();
      const lane = (turnId, requestedTier) => ({ turnId, requestedTier, status: 'preparing', startedAt, outputTokens: 0 });
      current = { id: randomUUID(), primaryTurnId, model, reasoningEffort, startedAt, finished: false,
        progress: { status: 'pending' },
        ultrafast: lane(primaryTurnId, 'ultrafast'), standard: lane(standardTurnId, 'default') };
      previewsDirty = true;
      changed(true);
      return read();
    },
    progress(id, estimate) {
      if (closed || !current || current.id !== id || current.finished || current.progress.status !== 'pending') return;
      if (terminal.has(current.ultrafast.status) && terminal.has(current.standard.status)) return;
      if (!['ready', 'fallback'].includes(estimate?.status) || !validBuildOutputTokens(estimate.expectedOutputTokens)) return;
      current.progress = { status: estimate.status, expectedOutputTokens: estimate.expectedOutputTokens };
      changed(true);
    },
    lifecycle(id, lane, incoming) {
      const next = laneFor(id, lane, incoming.turnId);
      if (!next) return;
      if (incoming.type === 'turn.started' || incoming.type === 'model.started') {
        // A delayed start event cannot reopen a finished turn. Final output
        // telemetry can still arrive separately and improve its token count.
        if (terminal.has(next.status)) return;
        next.status = 'running';
      }
      else if (incoming.type === 'model.completed') {
        const tier = incoming.data?.servedTier;
        if (typeof tier === 'string') next.servedTier = tier.slice(0, 80);
      } else if (incoming.type === 'draft.preview') {
        const html = incoming.data?.html;
        if (typeof html === 'string' && html.length <= MAX_HTML && !terminal.has(next.status) && next.html !== html) {
          next.html = html; previewsDirty = true;
        }
      } else if (/^turn\.(completed|failed|cancelled)$/.test(incoming.type)) {
        next.status = incoming.type.slice(5);
        next.endedAt = incoming.time || new Date().toISOString();
        if (next.status !== 'completed') next.error = publicError(incoming.detail || incoming.title);
        // Inert drafts from a failed run must never look like a finished result.
        if (next.status !== 'completed') { delete next.html; previewsDirty = true; }
      } else return;
      changed(terminal.has(next.status));
    },
    activity(id, lane, incoming) {
      const next = laneFor(id, lane, incoming.turnId);
      const speed = incoming.data?.throughput;
      if (!next || incoming.type !== 'activity.entry' || !speed || !Number.isFinite(speed.tokens)) return;
      const entryId = incoming.data.entryId;
      tokens[lane].set(entryId, Math.max(tokens[lane].get(entryId) || 0, speed.tokens, 0));
      const total = [...tokens[lane].values()].reduce((sum, count) => sum + count, 0);
      if (total === next.outputTokens) return;
      next.outputTokens = total;
      changed();
    },
    html(id, lane, turnId, html, { initial = false } = {}) {
      const next = laneFor(id, lane, turnId);
      if (!next || typeof html !== 'string' || html.length > MAX_HTML || initial && next.html !== undefined) return;
      if (next.status === 'failed' || next.status === 'cancelled') return;
      if (next.html === html) return;
      next.html = html; previewsDirty = true; changed();
    },
    fail(id, lane, turnId, error, cancelled = false) {
      const next = laneFor(id, lane, turnId);
      if (!next || terminal.has(next.status)) return;
      next.status = cancelled ? 'cancelled' : 'failed';
      next.error = publicError(error);
      next.endedAt = new Date().toISOString();
      delete next.html;
      previewsDirty = true;
      changed(true);
    },
    finish(id) {
      if (!current || current.id !== id) return;
      current.finished = true; changed(true);
    },
    reset() { current = null; tokens.ultrafast.clear(); tokens.standard.clear(); previewsDirty = true; changed(true); },
    subscribe(listener, onClose) {
      if (closed) { onClose?.(); return () => {}; }
      listeners.add(listener); if (onClose) closeListeners.add(onClose);
      return () => { listeners.delete(listener); if (onClose) closeListeners.delete(onClose); };
    },
    close() {
      closed = true; clearTimeout(timer);
      for (const listener of closeListeners) { try { listener(); } catch { /* Disconnected observer. */ } }
      listeners.clear(); closeListeners.clear(); current = null;
    },
  };
}
