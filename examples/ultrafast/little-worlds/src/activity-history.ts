import type { ActivityEntry } from './build-activity';
import type { RuntimeEvent, SavedTurn } from './types';

export type ActivityTurnSelection = Pick<SavedTurn, 'id' | 'message' | 'startedAt' | 'status'>;

const tools = new Set(['inspect_space', 'read_file', 'write_file', 'verify_workspace', 'publish_revision', 'apply_change', 'apply_patch']);
const lifecycle = new Set(['turn.started', 'turn.completed', 'turn.failed', 'turn.cancelled', 'message', 'model.started', 'model.completed', 'tool.started', 'tool.completed', 'tool.failed', 'revision.published', 'draft.preview']);
const resultKeys = ['tool', 'file', 'characters', 'sourceCharacters', 'testCharacters', 'revisionId', 'preservedContributions', 'model', 'requestedTier', 'servedTier', 'iteration', 'durationMs', 'ttftMs', 'headersMs', 'outputTokens', 'inputTokens', 'cachedInputTokens', 'reasoningTokens', 'transport', 'transportFallback'];
const safeText = (value: string, limit = 16_000) => value.slice(0, limit)
  .replace(/sk-[A-Za-z0-9_-]+/g, '[redacted]').replace(/\bBearer\s+[^\s"'<>]+/gi, 'Bearer [redacted]');
const record = (value: unknown): value is Record<string, unknown> => !!value && typeof value === 'object' && !Array.isArray(value);

function savedResult(data: RuntimeEvent['data']) {
  if (!data) return undefined;
  const result: Record<string, unknown> = {};
  for (const key of resultKeys) {
    const value = data[key];
    if (typeof value === 'string') result[key] = safeText(value, 1000);
    else if (typeof value === 'boolean' || typeof value === 'number' && Number.isFinite(value)) result[key] = value;
  }
  if (Array.isArray(data.files)) result.files = data.files.filter(value => typeof value === 'string').slice(0, 50).map(value => safeText(value, 256));
  if (Array.isArray(data.checks)) result.checks = data.checks.filter(record).slice(0, 100).map(check => ({
    ...(typeof check.name === 'string' ? { name: safeText(check.name, 1000) } : {}),
    ...(typeof check.ok === 'boolean' ? { ok: check.ok } : {}),
    ...(typeof check.message === 'string' ? { message: safeText(check.message, 2000) } : {}),
  }));
  return Object.keys(result).length ? JSON.stringify(result, null, 2) : undefined;
}

/** Recover saved lifecycle facts only. Generated code and model output are not persisted here. */
export function savedActivityForTurn(turn: ActivityTurnSelection, events: readonly RuntimeEvent[]): { entries: ActivityEntry[]; hasSavedEvents: boolean } {
  const entries: ActivityEntry[] = [];
  for (const event of events) {
    if (event.turnId !== turn.id || !lifecycle.has(event.type)) continue;
    const status: ActivityEntry['status'] = event.type.endsWith('.failed') ? 'failed'
      : event.type.endsWith('.cancelled') ? 'cancelled' : event.type.endsWith('.started') ? 'running' : 'completed';
    const request = event.type === 'turn.started' || event.type === 'message' && event.data?.steering === true;
    const tool = typeof event.data?.tool === 'string' && tools.has(event.data.tool) ? event.data.tool : undefined;
    const result = savedResult(event.data);
    entries.push({
      id: `saved-event:${event.id}`, time: event.time, turnId: turn.id,
      title: safeText(event.title, 240), kind: request ? 'request' : 'event',
      status: request ? 'completed' : status, eventType: event.type,
      ...(tool ? { tool } : {}),
      ...(typeof event.detail === 'string' ? { text: safeText(event.detail) } : {}),
      ...(result ? { result } : {}),
      ...(typeof event.durationMs === 'number' && Number.isFinite(event.durationMs) && event.durationMs >= 0 ? { durationMs: event.durationMs } : {}),
    });
    if (['model.completed', 'tool.completed', 'tool.failed'].includes(event.type)) {
      const startType = event.type.startsWith('model.') ? 'model.started' : 'tool.started';
      for (const entry of entries) {
        if (entry.eventType === startType && entry.status === 'running' && (startType === 'model.started' || entry.tool === tool)) entry.status = status;
      }
    }
  }
  const hasSavedEvents = entries.length > 0;
  if (!entries.some(entry => entry.eventType === 'turn.started')) entries.unshift({
    id: `saved-request:${turn.id}`, turnId: turn.id, time: turn.startedAt,
    title: 'Request', kind: 'request', status: 'completed', text: safeText(turn.message),
  });
  const terminal = [...entries].reverse().find(entry => /^turn\.(completed|failed|cancelled)$/.test(entry.eventType || ''));
  const finalStatus = terminal?.status || (['completed', 'failed', 'cancelled'].includes(turn.status) ? turn.status as ActivityEntry['status'] : undefined);
  if (finalStatus) for (const entry of entries) if (entry.status === 'running') entry.status = finalStatus;
  return { entries, hasSavedEvents };
}
