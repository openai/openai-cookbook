import test from 'node:test';
import assert from 'node:assert/strict';
import { validateGameBindings, verifyModule } from '../server/runtime.mjs';

const config = { id: 'garden-flight', tickMs: 50 };
const canvas = '<canvas data-game-canvas aria-label="The flight path"></canvas>';
const start = '<button data-game-command="start">Start flying</button>';
const root = content => `<section data-game="garden-flight">${content}</section>`;
const markup = (content = '') => root(canvas + start + content);
const source = html => `
export const meta = {title:'Garden flight',subtitle:'',accent:'#567764',game:${JSON.stringify(config)}};
export function render(state, actor){return ${JSON.stringify(html)}}
export function reduce(state){return state}
export const game = {
  init(saved,actor){return saved || {actorId:actor.id,ticks:0}},
  step(state,action){return {...state,ticks:state.ticks+(action.type==='tick'?1:0)}},
  view(){return {width:320,height:180,objects:[]}}
};`;
const featureTests = 'export function runTests(){return [{name:"Authored tests pass",ok:true}]}';
const state = () => ({projects:[],contributions:[],extras:{}});

test('accepts game-specific controls without prescribing game mechanics or authored tabindex', () => {
  const actions = '<button data-game-action=\'{"type":"flap","strength":2}\' data-game-keys="Space ArrowUp">Flap</button>'
    + '<button data-game-action=\'{"type":"flap","strength":2}\'>Touch to flap</button>';
  assert.deepEqual(validateGameBindings(markup(actions), config), { actions: [{ action: {type:'flap',strength:2}, label:'Flap' }] });
  assert.deepEqual(validateGameBindings(markup(), config), {actions:[]}, 'Automatic games need no directional controls');
});

test('only the matching live root can supply a game surface', () => {
  for (const html of ['<p>No game here</p>', markup().replace('data-game="garden-flight"', 'data-game="typo"'), markup() + markup(), markup() + '<section data-game="other"></section>']) {
    assert.throws(() => validateGameBindings(html, config), /exactly one rendered.*garden-flight.*root/);
  }
});

test('inert examples and attribute text cannot stand in for the playable game', () => {
  for (const html of [
    `<!-- ${markup()} -->`, `<template>${markup()}</template>`, `<textarea>${markup()}</textarea>`,
    `<style>.example:after{content:'${markup()}'}</style>`, `<div title='${markup().replaceAll("'", '&#39;')}'></div>`,
    markup().replaceAll('<', '&lt;').replaceAll('>', '&gt;'),
  ]) assert.throws(() => validateGameBindings(html, config), /exactly one rendered/);
  assert.deepEqual(validateGameBindings(markup() + `<template>${markup()}</template><!-- ${markup()} -->`, config), {actions:[]});
});

test('requires an owned canvas element rather than an unrelated canvas or lookalike hook', () => {
  assert.throws(() => validateGameBindings(root(start), config), /requires a <canvas data-game-canvas>/);
  assert.throws(() => validateGameBindings(canvas + root(start), config), /orphan canvas/);
  assert.throws(() => validateGameBindings(root('<div data-game-canvas></div>' + start), config), /canvas/);
  assert.throws(() => validateGameBindings(root(canvas + start + '<div data-game-canvas></div>'), config), /must be placed on a canvas/);
});

test('rejects controls and readouts detached from the declared game root', () => {
  for (const detached of [start, '<button data-game-action=\'{"type":"jump"}\'>Jump</button>', '<span data-game-value="score">0</span>', '<p data-game-runtime-status></p>']) {
    assert.throws(() => validateGameBindings(markup() + detached, config), /orphan canvas, controls, and readouts/);
  }
});

test('requires Start to be a labeled and enabled native control', () => {
  for (const control of ['', '<div data-game-command="start">Start</div>', '<button data-game-command="start" disabled>Start</button>', '<button data-game-command="start" aria-disabled="true">Start</button>', '<button data-game-command="start"></button>', '<button style="display:none" data-game-command="start">Start</button>', '<fieldset disabled>' + start + '</fieldset>', '<div hidden>' + start + '</div>']) {
    assert.throws(() => validateGameBindings(root(canvas + control), config), /native|Start control/);
  }
});

test('accepts native runtime button normalization, accessible labels, and lifecycle state presentation', () => {
  for (const control of [
    '<button type="submit" data-game-command="start"><span>Start flying</span></button>',
    '<input type="button" value="Start flying" data-game-command="start">',
    '<button aria-label="Start flying" data-game-command="start"></button>',
    '<span id="play-label"><strong>Start flying</strong></span><button aria-labelledby="play-label" data-game-command="start"></button>',
    '<button data-game-command="start" hidden>Start flying</button>',
    '<fieldset disabled><legend><button data-game-command="start">Start flying</button></legend></fieldset>',
    '<label for="start-flight">Start flying</label><input id="start-flight" type="button" data-game-command="start">',
  ]) assert.deepEqual(validateGameBindings(root(canvas + control), config), {actions:[]});
  assert.deepEqual(validateGameBindings(markup('<button hidden data-game-command="pause">Pause</button><button hidden data-game-command="resume">Resume</button><button data-game-command="restart">Again</button>'), config), {actions:[]});
});

test('requires a playable HTML container outside services and unavailable ancestors', () => {
  for (const html of [
    `<div data-service="space-agent">${markup()}</div>`, `<div hidden>${markup()}</div>`,
    `<div inert>${markup()}</div>`, `<div aria-hidden="true">${markup()}</div>`,
    markup().replace('<section', '<section hidden'), markup().replace('<section', '<section tabindex="not-a-number"'),
    `<svg>${markup()}</svg>`, markup().replaceAll('section', 'button'), `<select>${markup()}</select>`,
    `<div style="display: none">${markup()}</div>`,
  ]) assert.throws(() => validateGameBindings(html, config), /HTML container|available to players|numeric tabindex/);
  assert.deepEqual(validateGameBindings(markup().replace('<section', '<section tabindex="-1"'), config), {actions:[]}, 'Programmatic focus still supports game controls');
});

test('implicit HTML paragraph closure cannot leave required controls outside the game root', () => {
  const html = '<p data-game="garden-flight">' + canvas + '<div>' + start + '</div></p>';
  assert.throws(() => validateGameBindings(html, config), /orphan/);
});

test('nested lists retain a game rooted in an outer list item or definition', () => {
  const list = '<ul><li data-game="garden-flight">'+canvas+'<ul><li>Arrow keys move</li></ul>'+start+'</li></ul>';
  const definitions = '<dl><dt>Flight</dt><dd data-game="garden-flight">'+canvas+'<dl><dt>Controls</dt><dd>Arrow keys</dd></dl>'+start+'</dd></dl>';
  assert.deepEqual(validateGameBindings(list,config),{actions:[]});
  assert.deepEqual(validateGameBindings(definitions,config),{actions:[]});
});

test('rejects unsupported and ambiguous lifecycle controls with repair guidance', () => {
  for (const control of ['<button data-game-command="play">Play</button>', '<button data-game-command="action">Jump</button>', '<button data-game-command="">Play</button>']) {
    assert.throws(() => validateGameBindings(markup(control), config), /supports only start, pause, resume, or restart/);
  }
  assert.throws(() => validateGameBindings(markup('<button data-game-command="start" data-game-action=\'{"type":"jump"}\'>Start</button>'), config), /either data-game-command or data-game-action/);
});

test('rejects action payloads the frame would silently ignore', () => {
  const bad = ['broken', '[]', 'null', '"jump"', '{}', '{"type":""}', '{"type":"tick"}', '{"type":"jump now"}', '{"type":"jump","x":1e999}', '{"type":"jump","__proto__":{}}', '{"type":"jump","options":{"constructor":true}}', JSON.stringify({type:'jump',text:'x'.repeat(8000)})];
  let deep = {type:'jump',options:{}};
  let next = deep.options;
  for (let index = 0; index < 12; index++) next = next.child = {};
  bad.push(JSON.stringify(deep));
  for (const raw of bad) assert.throws(() => validateGameBindings(markup(`<button data-game-action='${raw}'>Jump</button>`), config), /data-game-action/);
});

test('accepts entity-encoded JSON and the browser first-attribute-wins rule', () => {
  const html = markup('<button data-game-action="{&quot;type&quot;:&quot;flap&quot;,&quot;text&quot;:&quot;up &amp; away&quot;}">Flap</button>')
    .replace('data-game="garden-flight"', 'data-game="garden&#45;flight" data-game="wrong"');
  assert.deepEqual(validateGameBindings(html, config).actions, [{action:{type:'flap',text:'up & away'},label:'Flap'}]);
});

test('key bindings attach to semantic action controls instead of inert markup or lifecycle commands', () => {
  for (const control of ['<span data-game-keys="ArrowLeft">Left</span>', '<button data-game-command="pause" data-game-keys="p">Pause</button>', '<button data-game-action=\'{"type":"jump"}\' data-game-keys=" ">Jump</button>']) {
    assert.throws(() => validateGameBindings(markup(control), config), /data-game-keys requires/);
  }
});

test('held controls expose validated release actions and reject unpaired or oversized payloads', () => {
  const held = '<button data-game-action=\'{"type":"move","axis":-1}\' data-game-release=\'{"type":"move","axis":0}\' data-game-keys="ArrowLeft">Move left</button>';
  assert.deepEqual(validateGameBindings(markup(held),config).actions,[{action:{type:'move',axis:-1},label:'Move left',release:{type:'move',axis:0}}]);
  for(const control of [
    '<button data-game-release=\'{"type":"move","axis":0}\'>Stop</button>',
    '<button data-game-command="pause" data-game-release=\'{"type":"move","axis":0}\'>Pause</button>',
    held.replace('{"type":"move","axis":0}','{"type":"tick"}'),
    held.replace('{"type":"move","axis":0}','not-json'),
    held.replace('{"type":"move","axis":0}',JSON.stringify({type:'move',data:'x'.repeat(4096)})),
  ]) assert.throws(()=>validateGameBindings(markup(control),config),/data-game-release/);
  assert.throws(()=>validateGameBindings(markup('<button data-game-action=\''+JSON.stringify({type:'move',data:'x'.repeat(4096)})+'\'>Move</button>'),config),/4096/);
});

test('ordinary publication cannot bypass missing bindings with always-passing authored tests', async () => {
  const result = await verifyModule(source('<p>A game without playable controls.</p>'), featureTests, state());
  assert.equal(result.ok, false);
  assert.ok(result.checks.some(check => !check.ok && /data-game.*root/.test(check.message)), JSON.stringify(result.checks));
});

test('ordinary publication verifies rendered bindings for both owner and visitor', async () => {
  const valid = await verifyModule(source(markup('<button data-game-action=\'{"type":"flap"}\'>Flap</button>')), featureTests, state());
  assert.equal(valid.ok, true, JSON.stringify(valid.checks));
  const visitorMissing = source(markup()).replace('return "<section', 'return actor.id!=="mira" ? "<p>No visitor controls</p>" : "<section');
  const invalid = await verifyModule(visitorMissing, featureTests, state());
  assert.equal(invalid.ok, false);
  assert.ok(invalid.checks.some(check => !check.ok && /[Vv]isitor/.test(check.name) && /root/.test(check.message)), JSON.stringify(invalid.checks));
});
