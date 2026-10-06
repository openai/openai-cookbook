// Manual end-to-end fixture: node tests/browser/build-activity-server.mjs
// Open http://127.0.0.1:5190, sign in as Mira, and use the ordinary composer.
// Any request succeeds in about eight seconds; include "fail" for a provider
// failure or "cancel" for a slower stream that leaves time to press Stop.
// Include "patch" to watch a small edit update the middle of space.js.
// Include "focus" to edit deep inside a long wrapped line, or "focus multi"
// to follow that edit with a second change near the beginning of the file.
// Comparison builds use the same mock with a slower standard lane. Include
// "standard fail", "ultrafast fail", "standard first", or "quick" to exercise
// recovery, completion order, and shorter runs without any external services.
// "interactive comparison" pauses Standard after its preview is visible so
// browser checks can use the finished Ultrafast world before either lane closes.
// Estimates are mocked too: "estimate offline" exercises fallback, "estimate
// slow" reaches the deadline, and "estimate small" exercises budget overrun.
import { mkdtemp, rm } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join, resolve } from 'node:path';
import { fileURLToPath, pathToFileURL } from 'node:url';
import { once } from 'node:events';
import { createServer as createHttpServer } from 'node:http';
import { createHash, randomUUID } from 'node:crypto';
import { setTimeout as delay } from 'node:timers/promises';
import { createServer } from 'vite';
import { createApp } from '../../server/index.mjs';

const root = fileURLToPath(new URL('../../', import.meta.url));
const focusFixture = [
  ...Array.from({ length: 48 }, (_, index) => `// Unchanged context ${String(index + 1).padStart(2, '0')}: keep this line outside the edit highlight.`),
  `// ${'Existing wrapped text before the edited phrase. '.repeat(34)}<focus-value>revision 0: original text</focus-value>${' Existing text after the edited phrase.'.repeat(14)}`,
].join('\n');
const source = `export const meta = {
  title: 'A little notebook',
  subtitle: 'A quiet place for the ideas worth keeping.',
  accent: '#687957',
  layout: 'canvas'
};

// Focus label: original

function escape(value) {
  return String(value).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
}

export function render(state, actor) {
  const note = state.extras.notes?.[actor.id]?.text || '';
  return '<style>' +
    '.notebook{max-width:960px;margin:24px auto;padding:64px 48px;background:#edeedf;border:1px solid #d7deca;border-radius:30px;color:#37462f}' +
    '.notebook .eyebrow{font:600 11px sans-serif;letter-spacing:3px;text-transform:uppercase}' +
    '.notebook h1{font:normal clamp(40px,7vw,78px)/1 Georgia,serif;letter-spacing:-3px;margin:28px 0}' +
    '.notebook .lede{max-width:440px;line-height:1.8;color:#738066}' +
    '.notebook .cards{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:16px;margin:42px 0}' +
    '.notebook article{padding:24px;border:1px solid #d1dac3;border-radius:16px;background:#f6f6eb}' +
    '.notebook article span{font:12px monospace;color:#879475}.notebook h2{font:normal 24px Georgia,serif}' +
    '.notebook article p{font-size:13px;line-height:1.7;color:#738066}' +
    '.notebook label{display:block;font-size:13px;margin-bottom:12px}.notebook textarea{display:block;width:100%;box-sizing:border-box;min-height:90px;padding:18px;border:1px solid #c6d1b9;border-radius:14px;background:#fcfcf6;color:#37462f;font:14px/1.6 sans-serif}' +
    '.notebook button{margin-top:14px;padding:12px 20px;border:0;border-radius:24px;background:#556b46;color:white;font:13px sans-serif}' +
    '@media(max-width:600px){.notebook{padding:28px 22px;margin:16px}.notebook .cards{grid-template-columns:1fr}.notebook h1{letter-spacing:-1px}}' +
    '</style><section class="notebook"><p class="eyebrow">Field notes · a living collection</p>' +
    '<h1>A little notebook.</h1><p class="lede">For half-formed ideas, small discoveries, and things you would like to return to.</p>' +
    '<div class="cards"><article><span>01 / NOTICE</span><h2>Look a little closer.</h2><p>A shape, a phrase, or something growing beside the path.</p></article>' +
    '<article><span>02 / COLLECT</span><h2>Keep the good bits.</h2><p>There is room for unfinished thoughts and unexpected connections.</p></article>' +
    '<article><span>03 / RETURN</span><h2>Let an idea grow.</h2><p>Come back with fresh eyes. See what feels different.</p></article></div>' +
    '<form data-action="{&quot;type&quot;:&quot;note&quot;}"><label for="notebook-note">Your latest note</label><textarea id="notebook-note" name="text" maxlength="1200">' + escape(note) + '</textarea><button type="submit">Keep this note</button></form></section>';
}

${focusFixture}

export function reduce(state, action, actor) {
  if (action.type !== 'note' || typeof action.text !== 'string' || !action.text.trim()) throw Error('Write a note first.');
  state.extras.notes = state.extras.notes || {};
  state.extras.notes[actor.id] = { actorId: actor.id, text: action.text.trim().slice(0, 1200) };
  return state;
}`;

const checks = `export function runTests(api) {
  const actor = { id: 'activity-browser-guest', name: 'Notebook guest' };
  const next = api.reduce(api.initialState, { type: 'note', text: 'A fresh idea' }, actor);
  return [
    { name: 'A person can keep a note', ok: next.extras.notes[actor.id].text === 'A fresh idea' },
    { name: 'Existing notes survive', ok: Object.entries(api.initialState.extras.notes || {}).every(([id, note]) => id === actor.id || JSON.stringify(next.extras.notes[id]) === JSON.stringify(note)) },
    { name: 'The notebook renders', ok: api.render(next, actor).includes('notebook') },
    { name: 'A note is escaped before rendering', ok: !api.render(api.reduce(next, { type: 'note', text: '<script>unsafe</script>' }, actor), actor).includes('<script>unsafe</script>') }
  ];
}`;

const noNetwork = async () => { throw new Error('External services are disabled in the activity browser fixture.'); };
const disabledAdapter = { keyAvailable: false, respond: noNetwork };

function addFile(path, content) {
  const text = content.endsWith('\n') ? content.slice(0, -1) : content;
  return `*** Add File: ${path}\n${text.split('\n').map(line => `+${line}`).join('\n')}`;
}

function updateFile(content, edits) {
  const lines = content.split('\n');
  return edits.map(({ search, replace }) => {
    if (typeof search !== 'string' || !search) throw new Error('The activity fixture requires an exact line to edit.');
    const index = lines.findIndex(line => line.includes(search));
    if (index < 0) throw new Error('The activity fixture could not find the line to edit.');
    const before = lines[index];
    lines[index] = before.replace(search, replace);
    // Separate ordered Update blocks preserve the fixture's lower-then-upper
    // edit sequence without asking an individual hunk to seek backwards.
    return `*** Update File: space.js\n@@\n-${before}\n+${lines[index]}`;
  }).join('\n');
}

async function respond({ input, onEvent, signal, tier = 'ultrafast' }) {
  const request = input.filter(item => item.role === 'user').at(-1)?.content || '';
  const prompt = String(request).split('\n\nCurrent workspace and live state')[0];
  const standard = tier === 'default';
  const lane = standard ? 'Standard' : 'Ultrafast';
  const standardFail = /\bstandard[ -]fail\b/i.test(prompt);
  const ultrafastFail = /\bultrafast[ -]fail\b/i.test(prompt);
  const fail = standardFail || ultrafastFail ? standard ? standardFail : ultrafastFail : /\bfail\b/i.test(prompt);
  const slow = /\bcancel\b/i.test(prompt);
  const speed = (/\bquick\b/i.test(prompt) ? .25 : 1) * (standard ? /\bstandard[ -]first\b/i.test(prompt) ? .3 : 2.8 : 1);
  const patch = /\bpatch\b/i.test(prompt);
  const focus = /\bfocus\b/i.test(prompt);
  const multiple = /\bmulti\b/i.test(prompt);
  const delimiter = '\n\nCurrent workspace and live state (authoritative for this turn):\n';
  const workspace = JSON.parse(String(request).split(delimiter)[1]);
  const focusBefore = workspace.source.match(/<focus-value>.*?<\/focus-value>/)?.[0];
  const focusRevision = Number(focusBefore?.match(/revision (\d+)/)?.[1] || 0) + 1;
  const focusEdits = focus && focusBefore ? [{
    search: focusBefore,
    replace: `<focus-value>revision ${focusRevision}: ${'New words arrive here while the surrounding code stays unchanged. '.repeat(12)}</focus-value>`,
  }] : [];
  if (focus && multiple) {
    const labelBefore = workspace.source.match(/^\/\/ Focus label:.*$/m)?.[0];
    if (labelBefore) focusEdits.push({ search: labelBefore, replace: `// Focus label: revision ${focusRevision}, a second separate edit` });
  }
  const started = performance.now();
  const id = randomUUID();
  const message = { type: 'message', id: `message-${id}`, role: 'assistant', content: [{ type: 'output_text', text: focus ? 'I’m updating the phrase inside the long line, keeping the surrounding text intact, and checking the finished page.' : 'I’m making the notebook a little brighter, keeping its notes intact, and checking the finished page.' }] };
  const accentBefore = workspace.source.match(/accent: '#[a-f\d]+'/i)?.[0];
  const patchBody = focus ? updateFile(workspace.source, focusEdits) : patch ? updateFile(workspace.source, [{
    search: accentBefore,
    replace: accentBefore === "accent: '#557c68'" ? "accent: '#687957'" : "accent: '#557c68'",
  }]) : [addFile('space.js', source.replaceAll('A little notebook', `A brighter notebook · ${lane}`)), addFile('tests.js', checks)].join('\n');
  const call = { type: 'custom_tool_call', id: `item-${id}`, call_id: `call-${id}`, name: 'apply_patch', input: `*** Begin Patch\n${patchBody}\n*** End Patch` };
  const emit = async event => { signal.throwIfAborted(); await onEvent(event); };
  await emit({ type: 'response.output_item.added', output_index: 0, item: { ...message, content: [] } });
  for (const delta of message.content[0].text.match(/.{1,18}/gu)) {
    await delay(145 * speed, undefined, { signal });
    await emit({ type: 'response.output_text.delta', output_index: 0, item_id: message.id, content_index: 0, delta });
  }
  await emit({ type: 'response.output_text.done', output_index: 0, item_id: message.id, content_index: 0, text: message.content[0].text });
  await emit({ type: 'response.output_item.done', output_index: 0, item: message });
  await emit({ type: 'response.output_item.added', output_index: 1, item: { ...call, input: '' } });
  const chunkSize = Math.ceil(call.input.length / 56);
  let chunk = 0;
  let heldForInteraction = false;
  for (let index = 0; index < call.input.length; index += chunkSize) {
    await delay((slow ? 650 : 125) * speed, undefined, { signal });
    await emit({ type: 'response.custom_tool_call_input.delta', output_index: 1, item_id: call.id, delta: call.input.slice(index, index + chunkSize) });
    if (standard && !heldForInteraction && /interactive comparison/i.test(prompt) && index + chunkSize >= call.input.length * .6) {
      heldForInteraction = true;
      await delay(10000, undefined, { signal });
    }
    if (fail && ++chunk === 10) throw new Error('The browser fixture provider failed while writing. Your published space is unchanged.');
  }
  await emit({ type: 'response.custom_tool_call_input.done', output_index: 1, item_id: call.id, input: call.input });
  await emit({ type: 'response.output_item.done', output_index: 1, item: call });
  const response = { status: 'completed', model: 'activity-fixture', service_tier: tier, output: [message, call] };
  await emit({ type: 'response.completed', response });
  return { ...response, metrics: { durationMs: Math.round(performance.now() - started), ttftMs: 145 * speed, outputTokens: Math.ceil(call.input.length / 4), servedTier: tier } };
}

export async function startBuildActivityServer({ apiPort = 4391, webPort = 5190, naturalSeeds = false } = {}) {
  const temporary = await mkdtemp(join(tmpdir(), 'little-worlds-activity-browser-'));
  const buildCalls = [];
  const estimateCalls = [];
  const progressEstimator = async ({ context, signal }) => {
    const prompt = String(context.prompt || '');
    const call = { startedAt: Date.now(), status: 'running', prompt };
    estimateCalls.push(call);
    try {
      await delay(/estimate slow/i.test(prompt) ? 6000 : 1000, undefined, { signal });
      if (/estimate offline/i.test(prompt)) throw new Error('The mock progress estimator is unavailable.');
      const expectedOutputTokens = /estimate small/i.test(prompt) ? 500 : 3200;
      call.status = 'completed';
      call.expectedOutputTokens = expectedOutputTokens;
      return { expectedOutputTokens };
    } catch (error) {
      call.status = signal.aborted ? 'cancelled' : 'failed';
      throw error;
    } finally { call.endedAt = Date.now(); }
  };
  const fingerprint = value => createHash('sha256').update(JSON.stringify(value ?? null)).digest('hex');
  const adapter = tier => ({
    keyAvailable: true, model: 'activity-fixture', tier, reasoningEffort: 'low',
    async respond(args) {
      const call = { tier: args.tier || tier, startedAt: Date.now(), status: 'running',
        inputHash: fingerprint(args.input), instructionsHash: fingerprint(args.instructions), toolsHash: fingerprint(args.tools) };
      buildCalls.push(call);
      try {
        const result = await respond({ ...args, tier: call.tier });
        call.status = 'completed';
        return result;
      } catch (error) {
        call.status = args.signal?.aborted ? 'cancelled' : 'failed';
        throw error;
      } finally { call.endedAt = Date.now(); }
    },
  });
  let instance;
  let apiServer;
  let webServer;
  let closing;
  const close = () => closing ||= (async () => {
    await webServer?.close();
    if (apiServer) {
      apiServer.closeAllConnections();
      await new Promise(done => apiServer.close(done));
    }
    await instance?.close();
    await rm(temporary, { recursive: true, force: true });
  })();
  try {
    instance = await createApp({
      dataDir: join(temporary, 'data'),
      ...(naturalSeeds ? {} : { seedOverride: { source, tests: checks, state: { projects: [], contributions: [], extras: {} } } }),
      adapter: adapter('ultrafast'), comparisonAdapter: adapter('default'),
      progressEstimator,
      apiKey: '', generateIcons: false,
      healthAdapter: disabledAdapter, spaceAgentAdapter: disabledAdapter, voiceAdapter: disabledAdapter,
      newsFetchImpl: noNetwork, voiceFetchImpl: noNetwork, voiceResponsesFetchImpl: noNetwork,
    });
    apiServer = createHttpServer((request, response) => {
      if (request.method === 'GET' && request.url === '/api/_fixture/builds') {
        response.writeHead(200, { 'Content-Type': 'application/json', 'Cache-Control': 'no-store' });
        response.end(JSON.stringify({ calls: buildCalls, estimates: estimateCalls }));
      } else instance.app(request, response);
    }).listen(apiPort, '127.0.0.1');
    await once(apiServer, 'listening');
    const actualApiPort = apiServer.address().port;
    webServer = await createServer({
      root, configFile: join(root, 'vite.config.ts'),
      server: { host: '127.0.0.1', port: webPort, strictPort: true, proxy: { '/api': { target: `http://127.0.0.1:${actualApiPort}`, changeOrigin: false } } },
    });
    await webServer.listen();
    return { url: `http://127.0.0.1:${webServer.httpServer.address().port}`, apiUrl: `http://127.0.0.1:${actualApiPort}`, temporary, instance, buildCalls, estimateCalls, close };
  } catch (error) {
    await close();
    throw error;
  }
}

if (process.argv[1] && pathToFileURL(resolve(process.argv[1])).href === import.meta.url) {
  const fixture = await startBuildActivityServer({ naturalSeeds: process.argv.includes('--natural-seeds') });
  console.log(`Activity browser fixture: ${fixture.url}`);
  console.log('Sign in as Mira. Submit any request, "fail", "cancel", "patch", "focus", "focus multi", "standard fail", "ultrafast fail", "standard first", or "quick" in the normal composer.');
  console.log(`Temporary data only: ${fixture.temporary}`);
  const stop = async () => { await fixture.close(); process.exit(0); };
  process.on('SIGINT', stop);
  process.on('SIGTERM', stop);
}
