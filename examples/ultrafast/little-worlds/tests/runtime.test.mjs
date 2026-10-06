import test from 'node:test';
import assert from 'node:assert/strict';
import { compileModule, renderModule, reduceModule, verifyModule } from '../server/runtime.mjs';
import { actors, initialState, seedSource, seedTests } from '../server/seed.mjs';

const clone = value => structuredClone(value);
const supportSource = `
export const meta = { title: 'Choose what grows', subtitle: 'One little nudge.', accent: '#567764', budget: 1 };
export function render(state, actor) {
  return '<div>' + state.projects.map(p => '<button>' + p.title + '</button>').join('') + '</div>';
}
export function reduce(state, action, actor) {
  if (action.type !== 'support') throw new Error('Unknown action');
  if (!state.projects.some(p => p.id === action.projectId)) throw new Error('Unknown project');
  if (state.contributions.some(c => c.actorId === actor.id)) throw new Error('You already supported a project.');
  state.contributions.push({id: actor.id + '-support', actorId: actor.id, projectId: action.projectId, points: 1});
  return state;
}`;

const supportTests = `export function runTests(api) {
  const guest = {id:'isolated-guest', name:'Guest'};
  const next = api.reduce(api.initialState, {type:'support', projectId:'tidepool'}, guest);
  let limited = false;
  try { api.reduce(next, {type:'support', projectId:'smallhours'}, guest); } catch { limited = true; }
  return [
    {name:'New guest can support a project', ok:next.contributions.some(c => c.actorId === guest.id && c.points === 1)},
    {name:'Second support is rejected', ok:limited},
    {name:'Existing contributions survive', ok:api.initialState.contributions.every(c => next.contributions.some(n => n.id === c.id && n.points === c.points))}
  ];
}`;

function sourceWithReducer(body) {
  return `${seedSource.slice(0, seedSource.indexOf('export function reduce'))}\nexport function reduce(state, action, actor) { ${body} }`;
}

function sourceWithHtml(html) {
  return `export const meta={title:'x',subtitle:'',accent:'#123456'}; export function render(){return ${JSON.stringify(html)}}; export function reduce(s){return s}`;
}

test('seed compiles, renders, and verifies with real isolated checks', async () => {
  const result = await verifyModule(seedSource, seedTests, clone(initialState));
  assert.equal(result.ok, true, JSON.stringify(result.checks));
  assert.equal(result.meta.accent, '#04b84c');
  assert.ok(result.checks.length >= 8);
  assert.match(await renderModule(result.bundle, initialState, actors.mira), /room to play/);
});

test('supports independent visitors while preserving host input and previous contributions', async () => {
  const { bundle } = await compileModule(supportSource);
  const state = clone(initialState);
  const snapshot = clone(state);
  const next = await reduceModule(bundle, state, { type: 'support', projectId: 'tidepool' }, actors.leo);
  assert.deepEqual(state, snapshot, 'a mutating generated reducer cannot mutate host state');
  assert.equal(next.contributions.length, 1);
  const nextAgain = await reduceModule(bundle, next, { type: 'support', projectId: 'smallhours' }, actors.mira);
  assert.deepEqual(nextAgain.contributions[0], next.contributions[0]);
  assert.equal(nextAgain.contributions.length, 2);
  await assert.rejects(reduceModule(bundle, next, { type: 'support', projectId: 'afterhours' }, actors.leo), /already supported/);
});

test('feature behavior tests execute against the current populated state', async () => {
  const state = clone(initialState);
  state.contributions.push({ id: 'leo-support', actorId: 'leo', projectId: 'afterhours', points: 1 });
  const result = await verifyModule(supportSource, supportTests, state);
  assert.equal(result.ok, true, JSON.stringify(result.checks));
  assert.deepEqual(state.contributions, [{ id: 'leo-support', actorId: 'leo', projectId: 'afterhours', points: 1 }]);
  assert.ok(result.checks.some(check => check.name === 'Second support is rejected' && check.ok));
});

test('publishing a budget change retains contributions, then enforces the new budget', async () => {
  const { bundle: first } = await compileModule(supportSource);
  const state = await reduceModule(first, initialState, { type: 'support', projectId: 'tidepool' }, actors.leo);
  const upgraded = supportSource
    .replace('budget: 1', 'budget: 3')
    .replace("if (state.contributions.some(c => c.actorId === actor.id)) throw new Error('You already supported a project.');", "if (state.contributions.filter(c => c.actorId === actor.id).reduce((sum,c) => sum+c.points,0) >= 3) throw new Error('All three points used.');")
    .replace("id: actor.id + '-support'", "id: actor.id + '-' + state.contributions.length");
  const { bundle: second } = await compileModule(upgraded);
  const afterRender = clone(state);
  await renderModule(second, state, actors.leo);
  assert.deepEqual(state, afterRender);
  let next = await reduceModule(second, state, { type: 'support', projectId: 'smallhours' }, actors.leo);
  next = await reduceModule(second, next, { type: 'support', projectId: 'afterhours' }, actors.leo);
  assert.deepEqual(next.contributions[0], state.contributions[0]);
  assert.equal(next.contributions.reduce((sum, c) => sum + c.points, 0), 3);
  await assert.rejects(reduceModule(second, next, { type: 'support', projectId: 'tidepool' }, actors.leo), /three points/);
});

test('rejects any edit or removal of existing project records', async () => {
  for (const body of ["state.projects[0].title = 'Changed'; return state;", 'state.projects.pop(); return state;']) {
    const { bundle } = await compileModule(sourceWithReducer(body));
    await assert.rejects(reduceModule(bundle, initialState, { type: 'support' }, actors.leo), /projects must be preserved/);
  }
});

test('rejects deletion, modification, ownership change, or invention of another visitor’s contribution', async () => {
  const state = clone(initialState);
  state.contributions.push({ id: 'mira-support', actorId: 'mira', projectId: 'tidepool', points: 1 });
  const mutations = [
    'state.contributions = []; return state;',
    'state.contributions[0].points = 10; return state;',
    "state.contributions[0].actorId = 'leo'; return state;",
    "state.contributions.push({id:'new',actorId:'mira',projectId:'afterhours',points:1}); return state;",
  ];
  for (const body of mutations) {
    const { bundle } = await compileModule(sourceWithReducer(body));
    await assert.rejects(reduceModule(bundle, state, { type: 'support' }, actors.leo), /own contributions|ownership/);
  }
});

test('rejects malformed contributions and non-JSON state', async () => {
  const mutations = [
    "state.contributions.push({id:'a',actorId:actor.id,projectId:'missing',points:1}); return state;",
    "state.contributions.push({id:'a',actorId:actor.id,projectId:'tidepool',points:0}); return state;",
    "state.contributions.push({id:'a',actorId:actor.id,projectId:'tidepool',points:NaN}); return state;",
    'state.extras.self = state; return state;',
    'return Promise.resolve(state);',
  ];
  for (const body of mutations) {
    const { bundle } = await compileModule(sourceWithReducer(body));
    await assert.rejects(reduceModule(bundle, initialState, { type: 'support' }, actors.leo), /unknown project|whole numbers|JSON|cycles|requires/);
  }
});

test('rendering cannot mutate saved data or add executable markup', async () => {
  const mutable = seedSource.replace("return '<style>", "state.extras.changed = true; return '<style>");
  const { bundle: mutation } = await compileModule(mutable);
  await assert.rejects(renderModule(mutation, initialState, actors.leo), /must not change/);
  for (const html of ['<script>alert(1)</script>', '<button onclick="alert(1)">Go</button>', '<iframe src="about:blank"></iframe>', '<img src="https://example.com/beacon">']) {
    const source = `export const meta={title:'x',subtitle:'',accent:'#123456'}; export function render(){return ${JSON.stringify(html)}}; export function reduce(s){return s}`;
    const { bundle } = await compileModule(source);
    await assert.rejects(renderModule(bundle, initialState, actors.mira), /executable|data-action|external/);
  }
});

test('escaped visitor wishes and ordinary text are not treated as executable markup', async () => {
  const safe = [
    '<p>&lt;img src=x onerror=alert(1)&gt;</p>',
    '<p>onboarding=done; javascript: is a URL scheme; src=https://example.com is text.</p>',
    '<p>&lt;script&gt;alert(1)&lt;/script&gt;</p>',
    '<button data-action=\'{"type":"wish","text":"onerror=alert(1) and javascript:"}\'>Plant wish</button>',
    '<div title="A > B, onerror=not-an-attribute, javascript: text">A wish</div>',
    '<textarea>Type a wish. Examples: <img src=x onerror=alert(1)></textarea>',
    '<style>.label:after{content:"onerror=words <img src=x onerror=words>"}</style><p>A wish</p>',
    '<!-- A documented example: <img src=x onerror=alert(1)> --><p>A wish</p>',
  ];
  for (const html of safe) {
    const source = `export const meta={title:'x',subtitle:'',accent:'#123456'}; export function render(){return ${JSON.stringify(html)}}; export function reduce(s){return s}`;
    const { bundle } = await compileModule(source);
    assert.equal(await renderModule(bundle, initialState, actors.leo), html);
  }
});

test('an unfinished stylesheet cannot pass publication even when generated feature tests pass', async () => {
  const broken = '<style>.tile{display:grid;color:#38634a} }] <main><button data-action=\'{"type":"support"}\'>Fern House</button></main>';
  const featureTests = `export function runTests(){return [{name:'Project is configured',ok:true}]}`;
  const result = await verifyModule(sourceWithHtml(broken), featureTests, initialState);
  assert.equal(result.ok, false, 'unclosed style consumes the tile and the trusted host markup');
  assert.ok(result.checks.some(check => !check.ok && /style|incomplete/i.test(check.message)), JSON.stringify(result.checks));
  const repaired = broken.replace(' }]', '</style>');
  const repairedResult = await verifyModule(sourceWithHtml(repaired), featureTests, initialState);
  assert.equal(repairedResult.ok, true, JSON.stringify(repairedResult.checks));
});

test('incomplete text elements and markup cannot consume the trusted host suffix', async () => {
  const incomplete = [
    '<style>.tile{color:green}',
    '<style>.tile{color:green}</stylesheet>',
    '<style/>.tile{color:green}',
    '<style>.tile{color:green}</style',
    '<style>.tile{color:green}</style title="unfinished >',
    ...['textarea', 'title', 'xmp', 'noembed', 'noframes', 'noscript'].map(tag => `<${tag}>Text`),
    '<form',
    '<button data-action=',
    '<button aria-label="Unfinished > <main>text</main>',
    "<button aria-label='Unfinished >",
    '<div></div',
    '<div></div title="unfinished >',
    '<!-- unfinished comment >',
    '<!unfinished declaration',
    '<!DOCTYPE html PUBLIC "unfinished',
    '<?unfinished instruction',
    '<svg><![CDATA[unfinished text ></svg>',
    '<template><button>Example</button>',
    '<template><template></template>',
    '<template><svg><template></template></svg>',
    '<plaintext>Text</plaintext>',
    '<svg><foreignObject><style>.tile{color:green}</foreignObject></svg>',
    '<svg><desc><textarea></svg>',
    '<math><mtext><textarea></math>',
    '<math><annotation-xml encoding="text&#x2f;html"><style></math>',
    '<svg><p><style></svg>',
    '<svg><foreignObject><template></svg>',
  ];
  for (const html of incomplete) {
    const { bundle } = await compileModule(sourceWithHtml(html));
    await assert.rejects(renderModule(bundle, initialState, actors.leo), /incomplete|plaintext/i, html);
  }
});

test('complete HTML, CSS, SVG, and optional end tags remain renderable', async () => {
  const complete = [
    '<style>.tile::after{content:"<button title=\'example\'> & >"}@media(width > 10px){.tile{color:green}}</STYLE ><main>Fern House</main>',
    '<div title="A < B and C > D" data-label=\'say "hello"\'>Text</div>',
    '<p>One<p>Two<ul><li>First<li>Second</ul><br><input value="">',
    '<select><option>First<option>Second</select>',
    'A < B and C > D. A final less-than sign: <',
    '<textarea>&lt;button&gt; Text</textarea><title>Fern House</title>',
    '<template><article>Example</article><template><span>Nested</span></template></template>',
    '<svg viewBox="0 0 10 10"><title>Fern House</title><style>.leaf{fill:green}</style><path class="leaf" d="M0 0L10 10"/></svg>',
    '<svg><title/><style/><path d="M0 0"/></svg>',
    '<svg><style><![CDATA[.leaf::after{content:"<example>"}]]></style></svg>',
    '<svg><foreignObject><style>.leaf::after{content:"<button title=\'example\'>"}</style><p>Fern</p></foreignObject></svg>',
    '<!-- example <unfinished -->Text',
    '<!doctype html><p>Text</p>',
    '<!doctype html PUBLIC "example public" "example system"><p>Text</p>',
  ];
  for (const html of complete) {
    const { bundle } = await compileModule(sourceWithHtml(html));
    assert.equal(await renderModule(bundle, initialState, actors.leo), html);
  }
});

test('markup-aware checks still block actual handlers, script tags, and resource URLs', async () => {
  const unsafe = [
    '<img src=x onerror=alert(1)>',
    '<svg/onload=alert(1)>',
    '<div title="safe > words" onclick="alert(1)">A wish</div>',
    '<div title=bad"quote><script>alert(1)</script></div>',
    '<textarea>Safe text</textarea><img src=x onerror=alert(1)>',
    '<svg><title><img src=x onerror=alert(1)></title></svg>',
    '<svg><style><img src=x onerror=alert(1)></style></svg>',
    '<svg><foreignObject><style><img src=x onerror=alert(1)></style></foreignObject></svg>',
    '<math><annotation-xml encoding="text&SOL;html"><style><img src=x onerror=alert(1)></style></annotation-xml></math>',
    '<math><annotation-xml encoding="text&#38;sol;html"><style><img src=x onerror=alert(1)></style></annotation-xml></math>',
    '<math><annotation-xml encoding="text&#x26;sol;html"><style><img src=x onerror=alert(1)></style></annotation-xml></math>',
    '<math><annotation-xml><svg><mtext><style><img src=x onerror=alert(1)></style></mtext></svg></annotation-xml></math>',
    '<div><svg><foreignObject><span></div></span></foreignObject><style><img src=x onerror=alert(1)></style></svg>',
    '<svg><title/></svg><img src=x onerror=alert(1)>',
    '<svg><![CDATA[<img src=x onerror=example>]]></svg><img src=x onerror=alert(1)>',
    '<![CDATA[<img src=x onerror=example>]]><img src=x onerror=alert(1)>',
    '<!DOCTYPE html><img src=x onerror=alert(1)>',
    '<?example "><img src=x onerror=alert(1)>',
    '<a href="javascript:alert(1)">Go</a>',
    '<a href="java&#x73;cript&colon;alert(1)">Go</a>',
    '<a href="java\tscript:alert(1)">Go</a>',
    '<a href="java&Tab;&NewLine;script&colon;alert(1)">Go</a>',
    '<img src="https://example.com/beacon">',
    '<img src="&#x68;ttps://example.com/beacon">',
    '<img srcset="data:image/png;base64,x 1x, https://example.com/beacon 2x">',
    '<svg><image xlink:href="//example.com/beacon" /></svg>',
  ];
  for (const html of unsafe) {
    const source = `export const meta={title:'x',subtitle:'',accent:'#123456'}; export function render(){return ${JSON.stringify(html)}}; export function reduce(s){return s}`;
    const { bundle } = await compileModule(source);
    await assert.rejects(renderModule(bundle, initialState, actors.leo), /executable|data-action|external/);
  }
});

test('malformed doctypes cannot conceal active markup behind bogus quotes', async () => {
  for (const html of [
    '<!DOCTYPE \'> <img src=x onerror=alert(1)> \'>',
    '<!DOCTYPE html PUBLIC "><img src=x onerror=alert(1)>">',
    '<!DOCTYPE html SYSTEM "><img src=x onerror=alert(1)>">',
  ]) {
    const { bundle } = await compileModule(sourceWithHtml(html));
    await assert.rejects(renderModule(bundle, initialState, actors.leo), /data-action/);
  }
});

test('foreign content remains conservatively inspected inside select controls', async () => {
  for (const html of [
    '<select><svg><![CDATA[></select><img src=x onerror=alert(1)>]]></svg>',
    '<select><svg><foreignObject><style></select><img src=x onerror=alert(1)></style></foreignObject></svg>',
    '<select><math><mtext><style></select><img src=x onerror=alert(1)></style></mtext></math>',
  ]) {
    const { bundle } = await compileModule(sourceWithHtml(html));
    await assert.rejects(renderModule(bundle, initialState, actors.leo), /data-action/);
  }
});

test('imports and dynamic imports fail before execution', async () => {
  for (const prefix of ["import fs from 'node:fs';", "import './secret.js';", "const leak = import('node:fs');", "export * from './secret.js';"]) {
    await assert.rejects(compileModule(`${prefix}\n${seedSource}`), /[Ii]mports/);
  }
});

test('isolated source cannot access Node, credentials, network, or timers', async () => {
  const source = `${seedSource}\nif ([typeof process, typeof fetch, typeof WebSocket, typeof setTimeout].some(t=>t!=='undefined')) throw new Error('Host access leaked');`;
  await compileModule(source);
  const { bundle } = await compileModule(sourceWithReducer('fetch("https://example.com"); return state;'));
  await assert.rejects(reduceModule(bundle, initialState, { type: 'support' }, actors.mira), /fetch.*not defined/);
});

test('infinite loops are interrupted and the runtime remains usable', async () => {
  const { bundle } = await compileModule(sourceWithReducer('while (true) {}'));
  const start = performance.now();
  await assert.rejects(reduceModule(bundle, initialState, { type: 'support' }, actors.mira), /time limit/);
  assert.ok(performance.now() - start < 2000);
  const good = await compileModule(seedSource);
  assert.match(await renderModule(good.bundle, initialState, actors.mira), /room to play/);
});

test('unbounded allocations cannot consume the host heap', async () => {
  const { bundle } = await compileModule(sourceWithReducer('const all=[]; while(true) all.push(new Array(100000).fill("many"));'));
  let heartbeat = false;
  const timer = setTimeout(() => { heartbeat = true; }, 20);
  const pending = reduceModule(bundle, initialState, { type: 'support' }, actors.mira);
  await new Promise(resolve => setTimeout(resolve, 60));
  assert.equal(heartbeat, true, 'host event loop stays responsive during an allocation attack');
  clearTimeout(timer);
  await assert.rejects(pending, /memory limit|time limit/);
});

test('fresh contexts prevent globals leaking between renders', async () => {
  const source = `export const meta={title:'x',subtitle:'',accent:'#123456'}; export function render(){globalThis.views=(globalThis.views||0)+1;return '<p>'+globalThis.views+'</p>'}; export function reduce(s){return s}`;
  const { bundle } = await compileModule(source);
  assert.equal(await renderModule(bundle, initialState, actors.mira), '<p>1</p>');
  assert.equal(await renderModule(bundle, initialState, actors.mira), '<p>1</p>');
});

test('host validation cannot be disabled by generated code', async () => {
  const source = `${sourceWithReducer('state.contributions=[]; return state;')}\nglobalThis.validateTransition=()=>{};`;
  const state = clone(initialState);
  state.contributions.push({ id: 'mira-1', actorId: 'mira', projectId: 'tidepool', points: 1 });
  const { bundle } = await compileModule(source);
  await assert.rejects(reduceModule(bundle, state, { type: 'support' }, actors.leo), /own contributions/);
});

test('render results remain bounded strings and host-validated after isolated serialization', async () => {
  const cases = [
    ["return {toJSON(){return '<main>Not a string</main>'}}", /HTML string/],
    ["return 'x'.repeat(180001)", /too large/],
    ["globalThis.validateHtml=()=>{}; return '<button onclick=\"alert(1)\">Go</button>'", /inline JavaScript/],
    ["const stringify=JSON.stringify; JSON.stringify=value=>value==='<main>Safe before serialization</main>'?stringify('<script>alert(1)</script>'):stringify(value); return '<main>Safe before serialization</main>'", /executable/],
  ];
  for (const [body, expected] of cases) {
    const source = `export const meta={title:'Boundary',subtitle:'',accent:'#123456'};
      export function render(){${body}} export function reduce(state){return state}`;
    const { bundle } = await compileModule(source);
    await assert.rejects(renderModule(bundle, initialState, actors.mira), expected);
  }
});

test('a runaway render is interrupted and a later valid render still succeeds', async () => {
  const source = `export const meta={title:'Runaway',subtitle:'',accent:'#123456'};
    export function render(){while(true){}} export function reduce(state){return state}`;
  const { bundle } = await compileModule(source);
  const start = performance.now();
  await assert.rejects(renderModule(bundle, initialState, actors.mira), /time limit/);
  assert.ok(performance.now() - start < 2000);
  const good = await compileModule(seedSource);
  assert.match(await renderModule(good.bundle, initialState, actors.mira), /room to play/);
});

test('a false, empty, malformed, or timed-out generated test blocks publication', async () => {
  const failures = [
    'export function runTests(){return [{name:"Incorrect rule",ok:false,message:"Budget was not enforced"}]}',
    'export function runTests(){return []}',
    'export function runTests(){return [{name:"Pretend",ok:"true"}]}',
    'export function runTests(){while(true){}}',
  ];
  for (const tests of failures) {
    const result = await verifyModule(seedSource, tests, initialState);
    assert.equal(result.ok, false);
    assert.ok(result.checks.some(check => check.ok === false));
  }
});

test('bad source, invalid actors, and oversized input fail cleanly', async () => {
  assert.equal((await verifyModule('not valid {', seedTests, initialState)).ok, false);
  await assert.rejects(compileModule(' '.repeat(96_001) + seedSource), /too large/);
  const { bundle } = await compileModule(seedSource);
  await assert.rejects(renderModule(bundle, initialState, { id: 'a/b', name: 'Visitor' }), /participant/);
  await assert.rejects(reduceModule(bundle, initialState, { type: 'support', detail: 'x'.repeat(17_000) }, actors.mira), /too large/);
});
