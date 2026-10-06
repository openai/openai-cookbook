import test from 'node:test';
import assert from 'node:assert/strict';
import { verifyModule } from '../server/runtime.mjs';

const owner = { id: 'mira', name: 'Mira' };
const visitor = { id: 'leo', name: 'Leo' };
const liveState = () => ({
  projects: [], contributions: [],
  extras: {
    arcade: { mira: { actorId: 'mira', x: 7, ticks: 4 }, leo: { actorId: 'leo', x: 9, ticks: 2 } },
    notes: { mira: { actorId: 'mira', text: 'Keep my other feature' }, erica: { actorId: 'erica', text: 'Keep another person' } },
  },
});
const checkpoint = `return {...state,extras:{...state.extras,arcade:{...state.extras.arcade,[actor.id]:action.game}}};`;
const step = `if(action.type==='tick')return {...state,x:state.x+1,ticks:state.ticks+1};
  if(action.type==='launch')return {...state,x:state.x+10};throw Error('Unknown control');`;
const markup = `<section data-game="arcade" aria-label="Arcade"><canvas data-game-canvas aria-label="Play area"></canvas><button data-game-command="start">Start game</button><button data-game-action='{"type":"launch"}' aria-label="Launch game">Launch game</button></section>`;
const moduleSource = ({ save = true, saveBody = checkpoint, stepBody = step, initBody } = {}) => `
export const meta={title:'An interactive arcade',subtitle:'',accent:'#687957',layout:'canvas',game:{id:'arcade',tickMs:50${save ? ",saveAction:'save_game'" : ''}}};
export function render(){return ${JSON.stringify(markup)};}
export function reduce(state,action,actor){if(action.type!=='save_game'||action.game.actorId!==actor.id)throw Error('Invalid checkpoint');${saveBody}}
export const game={
  init(saved,actor){${initBody || 'return saved?{...saved}:{actorId:actor.id,x:0,ticks:0};'}},
  step(state,action){${stepBody}},
  view(state){return {width:300,height:200,objects:[{id:'player',type:'circle',x:state.x,y:50,radius:7}],values:{score:state.x}};}
};`;
const behaviorTests = `export function runTests(api){
  const actor={id:'feature-player',name:'Player'},initial=api.gameInit(null,actor);
  const next=api.gameStep(initial,{type:'tick',deltaMs:50},actor);
  let rejected=false;try{api.gameStep(initial,{type:'unknown'},actor)}catch{rejected=true;}
  return [
    {name:'A new player owns their game',ok:initial.actorId===actor.id},
    {name:'Ticks move the player',ok:next.x===initial.x+1},
    {name:'The scene follows the simulation',ok:api.gameView(next,actor).objects[0].x===next.x},
    {name:'Unknown controls are rejected',ok:rejected}
  ];
}`;
const verify = (options, state = liveState(), tests = behaviorTests) => verifyModule(moduleSource(options), tests, state, { owner, visitor });
const failedChecks = result => result.checks.filter(check => !check.ok);

test('publication exercises fresh and returning player checkpoints without changing live data', async () => {
  const state = liveState(), before = structuredClone(state);
  const result = await verify({}, state);
  assert.equal(result.ok, true, JSON.stringify(failedChecks(result)));
  for (const name of ['Owner', 'Visitor']) {
    assert.ok(result.checks.some(check => check.name === `${name} game checkpoints preserve progress and unrelated data` && check.ok));
  }
  assert.deepEqual(state, before);
});

test('a checkpoint that silently keeps an old valid record cannot publish', async () => {
  const result = await verify({ saveBody: 'return state;' });
  assert.equal(result.ok, false);
  assert.equal(failedChecks(result).filter(check => /checkpoints/.test(check.name)).length, 2);
  assert.match(failedChecks(result)[0].message, /complete game record/);
});

test('checkpoint validation catches partial records and changes to another feature owned by the same player', async () => {
  const partial = await verify({ saveBody: checkpoint.replace('action.game}}', '{actorId:actor.id,x:action.game.x}}}') });
  assert.equal(partial.ok, false, 'Dropping simulation fields cannot be reported as saved');
  assert.ok(failedChecks(partial).some(check => /complete game record/.test(check.message)));
  const otherFeature = await verify({ saveBody: `state.extras.notes[actor.id]={actorId:actor.id,text:'Overwritten'};${checkpoint}` });
  assert.equal(otherFeature.ok, false);
  assert.ok(failedChecks(otherFeature).some(check => /every other record/.test(check.message)));
});

test('a checkpoint only implemented for the owner cannot publish for visitors', async () => {
  const result = await verify({ saveBody: `if(actor.id==='leo')throw Error('Owner only checkpoint');${checkpoint}` });
  assert.equal(result.ok, false);
  assert.ok(result.checks.some(check => /Owner game checkpoints/.test(check.name) && check.ok));
  assert.ok(result.checks.some(check => /Visitor game checkpoints/.test(check.name) && !check.ok && /Owner only/.test(check.message)));
});

test('a nonpersistent game does not require a checkpoint reducer', async () => {
  const result = await verify({ save: false, saveBody: "throw Error('No saved games');" });
  assert.equal(result.ok, true, JSON.stringify(failedChecks(result)));
  assert.ok(result.checks.every(check => !/checkpoints/.test(check.name)));
});

test('a freshly saved game must initialize and render when the player returns', async () => {
  const result = await verify({ initBody: "if(saved&&saved.ticks===0)throw Error('Cannot resume initial progress');return saved?{...saved}:{actorId:actor.id,x:0,ticks:0};" });
  assert.equal(result.ok, false);
  assert.ok(failedChecks(result).some(check => /checkpoints/.test(check.name) && /Cannot resume initial progress/.test(check.message)));
});

test('host simulation catches games that fail after their first valid tick', async () => {
  const state = liveState();
  delete state.extras.arcade;
  const result = await verify({ stepBody: `if(action.type==='tick'&&state.ticks>0)throw Error('Later frame is broken');${step}` }, state);
  assert.equal(result.ok, false);
  assert.ok(failedChecks(result).some(check => /advances/.test(check.name) && /Later frame/.test(check.message)));
});

test('terminal games are not ticked again by publication smoke checks', async () => {
  const source = moduleSource({ stepBody: `if(state.ticks>=1)throw Error('Already finished');${step}` })
    .replace('values:{score:state.x}', 'values:{score:state.x},finished:state.ticks>=1');
  const result = await verifyModule(source, behaviorTests, liveState(), { owner, visitor });
  assert.equal(result.ok, true, JSON.stringify(failedChecks(result)));
});

test('declared game controls are available to behavioral tests without rejecting state-gated actions', async () => {
  const source = moduleSource({ stepBody: `if(action.type==='launch'&&state.ticks<2)throw Error('Wait until charged');${step}` });
  const tests = `export function runTests(api){
    const actor={id:'controls-player',name:'Player'};
    const binding=api.gameActions.find(item=>item.action.type==='launch');
    let state=api.gameInit(null,actor),gated=false;
    try{api.gameStep(state,binding.action,actor)}catch{gated=true;}
    for(let i=0;i<2;i++)state=api.gameStep(state,{type:'tick',deltaMs:50},actor);
    const launched=api.gameStep(state,binding.action,actor);
    return [{name:'The rendered launch control works after charging',ok:gated&&binding.label==='Launch game'&&launched.x===state.x+10}];
  }`;
  const result = await verifyModule(source, tests, liveState(), { owner, visitor });
  assert.equal(result.ok, true, JSON.stringify(failedChecks(result)));
});
