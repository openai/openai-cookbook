import test from 'node:test';
import assert from 'node:assert/strict';
import vm from 'node:vm';
import { build } from 'esbuild';

async function load(path, minify = false) {
  const result = await build({ entryPoints: [new URL(path, import.meta.url).pathname], bundle: true, format: 'esm', write: false, minify, target: 'es2020' });
  return import(`data:text/javascript;base64,${Buffer.from(result.outputFiles[0].text).toString('base64')}`);
}
const { installFrameVoice } = await load('../src/frame-voice.ts');
const { frameBridgeScript } = await load('../src/frame-service-bridge.ts', true);
const registry = await load('../src/voice-frame-registry.ts');

function frame() {
  const handlers = {}, messages = [], events = [], submissions = [];
  class Element {
    constructor(tag = 'div', attributes = {}, content = '') {
      this.tagName = tag.toUpperCase(); this.attributes = {}; this.dataset = {}; this.children = [];
      this.textContent = content; this.isConnected = true; this.disabled = false; this.hidden = false;
      this.display = 'block'; this.visibility = 'visible'; this.scrollHeight = 0; this.clientHeight = 0; this.scrollWidth = 0; this.clientWidth = 0;
      for (const [key, value] of Object.entries(attributes)) this.setAttribute(key, value);
    }
    setAttribute(name, value) {
      this.attributes[name] = String(value);
      if (name.startsWith('data-')) this.dataset[name.slice(5).replace(/-([a-z])/g, (_, c) => c.toUpperCase())] = String(value);
      if (name === 'id') this.id = String(value);
      if (name === 'type' || name === 'name' || name === 'href') this[name] = String(value);
      if (name === 'hidden') this.hidden = true;
    }
    getAttribute(name) { return this.attributes[name] ?? null; }
    hasAttribute(name) { return name in this.attributes; }
    removeAttribute(name) { delete this.attributes[name]; if (name === 'href') delete this.href; }
    append(...children) { for (const child of children) { child.parent = this; this.children.push(child); } return this; }
    matches(selector) {
      return selector.split(',').some(part => {
        part = part.trim();
        if (part === ':disabled') return this.disabled;
        const tag = part.match(/^[a-z0-9-]+/i)?.[0];
        if (tag && this.tagName.toLowerCase() !== tag) return false;
        const attributes = [...part.matchAll(/\[([^\]=]+)(?:="([^"]*)")?\]/g)];
        return (tag || attributes.length) && attributes.every(([, name, value]) => this.hasAttribute(name) && (value === undefined || this.getAttribute(name) === value));
      });
    }
    closest(selector) { for (let node = this; node; node = node.parent) if (node.matches(selector)) return node; return null; }
    querySelectorAll(selector) { return this.children.flatMap(child => [...(child.matches(selector) ? [child] : []), ...child.querySelectorAll(selector)]); }
    querySelector(selector) { return this.querySelectorAll(selector)[0] || null; }
    getClientRects() { return this.display === 'none' ? [] : [{ width: 100, height: 30 }]; }
    getBoundingClientRect() { return this.bounds || { top: 0, left: 0, right: 100, bottom: 30, width: 100, height: 30 }; }
    scrollIntoView(options) { this.scrolledInto = options; }
    scrollBy(options) { this.scrolled = options; }
    dispatchEvent(event) { event.target = this; events.push([this, event.type]); handlers[`document:${event.type}`]?.(event); return !event.defaultPrevented; }
    click() { this.clicks = (this.clicks || 0) + 1; if (this.type === 'checkbox') this.checked = !this.checked; this.dispatchEvent(new Event('click')); }
    get innerText() { return [this.textContent, ...this.children.filter(child => !child.hidden && child.display !== 'none').map(child => child.innerText)].join(' '); }
    get labels() { return []; }
    get form() { return this.closest('form'); }
  }
  class HTMLElement extends Element {}
  class HTMLInputElement extends HTMLElement {
    constructor(attributes = {}, value = '') { super('input', attributes); this.type ||= 'text'; this.name ||= ''; this._value = value; this.readOnly = false; this.maxLength = -1; this.checked = false; }
    get value() { return this._value; }
    set value(value) { this._value = this.type === 'number' && value && !Number.isFinite(Number(value)) ? '' : String(value); }
  }
  class HTMLTextAreaElement extends HTMLElement {
    constructor(attributes = {}, value = '') { super('textarea', attributes); this._value = value; this.readOnly = false; this.maxLength = -1; }
    get value() { return this._value; }
    set value(value) { this._value = String(value); }
  }
  class HTMLSelectElement extends HTMLElement {
    constructor(attributes = {}, options = []) { super('select', attributes); this.options = options; this._value = options[0]?.value || ''; }
    get value() { return this._value; }
    set value(value) { this._value = String(value); }
  }
  class HTMLButtonElement extends HTMLElement { constructor(attributes = {}, content = '') { super('button', attributes, content); this.type ||= 'submit'; } }
  class HTMLAnchorElement extends HTMLElement { constructor(attributes = {}, content = '') { super('a', attributes, content); } }
  class HTMLFormElement extends HTMLElement {
    constructor(attributes = {}) { super('form', attributes); this.valid = true; }
    checkValidity() { return this.valid; }
    reportValidity() { this.reported = true; return this.valid; }
    requestSubmit(submitter) { submissions.push({ form: this, submitter }); this.dispatchEvent(Object.assign(new Event('submit'), { submitter })); }
    get elements() { return this.querySelectorAll('input,textarea,select,button'); }
    reset() {}
  }
  class Event { constructor(type, options = {}) { this.type = type; Object.assign(this, options); this.defaultPrevented = false; } preventDefault() { this.defaultPrevented = true; } }
  const root = new HTMLElement('div', { id: 'living-space-content' });
  let rootAvailable = true;
  const document = {
    getElementById: id => rootAvailable ? [root, ...root.querySelectorAll('[id]')].find(node => node.id === id) || null : null,
    querySelectorAll: selector => selector === '[data-paint-grid]' ? [] : root.querySelectorAll(selector),
    addEventListener: (type, fn) => { handlers[`document:${type}`] = fn; },
    documentElement: { style: { setProperty() {} }, clientHeight: 0, scrollTop: 0, scrollLeft: 0 }, body: { scrollHeight: 100, getBoundingClientRect: () => ({ height: 100 }) },
  };
  const parent = { postMessage: data => messages.push(data) };
  const globals = { document, parent, Element, HTMLElement, HTMLInputElement, HTMLTextAreaElement, HTMLButtonElement, HTMLSelectElement, HTMLFormElement, HTMLAnchorElement, HTMLTemplateElement: class extends HTMLElement {},
    Event, URL, queueMicrotask, getComputedStyle: node => ({ display: node.display, visibility: node.visibility }),
    FormData: class { *[Symbol.iterator]() { for (const item of this.form.elements) if (item.name && item.value !== undefined) yield [item.name, item.value]; } constructor(form) { this.form = form; } },
    ResizeObserver: class { observe() {} }, window: { innerHeight: 0, addEventListener: (type, fn) => { handlers[`window:${type}`] = fn; } },
  };
  const voice = vm.runInNewContext(`(${installFrameVoice.toString()})()`, globals);
  const control = (snapshot, name) => snapshot.controls.find(item => item.label === name);
  function bridge() {
    rootAvailable = false;
    vm.runInNewContext(frameBridgeScript('voice-key', 'http://127.0.0.1:5173'), globals);
    rootAvailable = true;
    const receive = (type, data = {}, override = {}) => handlers['window:message']({ source: parent, origin: 'http://127.0.0.1:5173', data: { channel: 'living-space-host', bridgeKey: 'voice-key', type, ...data }, ...override });
    receive('render', { version: 4, html: '' }); receive('service.configure', { active: true, capabilities: [] });
    return receive;
  }
  return { voice, root, control, events, messages, submissions, bridge, HTMLElement, HTMLInputElement, HTMLTextAreaElement, HTMLSelectElement, HTMLButtonElement, HTMLAnchorElement, HTMLFormElement };
}

test('frame surface exposes bounded semantic controls with fresh opaque snapshot IDs, not hidden controls or pixel grids', () => {
  const f = frame();
  const service = new f.HTMLElement('section', { 'data-service': 'space-agent' }).append(new f.HTMLElement('h2', {}, 'Art helper'));
  const input = new f.HTMLInputElement({ 'aria-label': 'Drawing idea', name: 'message' }, 'Draw a sun');
  const disabled = new f.HTMLButtonElement({ type: 'button' }, 'Unavailable'); disabled.disabled = true;
  service.append(input, disabled);
  f.root.append(service, new f.HTMLInputElement({ type: 'password', 'aria-label': 'Secret' }), new f.HTMLButtonElement({ hidden: '', type: 'button' }, 'Hidden'), new f.HTMLButtonElement({ 'data-paint-cell': '1', type: 'button' }, 'Pixel'));
  const first = f.voice.read(4), second = f.voice.read(4);
  assert.equal(first.controls.length, 2);
  assert.notEqual(first.controls[0].id, second.controls[0].id);
  assert.equal(first.controls[0].id.split(':')[1], second.controls[0].id.split(':')[1]);
  assert.equal(first.controls[0].value, 'Draw a sun');
  assert.equal(first.controls[0].context, 'space-agent · Art helper');
  assert.equal(first.controls[1].disabled, true);
  assert.ok(!first.controls[0].id.includes('Drawing'));
  for (let i = 0; i < 200; i++) f.root.append(new f.HTMLButtonElement({ type: 'button' }, `Option ${i}`));
  assert.equal(f.voice.read(4).controls.length, 160);
});

test('frame controls reject stale snapshots, unknown IDs and controls that become disabled, hidden or detached', () => {
  const f = frame(), button = new f.HTMLButtonElement({ type: 'button' }, 'Support'); f.root.append(button);
  const id = f.voice.read(4).controls[0].id;
  assert.equal(f.voice.execute({ type: 'click', id }, 3).ok, false);
  assert.equal(f.voice.execute({ type: 'click', id: '#arbitrary-selector' }, 4).ok, false);
  button.disabled = true; assert.equal(f.voice.execute({ type: 'click', id }, 4).ok, false); button.disabled = false;
  button.setAttribute('inert', ''); assert.equal(f.voice.execute({ type: 'click', id }, 4).ok, false); button.removeAttribute('inert');
  button.isConnected = false; assert.equal(f.voice.execute({ type: 'click', id }, 4).ok, false); button.isConnected = true;
  f.voice.invalidate(); assert.equal(f.voice.execute({ type: 'click', id }, 4).ok, false);
  assert.equal(button.clicks, undefined);
});

test('a background frame read invalidates an older plan even when the published version is unchanged', () => {
  const f = frame(), input = new f.HTMLInputElement({ 'aria-label': 'Draft' }, 'Original'); f.root.append(input);
  const oldId = f.voice.read(4).controls[0].id;
  input.value = 'New manual thought';
  const currentId = f.voice.read(4).controls[0].id;
  assert.equal(f.voice.execute({ type: 'fill', id: oldId, value: 'Old plan' }, 4).ok, false);
  assert.equal(input.value, 'New manual thought');
  assert.equal(f.voice.execute({ type: 'fill', id: currentId, value: 'Current plan' }, 4).ok, true);
});

test('a local animation may update unrelated content but cannot change a captured control meaning', () => {
  const f = frame(), status = new f.HTMLElement('p', {}, 'Score 1');
  const button = new f.HTMLButtonElement({ type: 'button', 'data-action': '{"type":"right"}' }, 'Move right');
  f.root.append(status, button);
  let id = f.voice.read(4).controls[0].id;
  status.textContent = 'Score 2';
  assert.equal(f.voice.execute({ type: 'click', id }, 4).ok, true);
  id = f.voice.read(4).controls[0].id;
  button.setAttribute('data-action', '{"type":"reset"}');
  assert.equal(f.voice.execute({ type: 'click', id }, 4).ok, false);
  id = f.voice.read(4).controls[0].id;
  button.textContent = 'Reset game';
  assert.equal(f.voice.execute({ type: 'click', id }, 4).ok, false);
  assert.equal(button.clicks, 1);
});

test('manual field changes cannot be overwritten or submitted by an earlier frame plan', () => {
  const f = frame(), form = new f.HTMLFormElement(), input = new f.HTMLInputElement({ 'aria-label': 'Draft' }, 'Original'), check = new f.HTMLInputElement({ type: 'checkbox', 'aria-label': 'Public' }), button = new f.HTMLButtonElement({}, 'Send');
  form.append(input, check, button); f.root.append(form);
  const old = f.voice.read(4), inputId = f.control(old, 'Draft').id, sendId = f.control(old, 'Send').id, checkId = f.control(old, 'Public').id;
  input.value = 'New manual thought';
  assert.equal(f.voice.execute({ type: 'fill', id: inputId, value: 'Old plan' }, 4).ok, false);
  assert.equal(f.voice.execute({ type: 'click', id: sendId }, 4).ok, false);
  assert.equal(f.voice.execute({ type: 'press', id: inputId, key: 'Enter' }, 4).ok, false);
  assert.equal(input.value, 'New manual thought'); assert.equal(f.submissions.length, 0);
  check.checked = true;
  assert.equal(f.voice.execute({ type: 'click', id: checkId }, 4).ok, false); assert.equal(check.checked, true);
  const current = f.voice.read(4);
  assert.equal(f.voice.execute({ type: 'click', id: f.control(current, 'Send').id }, 4).ok, true); assert.equal(f.submissions.length, 1);
});

test('native toggle snapshots expose checked state and require a fresh read after it changes', () => {
  const f = frame();
  const cases = [
    { element: new f.HTMLInputElement({ type: 'checkbox', 'aria-label': 'Public', 'aria-checked': 'true' }), initial: false, change: element => { element.checked = true; } },
    { element: new f.HTMLInputElement({ type: 'radio', 'aria-label': 'Morning' }), initial: false, change: element => { element.checked = true; } },
    { element: new f.HTMLButtonElement({ type: 'button', 'aria-pressed': 'false' }, 'Pause'), initial: false, change: element => element.setAttribute('aria-pressed', 'true') },
    { element: new f.HTMLButtonElement({ type: 'button', 'aria-checked': 'true' }, 'Remember'), initial: true, change: element => element.setAttribute('aria-checked', 'false') },
    { element: new f.HTMLAnchorElement({ 'data-action': '{"type":"pin"}', 'aria-checked': 'false' }, 'Pin'), initial: false, change: element => element.setAttribute('aria-checked', 'true') },
    { element: new f.HTMLInputElement({ type: 'button', 'aria-label': 'Favorite', 'aria-pressed': 'true' }), initial: true, change: element => element.setAttribute('aria-pressed', 'false') },
  ];
  for (const { element, initial, change } of cases) {
    f.root.append(element);
    const original = f.voice.read(4).controls.at(-1);
    assert.equal(original.checked, initial, original.label);
    change(element);
    assert.equal(f.voice.execute({ type: 'click', id: original.id }, 4).ok, false, original.label);
    assert.equal(f.voice.execute({ type: 'press', id: original.id, key: 'Space' }, 4).ok, false, original.label);
    assert.equal(element.clicks, undefined, original.label);
    const current = f.voice.read(4).controls.at(-1);
    assert.equal(current.checked, !initial, current.label);
    assert.equal(f.voice.execute({ type: 'press', id: current.id, key: 'Enter' }, 4).ok, true, current.label);
    assert.equal(element.clicks, 1, current.label);
  }
});

test('ARIA toggle state additions and removals invalidate activation without exposing custom controls', () => {
  const f = frame(), button = new f.HTMLButtonElement({ type: 'button', 'aria-pressed': 'mixed' }, 'Filter');
  f.root.append(button, new f.HTMLElement('div', { role: 'button', 'data-action': '{"type":"toggle"}', 'aria-checked': 'true' }, 'Custom toggle'));
  const first = f.voice.read(4);
  assert.equal(first.controls.length, 1);
  assert.equal('checked' in first.controls[0], false);
  button.setAttribute('aria-pressed', 'false');
  assert.equal(f.voice.execute({ type: 'click', id: first.controls[0].id }, 4).ok, false);
  const second = f.voice.read(4);
  assert.equal(second.controls[0].checked, false);
  button.removeAttribute('aria-pressed');
  assert.equal(f.voice.execute({ type: 'click', id: second.controls[0].id }, 4).ok, false);
  const third = f.voice.read(4);
  assert.equal('checked' in third.controls[0], false);
  assert.equal(f.voice.execute({ type: 'click', id: third.controls[0].id }, 4).ok, true);
  assert.equal(button.clicks, 1);
});

test('voice fills native fields and dispatches normal events without submitting or losing drafts on invalid values', () => {
  const f = frame(), input = new f.HTMLTextAreaElement({ 'aria-label': 'Question' }, 'Old draft'); input.maxLength = 30; f.root.append(input);
  const id = f.voice.read(4).controls[0].id;
  assert.equal(f.voice.execute({ type: 'fill', id, value: 'New draft' }, 4).ok, true);
  assert.equal(input.value, 'New draft'); assert.deepEqual(f.events.map(([, type]) => type), ['input', 'change']); assert.equal(f.submissions.length, 0);
  assert.equal(f.voice.execute({ type: 'fill', id, value: 'x'.repeat(31) }, 4).ok, false); assert.equal(input.value, 'New draft');
  input.readOnly = true; assert.equal(f.voice.execute({ type: 'fill', id, value: 'Forbidden' }, 4).ok, false);
  const number = new f.HTMLInputElement({ type: 'number', 'aria-label': 'Amount' }, '42'); f.root.append(number);
  const amount = f.control(f.voice.read(4), 'Amount').id;
  assert.equal(f.voice.execute({ type: 'fill', id: amount, value: 'wrong' }, 4).ok, false); assert.equal(number.value, '42');
});

test('numeric controls expose native format and bounds, while SVG names describe the current game state', () => {
  const f = frame(), form = new f.HTMLFormElement();
  const rate = new f.HTMLInputElement({ type: 'number', min: '-10', max: '20', step: 'any', 'aria-label': 'Annual rate (%)' }, '5');
  form.append(rate, new f.HTMLButtonElement({ type: 'submit' }, 'Save my scenario'));
  f.root.append(form, new f.HTMLElement('svg', { role: 'img', 'aria-label': 'Player at column 3, row 4. 12 dots remain.' }), new f.HTMLElement('svg', { hidden: '', 'aria-label': 'Hidden game' }));
  const surface = f.voice.read(4), control = f.control(surface, 'Annual rate (%)');
  assert.equal(control.role, 'spinbutton');
  assert.equal(control.type, 'number');
  assert.equal(control.min, -10); assert.equal(control.max, 20);
  assert.equal(control.step, undefined);
  assert.match(control.context, /Save my scenario.*drafts.*without units.*Decimals allowed/);
  assert.match(surface.text, /Player at column 3, row 4\. 12 dots remain/);
  assert.doesNotMatch(surface.text, /Hidden game/);
  const filled = f.voice.execute({ type: 'fill', id: control.id, value: '20' }, 4);
  assert.equal(filled.ok, true); assert.match(filled.message, /20.*draft/);
  assert.equal(f.submissions.length, 0);
  const fresh = f.voice.read(4);
  assert.equal(f.voice.execute({ type: 'click', id: f.control(fresh, 'Save my scenario').id }, 4).ok, true);
  assert.equal(f.submissions.length, 1);
});

test('disclosures expose their current state and reject stale expansion actions', () => {
  const f = frame();
  const details = new f.HTMLElement('details');
  const summary = new f.HTMLElement('summary', {}, 'Advanced settings');
  details.append(summary); f.root.append(details);
  const collapsed = f.control(f.voice.read(4), 'Advanced settings');
  assert.equal(collapsed.role, 'button');
  assert.equal(collapsed.expanded, false);
  assert.match(collapsed.context, /Disclosure is collapsed.*expand/);
  assert.equal(f.voice.execute({ type: 'click', id: collapsed.id }, 4).ok, true);
  details.setAttribute('open', '');
  assert.equal(f.voice.execute({ type: 'click', id: collapsed.id }, 4).ok, false);
  const expanded = f.control(f.voice.read(4), 'Advanced settings');
  assert.equal(expanded.expanded, true);
  assert.match(expanded.context, /Disclosure is expanded.*collapse/);
  assert.equal(f.voice.execute({ type: 'press', id: expanded.id, key: 'Space' }, 4).ok, true);
  assert.equal(summary.clicks, 2);
});

test('ARIA disclosures expose independent expansion and named regions and reject stale or retargeted actions', () => {
  const f = frame();
  const outline = new f.HTMLButtonElement({ type: 'button', 'aria-expanded': 'false', 'aria-controls': 'outline-region' }, 'Outline');
  const inspector = new f.HTMLButtonElement({ type: 'button', 'aria-expanded': 'false', 'aria-controls': 'inspector-region' }, 'Inspector');
  f.root.append(outline, inspector,
    new f.HTMLElement('section', { id: 'outline-region', hidden: '', 'aria-label': 'Document outline' }, 'HIDDEN_OUTLINE_PAYLOAD'),
    new f.HTMLElement('section', { id: 'inspector-region', hidden: '', 'aria-labelledby': 'inspector-label' }, 'HIDDEN_INSPECTOR_PAYLOAD'),
    new f.HTMLElement('h2', { id: 'inspector-label' }, 'Selection inspector'));
  for (const button of [outline, inspector]) button.click = () => {
    button.clicks = (button.clicks || 0) + 1;
    button.setAttribute('aria-expanded', button.getAttribute('aria-expanded') === 'true' ? 'false' : 'true');
  };
  const first = f.control(f.voice.read(4), 'Outline');
  assert.equal(first.expanded, false);
  assert.match(first.context, /Controls: Document outline/);
  assert.doesNotMatch(first.context, /HIDDEN_OUTLINE_PAYLOAD/);
  assert.equal(f.voice.execute({ type: 'click', id: first.id }, 4).ok, true);
  assert.equal(f.voice.execute({ type: 'click', id: first.id }, 4).ok, false, 'Same-label state change invalidates the old capture');
  const second = f.control(f.voice.read(4), 'Inspector');
  assert.equal(second.expanded, false);
  assert.match(second.context, /Controls: Selection inspector/);
  assert.equal(f.voice.execute({ type: 'click', id: second.id }, 4).ok, true);
  const both = f.voice.read(4);
  assert.equal(f.control(both, 'Outline').expanded, true);
  assert.equal(f.control(both, 'Inspector').expanded, true);
  outline.setAttribute('aria-controls', 'inspector-region');
  assert.equal(f.voice.execute({ type: 'click', id: f.control(both, 'Outline').id }, 4).ok, false, 'Retargeting the controlled region invalidates the old capture');
  assert.equal(outline.clicks, 1);
  assert.equal(inspector.clicks, 1);
  inspector.setAttribute('aria-expanded', 'invalid');
  assert.equal(f.control(f.voice.read(4), 'Inspector').expanded, undefined);
});

test('game controls keep their local group and accessible descriptions in a multi-experience page', () => {
  const f = frame();
  const article = new f.HTMLElement('article', { 'aria-label': 'Play room' });
  const racing = new f.HTMLElement('div', { 'data-game': 'racer', 'aria-label': 'Moon rally' });
  const puzzle = new f.HTMLElement('div', { 'data-game': 'puzzle', 'aria-label': 'Tile puzzle' });
  racing.append(new f.HTMLButtonElement({ type: 'button', 'data-game-action': '{"type":"turn","direction":"left"}', 'aria-describedby': 'steering-help' }, 'Left'));
  puzzle.append(new f.HTMLButtonElement({ type: 'button', 'data-game-action': '{"type":"slide","direction":"left"}' }, 'Left'));
  article.append(racing, puzzle, new f.HTMLElement('p', { id: 'steering-help' }, 'Turn the car toward the left lane.'));
  f.root.append(article);
  const left = f.voice.read(4).controls.filter(control => control.label === 'Left');
  assert.equal(left.length, 2);
  assert.match(left[0].context, /Moon rally.*Turn the car toward the left lane/);
  assert.match(left[1].context, /Tile puzzle/);
  assert.doesNotMatch(left[0].context, /Play room/);
  racing.children[0].setAttribute('data-game-release', '{"type":"coast"}');
  assert.equal(f.voice.execute({ type: 'click', id: left[0].id }, 4).ok, false, 'changed hold/release semantics require a fresh read');
});

test('long generated pages discover later controls after parent scrolling without losing stable element identities', () => {
  const f = frame();
  for (let index = 0; index < 210; index++) {
    const button = new f.HTMLButtonElement({ type: 'button' }, `Item ${index}`);
    button.bounds = { top: index * 20, bottom: index * 20 + 18, left: 0, right: 100, width: 100, height: 18 };
    f.root.append(button);
  }
  const first = f.voice.read(4, { top: 0, left: 0, width: 300, height: 100 });
  assert.equal(first.controls.length, 160);
  assert.ok(f.control(first, 'Item 0')); assert.equal(f.control(first, 'Item 209'), undefined);
  assert.match(first.text, /Showing 160 of 210 controls.*Scroll/);
  const last = f.voice.read(4, { top: 4000, left: 0, width: 300, height: 100 });
  assert.ok(f.control(last, 'Item 209')); assert.equal(f.control(last, 'Item 0'), undefined);
  assert.equal(f.control(first, 'Item 100').id.split(':')[1], f.control(last, 'Item 100').id.split(':')[1]);
  assert.equal(f.voice.execute({ type: 'click', id: f.control(last, 'Item 209').id }, 4).ok, true);
  assert.equal(f.root.children[209].clicks, 1);
});

test('voice form submission uses native validation, the existing submitter, and rejects disabled submit buttons', () => {
  const f = frame(), form = new f.HTMLFormElement({ 'aria-label': 'Wish' }), input = new f.HTMLInputElement({ 'aria-label': 'Your wish' }), button = new f.HTMLButtonElement({}, 'Plant');
  form.append(input, button); f.root.append(form);
  const snapshot = f.voice.read(4), inputId = f.control(snapshot, 'Your wish').id, buttonId = f.control(snapshot, 'Plant').id;
  form.valid = false; assert.equal(f.voice.execute({ type: 'click', id: buttonId }, 4).ok, false); assert.equal(form.reported, true); assert.equal(f.submissions.length, 0);
  form.valid = true; assert.equal(f.voice.execute({ type: 'press', id: inputId, key: 'Enter' }, 4).ok, true); assert.equal(f.submissions[0].submitter, button);
  button.disabled = true; assert.equal(f.voice.execute({ type: 'press', id: inputId, key: 'Enter' }, 4).ok, false); assert.equal(f.submissions.length, 1);
  assert.equal(f.voice.execute({ type: 'press', id: inputId, key: 'F12' }, 4).ok, false);
});

test('select, checkbox and reference actions operate only on their observed allowed controls', () => {
  const f = frame(), blue = new f.HTMLElement('option', {}, 'Blue'), red = new f.HTMLElement('option', {}, 'Red'), green = new f.HTMLElement('option', {}, 'Green');
  blue.value = 'blue'; blue.label = 'Blue'; red.value = 'red'; red.label = 'Red'; red.disabled = true;
  green.value = 'green'; green.label = 'Green';
  const disabledGroup = new f.HTMLElement('optgroup', { disabled: '' }).append(green);
  const select = new f.HTMLSelectElement({ 'aria-label': 'Color' }, [blue, red, green]); select.append(blue, red, disabledGroup);
  const check = new f.HTMLInputElement({ type: 'checkbox', 'aria-label': 'Join' });
  const good = new f.HTMLAnchorElement({ 'data-service-link': 'finance-news', href: 'https://www.federalreserve.gov/' }, 'Official reference');
  const arbitrary = new f.HTMLAnchorElement({ href: 'https://example.com' }, 'Not a reference'); f.root.append(select, check, good, arbitrary);
  const snapshot = f.voice.read(4), colorId = f.control(snapshot, 'Color').id;
  assert.equal(snapshot.controls.length, 3); assert.equal(f.control(snapshot, 'Color').options.length, 1);
  assert.equal(f.voice.execute({ type: 'select', id: colorId, value: 'red' }, 4).ok, false);
  assert.equal(f.voice.execute({ type: 'select', id: colorId, value: 'green' }, 4).ok, false);
  assert.equal(f.voice.execute({ type: 'select', id: colorId, value: 'blue' }, 4).ok, true);
  assert.equal(f.voice.execute({ type: 'click', id: f.control(snapshot, 'Join').id }, 4).ok, true); assert.equal(check.checked, true);
  good.removeAttribute('href'); assert.equal(f.voice.execute({ type: 'click', id: f.control(snapshot, 'Official reference').id }, 4).ok, false);
});

test('frame voice protocol verifies sender and nonce, refuses drafts and stale versions, and awaits saved actions', async () => {
  const f = frame(), button = new f.HTMLButtonElement({ type: 'button', 'data-action': '{"type":"support"}' }, 'Support'); f.root.append(button);
  const receive = f.bridge();
  receive('voice.snapshot', { requestId: 1, version: 4 }, { source: {} });
  receive('voice.snapshot', { requestId: 1, version: 4 }, { origin: 'https://elsewhere.test' });
  receive('voice.snapshot', { requestId: 1, version: 4 }, { data: { channel: 'living-space-host', bridgeKey: 'wrong-key', type: 'voice.snapshot', requestId: 1, version: 4 } });
  assert.equal(f.messages.filter(item => item.type === 'voice.result').length, 0);
  receive('voice.snapshot', { requestId: 2, version: 4 });
  const snapshot = f.messages.find(item => item.requestId === 2).surface;
  receive('render', { version: 5, html: '' });
  receive('voice.execute', { requestId: 3, version: 4, action: { type: 'click', id: snapshot.controls[0].id } });
  const action = f.messages.find(item => item.type === 'action'); assert.equal(action.action.type, 'support');
  await Promise.resolve(); assert.equal(f.messages.some(item => item.type === 'voice.result' && item.requestId === 3), false);
  receive('action.result', { requestId: action.requestId, ok: true, version: 5, html: '' });
  await Promise.resolve(); await Promise.resolve();
  assert.equal(f.messages.find(item => item.type === 'voice.result' && item.requestId === 3).ok, true);
  assert.match(f.messages.find(item => item.type === 'voice.result' && item.requestId === 3).message, /The change was saved/);
  receive('voice.execute', { requestId: 4, version: 3, action: { type: 'click', id: snapshot.controls[0].id } });
  assert.equal(f.messages.find(item => item.type === 'voice.result' && item.requestId === 4).ok, false);
  receive('service.configure', { active: false, capabilities: [] }); receive('voice.snapshot', { requestId: 5, version: 5 });
  assert.equal(f.messages.find(item => item.type === 'voice.result' && item.requestId === 5).ok, false);
});

test('dictating and submitting a generated service form follows the private service path', async () => {
  const f = frame(), service = new f.HTMLElement('section', { 'data-service': 'space-agent' }), form = new f.HTMLFormElement(), input = new f.HTMLInputElement({ name: 'message', 'aria-label': 'Tell the artist' }), button = new f.HTMLButtonElement({}, 'Ask artist');
  form.append(input, button); service.append(form); f.root.append(service);
  const receive = f.bridge(); receive('service.configure', { active: true, capabilities: ['space-agent'] });
  receive('voice.snapshot', { requestId: 20, version: 4 });
  const snapshot = f.messages.find(item => item.requestId === 20).surface;
  receive('voice.execute', { requestId: 21, version: 4, action: { type: 'fill', id: f.control(snapshot, 'Tell the artist').id, value: 'Draw a blue lake' } });
  receive('voice.snapshot', { requestId: 23, version: 4 });
  const updated = f.messages.find(item => item.requestId === 23).surface;
  receive('voice.execute', { requestId: 22, version: 4, action: { type: 'click', id: f.control(updated, 'Ask artist').id } });
  await Promise.resolve(); await Promise.resolve();
  assert.equal(f.messages.filter(item => item.type === 'action').length, 0);
  assert.equal(f.messages.find(item => item.type === 'service.draft').value, 'Draw a blue lake');
  const dispatched = f.messages.find(item => item.type === 'service.request');
  const request = dispatched.request;
  assert.equal(request.service, 'space-agent'); assert.equal(request.input.message, 'Draw a blue lake');
  assert.equal(f.messages.some(item => item.type === 'voice.result' && item.requestId === 22), false, 'a click is not an acknowledgement that the service accepted the request');
  receive('service.result', { requestId: dispatched.requestId, ok: true }, { source: {} });
  await Promise.resolve();
  assert.equal(f.messages.some(item => item.type === 'voice.result' && item.requestId === 22), false, 'only the authenticated parent may accept a request');
  receive('service.result', { requestId: dispatched.requestId, ok: true });
  await Promise.resolve(); await Promise.resolve();
  assert.equal(f.messages.find(item => item.type === 'voice.result' && item.requestId === 22).ok, true);
  assert.match(f.messages.find(item => item.type === 'voice.result' && item.requestId === 22).message, /request was accepted/);
  assert.doesNotMatch(f.messages.find(item => item.type === 'voice.result' && item.requestId === 22).message, /saved|completed/);
});

test('rejected service admission cannot become successful voice activation', async () => {
  const f = frame(), service = new f.HTMLElement('section', { 'data-service': 'space-agent' });
  const button = new f.HTMLButtonElement({ type: 'button', 'data-service-operation': 'submit', 'data-service-input': '{"message":"Draw a lake"}' }, 'Ask artist');
  service.append(button); f.root.append(service);
  const receive = f.bridge(); receive('service.configure', { active: true, capabilities: ['space-agent'] });
  receive('voice.snapshot', { requestId: 40, version: 4 });
  const snapshot = f.messages.find(item => item.type === 'voice.result' && item.requestId === 40).surface;
  receive('voice.execute', { requestId: 41, version: 4, action: { type: 'click', id: f.control(snapshot, 'Ask artist').id } });
  const dispatched = f.messages.find(item => item.type === 'service.request');
  receive('service.result', { requestId: dispatched.requestId, ok: false });
  await Promise.resolve(); await Promise.resolve();
  const reply = f.messages.find(item => item.type === 'voice.result' && item.requestId === 41);
  assert.equal(reply.ok, false); assert.match(reply.message, /not accepted/);
  receive('service.result', { requestId: dispatched.requestId, ok: true });
  await Promise.resolve();
  assert.equal(f.messages.filter(item => item.type === 'voice.result' && item.requestId === 41).length, 1, 'a later acknowledgement cannot reverse a failed admission');
});

test('deactivation and capability removal settle pending voice service requests as failures', async () => {
  for (const active of [true, false]) {
    const f = frame(), service = new f.HTMLElement('section', { 'data-service': 'finance-news' });
    const button = new f.HTMLButtonElement({ type: 'button', 'data-service-operation': 'refresh' }, 'Refresh articles');
    service.append(button); f.root.append(service);
    const receive = f.bridge(); receive('service.configure', { active: true, capabilities: ['finance-news'] });
    receive('voice.snapshot', { requestId: 50, version: 4 });
    const snapshot = f.messages.find(item => item.type === 'voice.result' && item.requestId === 50).surface;
    receive('voice.execute', { requestId: 51, version: 4, action: { type: 'click', id: f.control(snapshot, 'Refresh articles').id } });
    assert.equal(f.messages.filter(item => item.type === 'service.request').length, 1);
    receive('service.configure', { active, capabilities: [] });
    await Promise.resolve(); await Promise.resolve();
    assert.equal(f.messages.find(item => item.type === 'voice.result' && item.requestId === 51).ok, false);
  }
});

test('failed generated actions report failure and scroll requests remain bounded', async () => {
  const f = frame(), button = new f.HTMLButtonElement({ type: 'button', 'data-action': '{"type":"support"}' }, 'Support'); f.root.append(button);
  const receive = f.bridge(); receive('voice.snapshot', { requestId: 30, version: 4 });
  const snapshot = f.messages.find(item => item.requestId === 30).surface, id = snapshot.controls[0].id;
  receive('voice.execute', { requestId: 31, version: 4, action: { type: 'click', id } });
  const action = f.messages.find(item => item.type === 'action'); receive('action.result', { requestId: action.requestId, ok: false, version: 4, html: '' });
  await Promise.resolve(); await Promise.resolve();
  assert.equal(f.messages.find(item => item.type === 'voice.result' && item.requestId === 31).ok, false);
  const localId = f.voice.read(4).controls[0].id;
  assert.equal(f.voice.execute({ type: 'scroll', id: localId, amount: 100_000, direction: 'down' }, 4).ok, true);
  assert.equal(button.scrolled.top, 1200);
});

test('releasing an old frame cannot unregister its replacement', () => {
  const old = { read() {}, execute() {} }, current = { read() {}, execute() {} };
  const unregisterOld = registry.registerVoiceFrame(old), unregisterCurrent = registry.registerVoiceFrame(current);
  unregisterOld(); assert.equal(registry.getVoiceFrame(), current);
  unregisterCurrent(); assert.equal(registry.getVoiceFrame(), undefined);
});
