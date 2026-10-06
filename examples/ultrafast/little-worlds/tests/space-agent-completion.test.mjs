import test from 'node:test';
import assert from 'node:assert/strict';
import { createSpaceAgent } from '../server/space-agent.mjs';

const fill = {
  name: 'fill_canvas', description: 'Fill every pixel with one palette color.',
  parameters: {
    type: 'object', properties: { color: { type: 'integer', minimum: 0, maximum: 7 } },
    required: ['color'], additionalProperties: false,
  },
};
const call = id => ({ type: 'function_call', call_id: id, name: 'fill_canvas', arguments: '{"color":3}' });
const reply = text => ({ type: 'message', content: [{ type: 'output_text', text }] });

function fixture(t, respond, { rejectActions = false } = {}) {
  const saved = {
    currentRevisionId: 1,
    revisions: [{ id: 1, meta: { title: 'Canvas', capabilities: ['space-agent'], agent: { instructions: 'Paint using the supplied palette.', actions: [fill] } } }],
    state: { extras: { canvas: { iris: { actorId: 'iris', color: 0 } } } },
  };
  const requests = [], mutations = [], events = [];
  const runtime = createSpaceAgent({ adapter: {
    model: 'fixture-model', keyAvailable: true,
    async respond(request) { requests.push(request); return { output: await respond(request, requests.length) }; },
  } });
  t.after(() => runtime.close());
  const service = {
    owner: { id: 'iris' }, store: { read: () => structuredClone(saved) },
    async action(action) {
      action.signal.throwIfAborted();
      if (rejectActions) throw new Error('The canvas cannot apply this action.');
      mutations.push(action);
      saved.state.extras.canvas.iris.color = action.action.color;
    },
  };
  const run = () => runtime.run({ service, actorId: 'iris', revisionId: 1,
    messages: [{ role: 'user', content: 'Paint the whole canvas green.' }], onEvent: event => events.push(event) });
  return { run, requests, mutations, events };
}

function publicContext(request) {
  return JSON.parse(request.input[0].content.split('\n')[1]);
}

test('a semantic fill can finish after one action with refreshed state and no mandatory extra actions', async t => {
  const { run, requests, mutations, events } = fixture(t, (request, round) => {
    if (round === 1) return [call('fill-1')];
    assert.match(request.input[0].content, /"iris":\{"actorId":"iris","color":3\}/);
    return [reply('Painted the whole canvas green.')];
  });
  const answer = await run();
  assert.equal(requests.length, 2);
  assert.equal(mutations.length, 1);
  assert.equal(answer.text, 'Painted the whole canvas green.');
  assert.equal(publicContext(requests[0]).actionsRemaining, 8);
  assert.equal(publicContext(requests[1]).actionsRemaining, 7);
  assert.equal(publicContext(requests[0]).responsesRemaining, 8);
  assert.equal(publicContext(requests[1]).responsesRemaining, 7);
  assert.equal(publicContext(requests[1]).actionsApplied, 1);
  assert.deepEqual(events.map(event => event.type), ['action', 'delta', 'complete']);
});

test('exhausting model rounds reports saved changes and unconfirmed completion instead of success', async t => {
  const { run, requests, mutations, events } = fixture(t, (_request, round) => [call(`fill-${round}`)]);
  const answer = await run();
  assert.equal(requests.length, 8);
  assert.equal(mutations.length, 8);
  assert.equal(publicContext(requests.at(-1)).actionsRemaining, 1);
  assert.equal(publicContext(requests.at(-1)).responsesRemaining, 1);
  assert.match(answer.text, /Applied 8 updates/);
  assert.match(answer.text, /reached its limit before completion could be confirmed/);
  assert.match(answer.text, /changes are saved/);
  assert.equal(events.at(-1).type, 'complete', 'The request is terminal even when the work is unconfirmed.');
  assert.equal(events.at(-1).actionsApplied, 8);
});

test('rejected actions consume the budget without inventing saved work or completion', async t => {
  const { run, requests, mutations } = fixture(t, (_request, round) => [call(`fill-${round}`)], { rejectActions: true });
  const answer = await run();
  assert.equal(requests.length, 8);
  assert.equal(mutations.length, 0);
  assert.equal(publicContext(requests.at(-1)).actionsRemaining, 1);
  assert.equal(publicContext(requests.at(-1)).actionsApplied, 0);
  assert.equal(answer.actionsApplied, 0);
  assert.match(answer.text, /reached its limit without applying a change/);
  assert.match(answer.text, /No changes were made/);
});
