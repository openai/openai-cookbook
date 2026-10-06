import { readAppStorage, removeAppStorage, writeAppStorage } from './storage';
import type { Actor, RuntimeEvent } from './types';

const key = 'little-worlds:demo-session';
let token = (() => { try { return readAppStorage(sessionStorage, key); } catch { return null; } })();

// HTTP/1 browsers share a small connection pool across every tab on an origin.
// Keep idle tabs out of that pool and let a queued user request briefly borrow
// stream connections. Replays resume by cursor; writes are never retried.
const eventConnections = new Set<{ pause: () => void; resume: () => void }>();
const eventBudgetChannel = 'little-worlds:event-connections';
let eventChannel: BroadcastChannel | undefined;
let yieldingEvents = false;
let eventYieldTimer: ReturnType<typeof setTimeout> | undefined;
const pageHidden = () => typeof document !== 'undefined' && document.hidden === true;

function yieldEventConnections() {
  yieldingEvents = true;
  clearTimeout(eventYieldTimer);
  for (const connection of eventConnections) connection.pause();
  eventYieldTimer = setTimeout(() => {
    yieldingEvents = false;
    eventYieldTimer = undefined;
    for (const connection of eventConnections) connection.resume();
  }, 1000);
}

function subscribeEventBudget() {
  if (eventChannel || typeof window === 'undefined' || typeof BroadcastChannel === 'undefined') return;
  try {
    eventChannel = new BroadcastChannel(eventBudgetChannel);
    eventChannel.onmessage = event => { if (event.data === 'yield-streams') yieldEventConnections(); };
  } catch { /* Local connection yielding still works without cross-tab support. */ }
}

async function prioritizedFetch(path: string, init: RequestInit) {
  const timer = setTimeout(() => {
    yieldEventConnections();
    if (typeof window === 'undefined' || typeof BroadcastChannel === 'undefined') return;
    try {
      const channel = eventChannel || new BroadcastChannel(eventBudgetChannel);
      channel.postMessage('yield-streams');
      if (channel !== eventChannel) channel.close();
    } catch { /* No credentials or app state are sent to other tabs. */ }
  }, 500);
  try { return await fetch(path, init); }
  finally { clearTimeout(timer); }
}

export function setSessionToken(value: string | null) {
  token = value;
  try { if (value) writeAppStorage(sessionStorage, key, value); else removeAppStorage(sessionStorage, key); } catch { /* The session still works in this tab. */ }
}
export function hasSessionToken() { return !!token; }
export function authedFetch(path: string, init: RequestInit = {}) {
  const headers = new Headers(init.headers);
  if (token) headers.set('Authorization', `Bearer ${token}`);
  return prioritizedFetch(path, { ...init, headers });
}
export class ApiError extends Error {
  constructor(message: string, public status: number) { super(message); }
}
async function requestJson<T>(sessionToken: string | null, path: string, body?: unknown): Promise<T> {
  const response = await prioritizedFetch(path, {
    method: body === undefined ? 'GET' : 'POST',
    headers: { ...(sessionToken ? { Authorization: `Bearer ${sessionToken}` } : {}), ...(body === undefined ? {} : { 'Content-Type': 'application/json' }) },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  const data = await response.json();
  if (!response.ok) throw new ApiError(data.error || `Request failed (${response.status})`, response.status);
  return data;
}

export function api<T>(path: string, body?: unknown): Promise<T> {
  return requestJson<T>(token, path, body);
}

// A mounted resource can finish its own requests after navigation. Binding its
// session prevents those requests from acting as a newly selected account.
// The server still rejects the captured credential if that session is revoked.
export function captureSessionApi() {
  const sessionToken = token;
  return function scopedApi<T>(path: string, body?: unknown): Promise<T> {
    return requestJson<T>(sessionToken, path, body);
  };
}

export interface DemoResetResult { ok: true; users: Actor[] }

// The welcome screen can reset the local demo too. Do not attach a session
// credential here: successful reset revokes every existing demo session.
export async function resetDemo(): Promise<DemoResetResult> {
  const response = await prioritizedFetch('/api/demo/reset', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ confirmation: 'reset-demo' }),
  });
  const data = await response.json();
  if (!response.ok) throw new ApiError(data.error || 'Could not reset the demo. Please try again.', response.status);
  return data;
}

// Fetch keeps the per-tab credential out of URLs, event payloads, and logs.
// Every reconnection uses the ledger cursor, so a page can resume a running turn.
export function watchEvents(path: string, onEvents: (events: RuntimeEvent[]) => void, onConnection: (connected: boolean) => void, onExpired: () => void) {
  const sessionToken = token;
  let stopped = false;
  let controller: AbortController | undefined;
  let connected = false;
  let timer: ReturnType<typeof setTimeout> | undefined;
  let lastId = '';
  let failures = 0;
  const blocked = () => stopped || pageHidden() || yieldingEvents;
  const connection = (value: boolean) => { connected = value; onConnection(value); };
  const pause = () => {
    clearTimeout(timer); timer = undefined;
    const current = controller;
    controller = undefined;
    current?.abort();
    if (connected) connection(false);
  };
  async function connect() {
    if (blocked() || controller) return;
    const attempt = new AbortController();
    controller = attempt;
    try {
      const response = await fetch(path, { signal: attempt.signal, headers: {
        Authorization: `Bearer ${sessionToken || ''}`,
        ...(lastId ? { 'Last-Event-ID': lastId } : {}),
      } });
      if (attempt.signal.aborted || controller !== attempt) return;
      if (response.status === 401) { stopped = true; onExpired(); return; }
      if (!response.ok || !response.body) throw new Error('Event stream unavailable');
      connection(true); failures = 0;
      const reader = response.body.getReader();
      const decoder = new TextDecoder();
      let buffer = '';
      let eventId = '';
      let data: string[] = [];
      while (!attempt.signal.aborted) {
        const part = await reader.read();
        if (attempt.signal.aborted || controller !== attempt) return;
        if (part.done) break;
        buffer += decoder.decode(part.value, { stream: true });
        const events: RuntimeEvent[] = [];
        let newline: number;
        while ((newline = buffer.indexOf('\n')) !== -1) {
          const line = buffer.slice(0, newline).replace(/\r$/, '');
          buffer = buffer.slice(newline + 1);
          if (line === '') {
            if (data.length) {
              try { events.push(JSON.parse(data.join('\n'))); if (eventId) lastId = eventId; } catch { /* Ignore malformed transport data. */ }
            }
            eventId = ''; data = [];
          } else if (line.startsWith('id:')) eventId = line.slice(3).trim();
          else if (line.startsWith('data:')) data.push(line.slice(5).trimStart());
        }
        // Replayed ledgers can contain hundreds of events in one chunk. Merge
        // and invalidate once, rather than rendering/fetching for each record.
        if (events.length) onEvents(events);
      }
    } catch { /* Reconnect below unless the view was closed. */ }
    if (controller !== attempt) return;
    controller = undefined;
    if (!blocked()) {
      connection(false);
      timer = setTimeout(() => void connect(), Math.min(5000, 750 * ++failures));
    }
  }
  const resume = () => { if (!blocked()) { clearTimeout(timer); timer = undefined; void connect(); } };
  const budget = { pause, resume };
  const visibility = () => { if (pageHidden()) pause(); else resume(); };
  eventConnections.add(budget);
  subscribeEventBudget();
  if (typeof document !== 'undefined') document.addEventListener('visibilitychange', visibility);
  void connect();
  return () => {
    stopped = true;
    pause();
    eventConnections.delete(budget);
    if (typeof document !== 'undefined') document.removeEventListener('visibilitychange', visibility);
    if (!eventConnections.size) { eventChannel?.close(); eventChannel = undefined; }
  };
}
