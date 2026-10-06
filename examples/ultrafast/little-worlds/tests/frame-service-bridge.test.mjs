import test from 'node:test';
import assert from 'node:assert/strict';
import vm from 'node:vm';
import { build } from 'esbuild';

async function loadBridge(minify = false) {
  const result = await build({ entryPoints: [new URL('../src/frame-service-bridge.ts', import.meta.url).pathname], bundle: true, format: 'esm', write: false, minify, target: 'es2020' });
  return import(`data:text/javascript;base64,${Buffer.from(result.outputFiles[0].text).toString('base64')}`);
}
const bridge = await loadBridge();

test('only declared capabilities and service-specific operations become requests', () => {
  const allowed = bridge.frameCapabilities(['finance-news', 'unknown', 'health-chat', 'health-chat']);
  assert.deepEqual(allowed, ['health-chat', 'finance-news']);
  assert.deepEqual(bridge.frameServiceRequest({ service: 'health-chat', input: { message: 'How does sleep work?' } }, allowed), { service: 'health-chat', operation: 'submit', input: { message: 'How does sleep work?' } });
  assert.equal(bridge.frameServiceRequest({ service: 'health-chat', operation: 'load' }, allowed), undefined);
  assert.equal(bridge.frameServiceRequest({ service: 'finance-news', operation: 'submit' }, allowed), undefined);
  assert.equal(bridge.frameServiceRequest({ service: 'health-chat', operation: 'submit' }, ['finance-news']), undefined);
  assert.equal(bridge.frameServiceRequest({ service: 'shell', operation: 'exec' }, allowed), undefined);
});

test('service request fields are bounded strings and reserved names cannot cross the bridge', () => {
  const request = input => bridge.frameServiceRequest({ service: 'health-chat', input }, ['health-chat']);
  assert.equal(request({ message: 'x'.repeat(4001) }), undefined);
  assert.equal(request({ message: { value: 'nested' } }), undefined);
  assert.equal(request({ constructor: 'override' }), undefined);
  assert.equal(request(JSON.parse('{"__proto__":"override"}')), undefined);
  assert.equal(request(Array.from({ length: 2 }, () => 'field')), undefined);
  assert.equal(request({ a: 'a'.repeat(4000), b: 'b'.repeat(4000) }), undefined);
});

test('reference URLs require the exact approved HTTPS origin for that service', () => {
  assert.equal(bridge.approvedServiceUrl('https://www.cdc.gov/health', 'health-chat'), 'https://www.cdc.gov/health');
  assert.equal(bridge.approvedServiceUrl('https://www.federalreserve.gov/newsevents/', 'finance-news'), 'https://www.federalreserve.gov/newsevents/');
  for (const url of ['javascript:alert(1)', 'http://www.cdc.gov/health', 'https://www.cdc.gov.evil.test/', 'https://user:secret@www.cdc.gov/', 'https://www.cdc.gov:8443/', 'data:text/html,hello']) assert.equal(bridge.approvedServiceUrl(url, 'health-chat'), undefined);
  assert.equal(bridge.approvedServiceUrl('https://www.cdc.gov/health', 'finance-news'), undefined);
});

test('service snapshots expose only bounded text and approved data links', () => {
  const state = bridge.frameServiceState({ status: 'ready', text: '<img onerror=alert(1)>', messages: [{ role: 'assistant', content: '<script>kept as text</script>' }], sources: [{ title: 'Official', url: 'https://www.cdc.gov/health' }, { title: 'Unsafe', url: 'https://evil.test/' }], privateToken: 'should disappear' }, 'health-chat');
  assert.equal(state.text, '<img onerror=alert(1)>');
  assert.equal(state.messages[0].content, '<script>kept as text</script>');
  assert.equal(state.privateToken, undefined);
  assert.deepEqual(bridge.serviceStateUrls(state), ['https://www.cdc.gov/health']);
  assert.equal(bridge.frameServiceState({ status: 'invented' }, 'health-chat'), undefined);
});

test('general space agents require their declared capability and expose chat-only operations', () => {
  const allowed = bridge.frameCapabilities(['space-agent', 'health-chat', 'space-agent', 'unknown']);
  assert.deepEqual(allowed, ['health-chat', 'space-agent']);
  assert.deepEqual(bridge.frameServiceRequest({ service: 'space-agent', input: { message: 'Draw a yellow sun' } }, allowed), { service: 'space-agent', operation: 'submit', input: { message: 'Draw a yellow sun' } });
  for (const operation of ['clear', 'cancel']) assert.equal(bridge.frameServiceRequest({ service: 'space-agent', operation }, allowed).operation, operation);
  for (const operation of ['load', 'refresh', 'action', 'execute']) assert.equal(bridge.frameServiceRequest({ service: 'space-agent', operation }, allowed), undefined);
  assert.equal(bridge.frameServiceRequest({ service: 'space-agent', input: { message: 'Draw a sun' } }, ['health-chat']), undefined);
});

test('general agent output cannot introduce links, executable actions, or permissions', () => {
  const state = bridge.frameServiceState({ status: 'ready', text: '<script>Not executable</script>', note: 'Updated the shared space.', actions: [{ type: 'reset' }], canEdit: true, sources: [{ title: 'A link', url: 'https://www.cdc.gov/health' }], items: [{ title: 'Another link', url: 'https://www.federalreserve.gov/' }] }, 'space-agent');
  assert.equal(state.text, '<script>Not executable</script>');
  assert.equal(state.actions, undefined);
  assert.equal(state.canEdit, undefined);
  assert.deepEqual(bridge.serviceStateUrls(state), []);
  for (const url of ['https://www.cdc.gov/health', 'https://www.federalreserve.gov/', 'https://example.com', 'javascript:alert(1)']) assert.equal(bridge.approvedServiceUrl(url, 'space-agent'), undefined);
});

test('private message drafts accept bounded strings only for chat services', () => {
  assert.equal(bridge.frameServiceDraft('An unfinished drawing request', 'space-agent'), 'An unfinished drawing request');
  assert.equal(bridge.frameServiceDraft('', 'health-chat'), '');
  for (const value of ['x'.repeat(4001), 'message\0tail', { message: 'nested data' }, null]) assert.equal(bridge.frameServiceDraft(value, 'space-agent'), undefined);
  assert.equal(bridge.frameServiceDraft('A private draft', 'finance-news'), undefined);
});

function draftFrame() {
  const messages = [];
  const handlers = {};
  const parent = { postMessage: data => messages.push(data) };
  class Element {}
  class HTMLElement extends Element {
    dataset = {};
    setAttribute() {}
    hasAttribute() { return false; }
    closest() { return root; }
  }
  class HTMLInputElement extends HTMLElement { type = 'text'; name = 'message'; value = ''; disabled = false; }
  class HTMLTextAreaElement extends HTMLElement {}
  class HTMLButtonElement extends HTMLElement {}
  class HTMLSelectElement extends HTMLElement {}
  class HTMLFormElement extends HTMLElement {
    hasAttribute(name) { return name === 'data-service-reset-on-submit'; }
    reset() { input.value = ''; handlers['document:reset']({ target: this, defaultPrevented: false }); }
  }
  const root = new HTMLElement();
  root.dataset.service = 'space-agent';
  root.querySelectorAll = selector => ['input[name="message"],textarea[name="message"]', 'button,input,textarea,select'].includes(selector) ? [input] : [];
  const input = new HTMLInputElement();
  const form = new HTMLFormElement();
  input.form = form;
  const context = {
    parent, URL, queueMicrotask, Element, HTMLElement, HTMLInputElement, HTMLTextAreaElement, HTMLButtonElement, HTMLSelectElement, HTMLFormElement,
    HTMLTemplateElement: class extends HTMLElement {},
    FormData: class { *[Symbol.iterator]() { yield ['message', input.value]; } },
    document: { getElementById: () => null, querySelectorAll: () => [root], addEventListener: (type, fn) => { handlers[`document:${type}`] = fn; }, documentElement: { style: { setProperty() {} }, clientHeight: 0, scrollTop: 0, scrollLeft: 0 }, body: { scrollHeight: 300, getBoundingClientRect: () => ({ height: 300 }) } },
    window: { innerHeight: 0, addEventListener: (type, fn) => { handlers[`window:${type}`] = fn; } },
    ResizeObserver: class { observe() {} },
  };
  vm.runInNewContext(bridge.frameBridgeScript('draft-nonce', 'http://127.0.0.1:5173'), context);
  const configure = drafts => handlers['window:message']({ source: parent, origin: 'http://127.0.0.1:5173', data: { channel: 'living-space-host', bridgeKey: 'draft-nonce', type: 'service.configure', active: true, capabilities: ['space-agent'], states: {}, drafts } });
  return { messages, handlers, input, form, configure };
}

test('trusted frame rehydrates private drafts and does not overwrite newer local typing', () => {
  const first = draftFrame();
  first.configure({ 'space-agent': 'Paint a little' });
  assert.equal(first.input.value, 'Paint a little');
  first.input.value += ' yellow sun';
  first.handlers['document:input']({ target: first.input });
  const saved = first.messages.at(-1);
  assert.equal(saved.type, 'service.draft');
  assert.equal(saved.service, 'space-agent');
  assert.equal(saved.value, 'Paint a little yellow sun');
  first.configure({ 'space-agent': 'Older cached input' });
  assert.equal(first.input.value, saved.value);
  const replacement = draftFrame();
  replacement.configure({ 'space-agent': saved.value });
  assert.equal(replacement.input.value, saved.value);
  const otherContext = draftFrame();
  otherContext.configure({});
  assert.equal(otherContext.input.value, '');
});

test('submitting a reset-on-submit service form clears the private cached draft', async () => {
  const frame = draftFrame();
  frame.configure({ 'space-agent': 'Paint a sun' });
  frame.handlers['document:submit']({ target: frame.form, preventDefault() {} });
  await new Promise(resolve => queueMicrotask(resolve));
  assert.equal(frame.input.value, '');
  const request = frame.messages.find(message => message.type === 'service.request');
  assert.equal(request.request.input.message, 'Paint a sun');
  assert.equal(frame.messages.at(-1).type, 'service.draft');
  assert.equal(frame.messages.at(-1).value, '');
  assert.ok(frame.messages.every(message => message.type !== 'action'));
});

test('draft capture excludes password fields and non-message values', () => {
  const frame = draftFrame();
  frame.configure({});
  const count = frame.messages.length;
  frame.input.type = 'password';
  frame.input.value = 'Do not copy this';
  frame.handlers['document:input']({ target: frame.input });
  frame.input.type = 'text';
  frame.input.name = 'other-field';
  frame.handlers['document:input']({ target: frame.input });
  assert.equal(frame.messages.length, count);
});

test('serialized production bridge starts without imports and verifies parent identity', async () => {
  const production = await loadBridge(true);
  const script = production.frameBridgeScript('test-nonce', 'http://127.0.0.1:5173');
  const messages = [];
  const handlers = {};
  const parent = { postMessage: (data, origin) => messages.push({ data, origin }) };
  const context = { parent, URL, document: { getElementById: () => null, querySelectorAll: () => [], addEventListener() {}, documentElement: { style: { setProperty() {} }, clientHeight: 0, scrollTop: 0, scrollLeft: 0 }, body: { scrollHeight: 300, getBoundingClientRect: () => ({ height: 299.5 }) } }, window: { innerHeight: 0, addEventListener: (type, fn) => { handlers[type] = fn; } }, ResizeObserver: class { observe() {} } };
  vm.runInNewContext(script, context);
  assert.deepEqual(messages.map(item => item.data.type), ['resize', 'ready']);
  assert.equal(messages[0].data.height, 300);
  assert.ok(messages.every(item => item.origin === 'http://127.0.0.1:5173' && item.data.bridgeKey === 'test-nonce'));
  assert.doesNotThrow(() => handlers.message({ source: {}, origin: 'https://evil.test', data: { channel: 'living-space-host', bridgeKey: 'test-nonce', type: 'service.configure', active: true } }));
  assert.doesNotThrow(() => handlers.message({ source: parent, origin: 'http://127.0.0.1:5173', data: { channel: 'living-space-host', bridgeKey: 'test-nonce', type: 'service.configure', active: true, capabilities: ['health-chat'], states: {} } }));
});

test('frame sizing measures full-width content, caps tall worlds, and preserves horizontal access', async () => {
  const production = await loadBridge(true);
  const messages = [];
  let measureAgain;
  let mode = 'auto';
  let contentHeight = 599;
  let horizontalGutter = 0;
  const root = {
    scrollTop: 0, scrollLeft: 0,
    get clientHeight() { return 120 - horizontalGutter; },
    style: { setProperty(name, value, priority) {
      assert.equal(name, 'overflow-y');
      assert.equal(priority, 'important');
      mode = value;
      // Simulate a layout probe clamping scroll offsets. They must be restored.
      root.scrollTop = 0;
      root.scrollLeft = 0;
    } },
  };
  const body = {
    get scrollHeight() { return contentHeight - (mode === 'auto' ? 8 : 0); },
    getBoundingClientRect() { return { height: this.scrollHeight }; },
  };
  vm.runInNewContext(production.frameBridgeScript('sizing', 'http://127.0.0.1:5173'), {
    parent: { postMessage: data => messages.push(data) }, URL,
    document: { documentElement: root, body, getElementById: () => null, querySelectorAll: () => [], addEventListener() {} },
    window: { innerHeight: 120, addEventListener() {} },
    ResizeObserver: class { constructor(callback) { measureAgain = callback; } observe() {} },
  });
  const sizes = () => messages.filter(item => item.type === 'resize').map(item => item.height);
  assert.equal(mode, 'hidden');
  assert.deepEqual(sizes(), [599], 'Measures full width, not the narrower 591px layout');
  measureAgain();
  assert.deepEqual(sizes(), [599], 'Unchanged geometry does not emit repeated messages');

  contentHeight = production.MAX_FRAME_HEIGHT + 1;
  root.scrollTop = 400; root.scrollLeft = 12;
  measureAgain(); measureAgain();
  assert.equal(mode, 'auto', 'The narrow layout fitting below the cap must not toggle scrollbars');
  assert.equal(root.scrollTop, 400);
  assert.equal(root.scrollLeft, 12);
  assert.deepEqual(sizes(), [599, 8000]);

  contentHeight = production.MAX_FRAME_HEIGHT;
  measureAgain();
  assert.equal(mode, 'hidden', 'Exact fits return to full width');
  contentHeight = 320.25; horizontalGutter = 15;
  measureAgain();
  assert.equal(mode, 'hidden');
  assert.equal(sizes().at(-1), 336, 'Reserve horizontal scrollbar space without clipping the bottom row');
});
