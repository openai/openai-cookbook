import { createResponsesWebSocket, WebSocketConnectionError } from './responses-websocket.mjs';
import { appSetting } from './environment.mjs';

export async function loadApiKey() {
  return process.env.OPENAI_API_KEY?.trim() || '';
}

export function publicError(error) {
  return String(error?.message || error || 'Something went wrong.').replace(/sk-[A-Za-z0-9_-]+/g, '[redacted]').slice(0, 700);
}

// Adapter seam: the harness consumes completed Responses items and progress events.
// A future hosted Agents adapter can keep the application state/publish tools intact.
export function createResponsesAdapter({
  apiKey, model = appSetting('MODEL', 'gpt-6-astra'), tier = appSetting('TIER', 'ultrafast'), fetchImpl,
  transport = fetchImpl ? 'http' : appSetting('TRANSPORT', 'auto'),
  WebSocketImpl, websocketOptions = {}, maxOutputTokens = 6000,
} = {}) {
  if (!['auto', 'http', 'websocket'].includes(transport)) throw new Error('LITTLE_WORLDS_TRANSPORT must be auto, http, or websocket.');
  if (!Number.isInteger(maxOutputTokens) || maxOutputTokens < 256 || maxOutputTokens > 32000) throw new Error('maxOutputTokens must be an integer from 256 to 32000.');
  const request = fetchImpl || fetch;
  const reasoningEffort = 'low';
  const lifecycle = new AbortController();
  let websocket, websocketKey, websocketBusy = false, websocketRetryAt = 0;
  const usageMetrics = response => ({
    outputTokens: response.usage?.output_tokens || 0, inputTokens: response.usage?.input_tokens || 0,
    cachedInputTokens: response.usage?.input_tokens_details?.cached_tokens ?? null,
    reasoningTokens: response.usage?.output_tokens_details?.reasoning_tokens ?? null,
    servedTier: response.service_tier || 'unknown',
  });
  return {
    model, tier, reasoningEffort, transport, keyAvailable: Boolean(apiKey),
    close() {
      lifecycle.abort(new Error('The model adapter was closed.'));
      websocket?.close();
    },
    resetConnection() {
      lifecycle.signal.throwIfAborted();
      if (websocketBusy) throw new Error('Wait for the active model request before resetting its connection.');
      websocket?.close();
      websocket = undefined; websocketKey = undefined; websocketRetryAt = 0;
    },
    async respond({ input, instructions, tools, signal, onEvent, cacheKey, tier: requestTier = tier, timeoutMs = 120_000 }) {
      if (!apiKey) throw new Error('No API key is configured. Add OPENAI_API_KEY to the server environment or this example\'s .env file.');
      lifecycle.signal.throwIfAborted();
      signal?.throwIfAborted();
      const started = performance.now();
      if (!Number.isInteger(timeoutMs) || timeoutMs < 1 || timeoutMs > 300_000) throw new Error('Model request timeout must be between 1 and 300,000 ms.');
      const requestSignal = AbortSignal.any([lifecycle.signal, ...(signal ? [signal] : []), AbortSignal.timeout(timeoutMs)]);
      const body = { model, service_tier: requestTier, store: false, stream: true, include: ['reasoning.encrypted_content'], reasoning: { effort: reasoningEffort }, text: { verbosity: 'low' }, max_output_tokens: maxOutputTokens, input, instructions, tools, parallel_tool_calls: false, ...(cacheKey ? { prompt_cache_key: cacheKey } : {}) };
      let transportFallback = false;
      // Shared services (such as health chat) have no stable space affinity and
      // can serve concurrent viewers. Keep those independent requests on HTTP.
      const useWebSocket = transport === 'websocket' || (transport === 'auto' && cacheKey && Date.now() >= websocketRetryAt);
      if (useWebSocket) {
        if (websocketBusy) throw new Error('A model request is already running for this space.');
        const connectionKey = JSON.stringify([cacheKey, requestTier]);
        if (!websocket || websocketKey !== connectionKey) {
          websocket?.close();
          websocket = createResponsesWebSocket({ ...websocketOptions, apiKey, ...(WebSocketImpl ? { WebSocketImpl } : {}) });
          websocketKey = connectionKey;
        }
        websocketBusy = true;
        try {
          const { response, metrics } = await websocket.respond({ body, signal: requestSignal, onEvent,
            timeoutMs: websocketOptions.responseTimeoutMs ?? timeoutMs });
          return { ...response, metrics: { ...metrics, ...usageMetrics(response) } };
        } catch (error) {
          requestSignal.throwIfAborted();
          if (transport !== 'auto' || !(error instanceof WebSocketConnectionError)) throw error;
          // No request was sent. Avoid paying repeated upgrade failures while
          // the endpoint or network is temporarily unavailable.
          websocket?.close(); websocket = undefined;
          websocketRetryAt = Date.now() + 60_000;
          transportFallback = true;
        } finally { websocketBusy = false; }
      }
      let firstOutputAt;
      const response = await request('https://api.openai.com/v1/responses', {
        method: 'POST',
        headers: { Authorization: `Bearer ${apiKey}`, 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
        signal: requestSignal,
      });
      const headersMs = Math.round(performance.now() - started);
      if (!response.ok) {
        let info;
        try { info = await response.json(); } catch { info = {}; }
        throw new Error(`OpenAI request failed (${response.status}): ${publicError(info.error?.message || response.statusText)}`);
      }
      if (!response.body) throw new Error('OpenAI returned an empty stream.');
      let buffer = '';
      let completed;
      const decoder = new TextDecoder();
      async function consume(block) {
        const payload = block.split('\n').filter((line) => line.startsWith('data:')).map((line) => line.slice(5).trimStart()).join('\n');
        if (!payload || payload === '[DONE]') return;
        let event;
        try { event = JSON.parse(payload); } catch { throw new Error('OpenAI returned an unreadable stream event.'); }
        if (/^(response\.(output_text|function_call_arguments|custom_tool_call_input)\.delta)$/.test(event.type) && firstOutputAt === undefined) firstOutputAt = performance.now();
        if (event.type === 'error' || event.type === 'response.failed') throw new Error(publicError(event.error?.message || event.message || event.response?.error?.message || 'The model request failed.'));
        if (event.type === 'response.incomplete') throw new Error('The model reached its output limit before finishing. Try a smaller change.');
        if (event.type === 'response.completed') {
          if (!event.response || typeof event.response !== 'object' || event.response.status !== 'completed') throw new Error('OpenAI returned an invalid completed response.');
          completed = event.response;
        }
        await onEvent?.(event);
      }
      const reader = response.body.getReader();
      // The terminal event is authoritative. Waiting for EOF can hold the next
      // tool action indefinitely when a proxy keeps the HTTP stream open.
      const cancelReader = () => { void reader.cancel().catch(() => {}); };
      requestSignal.addEventListener('abort', cancelReader, { once: true });
      try {
        requestSignal.throwIfAborted();
        while (!completed) {
          const { done, value } = await reader.read();
          requestSignal.throwIfAborted();
          if (done) break;
          buffer = (buffer + decoder.decode(value, { stream: true })).replace(/\r\n/g, '\n');
          if (buffer.length > 2_000_000) throw new Error('Model stream exceeded the local size limit.');
          let boundary;
          while (!completed && (boundary = buffer.indexOf('\n\n')) !== -1) {
            const block = buffer.slice(0, boundary); buffer = buffer.slice(boundary + 2);
            await consume(block);
          }
        }
        if (!completed) {
          buffer += decoder.decode();
          if (buffer.trim()) await consume(buffer);
        }
        requestSignal.throwIfAborted();
        if (!completed) throw new Error('The connection ended before the model finished. Your published space is unchanged.');
      } finally {
        requestSignal.removeEventListener('abort', cancelReader);
        // Cancellation itself may wait on a broken transport; cleanup must not
        // delay a confirmed completion, error, or abort.
        cancelReader();
        reader.releaseLock();
      }
      return { ...completed, metrics: { durationMs: Math.round(performance.now() - started), headersMs, ttftMs: firstOutputAt === undefined ? null : Math.round(firstOutputAt - started), transport: 'http', transportFallback, ...usageMetrics(completed) } };
    },
  };
}
