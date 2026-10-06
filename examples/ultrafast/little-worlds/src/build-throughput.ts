import type { ActivityEntry } from './build-activity';

export type ThroughputReading = {
  rate: number | null;
  mode: 'waiting' | 'streaming' | 'paused' | 'complete' | 'unavailable' | 'disconnected';
};

/** Server arrival times keep reconnects and large replay snapshots from becoming bursts. */
export function buildThroughput(entries: readonly ActivityEntry[], now: number, running: boolean, connected: boolean): ThroughputReading {
  const responses = entries.filter(entry => entry.eventType === 'model.started');
  const latest = responses.at(-1)?.throughput;
  if (running && !connected) return { rate: null, mode: 'disconnected' };
  if (!latest) return { rate: null, mode: 'unavailable' };
  if (!running) {
    // Retention removes an oldest prefix. Without the original start, earlier
    // model responses may also have been evicted: do not label their tail an average.
    if (!entries.some(entry => entry.eventType === 'turn.started')) return { rate: null, mode: 'unavailable' };
    const samples = responses.flatMap(entry => entry.throughput ? [entry.throughput] : []);
    // Missing response telemetry cannot provide a complete request average.
    if (samples.length !== responses.length) return { rate: null, mode: 'unavailable' };
    const duration = samples.reduce((sum, sample) => sum + sample.durationMs, 0);
    const tokens = samples.reduce((sum, sample) => sum + sample.tokens, 0);
    return { rate: duration > 0 && tokens > 0 ? tokens * 1000 / duration : null, mode: 'complete' };
  }
  if (latest.state === 'complete') return { rate: 0, mode: 'paused' };
  if (latest.lastDeltaAt === null) return { rate: 0, mode: 'waiting' };
  // Hold between normal small batches, then let an idle stream settle to zero.
  // No synthetic progress while waiting on the model, tools, or the network.
  const age = Math.max(0, now - latest.sampledAt);
  const decay = Math.max(0, 1 - Math.max(0, age - 250) / 1000);
  const rate = Math.max(0, latest.rate * decay);
  return { rate, mode: rate > 0 ? 'streaming' : 'paused' };
}
