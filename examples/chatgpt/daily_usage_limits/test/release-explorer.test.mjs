import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import vm from 'node:vm';

// Run the actual standalone script without a browser dependency. Browser QA also
// exercises native form controls, keyboard access, and responsive layouts.
const html = readFileSync(new URL('../assets/release-explorer.html', import.meta.url), 'utf8');
function explorer(pathname = '/release-explorer.html') {
  class Element {
    constructor(attributes = {}) {
      Object.assign(this, { value: '', min: '', max: '', step: '1', textContent: '', children: [], style: {}, hidden: false }, attributes);
      this.listeners = new Map(); this.attributes = new Map(Object.entries(attributes));
      this.classList = { add() {}, remove() {}, toggle() {} };
    }
    addEventListener(event, listener) { this.listeners.set(event, listener); }
    setAttribute(key, value) { this.attributes.set(key, value); }
    getAttribute(key) { return this.attributes.get(key); }
    removeAttribute(key) { this.attributes.delete(key); delete this[key]; }
    descendants() { return this.children.flatMap(child => [child, ...child.descendants()]); }
    querySelector(selector) { return this.descendants().find(child => child.id === selector.slice(1)); }
    querySelectorAll(selector) { const key = selector.slice(1, -1); return this.descendants().filter(child => key === 'id' ? child.id : child.attributes.has(key)); }
    cloneNode() { const node = new Element(Object.fromEntries(this.attributes)); node.value = this.value; node.children = this.children.map(child => child.cloneNode()); return node; }
    checkValidity() {
      const value = Number(this.value);
      return this.value !== '' && Number.isFinite(value) && value >= Number(this.min) && value <= Number(this.max) && Number.isInteger(value);
    }
    replaceChildren(...children) { this.children = children; }
    append(child) { this.children.push(child); }
    focus() { document.activeElement = this; }
  }
  const nodes = new Map();
  for (const match of html.matchAll(/<[^!][^>]*\bid="([^"]+)"[^>]*>/g)) {
    const attributes = Object.fromEntries([...match[0].matchAll(/([\w-]+)="([^"]*)"/g)].map(item => [item[1], item[2]]));
    nodes.set(match[1], new Element(attributes));
  }
  nodes.get('preset').value = 'weekly'; nodes.get('unit').value = 'credit';
  const markup = html.slice(html.indexOf('<div id="single-explorer">'), html.indexOf('<section id="comparison"'));
  nodes.get('single-explorer').children = [...markup.matchAll(/\bid="([^"]+)"/g)].map(match => match[1]).filter(id => id !== 'single-explorer').map(id => nodes.get(id));
  const lookup = id => nodes.get(id) ?? [...nodes.values()].flatMap(node => node.descendants()).find(node => node.id === id);
  const document = { getElementById: lookup, createElement: () => new Element() };
  const context = vm.createContext({ document, window: { location: { pathname } }, Intl });
  vm.runInContext(html.match(/<script>([\s\S]*?)<\/script>/)[1], context);
  const get = lookup;
  const set = (id, value, event = id === 'unit' || id === 'preset' ? 'change' : 'input') => { get(id).value = String(value); get(id).listeners.get(event)(); };
  const click = id => get(id).listeners.get('click')();
  const rows = () => get('schedule').children.map(row => row.children.map(cell => cell.textContent));
  return { get, set, click, rows };
}

test('native units start with independent illustrative budgets and preserve each set of inputs', () => {
  const ui = explorer();
  assert.equal(ui.get('released').textContent, '500');
  ui.set('monthly', '2400'); ui.set('used', '125'); ui.click('advance');
  ui.set('unit', 'usd');
  assert.equal(ui.get('monthly').value, '200.00');
  assert.equal(ui.get('released').textContent, '$50.00');
  ui.set('monthly', '350.25'); ui.set('preset', 'custom'); ui.set('start', '100.25'); ui.set('increment', '10.01'); ui.set('interval', '1'); ui.set('used', '0.10'); ui.click('advance');
  assert.equal(ui.get('available').textContent, '$110.16');
  ui.set('unit', 'credit');
  assert.equal(ui.get('monthly').value, '2400');
  assert.equal(ui.get('released').textContent, '1,200');
  assert.equal(ui.get('available').textContent, '1,075');
  ui.set('unit', 'usd');
  assert.equal(ui.get('preset').value, 'custom');
  assert.equal(ui.get('interval').value, '1');
  assert.equal(ui.get('available').textContent, '$110.16');
});

test('daily dollar releases finish at the monthly budget to the cent', () => {
  const ui = explorer(); ui.set('unit', 'usd'); ui.set('preset', 'daily');
  assert.equal(ui.get('released').textContent, '$6.67');
  const rows = ui.rows();
  assert.equal(rows.length, 30);
  assert.deepEqual(rows.at(-1), ['Day 30', '$6.57', '$200.00']);
  ui.set('elapsed', 719); ui.set('used', '199.99');
  assert.equal(ui.get('available').textContent, '$0.01');
  assert.equal(ui.get('advance').disabled, true);
});

test('hourly USD increments and subtraction do not accumulate floating point errors', () => {
  const ui = explorer(); ui.set('unit', 'usd'); ui.set('monthly', '0.30'); ui.set('preset', 'custom'); ui.set('start', '0.10'); ui.set('increment', '0.10'); ui.set('interval', '1');
  assert.deepEqual(ui.rows(), [['Day 1', '$0.10', '$0.10'], ['Day 1 at 01:00', '$0.10', '$0.20'], ['Day 1 at 02:00', '$0.10', '$0.30']]);
  ui.click('advance'); ui.click('advance'); ui.set('used', '0.20');
  assert.equal(ui.get('available').textContent, '$0.10');
  assert.equal(ui.get('equation').textContent, '$0.30 released − $0.20 used = $0.10 available');
});

test('small budgets, rounded final releases, and custom intervals stay within the example month', () => {
  const ui = explorer(); ui.set('unit', 'usd'); ui.set('monthly', '0.01'); ui.set('preset', 'daily');
  assert.deepEqual(ui.rows(), [['Day 1', '$0.01', '$0.01']]);
  assert.equal(ui.get('advance').disabled, true);
  ui.set('monthly', '1.01'); ui.set('preset', 'fortnightly');
  assert.deepEqual(ui.rows(), [['Day 1', '$0.51', '$0.51'], ['Day 15', '$0.50', '$1.01']]);
  ui.set('preset', 'custom'); ui.set('start', '0.01'); ui.set('increment', '0.01'); ui.set('interval', '744');
  assert.deepEqual(ui.rows(), [['Day 1', '$0.01', '$0.01']]);
  assert.match(ui.get('next').textContent, /Unassigned.*\$1\.00/);
  ui.set('interval', '719');
  assert.deepEqual(ui.rows().at(-1), ['Day 30 at 23:00', '$0.01', '$0.02']);
});

test('credit release rounding remains whole-credit and bounded', () => {
  const ui = explorer(); ui.set('preset', 'daily');
  assert.equal(ui.get('released').textContent, '67');
  assert.deepEqual(ui.rows().at(-1), ['Day 30', '57 credits', '2,000 credits']);
});

test('invalid amounts never produce a valid plan or silently round extra precision', () => {
  const ui = explorer();
  for (const value of ['', '0', '-1', '1.5', '1e3', '1000001']) {
    ui.set('monthly', value);
    assert.equal(ui.get('show-plan').disabled, true, value);
    assert.equal(ui.get('released').textContent, 'N/A');
    assert.equal(ui.get('monthly').attributes.get('aria-invalid'), 'true');
  }
  ui.set('unit', 'usd');
  for (const value of ['', '0', '-0.01', '0.001', '1.999', '1e2', '1000000.01']) {
    ui.set('monthly', value);
    assert.equal(ui.get('show-plan').disabled, true, value);
    assert.match(ui.get('monthly-error').textContent, /two decimal places/);
  }
  ui.set('monthly', '.50');
  assert.equal(ui.get('show-plan').disabled, false);
  assert.equal(ui.get('released').textContent, '$0.13');
  ui.set('preset', 'custom'); ui.set('start', '0.001');
  assert.equal(ui.get('released').textContent, 'N/A');
  assert.equal(ui.get('start').attributes.get('aria-invalid'), 'true');
  ui.set('start', '0.10'); ui.set('increment', '0.10'); ui.set('interval', '1.5');
  assert.equal(ui.get('released').textContent, 'N/A');
  ui.set('interval', '1'); ui.set('used', '0.101');
  assert.equal(ui.get('available').textContent, 'N/A');
  ui.set('used', '0.11');
  assert.equal(ui.get('available').textContent, 'N/A');
  ui.set('used', '0.10');
  assert.equal(ui.get('available').textContent, '$0.00');
});

test('unit changes update labels, table amounts, precision, and accessible time feedback', () => {
  const ui = explorer(); ui.set('unit', 'usd'); ui.click('advance');
  for (const id of ['monthly-label', 'start-label', 'increment-label', 'used-label', 'available-label', 'budget-total', 'schedule-caption']) assert.match(ui.get(id).textContent, /USD/, id);
  for (const id of ['monthly','start','increment','used']) assert.equal(ui.get(id).step, '0.01');
  assert.equal(ui.get('problem-zero-2').textContent, '$0.00');
  assert.equal(ui.get('elapsed').attributes.get('aria-valuetext'), 'Day 8');
  assert.deepEqual(ui.rows().at(-1), ['Day 22', '$50.00', '$200.00']);
  ui.click('reset');
  assert.equal(ui.get('released').textContent, '$50.00');
  assert.equal(ui.get('used').value, '0.00');
  ui.set('unit', 'credit');
  assert.equal(ui.get('monthly').step, '1');
});

test('standalone file has no external assets and returns to the correct source or published guide', () => {
  assert.doesNotMatch(html, /<script[^>]+src=|<link[^>]+rel="stylesheet"|—/);
  assert.equal(explorer().get('cookbook-link').href, '../README.md');
  assert.equal(explorer('/cookbook/assets/examples/chatgpt/daily_usage_limits/assets/release-explorer.html').get('cookbook-link').href, '/cookbook/examples/chatgpt/daily_usage_limits/readme');
});


test('Both reuses independent plans and retains edits when returning to a single unit', () => {
  const ui = explorer(); ui.set('unit', 'both');
  assert.equal(ui.get('single-explorer').hidden, true);
  assert.equal(ui.get('comparison').hidden, false);
  assert.equal(ui.get('credit-monthly').value, '2000');
  assert.equal(ui.get('usd-monthly').value, '200.00');
  ui.set('credit-monthly', '3000'); ui.set('usd-monthly', '150.01');
  assert.equal(ui.get('credit-released').textContent, '750');
  assert.equal(ui.get('usd-released').textContent, '$37.51');
  ui.set('usd-preset', 'daily', 'change'); ui.set('usd-used', '0.01');
  assert.equal(ui.get('usd-available').textContent, '$5.00');
  assert.equal(ui.get('credit-released').textContent, '750');
  ui.set('unit', 'usd');
  assert.equal(ui.get('monthly').value, '150.01');
  assert.equal(ui.get('preset').value, 'daily');
  assert.equal(ui.get('available').textContent, '$5.00');
  ui.set('unit', 'credit');
  assert.equal(ui.get('monthly').value, '3000');
  assert.equal(ui.get('released').textContent, '750');
});

test('daily plans preserve every cent across small budgets with uneven portions', () => {
  const ui = explorer(); ui.set('unit', 'usd'); ui.set('preset', 'daily');
  for (let cents = 1; cents <= 100; cents++) {
    ui.set('monthly', (cents / 100).toFixed(2));
    const rows = ui.rows();
    const releasedCents = rows.map(row => Number(row[1].replace(/[^\d]/g, '')));
    assert.equal(releasedCents.reduce((sum, value) => sum + value, 0), cents);
    assert.ok(releasedCents.every(value => value >= 1));
    assert.ok(rows.length <= 30);
    assert.equal(rows.at(-1)[2], `$${(cents / 100).toFixed(2)}`);
  }
});
