import { authedFetch } from './api';

export type SpaceServiceName = 'health-chat' | 'finance-news' | 'space-agent';
export type SpaceServiceOperation = 'submit' | 'load' | 'refresh' | 'clear' | 'cancel';
export type SpaceServiceRequest = {
  service: SpaceServiceName;
  operation?: SpaceServiceOperation;
  input?: Record<string, unknown>;
};
export type SpaceServiceMessage = { role: 'user' | 'assistant'; content: string };
export type SpaceServiceSource = { id: string; title: string; url: string; checkedAt?: string };
export type SpaceServiceItem = { id: string; title: string; summary: string; date: string; publishedAt: string; url: string; source: string };
export type SpaceServiceEvent = {
  status: 'loading' | 'ready' | 'error';
  text?: string;
  messages?: SpaceServiceMessage[];
  sources?: SpaceServiceSource[];
  items?: SpaceServiceItem[];
  note?: string;
  error?: string;
  urgent?: boolean;
  stopped?: boolean;
};
export type SpaceServiceEmitter = (event: SpaceServiceEvent) => void;
export type SpaceServiceController = {
  request(request: SpaceServiceRequest, emit: SpaceServiceEmitter): Promise<void>;
  cancel(service?: SpaceServiceName): void;
  dispose(): void;
};
type ActiveRequest = { controller: AbortController; emit: SpaceServiceEmitter };
type ChatServiceName = Exclude<SpaceServiceName, 'finance-news'>;

const sourceHosts = new Set(['www.nhlbi.nih.gov', 'www.cdc.gov', 'medlineplus.gov', 'www.nimh.nih.gov', 'www.nhs.uk']);
const newsHosts = new Set(['www.federalreserve.gov']);
const names = new Set<SpaceServiceName>(['health-chat', 'finance-news', 'space-agent']);
const operations = new Set<SpaceServiceOperation>(['submit', 'load', 'refresh', 'clear', 'cancel']);
function record(value: unknown): value is Record<string, unknown> { return !!value && typeof value === 'object' && !Array.isArray(value); }
function safeUrl(value: unknown, hosts: Set<string>): value is string {
  if (typeof value !== 'string' || value.length > 1800) return false;
  try { const url = new URL(value); return url.protocol === 'https:' && hosts.has(url.hostname) && !url.username && !url.password; } catch { return false; }
}
function textValue(value: unknown, limit: number) { return typeof value === 'string' ? value.slice(0, limit) : ''; }
function dateLabel(value: string) {
  const date = new Date(value);
  return Number.isFinite(date.getTime()) ? new Intl.DateTimeFormat('en', { month: 'short', day: 'numeric', year: 'numeric', timeZone: 'UTC' }).format(date) : '';
}
function readSources(value: unknown): SpaceServiceSource[] {
  if (!Array.isArray(value)) return [];
  return value.filter(source => record(source) && typeof source.title === 'string' && safeUrl(source.url, sourceHosts)).slice(0, 8).map(source => ({
    id: textValue(source.id, 100) || source.url,
    title: textValue(source.title, 200), url: source.url,
    ...(typeof source.checkedAt === 'string' && dateLabel(source.checkedAt) ? { checkedAt: source.checkedAt } : {}),
  }));
}
function readNews(value: unknown): SpaceServiceItem[] {
  if (!Array.isArray(value)) return [];
  return value.filter(item => record(item) && typeof item.title === 'string' && safeUrl(item.url, newsHosts) && typeof item.publishedAt === 'string' && dateLabel(item.publishedAt)).slice(0, 3).map(item => ({
    id: textValue(item.id, 1800) || item.url, title: textValue(item.title, 300),
    summary: textValue(item.summary, 600), date: dateLabel(item.publishedAt), publishedAt: item.publishedAt,
    url: item.url, source: 'Federal Reserve',
  }));
}
function historyFor(messages: SpaceServiceMessage[], nextQuestion: string) {
  const history = messages.slice(-10);
  // Keep complete exchanges and leave the new user message inside the server limit.
  while (history.length && history.reduce((size, message) => size + message.content.length, nextQuestion.length) > 16_000) history.splice(0, 2);
  return history;
}
function emptyState(service: SpaceServiceName): SpaceServiceEvent {
  return service === 'finance-news' ? { status: 'ready', items: [], note: '' } : { status: 'ready', text: '', messages: [], sources: [], note: '' };
}

// A disconnected transport must not leave the UI busy forever, even when its
// pending read does not reject on abort. Attach both handlers to consume late
// settlement without letting it update a subsequent request.
function untilAborted<T>(pending: Promise<T>, signal: AbortSignal): Promise<T> {
  return new Promise((resolve, reject) => {
    const abort = () => reject(signal.reason);
    const clean = () => signal.removeEventListener('abort', abort);
    signal.addEventListener('abort', abort, { once: true });
    pending.then(value => { clean(); resolve(value); }, error => { clean(); reject(error); });
    if (signal.aborted) { clean(); abort(); }
  });
}

/**
 * One ephemeral service session for one signed-in person's view of one space.
 * The host must validate the published module's capabilities before dispatch.
 * Layout and presentation belong entirely to that module; this controller emits data.
 */
export function createSpaceServices({ spaceId, revisionId, onExpired, fetchImpl = authedFetch, requestTimeoutMs = 125_000 }: {
  spaceId: string;
  revisionId: number;
  onExpired?: () => void;
  fetchImpl?: (path: string, init?: RequestInit) => Promise<Response>;
  /** Transport watchdog, just beyond the server's two-minute request limit. */
  requestTimeoutMs?: number;
}): SpaceServiceController {
  if (typeof spaceId !== 'string' || !spaceId.trim() || spaceId.length > 160 || !Number.isSafeInteger(revisionId) || revisionId < 1) throw new Error('A current space revision is required for services.');
  if (!Number.isFinite(requestTimeoutMs) || requestTimeoutMs <= 0) throw new Error('A positive service request timeout is required.');
  const servicePath = `/api/spaces/${encodeURIComponent(spaceId)}/services`;
  let disposed = false;
  const histories: Record<ChatServiceName, SpaceServiceMessage[]> = { 'health-chat': [], 'space-agent': [] };
  const active = new Map<SpaceServiceName, ActiveRequest>();
  const snapshots: Record<SpaceServiceName, SpaceServiceEvent> = {
    'health-chat': emptyState('health-chat'),
    'finance-news': emptyState('finance-news'),
    'space-agent': emptyState('space-agent'),
  };
  const emitCopy = (emit: SpaceServiceEmitter, snapshot: SpaceServiceEvent) => { if (!disposed) emit(structuredClone(snapshot)); };
  function publish(service: SpaceServiceName, snapshot: SpaceServiceEvent, emit: SpaceServiceEmitter) {
    snapshots[service] = snapshot;
    emitCopy(emit, snapshot);
  }
  function stop(service: SpaceServiceName, emit?: SpaceServiceEmitter) {
    const running = active.get(service);
    if (running) { active.delete(service); running.controller.abort(); }
    const snapshot = { ...snapshots[service], status: 'ready' as const, ...(running ? { stopped: true, note: '' } : {}), error: undefined };
    snapshots[service] = snapshot;
    const listener = emit || running?.emit;
    if (listener) emitCopy(listener, snapshot);
  }
  async function assertResponse(response: Response, service: SpaceServiceName) {
    if (response.status === 401) { onExpired?.(); throw new Error('Please sign in again to continue.'); }
    if (response.ok) return;
    if ([400, 403, 409].includes(response.status)) {
      const body: unknown = await response.json().catch(() => null);
      if (record(body) && typeof body.error === 'string') throw new Error(body.error.slice(0, 300));
    }
    throw new Error(service === 'health-chat' ? 'The health guide is unavailable. Please try again.' : service === 'space-agent' ? 'The space’s assistant is unavailable. Please try again.' : 'The reading list is unavailable. Please try again.');
  }

  return {
    async request(request, emit) {
      if (disposed) return;
      if (!record(request) || !names.has(request.service) || (request.operation !== undefined && !operations.has(request.operation))) {
        emitCopy(emit, { status: 'error', error: 'This service request is not supported.' }); return;
      }
      const service = request.service;
      const chat = service !== 'finance-news';
      const operation = request.operation || (chat ? 'submit' : 'load');
      if (operation === 'cancel') { stop(service, emit); return; }
      if (operation === 'clear') {
        const running = active.get(service);
        if (running) { active.delete(service); running.controller.abort(); }
        if (chat) histories[service] = [];
        publish(service, emptyState(service), emit);
        return;
      }
      if (chat && operation === 'load') { emitCopy(emit, snapshots[service]); return; }
      if ((chat && operation !== 'submit') || (service === 'finance-news' && operation === 'submit')) {
        emitCopy(emit, { ...snapshots[service], status: 'error', error: 'This operation is not supported by this service.' }); return;
      }
      if (active.has(service)) {
        emitCopy(emit, { ...snapshots[service], status: 'error', error: 'This request is already running.' }); return;
      }
      const message = record(request.input) && typeof request.input.message === 'string' ? request.input.message.trim() : '';
      if (chat && (!message || message.length > 1200 || message.includes('\0'))) {
        emitCopy(emit, { ...snapshots[service], status: 'error', error: `Enter a ${service === 'space-agent' ? 'message' : 'question'} of 1–1,200 characters.` }); return;
      }
      const running: ActiveRequest = { controller: new AbortController(), emit };
      active.set(service, running);
      const current = () => !disposed && active.get(service) === running;
      const update = (snapshot: SpaceServiceEvent) => { if (current()) publish(service, snapshot, emit); };
      const timeout = setTimeout(() => running.controller.abort(new Error(service === 'space-agent'
        ? 'The assistant took too long to finish. Any completed changes remain saved. Please try again.'
        : 'This request took too long to finish. Please try again.')), requestTimeoutMs);
      const wait = <T,>(pending: Promise<T>) => untilAborted(pending, running.controller.signal);
      try {
        if (service === 'finance-news') {
          update({ ...snapshots[service], status: 'loading', error: undefined, stopped: false });
          const response = await wait(fetchImpl(`${servicePath}/finance-news`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ revisionId }), signal: running.controller.signal }));
          if (!current()) return;
          await wait(assertResponse(response, service));
          if (!current()) return;
          const feed: unknown = await wait(response.json());
          if (!record(feed)) throw new Error('The reading list returned an unreadable response.');
          const items = readNews(feed.items);
          if (!items.length) throw new Error('The reading list has no verified source links.');
          const checked = typeof feed.refreshedAt === 'string' ? dateLabel(feed.refreshedAt) : '';
          const label = feed.mode === 'feed' ? 'Feed checked' : 'Saved reading list';
          update({ status: 'ready', items, note: `${label}${checked ? ` · ${checked}` : ''}. For context, not live market data or investment advice.` });
          return;
        }

        const context = historyFor(histories[service], message);
        const input: SpaceServiceMessage[] = [...context, { role: 'user', content: message }];
        let answer = '';
        let completed = false;
        let sources: SpaceServiceSource[] = [];
        let urgent = false;
        let note = '';
        const guide = service === 'space-agent' ? 'space’s assistant' : 'health guide';
        const result = (status: SpaceServiceEvent['status']): SpaceServiceEvent => ({
          status, text: answer, messages: [...input, ...(answer ? [{ role: 'assistant' as const, content: answer }] : [])], sources, urgent, note,
        });
        update(result('loading'));
        const response = await wait(fetchImpl(`${servicePath}/${service}`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ revisionId, messages: input }), signal: running.controller.signal }));
        if (!current()) return;
        await wait(assertResponse(response, service));
        if (!current()) return;
        if (!response.body) throw new Error(`The ${guide}’s connection could not start.`);
        const reader = response.body.getReader();
        const cancelReader = () => { void reader.cancel().catch(() => {}); };
        running.controller.signal.addEventListener('abort', cancelReader, { once: true });
        const decoder = new TextDecoder();
        let buffer = '';
        let received = 0;
        const consume = (block: string) => {
          const raw = block.split('\n').filter(line => line.startsWith('data:')).map(line => line.slice(5).trimStart()).join('\n');
          if (!raw || raw === '[DONE]') return;
          let event: unknown;
          try { event = JSON.parse(raw); } catch { throw new Error(`The ${guide} returned an unreadable answer.`); }
          if (!record(event)) return;
          if (completed) return;
          if (event.type === 'error') throw new Error(service === 'space-agent' && typeof event.message === 'string' && event.message.trim() ? event.message.slice(0, 300) : `The ${guide} could not finish this answer. Please try again.`);
          if (event.type === 'delta' && typeof event.text === 'string') {
            if (answer.length + event.text.length > 6000) throw new Error(`The ${guide}’s answer was too long. Please ask a shorter question.`);
            answer += event.text;
            update(result('loading'));
          }
          if (service === 'space-agent' && event.type === 'action') {
            // Actions are executed by the scoped server service. Stream payloads
            // are display-only and never enter the public action dispatch path.
            note = 'Updating the canvas…';
            update(result('loading'));
          }
          if (event.type === 'complete') {
            const updated = service === 'space-agent' && typeof event.actionsApplied === 'number' && Number.isSafeInteger(event.actionsApplied) && event.actionsApplied > 0;
            if (!answer.trim() && !updated) throw new Error(`The ${guide} did not return an answer. Please try again.`);
            completed = true;
            sources = service === 'health-chat' ? readSources(event.sources) : [];
            urgent = service === 'health-chat' && event.urgent === true;
            note = updated ? 'Updated the shared space.' : '';
            if (current() && answer.trim()) histories[service] = [...input, { role: 'assistant' as const, content: answer }].slice(-10);
            update(result('ready'));
          }
        };
        try {
          while (current() && !completed) {
            const chunk = await wait(reader.read());
            if (chunk.done || !current()) break;
            received += chunk.value.byteLength;
            buffer = (buffer + decoder.decode(chunk.value, { stream: true })).replace(/\r\n/g, '\n');
            if (buffer.length > 30_000 || received > 500_000) throw new Error(`The ${guide} returned too much data.`);
            let boundary;
            while (!completed && (boundary = buffer.indexOf('\n\n')) !== -1) { consume(buffer.slice(0, boundary)); buffer = buffer.slice(boundary + 2); }
          }
          if (!current()) return;
          buffer += decoder.decode();
          if (!completed && buffer.trim()) consume(buffer);
          if (!completed) throw new Error('The answer ended before it was complete. Please try again.');
        } finally {
          running.controller.signal.removeEventListener('abort', cancelReader);
          // Completion/error, not socket closure, releases the submit button.
          // Some broken connections never settle the cancellation promise.
          void reader.cancel().catch(() => {});
        }
      } catch (error) {
        if (current()) update({ ...snapshots[service], status: 'error', note: '', error: error instanceof Error ? error.message : 'This request could not be completed.' });
      } finally {
        clearTimeout(timeout);
        if (current()) active.delete(service);
      }
    },
    cancel(service) {
      if (disposed) return;
      if (service) { if (names.has(service)) stop(service); }
      else for (const name of [...active.keys()]) stop(name);
    },
    dispose() {
      disposed = true;
      for (const running of active.values()) running.controller.abort();
      active.clear(); histories['health-chat'] = []; histories['space-agent'] = [];
      for (const name of names) snapshots[name] = emptyState(name);
    },
  };
}
