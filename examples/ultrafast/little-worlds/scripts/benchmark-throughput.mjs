#!/usr/bin/env node
// Explicit opt-in only: real requests, disposable spaces, no live demo writes.
import { mkdtemp, rm, writeFile, readFile } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join, resolve } from 'node:path';
import { createHash } from 'node:crypto';
import { createSpaceService } from '../server/harness.mjs';
import { createResponsesAdapter, loadApiKey } from '../server/responses.mjs';

if (!process.argv.includes('--live')) {
  console.log('Explicit live benchmark: node scripts/benchmark-throughput.mjs --live [--rounds 3] [--output /tmp/throughput.json]');
  process.exit(0);
}
const option = (name, fallback) => {
  const index = process.argv.indexOf(name);
  return index < 0 ? fallback : process.argv[index + 1];
};
const rounds = Number(option('--rounds', 3));
if (!Number.isInteger(rounds) || rounds < 1 || rounds > 5) throw Error('--rounds must be 1–5');
const output = resolve(option('--output', join(tmpdir(), 'little-worlds-throughput.json')));
const liveData = new URL('../.local/', import.meta.url).pathname;
if (output.startsWith(liveData)) throw Error('Results must not overwrite live demo data');
const apiKey = await loadApiKey();
if (!apiKey) throw Error('No configured OpenAI API key');
const cases = [
  { name: 'build', prompt: 'Create a personal astronomy space with a beautiful hero and two tiles: a continuously orbiting planet around a star, and a daily observation note form saved separately for each visitor. Make it responsive and polished.' },
  { name: 'visual-edit', prompt: 'Change only the accent color and the orbiting planet to vivid blue. Preserve all motion, controls, content, and saved notes.' },
  { name: 'add-interaction', prompt: 'Add a third tile with a working launch counter, separate for each visitor, with Increase and Reset buttons. Preserve both existing tiles, their motion, and all saved notes.' },
];
const round = value => Number.isFinite(value) ? Math.round(value * 10) / 10 : null;
const quantile = (values, fraction) => {
  const sorted = values.filter(Number.isFinite).sort((a, b) => a - b);
  if (!sorted.length) return null;
  const position = (sorted.length - 1) * fraction;
  const low = Math.floor(position), high = Math.ceil(position);
  return round(sorted[low] + (sorted[high] - sorted[low]) * (position - low));
};
const configuration = createResponsesAdapter({ apiKey, maxOutputTokens: 12000 });
const report = {
  startedAt: new Date().toISOString(), model: configuration.model, requestedTier: configuration.tier,
  reasoningEffort: configuration.reasoningEffort, requestedTransport: configuration.transport,
  maxOutputTokens: 12000, rounds, cases, runs: [],
  methodology: 'Sequential real requests through the production builder, prompts, tools, validation, transport, and Activity meter. Each round starts a blank temporary space; its two edits reuse that space and conversation. No saved user spaces are read or changed. Live TPS is the same rolling tokenizer estimate seen in Activity. Average TPS sums estimated visible tokens divided by first-to-last-output delivery intervals (minimum 250 ms per response), excluding initial wait and tool execution. Provider non-reasoning TPS is a separate cross-check, not the live gauge. Only numeric telemetry and these synthetic prompts are retained.',
  sourceHashes: {},
};
configuration.close();
for (const name of ['harness', 'responses', 'build-activity', 'output-throughput']) {
  report.sourceHashes[name] = createHash('sha256').update(await readFile(new URL(`../server/${name}.mjs`, import.meta.url))).digest('hex');
}
let requests = 0;
function summarize() {
  const complete = report.runs.filter(run => run.outcome === 'completed');
  const live = complete.flatMap(run => run.liveSamples.filter(sample => sample.rate > 0).map(sample => sample.rate));
  const averages = complete.map(run => run.averageTps);
  return {
    attempted: report.runs.length, completed: complete.length, modelRequests: requests,
    averageTps: { min: quantile(averages, 0), median: quantile(averages, .5), max: quantile(averages, 1) },
    liveTps: { median: quantile(live, .5), p95: quantile(live, .95), max: quantile(live, 1) },
    suggestedScale: Math.ceil((quantile(live, 1) || 0) * 1.1 / 50) * 50,
    byCase: Object.fromEntries(cases.map(({ name }) => {
      const values = complete.filter(run => run.case === name);
      return [name, { count: values.length, medianAverageTps: quantile(values.map(run => run.averageTps), .5),
        peakLiveTps: quantile(values.map(run => run.peakLiveTps), 1),
        medianFirstOutputMs: quantile(values.map(run => run.firstOutputMs), .5),
        medianWallMs: quantile(values.map(run => run.wallMs), .5) }];
    })),
  };
}
for (let iteration = 1; iteration <= rounds; iteration++) {
  const directory = await mkdtemp(join(tmpdir(), 'little-worlds-tps-'));
  const provider = createResponsesAdapter({ apiKey, maxOutputTokens: 12000 });
  let service, modelMetrics = [], liveSamples = [], start = 0;
  const adapter = { ...provider, async respond(args) {
    if (++requests > rounds * 6) throw Error('Benchmark model request limit reached');
    const result = await provider.respond(args);
    modelMetrics.push(result.metrics);
    return result;
  } };
  try {
    service = await createSpaceService({ dataDir: directory, owner: { id: 'tps-benchmark', name: 'Benchmark' }, kind: 'blank', adapter });
    service.activity.subscribe(event => {
      const data = event.data?.throughput;
      if (data?.state === 'streaming') liveSamples.push({ elapsedMs: Date.now() - start, rate: data.rate, tokens: data.tokens, durationMs: data.durationMs });
    });
    for (const scenario of cases) {
      modelMetrics = []; liveSamples = []; start = Date.now();
      const timeout = setTimeout(() => void service.cancel(), 90_000);
      try {
        const { turnId } = await service.submit(scenario.prompt);
        await service.waitForIdle();
        const wallMs = Date.now() - start;
        const state = service.store.read();
        const telemetry = service.activity.read().filter(event => event.turnId === turnId && event.data?.throughput).map(event => event.data.throughput);
        const tokens = telemetry.reduce((sum, item) => sum + item.tokens, 0);
        const duration = telemetry.reduce((sum, item) => sum + item.durationMs, 0);
        const reported = modelMetrics.every(item => Number.isFinite(item.reasoningTokens) && Number.isFinite(item.ttftMs));
        const providerTokens = modelMetrics.reduce((sum, item) => sum + item.outputTokens - (item.reasoningTokens || 0), 0);
        const providerDuration = modelMetrics.reduce((sum, item) => sum + Math.max(0, item.durationMs - (item.ttftMs || 0)), 0);
        const result = {
          round: iteration, case: scenario.name, outcome: state.session.lastOutcome, wallMs,
          firstOutputMs: modelMetrics[0]?.ttftMs ?? null, estimatedVisibleTokens: tokens, outputDeliveryMs: duration,
          averageTps: duration > 0 ? round(tokens * 1000 / duration) : null,
          peakLiveTps: quantile(liveSamples.map(item => item.rate), 1),
          providerNonReasoningTps: reported && providerDuration > 0 ? round(providerTokens * 1000 / providerDuration) : null,
          models: modelMetrics, liveSamples,
          modelResponses: state.events.filter(event => event.turnId === turnId && event.type === 'model.completed').length,
          failure: state.events.find(event => event.turnId === turnId && event.type === 'turn.failed')?.detail ?? null,
        };
        report.runs.push(result); report.summary = summarize(); report.updatedAt = new Date().toISOString();
        await writeFile(output, JSON.stringify(report, null, 2) + '\n', { mode: 0o600 });
        console.log(JSON.stringify({ ...result, liveSamples: undefined, models: undefined }));
        if (result.outcome !== 'completed') break;
      } finally { clearTimeout(timeout); }
    }
  } finally { await service?.close(); provider.close(); await rm(directory, { recursive: true, force: true }); }
}
console.log(JSON.stringify({ output, summary: report.summary }));
