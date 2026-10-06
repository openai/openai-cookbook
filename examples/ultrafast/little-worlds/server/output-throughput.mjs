import { Tiktoken } from 'js-tiktoken/lite';
import ranks from 'js-tiktoken/ranks/o200k_base';

// Only the server loads the vocabulary. Reuse it for every space and response.
// This public tokenizer estimates visible text, not the provider's billed tokens.
const tokenizer = new Tiktoken(ranks);
const pretokenizer = new RegExp(ranks.pat_str, 'gu');

const safeEnd = (text, end) => end < text.length && /[\uD800-\uDBFF]/.test(text.charAt(end - 1)) && /[\uDC00-\uDFFF]/.test(text.charAt(end)) ? end - 1 : end;

export function countOutputTokens(text) {
  let total = 0, start = 0;
  // JS BPE can be quadratic on one enormous word, path, or whitespace run.
  // Keep ordinary tokenization intact; only split pathological pre-token spans.
  for (const match of text.matchAll(pretokenizer)) {
    if (match[0].length <= 256) continue;
    total += tokenizer.encode(text.slice(start, match.index), [], []).length;
    const end = match.index + match[0].length;
    start = match.index;
    while (start < end) {
      const next = safeEnd(text, Math.min(end, start + 64));
      total += tokenizer.encode(text.slice(start, next), [], []).length;
      start = next;
    }
  }
  return total + tokenizer.encode(text.slice(start), [], []).length;
}

/** Bounded incremental token estimates, measured from real output arrival times. */
export function createOutputThroughput({
  now = () => Date.now(), countTokens = countOutputTokens,
  windowMs = 1000, minDurationMs = 250, maxBufferChars = 8192,
  contextChars = 128, maxChannels = 32,
} = {}) {
  maxBufferChars = Math.max(2, Math.floor(maxBufferChars) || 8192);
  const channels = new Map();
  const samples = [];
  let firstDeltaAt = null, lastDeltaAt = null;
  let tokens = 0, pendingTokens = 0, complete = false, dirty = true;

  function count(channel) {
    if (!channel.pending) return;
    const text = channel.context + channel.pending;
    let start = Math.max(0, text.length - contextChars);
    if (/[\uDC00-\uDFFF]/.test(text.charAt(start))) start++;
    try {
      const total = countTokens(text);
      const context = text.slice(start);
      const contextTokens = countTokens(context);
      if (!Number.isFinite(total) || total < 0 || !Number.isFinite(contextTokens) || contextTokens < 0) throw new Error('Invalid token estimate');
      const added = Math.max(0, total - channel.contextTokens);
      tokens += added;
      pendingTokens += added;
      channel.context = context;
      channel.contextTokens = contextTokens;
    } catch {
      // Observational telemetry must never reject a valid build or its stream.
      channel.context = '';
      channel.contextTokens = 0;
    }
    channel.pending = '';
  }

  return {
    get dirty() { return dirty; },
    append(key, delta) {
      if (complete || typeof delta !== 'string' || !delta) return false;
      let channel = channels.get(key);
      if (!channel) {
        // The provider cannot grow an unbounded map with invented output IDs.
        if (channels.size >= maxChannels) return false;
        channel = { pending: '', context: '', contextTokens: 0 };
        channels.set(key, channel);
      }
      const arrivedAt = now();
      firstDeltaAt ??= arrivedAt;
      lastDeltaAt = Math.max(lastDeltaAt ?? arrivedAt, arrivedAt);
      dirty = true;
      // Normal bursts wait for the feed's shared flush. An oversized burst spills
      // in bounded chunks, without dropping output or retaining the whole file.
      let offset = 0;
      while (offset < delta.length) {
        const end = safeEnd(delta, Math.min(delta.length, offset + maxBufferChars - channel.pending.length));
        if (end === offset) { count(channel); continue; }
        channel.pending += delta.slice(offset, end);
        offset = end;
        if (channel.pending.length >= maxBufferChars - 1 && offset < delta.length) count(channel);
      }
      return true;
    },
    finish() { if (!complete) { complete = true; dirty = true; } },
    sample() {
      const sampledAt = now();
      for (const channel of channels.values()) count(channel);
      if (pendingTokens > 0) {
        if (samples.at(-1)?.at === lastDeltaAt) samples.at(-1).tokens += pendingTokens;
        else samples.push({ at: lastDeltaAt, tokens: pendingTokens });
        pendingTokens = 0;
      }
      while (samples.length && samples[0].at <= sampledAt - windowMs) samples.shift();
      // A caller may explicitly flush faster than the normal 90ms feed interval.
      while (samples.length > 128) {
        const oldest = samples.shift();
        samples[0].tokens += oldest.tokens;
      }
      const elapsed = firstDeltaAt === null ? 0 : Math.max(minDurationMs, sampledAt - firstDeltaAt);
      const durationMs = firstDeltaAt === null ? 0 : Math.max(minDurationMs, lastDeltaAt - firstDeltaAt);
      const rate = complete || !elapsed ? 0 : samples.reduce((sum, sample) => sum + sample.tokens, 0) * 1000 / Math.min(windowMs, elapsed);
      dirty = false;
      return { tokens, durationMs, rate: Math.round(rate * 10) / 10, sampledAt, lastDeltaAt,
        state: complete ? 'complete' : firstDeltaAt === null ? 'waiting' : 'streaming', estimated: true };
    },
  };
}
