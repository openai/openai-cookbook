#!/usr/bin/env node
// Runs real model requests against disposable copies. Never writes .local.
// Example:
// node scripts/benchmark-latency.mjs --seed /tmp/little-worlds-latency-2026-09-17/seed.json \
//   --server-dir /tmp/little-worlds-latency-2026-09-17/baseline/server \
//   --output /tmp/little-worlds-latency-2026-09-17/baseline.json --label baseline
import { readFile, writeFile, mkdtemp, rm, readdir } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join, resolve } from 'node:path';
import { fileURLToPath, pathToFileURL } from 'node:url';
import { createHash } from 'node:crypto';

const root = fileURLToPath(new URL('..', import.meta.url));
const options = Object.fromEntries(process.argv.slice(2).reduce((pairs, item, index, args) => {
  if (item.startsWith('--')) pairs.push([item.slice(2), args[index + 1]?.startsWith('--') ? true : args[index + 1] ?? true]);
  return pairs;
}, []));
if (options.help) {
  console.log(`Usage: node scripts/benchmark-latency.mjs [options]
  --seed PATH         Immutable JSON with {space, owner}; optional if --space-file is used
  --space-file PATH   Read-only saved space; required unless --seed is provided
  --server-dir PATH   Alternate server snapshot (must resolve project dependencies)
  --cases LIST        recolor,tile (default); build also available
  --samples N         Repetitions per case (default 3)
  --output PATH       Result JSON path (default /tmp/little-worlds-latency-results-latest.json)
  --label TEXT        Variant label
  --model MODEL       Override model
  --tier TIER         Override service tier
  --transport MODE    auto, http, or websocket (default auto)
  --reasoning EFFORT  Override when supported by the selected adapter
Every run begins at the same pre-request revision in a private temporary directory.
API keys are read by the local adapter and never included in results.`);
  process.exit(0);
}

if (!options.seed && !options['space-file']) throw new Error('Supply --seed PATH or --space-file PATH to select the read-only benchmark input.');
const hash = value => createHash('sha256').update(typeof value === 'string' ? value : JSON.stringify(value)).digest('hex');
// Load the actual app's server environment before importing a temporary snapshot.
const { appSetting } = await import(new URL('../server/environment.mjs', import.meta.url));
const { loadApiKey } = await import(new URL('../server/responses.mjs', import.meta.url));
const apiKey = await loadApiKey();
if (!apiKey) throw new Error('No API key configured.');
const serverDir = resolve(options['server-dir'] || join(root, 'server'));
const { createSpaceService } = await import(pathToFileURL(join(serverDir, 'harness.mjs')));
const { createResponsesAdapter } = await import(pathToFileURL(join(serverDir, 'responses.mjs')));
let saved, owner;
if (options.seed) ({ space: saved, owner } = JSON.parse(await readFile(resolve(options.seed), 'utf8')));
else {
  saved = JSON.parse(await readFile(resolve(options['space-file']), 'utf8'));
  const { users } = JSON.parse(await readFile(join(root, '.local/identities.json'), 'utf8'));
  const person = users.find(person => person.id === saved.ownerId);
  if (!person) throw new Error('Cannot find the saved space owner. Supply an immutable --seed file.');
  owner = { id: person.id, name: person.name };
}
const definitions = {
  recolor: 'Make the spaceship blue',
  tile: 'Add another tile below that one but with a red plane going around the moon',
  build: 'Make an animation of a space ship around the earth',
};
const cases = String(options.cases || 'recolor,tile').split(',');
const samples = Number(options.samples || 3);
if (!Number.isInteger(samples) || samples < 1 || samples > 20) throw new Error('--samples must be 1–20');
if (cases.some(key => !definitions[key])) throw new Error('Unknown benchmark case. Choose recolor, tile, or build.');
const outputPath = resolve(options.output || join(tmpdir(), 'little-worlds-latency-results-latest.json'));
if (outputPath === join(root, '.local') || outputPath.startsWith(join(root, '.local/'))) throw new Error('Benchmark output must be outside live .local data.');
const model = options.model || appSetting('MODEL', 'gpt-6-astra');
const tier = options.tier || appSetting('TIER', 'ultrafast');
const transport = options.transport || appSetting('TRANSPORT', 'auto');
if (!['auto', 'http', 'websocket'].includes(transport)) throw new Error('--transport must be auto, http, or websocket.');
const sourceHashes = {};
for (const file of (await readdir(serverDir)).filter(name => name.endsWith('.mjs')).sort()) sourceHashes[file] = hash(await readFile(join(serverDir, file), 'utf8'));
const report = {
  label: options.label || 'current', startedAt: new Date().toISOString(), model, requestedTier: tier, requestedTransport: transport,
  serverDir, sourceHashes, seedHash: hash(saved), cases: {}, runs: [],
  methodology: 'Sequential real requests. Each run uses a fresh disposable copy of the same saved pre-request source, tests, state, and thread. Raw source, private context, credentials, and reasoning content are excluded from results. Service initialization excluded from wallMs; submit, generation, verification and commit included. Runs do not alter the live app.',
};

function prepareCase(key) {
  const message = definitions[key];
  const turnIndex = saved.session.turns.findIndex(turn => turn.message === message);
  if (turnIndex < 0) throw new Error(`Recorded turn unavailable for ${key}`);
  const target = saved.session.turns[turnIndex];
  const previous = [...saved.revisions].filter(revision => revision.id < target.revisionId).at(-1);
  if (!previous) throw new Error(`Pre-request revision unavailable for ${key}`);
  const requestIndex = saved.session.items.findIndex(item => item.role === 'user' && typeof item.content === 'string' && item.content.startsWith(`Owner's request: ${message}\n`));
  if (requestIndex < 0) throw new Error(`Recorded model input unavailable for ${key}`);
  const copy = structuredClone(saved);
  copy.currentRevisionId = previous.id;
  copy.revisions = copy.revisions.filter(revision => revision.id <= previous.id);
  copy.session.turns = copy.session.turns.slice(0, turnIndex);
  copy.session.items = copy.session.items.slice(0, requestIndex);
  copy.session.status = 'idle';
  copy.events = [];
  return { copy, previous, message, requestIndex };
}
const round = value => Math.round(value);
const median = values => {
  if (!values.length) return null;
  const sorted = values.toSorted((a, b) => a - b);
  const i = Math.floor(sorted.length / 2);
  return sorted.length % 2 ? sorted[i] : (sorted[i - 1] + sorted[i]) / 2;
};
const summarize = () => Object.fromEntries(cases.map(key => {
  const runs = report.runs.filter(run => run.case === key);
  const successful = runs.filter(run => run.outcome === 'completed');
  const values = name => successful.map(run => run[name]).filter(Number.isFinite);
  return [key, { completed: successful.length, attempted: runs.length, medianWallMs: median(values('wallMs')), medianTurnMs: median(values('turnMs')), medianFirstOutputMs: median(values('firstOutputMs')), medianPublishedMs: median(values('publishedMs')), medianFirstPreviewMs: median(values('firstPreviewMs')), medianInputTokens: median(successful.map(run => run.models[0]?.inputTokens).filter(Number.isFinite)), medianOutputTokens: median(successful.map(run => run.models.reduce((n, model) => n + (model.outputTokens || 0), 0))), medianCachedInputTokens: median(successful.map(run => run.models[0]?.cachedInputTokens).filter(Number.isFinite)), medianReasoningTokens: median(successful.map(run => run.models.reduce((n, model) => n + (model.reasoningTokens || 0), 0))) }];
}));

// Interleave case order to make shared server/cache warmup less case-dependent.
for (let run = 1; run <= samples; run++) for (const key of cases) {
  const { copy, previous, message, requestIndex } = prepareCase(key);
  report.cases[key] ||= { message, startingRevision: previous.id, sourceHash: hash(previous.source), testsHash: hash(previous.tests), stateHash: hash(copy.state), sourceCharacters: previous.source.length, threadItems: copy.session.items.length };
  const directory = await mkdtemp(join(tmpdir(), 'little-worlds-latency-'));
  let service;
  try {
    await writeFile(join(directory, 'space.json'), JSON.stringify(copy), { mode: 0o600 });
    const baseAdapter = createResponsesAdapter({ apiKey, model, tier, transport, ...(options.reasoning ? { reasoningEffort: options.reasoning } : {}) });
    if (baseAdapter.transport && baseAdapter.transport !== transport) {
      throw new Error('The selected adapter does not support the requested transport.');
    }
    if (!baseAdapter.transport && transport === 'websocket') {
      throw new Error('The selected adapter predates WebSocket support. Use http for this snapshot.');
    }
    if (options.reasoning && baseAdapter.reasoningEffort !== options.reasoning) {
      throw new Error(`The selected adapter does not support the requested reasoning override. It uses ${baseAdapter.reasoningEffort || 'an unspecified effort'}.`);
    }
    const models = [];
    let firstOutputMs, firstPreviewMs, publishedMs, started;
    const adapter = { ...baseAdapter, async respond(args) {
      const modelStarted = performance.now();
      let modelFirstOutput;
      const response = await baseAdapter.respond({ ...args, onEvent: async event => {
        if (event.type.endsWith('.delta') && /output_text|function_call_arguments|custom_tool_call_input/.test(event.type)) {
          modelFirstOutput ??= round(performance.now() - modelStarted);
          firstOutputMs ??= round(performance.now() - started);
        }
        await args.onEvent?.(event);
      } });
      models.push({ ...response.metrics, observedDurationMs: round(performance.now() - modelStarted), observedTtftMs: modelFirstOutput ?? null, inputTokens: response.usage?.input_tokens ?? response.metrics?.inputTokens ?? null, outputTokens: response.usage?.output_tokens ?? response.metrics?.outputTokens ?? null, cachedInputTokens: response.usage?.input_tokens_details?.cached_tokens ?? response.metrics?.cachedInputTokens ?? null, reasoningTokens: response.usage?.output_tokens_details?.reasoning_tokens ?? response.metrics?.reasoningTokens ?? null, requestedReasoningEffort: baseAdapter.reasoningEffort ?? null, servedTier: response.service_tier || response.metrics?.servedTier || 'unknown' });
      return response;
    } };
    service = await createSpaceService({ dataDir: directory, owner, kind: copy.kind, adapter });
    service.store.subscribe(event => {
      if (event.type === 'draft.preview') firstPreviewMs ??= round(performance.now() - started);
      if (event.type === 'revision.published') publishedMs ??= round(performance.now() - started);
    });
    started = performance.now();
    const { turnId } = await service.submit(message);
    await service.waitForIdle();
    const wallMs = round(performance.now() - started);
    const result = service.store.read();
    const events = result.events.filter(event => event.turnId === turnId);
    const revision = result.revisions.find(revision => revision.id === result.currentRevisionId);
    const calls = result.session.items.slice(requestIndex).filter(item => item.type === 'function_call' || item.type === 'custom_tool_call');
    const entry = {
      case: key, run, outcome: result.session.lastOutcome, wallMs,
      turnMs: events.find(event => event.type === 'turn.completed' || event.type === 'turn.failed')?.durationMs ?? null,
      firstOutputMs: firstOutputMs ?? null, firstPreviewMs: firstPreviewMs ?? null, publishedMs: publishedMs ?? null,
      models, tools: calls.map(call => ({ name: call.name, argumentCharacters: (call.arguments || call.input || '').length })),
      validationMs: events.filter(event => event.stage === 'verify' && event.durationMs !== undefined).reduce((n, event) => n + event.durationMs, 0),
      failureCount: events.filter(event => event.type === 'tool.failed').length,
      error: events.find(event => event.type === 'turn.failed')?.detail ?? null,
      checkCount: revision.checks.length, allChecksPassed: revision.checks.every(check => check.ok),
      publishedNewRevision: result.currentRevisionId > previous.id,
      statePreserved: hash(result.state) === hash(copy.state), testsReused: revision.tests === previous.tests,
      finalSourceHash: hash(revision.source), finalSourceCharacters: revision.source.length,
    };
    report.runs.push(entry);
    report.summary = summarize();
    report.updatedAt = new Date().toISOString();
    await writeFile(outputPath, JSON.stringify(report, null, 2));
    console.log(JSON.stringify(entry));
  } finally {
    await service?.close();
    await rm(directory, { recursive: true, force: true });
  }
}
console.log(JSON.stringify({ output: outputPath, summary: report.summary }, null, 2));
