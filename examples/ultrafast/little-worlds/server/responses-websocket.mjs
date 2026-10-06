import WebSocket from 'ws';
import { HttpsProxyAgent } from 'https-proxy-agent';

// Only this error is safe to retry over HTTP: no response.create was sent.
export class WebSocketConnectionError extends Error {}

const abortError = signal => signal?.reason || new DOMException('The operation was aborted.', 'AbortError');
const safeMessage = value => String(value || 'The model request failed.').replace(/sk-[A-Za-z0-9_-]+/g, '[redacted]').slice(0, 700);

// One connection belongs to one adapter/space. Every call sends full input, so
// reconnects never rely on connection-local conversation state.
export function createResponsesWebSocket({
  apiKey, tier, WebSocketImpl = WebSocket,
  proxyUrl = process.env.HTTPS_PROXY || process.env.https_proxy || process.env.HTTP_PROXY || process.env.http_proxy,
  handshakeTimeoutMs = 5000, responseTimeoutMs = 120_000, idleTimeoutMs = 30_000,
} = {}) {
  let socket, busy = false, closed = false, idleTimer, cancelActive;

  function discard(target) {
    if (socket === target) socket = undefined;
    clearTimeout(idleTimer);
    // ws may emit an asynchronous error when terminating during its handshake.
    target?.terminate();
  }

  async function connect(signal) {
    if (signal?.aborted) throw abortError(signal);
    if (socket?.readyState === WebSocket.OPEN) return socket;
    const stale = socket;
    if (stale) discard(stale);
    let target;
    try {
      target = new WebSocketImpl('wss://api.openai.com/v1/responses', {
        headers: { Authorization: `Bearer ${apiKey}` },
        ...(proxyUrl ? { agent: new HttpsProxyAgent(proxyUrl) } : {}),
        handshakeTimeout: handshakeTimeoutMs,
        maxPayload: 2_000_000,
      });
    } catch {
      throw new WebSocketConnectionError('Could not open the model connection.');
    }
    socket = target;
    target.on('error', () => {});
    target.on('close', () => { if (socket === target) socket = undefined; });
    await new Promise((resolve, reject) => {
      let settled = false;
      const timer = setTimeout(() => fail(new WebSocketConnectionError('The model connection timed out.')), handshakeTimeoutMs);
      const cleanup = () => {
        clearTimeout(timer);
        target.off('open', opened); target.off('error', failed); target.off('close', ended); target.off('unexpected-response', rejected);
        signal?.removeEventListener('abort', aborted);
        cancelActive = undefined;
      };
      const fail = error => {
        if (settled) return;
        settled = true; cleanup(); discard(target); reject(error);
      };
      const opened = () => { if (!settled) { settled = true; cleanup(); resolve(); } };
      const failed = () => fail(new WebSocketConnectionError('Could not open the model connection.'));
      const ended = () => fail(new WebSocketConnectionError('The model connection closed before opening.'));
      const rejected = (_request, response) => {
        response.resume?.();
        fail(new WebSocketConnectionError(`The model connection was unavailable (${response.statusCode}).`));
      };
      const aborted = () => fail(abortError(signal));
      cancelActive = () => fail(new Error('The model adapter was closed.'));
      target.once('open', opened); target.once('error', failed); target.once('close', ended); target.once('unexpected-response', rejected);
      signal?.addEventListener('abort', aborted, { once: true });
      if (signal?.aborted) aborted();
    });
    return target;
  }

  return {
    close() {
      closed = true;
      cancelActive?.();
      discard(socket);
    },
    async respond({ body, signal, onEvent, timeoutMs = responseTimeoutMs }) {
      if (closed) throw new Error('The model adapter was closed.');
      if (busy) throw new Error('A model request is already running for this space.');
      busy = true;
      clearTimeout(idleTimer);
      const started = performance.now();
      const warm = socket?.readyState === WebSocket.OPEN;
      try {
        const target = await connect(signal);
        if (closed) throw new Error('The model adapter was closed.');
        if (signal?.aborted) throw abortError(signal);
        if (target.readyState !== WebSocket.OPEN) throw new WebSocketConnectionError('The model connection closed before sending.');
        const headersMs = Math.round(performance.now() - started);
        return await new Promise((resolve, reject) => {
          let settled = false, firstOutputAt, queue = Promise.resolve();
          const timer = setTimeout(() => fail(new Error('The model request timed out.')), timeoutMs);
          const cleanup = () => {
            clearTimeout(timer);
            target.off('message', received); target.off('error', failed); target.off('close', ended);
            signal?.removeEventListener('abort', aborted);
            cancelActive = undefined;
          };
          const fail = error => {
            if (settled) return;
            settled = true; cleanup(); discard(target); reject(error);
          };
          const finished = response => {
            if (settled) return;
            settled = true; cleanup();
            idleTimer = setTimeout(() => { if (socket === target && !busy) discard(target); }, idleTimeoutMs);
            idleTimer.unref?.();
            resolve({ response, metrics: {
              durationMs: Math.round(performance.now() - started), headersMs,
              ttftMs: firstOutputAt === undefined ? null : Math.round(firstOutputAt - started),
              transport: 'websocket', connectionReused: Boolean(warm),
            } });
          };
          const received = (raw, isBinary) => {
            // Process in arrival order, including asynchronous progress callbacks.
            // A completed frame cannot overtake the last streamed patch preview.
            queue = queue.then(async () => {
              if (settled) return;
              if (isBinary || raw.length > 2_000_000) throw new Error('The model returned an invalid stream frame.');
              let event;
              try { event = JSON.parse(raw.toString()); } catch { throw new Error('OpenAI returned an unreadable stream event.'); }
              if (/^response\.(output_text|function_call_arguments|custom_tool_call_input)\.delta$/.test(event.type) && firstOutputAt === undefined) firstOutputAt = performance.now();
              if (event.type === 'error' || event.type === 'response.failed') throw new Error(safeMessage(event.error?.message || event.message || event.response?.error?.message));
              if (event.type === 'response.incomplete') throw new Error('The model reached its output limit before finishing. Try a smaller change.');
              if (event.type === 'response.completed' && event.response?.status !== 'completed') throw new Error('The model returned an incomplete response.');
              await onEvent?.(event);
              if (event.type === 'response.completed') finished(event.response);
            }).catch(fail);
          };
          const failed = () => fail(new Error('The model connection failed. Your published space is unchanged.'));
          // A peer may close directly after a completed frame. Drain callbacks
          // first, so a valid completion is not mistaken for a truncated stream.
          const ended = () => { queue = queue.then(() => { if (!settled) fail(new Error('The connection ended before the model finished. Your published space is unchanged.')); }).catch(fail); };
          const aborted = () => fail(abortError(signal));
          cancelActive = () => fail(new Error('The model adapter was closed.'));
          target.on('message', received); target.once('error', failed); target.once('close', ended);
          signal?.addEventListener('abort', aborted, { once: true });
          if (signal?.aborted) { aborted(); return; }
          // From this point onward, never retry this request automatically. A
          // transport error cannot prove that the server did not receive it.
          try {
            const { stream: _stream, ...payload } = body;
            target.send(JSON.stringify({ type: 'response.create', ...payload }), error => { if (error) failed(); });
          } catch { failed(); }
        });
      } catch (error) {
        // Also cover cancellation in the small gap between opening the socket
        // and attaching the response listeners.
        discard(socket);
        throw error;
      } finally { busy = false; }
    },
  };
}
