import test from 'node:test';
import assert from 'node:assert/strict';
import { createSpaceAgent } from '../server/space-agent.mjs';
import { devDayAgentInstructions } from '../server/devday-theme.mjs';

const message = [{ role: 'user', content: 'Paint one red pixel.' }];
const action = {
  name: 'paint', description: 'Paint one pixel on the shared canvas.',
  parameters: { type: 'object', properties: { x: { type: 'integer', minimum: 0, maximum: 31 }, color: { type: 'string', enum: ['red', 'blue'] } }, required: ['x', 'color'], additionalProperties: false },
};
const call = (id = 'paint-1', args = { x: 3, color: 'red' }, name = 'paint') => ({ type: 'function_call', call_id: id, name, arguments: JSON.stringify(args) });
const result = (output = []) => ({ output, metrics: { servedTier: 'ultrafast' } });
const deferred = () => { let resolve; const promise = new Promise(done => { resolve = done; }); return { promise, resolve }; };

function fixture(t, respond, { actions = [action], act } = {}) {
  const saved = {
    currentRevisionId: 4,
    revisions: [{ id: 4, title: 'Common ground', source: 'PRIVATE_SOURCE', tests: 'PRIVATE_TESTS', meta: { title: 'Common ground', capabilities: ['space-agent'], agent: { instructions: 'Help visitors paint the shared pixel canvas.', actions } } }],
    state: { projects: [], contributions: [], extras: { canvas: {} } },
    session: { items: [{ role: 'user', content: 'PRIVATE_BUILDER_MESSAGE' }] }, icon: { dataUrl: 'PRIVATE_ICON_BYTES' },
  };
  const requests = [], mutations = [], events = [];
  let providerClosed = 0;
  const service = {
    owner: { id: 'mira', name: 'Mira' }, store: { read: () => structuredClone(saved) },
    async action(args) {
      args.signal.throwIfAborted();
      if (act) await act(args, saved);
      args.signal.throwIfAborted();
      mutations.push(args);
      saved.state.extras.canvas[args.action.x] = { color: args.action.color, actorId: args.actor };
      return { state: saved.state };
    },
  };
  const runtime = createSpaceAgent({ adapter: { model: 'fixture-astra', tier: 'ultrafast', keyAvailable: true,
    async respond(args) { requests.push(args); return respond(args, requests.length, saved); },
    close() { providerClosed++; },
  } });
  t.after(() => runtime.close());
  const run = extra => runtime.run({ service, actorId: 'leo', revisionId: 4, messages: message, onEvent: event => events.push(event), ...extra });
  return { saved, service, requests, mutations, events, runtime, run, providerClosed: () => providerClosed };
}

test('the default model adapter uses independent HTTP requests with low reasoning and Ultrafast', async t => {
  const { service } = fixture(t, async () => result(), { actions: [] });
  const captured = [];
  t.mock.method(globalThis, 'fetch', async (url, options) => {
    captured.push({ url, options });
    const events = [
      { type: 'response.output_text.delta', delta: 'Hello from Astra.' },
      { type: 'response.completed', response: { status: 'completed', output: [{ type: 'message', content: [{ type: 'output_text', text: 'Hello from Astra.' }] }], service_tier: 'ultrafast' } },
    ];
    return new Response(events.map(event => `data: ${JSON.stringify(event)}\n\n`).join(''), { status: 200 });
  });
  const runtime = createSpaceAgent({ apiKey: 'test-key', model: 'gpt-6-astra', tier: 'ultrafast' });
  t.after(() => runtime.close());
  const answer = await runtime.run({ service, actorId: 'leo', revisionId: 4, messages: message });
  assert.equal(answer.text, 'Hello from Astra.');
  assert.equal(captured.length, 1);
  assert.equal(captured[0].url, 'https://api.openai.com/v1/responses');
  const body = JSON.parse(captured[0].options.body);
  assert.equal(body.model, 'gpt-6-astra');
  assert.equal(body.service_tier, 'ultrafast');
  assert.deepEqual(body.reasoning, { effort: 'low' });
  assert.equal(body.stream, true);
  assert.equal(body.store, false);
  assert.deepEqual(body.tools, []);
  assert.equal(captured[0].options.headers.Authorization, 'Bearer test-key');
});

test('text-only embedded agents stream real responses without reading private builder context', async t => {
  const { run, requests, mutations, events, saved } = fixture(t, async ({ onEvent }) => {
    await onEvent({ type: 'response.output_text.delta', delta: 'Welcome ' });
    await onEvent({ type: 'response.output_text.delta', delta: 'to the canvas.' });
    return result();
  }, { actions: [] });
  const before = structuredClone(saved);
  const answer = await run();
  assert.equal(answer.text, 'Welcome to the canvas.');
  assert.equal(answer.actionsApplied, 0);
  assert.equal(answer.model, 'fixture-astra');
  assert.equal(answer.servedTier, 'ultrafast');
  assert.deepEqual(events.map(item => item.type), ['delta', 'delta', 'complete']);
  assert.deepEqual(requests[0].tools, []);
  assert.match(requests[0].instructions, /owner-defined purpose/);
  assert.match(requests[0].input[0].content, /"actorId":"leo"/);
  const sent = JSON.stringify(requests.map(({ input, instructions, tools }) => ({ input, instructions, tools })));
  for (const secret of ['PRIVATE_SOURCE', 'PRIVATE_TESTS', 'PRIVATE_BUILDER_MESSAGE', 'PRIVATE_ICON_BYTES']) assert.ok(!sent.includes(secret));
  assert.equal(mutations.length, 0);
  assert.deepEqual(saved, before);
});

test('declared actions use the authenticated actor and refresh public state before answering', async t => {
  const { run, requests, mutations, events } = fixture(t, async ({ onEvent }, round) => {
    if (round === 1) return result([call()]);
    await onEvent({ type: 'response.output_text.delta', delta: 'Painted a red pixel.' });
    return result();
  });
  const answer = await run();
  assert.equal(answer.actionsApplied, 1);
  assert.equal(mutations.length, 1);
  assert.equal(requests.length, 2, 'a completed task stops without using the remaining model responses');
  assert.deepEqual(mutations[0].action, { x: 3, color: 'red', type: 'paint' });
  assert.equal(mutations[0].actor, 'leo');
  assert.equal(mutations[0].revisionId, 4);
  assert.equal(mutations[0].requiredCapability, 'space-agent');
  assert.ok(mutations[0].signal instanceof AbortSignal);
  assert.deepEqual(requests[0].tools, [{ ...action, type: 'function', strict: false }]);
  assert.match(requests[1].input[0].content, /"3":\{"color":"red","actorId":"leo"\}/);
  const toolResult = requests[1].input.find(item => item.type === 'function_call_output');
  assert.deepEqual(JSON.parse(toolResult.output), { ok: true, action: 'paint', message: 'Applied to the shared space.' });
  assert.deepEqual(events.map(item => item.type), ['action', 'delta', 'complete']);
});

test('saved embedded agents receive DevDay art direction without remapping allowed colors or saved art', async t => {
  const { run, requests, mutations, saved } = fixture(t, async (_request, round) => round === 1
    ? result([call()])
    : result([{ type: 'message', content: [{ type: 'output_text', text: 'Painted the requested red pixel.' }] }]));
  saved.revisions[0].meta.agent.instructions = 'Paint with the existing red/blue palette on this old warm-paper canvas.';
  saved.state.extras.canvas.old = { color: 'blue', actorId: 'mira' };
  const originalConfig = structuredClone(saved.revisions[0].meta.agent);

  const answer = await run();

  assert.equal(answer.actionsApplied, 1);
  assert.deepEqual(mutations[0].action, { x: 3, color: 'red', type: 'paint' }, 'Requested valid colors are not coerced to the event palette.');
  assert.deepEqual(saved.state.extras.canvas.old, { color: 'blue', actorId: 'mira' });
  assert.deepEqual(saved.revisions[0].meta.agent, originalConfig, 'Style guidance does not rewrite the published agent or its palette schema.');
  for (const request of requests) {
    assert.ok(request.instructions.includes(devDayAgentInstructions));
    assert.match(request.instructions, /Honor the visitor's specific subject and requested artwork colors/);
    assert.match(request.instructions, /never invent a palette entry, change an index's meaning/);
    assert.deepEqual(request.tools[0].parameters.properties.color.enum, ['red', 'blue']);
  }
});

test('the completed response can supply text when a transport emits no deltas', async t => {
  const { run, events } = fixture(t, async () => result([{ type: 'message', content: [{ type: 'output_text', text: 'A ready canvas.' }] }]));
  assert.equal((await run()).text, 'A ready canvas.');
  assert.deepEqual(events[0], { type: 'delta', text: 'A ready canvas.' });
});

test('undeclared actions and malformed or spoofed arguments never reach the reducer', async t => {
  for (const invalid of [
    call('bad', { x: 3, color: 'red' }, 'apply_change'),
    { ...call('bad'), arguments: '{not json' },
    call('bad', { x: 3, color: 'red', actorId: 'mira' }),
    call('bad', { x: 3, color: 'red', type: 'erase' }),
    call('bad', { x: 900, color: 'red' }),
    call('bad', { x: 3, color: 'orange' }),
    call('bad', ['red']),
    { ...call('bad'), arguments: '{"x":3,"color":"red","__proto__":{"admin":true}}' },
    { ...call('bad'), arguments: 'x'.repeat(8001) },
  ]) {
    const { run, mutations, requests, events } = fixture(t, async ({ onEvent }, round) => {
      if (round === 1) return result([invalid]);
      await onEvent({ type: 'response.output_text.delta', delta: 'That action is not available.' });
      return result();
    });
    assert.equal((await run()).actionsApplied, 0);
    assert.equal(mutations.length, 0);
    assert.equal(events.some(event => event.type === 'action'), false);
    const feedback = JSON.parse(requests[1].input.find(item => item.type === 'function_call_output').output);
    assert.equal(feedback.ok, false);
    assert.match(feedback.message, /No change was applied/);
  }
});

test('a failed action gets bounded repair feedback, and a corrected call can succeed', async t => {
  let tries = 0;
  const { run, requests, mutations } = fixture(t, async ({ onEvent }, round) => {
    if (round < 3) return result([call(`attempt-${round}`, { x: round, color: 'red' })]);
    await onEvent({ type: 'response.output_text.delta', delta: 'Painted the pixel.' });
    return result();
  }, { act: async () => { if (++tries === 1) throw new Error(`The pixel is occupied. sk-secret${'x'.repeat(800)}`); } });
  const answer = await run();
  assert.equal(answer.actionsApplied, 1);
  assert.equal(mutations[0].action.x, 2);
  const feedback = JSON.parse(requests[1].input.find(item => item.type === 'function_call_output').output);
  assert.equal(feedback.ok, false);
  assert.ok(feedback.error.length <= 500);
  assert.ok(!feedback.error.includes('sk-secret'));
});

test('exact published capability and revision are checked before any model call', async t => {
  const { run, saved, requests } = fixture(t, async () => result());
  await assert.rejects(run({ revisionId: 3 }), error => error.status === 409);
  saved.revisions[0].meta.capabilities = [];
  await assert.rejects(run(), error => error.status === 403);
  assert.equal(requests.length, 0);
});

test('a publication during inference prevents stale tool calls from applying', async t => {
  const { run, mutations, events } = fixture(t, async (_args, _round, saved) => {
    saved.currentRevisionId = 5;
    saved.revisions.push({ ...saved.revisions[0], id: 5 });
    return result([call()]);
  });
  await assert.rejects(run(), error => error.status === 409);
  assert.equal(mutations.length, 0);
  assert.equal(events.some(event => event.type === 'complete'), false);
});

test('capability revocation while inference is running prevents all actions', async t => {
  const { run, mutations } = fixture(t, async (_args, _round, saved) => {
    saved.revisions[0].meta.capabilities = [];
    return result([call()]);
  });
  await assert.rejects(run(), error => error.status === 403);
  assert.equal(mutations.length, 0);
});

test('the reducer revision guard is fatal rather than a prompt-repair opportunity', async t => {
  const { run, requests, mutations } = fixture(t, async () => result([call()]), {
    act: async () => { throw Object.assign(new Error('This space just changed.'), { status: 409 }); },
  });
  await assert.rejects(run(), error => error.status === 409);
  assert.equal(requests.length, 1);
  assert.equal(mutations.length, 0);
});

test('public state too large to read accurately is rejected without dropping records', async t => {
  const { run, saved, requests } = fixture(t, async () => result());
  saved.state.extras.large = 'x'.repeat(40_001);
  await assert.rejects(run(), error => error.status === 413);
  assert.equal(requests.length, 0);
});

function paintingFixture(t, { columns = 192, rows = 128, respond = async () => result([{ type: 'message', content: [{ type: 'output_text', text: 'Ready to paint.' }] }]) } = {}) {
  const setup = fixture(t, respond);
  const { saved, service } = setup;
  saved.revisions[0].meta.agent.paintContext = { canvasKey: 'painting', namespace: 'canvas' };
  saved.state.extras.canvas = { iris: { actorId: 'iris', planes: [{ columns, rows, chunks: { 0: 'HIDDEN_LAYER_HISTORY'.repeat(3000) } }] } };
  saved.state.extras.notes = { iris: { actorId: 'iris', text: 'Keep this unrelated public record intact.' } };
  const paint = { action: 'paint', columns, rows, color: 0, colorValue: '#00f', palette: ['#00f', '#f00'], background: '#fff' };
  const snapshots = [];
  service.snapshot = async actorId => {
    snapshots.push(actorId);
    const pixels = Array.from({ length: columns * rows }, (_, index) => saved.state.extras.canvas[index]?.color === 'red' ? '1' : '0').join('');
    return {
      state: structuredClone(saved.state), revision: structuredClone(saved.revisions[0]),
      html: `<canvas data-key="painting" data-paint-grid='${JSON.stringify(paint)}' data-paint-pixels="${pixels}" tabindex="0" aria-label="Shared painting"></canvas>`,
      session: saved.session, config: { apiKey: 'PRIVATE_SNAPSHOT_CREDENTIAL' },
    };
  };
  return { ...setup, snapshots, paint };
}

const sharedContext = request => JSON.parse(request.input[0].content.split('\n').at(-1));

test('opted-in painting agents read dense high-resolution visible pixels without private layer history', async t => {
  for (const size of [96, 192, 256]) {
    const { run, requests, snapshots, saved } = paintingFixture(t, { columns: size, rows: size });
    const before = structuredClone(saved);
    await run();
    assert.deepEqual(snapshots, ['leo']);
    assert.equal(requests.length, 1);
    const state = sharedContext(requests[0]);
    const projected = state.extras.canvas;
    assert.equal(projected.representation, 'visible-paint-composite');
    assert.equal(projected.columns, size);
    assert.equal(projected.rows, size);
    assert.equal(projected.pixels, '0'.repeat(size * size));
    assert.deepEqual(projected.palette, ['#00f', '#f00']);
    assert.equal(projected.background, '#fff');
    assert.deepEqual(projected.layerActorIds, ['iris']);
    assert.deepEqual(state.extras.notes, before.state.extras.notes);
    assert.deepEqual(state.projects, before.state.projects);
    assert.deepEqual(state.contributions, before.state.contributions);
    assert.match(requests[0].input[0].content, /not full layer history/);
    assert.match(projected.description, /never replace saved state/);
    const sent = JSON.stringify(requests[0].input);
    for (const privateValue of ['HIDDEN_LAYER_HISTORY', 'PRIVATE_SOURCE', 'PRIVATE_TESTS', 'PRIVATE_BUILDER_MESSAGE', 'PRIVATE_SNAPSHOT_CREDENTIAL']) assert.ok(!sent.includes(privateValue));
    assert.deepEqual(saved, before, 'projection does not replace or mutate any stored records');
    assert.equal(requests[0].tools[0].name, 'paint');
  }
});

test('visible painting snapshots refresh after each action using the authenticated participant', async t => {
  const { run, requests, snapshots, mutations } = paintingFixture(t, { respond: async (_request, round) => round === 1
    ? result([call()]) : result([{ type: 'message', content: [{ type: 'output_text', text: 'Painted.' }] }]) });
  assert.equal((await run()).actionsApplied, 1);
  assert.deepEqual(snapshots, ['leo', 'leo']);
  assert.equal(sharedContext(requests[0]).extras.canvas.pixels[3], '0');
  assert.equal(sharedContext(requests[1]).extras.canvas.pixels[3], '1');
  assert.deepEqual(sharedContext(requests[1]).extras.canvas.layerActorIds.sort(), ['iris', 'leo']);
  assert.equal(mutations[0].actor, 'leo');
  assert.equal(mutations[0].requiredCapability, 'space-agent');
});

test('painting projection never silently drops oversized unrelated records', async t => {
  const { run, requests, saved } = paintingFixture(t);
  saved.state.extras.notes.iris.text = 'x'.repeat(40_001);
  await assert.rejects(run(), error => error.status === 413);
  assert.equal(requests.length, 0);
});

test('painting projection has a bounded total context even at maximum resolution', async t => {
  const { run, requests, saved } = paintingFixture(t, { columns: 256, rows: 256 });
  saved.state.extras.notes.iris.text = 'x'.repeat(36_000);
  await assert.rejects(run(), error => error.status === 413);
  assert.equal(requests.length, 0);
});

test('publication during an asynchronous painting snapshot blocks stale context', async t => {
  const { run, requests, saved, service } = paintingFixture(t);
  const snapshot = service.snapshot;
  service.snapshot = async actorId => {
    const captured = await snapshot(actorId);
    saved.currentRevisionId = 5;
    saved.revisions.push({ ...saved.revisions[0], id: 5 });
    return captured;
  };
  await assert.rejects(run(), error => error.status === 409);
  assert.equal(requests.length, 0);
});

test('painting snapshots must report the exact active revision', async t => {
  const { run, requests, service } = paintingFixture(t);
  const snapshot = service.snapshot;
  service.snapshot = async actorId => ({ ...await snapshot(actorId), revision: { id: 3 } });
  await assert.rejects(run(), error => error.status === 409);
  assert.equal(requests.length, 0);
});

test('painting projection requires one real matching canvas and valid participant-owned records', async t => {
  for (const invalid of ['missing', 'duplicate', 'malformed', 'invalid-owner']) {
    const { run, requests, saved, service } = paintingFixture(t);
    const snapshot = service.snapshot;
    service.snapshot = async actorId => {
      const captured = await snapshot(actorId);
      if (invalid === 'missing') captured.html = captured.html.replace('data-key="painting"', 'data-key="different"');
      if (invalid === 'duplicate') captured.html += captured.html;
      if (invalid === 'malformed') captured.html = captured.html.replace('data-paint-pixels="0', 'data-paint-pixels="!');
      return captured;
    };
    if (invalid === 'invalid-owner') saved.state.extras.canvas.iris.actorId = '';
    await assert.rejects(run());
    assert.equal(requests.length, 0);
  }
});

test('tool loops allow eight model rounds and report confirmed mutations honestly', async t => {
  const { run, requests, mutations, events } = fixture(t, async (_args, round) => result([call(`round-${round}`, { x: round, color: 'red' })]));
  const answer = await run();
  assert.equal(requests.length, 8);
  assert.equal(mutations.length, 8);
  assert.equal(answer.actionsApplied, 8);
  assert.match(answer.text, /Applied 8 updates/);
  assert.match(requests[0].instructions, /at most 8 action attempts across 8 model responses/);
  assert.equal(events.at(-1).type, 'complete');
});

test('even a model returning many calls cannot exceed eight action attempts', async t => {
  const { run, requests, mutations } = fixture(t, async () => result(Array.from({ length: 10 }, (_, x) => call(`many-${x}`, { x, color: 'red' }))));
  assert.equal((await run()).actionsApplied, 8);
  assert.equal(requests.length, 1);
  assert.equal(mutations.length, 8);
});

test('duplicate action IDs are rejected before applying a batch', async t => {
  const { run, mutations } = fixture(t, async () => result([call('same'), call('same')]));
  await assert.rejects(run(), /duplicate or invalid action identifiers/);
  assert.equal(mutations.length, 0);
});

test('a tool success followed by an empty final response confirms saved changes without claiming completion', async t => {
  const { run } = fixture(t, async (_args, round) => result(round === 1 ? [call()] : []));
  const answer = await run();
  assert.equal(answer.text, 'Changes saved. Completion of the requested result was not confirmed.');
  assert.equal(answer.actionsApplied, 1);
});

test('empty answers and excessive text fail without a misleading completion event', async t => {
  for (const respond of [async () => result(), async ({ onEvent }) => { await onEvent({ type: 'response.output_text.delta', delta: 'x'.repeat(6001) }); return result(); }]) {
    const { run, events } = fixture(t, respond);
    await assert.rejects(run(), /did not return an answer|too long/);
    assert.equal(events.some(event => event.type === 'complete'), false);
  }
});

test('cancellation during inference aborts the request and prevents mutation', async t => {
  const started = deferred();
  const controller = new AbortController();
  const { run, mutations, events } = fixture(t, async ({ signal }) => {
    started.resolve();
    await new Promise((resolve, reject) => signal.addEventListener('abort', () => reject(signal.reason), { once: true }));
    return result([call()]);
  });
  const pending = run({ signal: controller.signal });
  await started.promise;
  controller.abort(new DOMException('Cancelled', 'AbortError'));
  await assert.rejects(pending, { name: 'AbortError' });
  assert.equal(mutations.length, 0);
  assert.equal(events.some(event => event.type === 'complete'), false);
});

test('cancellation reaches the reducer commit guard', async t => {
  const controller = new AbortController();
  const { run, mutations, events } = fixture(t, async () => result([call()]), {
    act: async ({ signal }) => { controller.abort(); signal.throwIfAborted(); },
  });
  await assert.rejects(run({ signal: controller.signal }), { name: 'AbortError' });
  assert.equal(mutations.length, 0);
  assert.equal(events.length, 0);
});

test('a disconnected event consumer cannot turn a committed action into repair feedback', async t => {
  const { run, mutations, requests } = fixture(t, async () => result([call()]));
  await assert.rejects(run({ onEvent: () => { throw new Error('Viewer disconnected'); } }), /Viewer disconnected/);
  assert.equal(mutations.length, 1);
  assert.equal(requests.length, 1);
});

test('a failed follow-up stream acknowledges already committed actions without claiming nothing changed', async t => {
  const { run, mutations, events } = fixture(t, async (_args, round) => {
    if (round === 1) return result([call()]);
    throw new Error('The connection ended before the model finished. Your published space is unchanged.');
  });
  await assert.rejects(run(), error => {
    assert.match(error.message, /1 update was already applied to the shared space/);
    assert.match(error.message, /connection ended/);
    assert.doesNotMatch(error.message, /unchanged/);
    return true;
  });
  assert.equal(mutations.length, 1);
  assert.deepEqual(events.map(event => event.type), ['action']);
});

test('independent visitors keep their conversation context separate', async t => {
  const waiting = deferred();
  const { run, requests } = fixture(t, async ({ onEvent }, round) => {
    if (round === 2) waiting.resolve();
    await waiting.promise;
    await onEvent({ type: 'response.output_text.delta', delta: 'Hello.' });
    return result();
  });
  await Promise.all([
    run({ actorId: 'leo', messages: [{ role: 'user', content: 'Leo’s private question.' }] }),
    run({ actorId: 'mira', messages: [{ role: 'user', content: 'Mira’s private question.' }] }),
  ]);
  assert.equal(requests.length, 2);
  assert.equal(requests.filter(request => JSON.stringify(request.input).includes('Leo’s private question.')).length, 1);
  assert.equal(requests.filter(request => JSON.stringify(request.input).includes('Mira’s private question.')).length, 1);
});

test('closing the runtime aborts in-flight requests and denies later ones', async t => {
  const started = deferred();
  const { run, runtime, providerClosed } = fixture(t, async ({ signal }) => {
    started.resolve();
    await new Promise((resolve, reject) => signal.addEventListener('abort', () => reject(signal.reason), { once: true }));
    return result();
  });
  const pending = run();
  await started.promise;
  const failure = assert.rejects(pending, { name: 'AbortError' });
  await runtime.close();
  await runtime.close();
  await failure;
  assert.equal(providerClosed(), 1);
  await assert.rejects(run(), { name: 'AbortError' });
});
