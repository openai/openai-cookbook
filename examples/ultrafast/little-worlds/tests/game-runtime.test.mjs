import test from 'node:test';
import assert from 'node:assert/strict';
import { compileGameModule, compileModule, gameInit, gameStep, gameView, verifyModule } from '../server/runtime.mjs';

const actor = { id: 'mira', name: 'Mira' };
const liveState = () => ({ projects: [], contributions: [], extras: { arcade: { mira: { actorId: 'mira', x: 20 } }, notes: { leo: { actorId: 'leo', text: 'Keep this' } } } });
const source = `
const width = 260;
const privateCopy = 'PRIVATE_PAGE_COPY';
export const meta = {title:'Arcade',subtitle:'',accent:'#123456',game:{id:'arcade',tickMs:50,saveAction:'save_game'}};
export function render(){return '<section data-game="arcade"><canvas data-game-canvas></canvas><button data-game-command="start">Start</button></section>'+privateCopy;}
export function reduce(state, action, actor){
 if(action.type !== 'save_game' || action.game.actorId !== actor.id) throw Error('Invalid checkpoint');
 return {...state,extras:{...state.extras,arcade:{...state.extras.arcade,[actor.id]:action.game}}};
}
export const game = {
 init(saved,actor){return saved ? {...saved} : {actorId:actor.id,x:0};},
 step(state,action){if(action.type !== 'tick' || action.deltaMs !== 50) throw Error('Unknown input');state.x=(state.x+1)%width;return state;},
 view(state){return {width,height:260,background:'#123456',objects:[{id:'player',type:'circle',x:state.x,y:30,radius:8,fill:'#ffff00'}],values:{score:state.x}};}
};`;
const featureTests = `export function runTests(api){
 const actor={id:'test-player',name:'Player'};
 const initial=api.gameInit(null,actor);
 const next=api.gameStep(initial,{type:'tick',deltaMs:50},actor);
 const view=api.gameView(next,actor);
 const saved=api.reduce(api.initialState,{type:'save_game',game:next},actor);
 let invalid=false;try{api.gameStep(next,{type:'unknown'},actor)}catch{invalid=true;}
 return [
 {name:'Ticks advance the game',ok:next.x===initial.x+1},
 {name:'The scene follows the simulation',ok:view.objects[0].x===next.x},
 {name:'Unknown input is rejected',ok:invalid},
 {name:'Checkpoints preserve another participant',ok:saved.extras.notes.leo.text==='Keep this'}
 ];
}`;

test('normal publication verifies local games and exposes isolated game feature-test APIs', async () => {
  const state = liveState();
  const before = structuredClone(state);
  const result = await verifyModule(source, featureTests, state, { owner: actor, visitor: { id: 'leo', name: 'Leo' } });
  assert.equal(result.ok, true, JSON.stringify(result.checks));
  assert.ok(result.checks.some(check => check.name === 'Owner game initializes, advances, and renders safely' && check.ok));
  assert.ok(result.checks.some(check => check.name === 'Visitor game initializes, advances, and renders safely' && check.ok));
  assert.match(result.gameBundle, /GameModule/);
  assert.doesNotMatch(result.gameBundle, /PRIVATE_PAGE_COPY|save_game|data-game-command/);
  assert.deepEqual(state, before);
});

test('game helpers preserve caller input while returning validated owned state and scene', async () => {
  const { gameBundle } = await compileModule(source);
  const saved = { actorId: actor.id, x: 7 };
  const initial = await gameInit(gameBundle, saved, actor);
  const next = await gameStep(gameBundle, initial, { type: 'tick', deltaMs: 50 }, actor);
  const view = await gameView(gameBundle, next, actor);
  assert.deepEqual(saved, { actorId: actor.id, x: 7 });
  assert.deepEqual(initial, saved);
  assert.equal(next.x, 8);
  assert.equal(view.objects[0].x, 8);
  await assert.rejects(gameStep(gameBundle, next, { type: 'unknown' }, actor), /Unknown input/);
  await assert.rejects(gameInit(gameBundle, { actorId: 'leo', x: 0 }, actor), /actor|owner|participant/i);
});

test('game metadata and export must agree and contain all three functions', async () => {
  for (const broken of [
    source.replace("game:{id:'arcade',tickMs:50,saveAction:'save_game'}", "game:{id:'arcade',tickMs:1}"),
    source.replace(",game:{id:'arcade',tickMs:50,saveAction:'save_game'}", ''),
    source.replace('export const game =', 'const game ='),
    source.replace(' view(state){', ' other(state){'),
  ]) await assert.rejects(compileModule(broken), /game|tick/i);
});

test('game init and view cannot mutate their input, and step cannot change ownership', async () => {
  const init = await compileGameModule(source.replace('return saved ? {...saved}', 'if(saved)saved.x++;return saved ? {...saved}'));
  await assert.rejects(gameInit(init, { actorId: actor.id, x: 7 }, actor), /initialization must not change/);
  const view = await compileGameModule(source.replace('view(state){return', 'view(state){state.x++;return'));
  await assert.rejects(gameView(view, { actorId: actor.id, x: 7 }, actor), /rendering must not change/);
  const step = await compileGameModule(source.replace('state.x=(state.x+1)%width;', "state.actorId='leo';"));
  await assert.rejects(gameStep(step, { actorId: actor.id, x: 7 }, { type: 'tick', deltaMs: 50 }, actor), /actor|owner|participant/i);
});

test('host game validation still rejects unsafe output when generated code shadows interpreter checks', async () => {
  const stateBundle = await compileGameModule(source.replace('state.x=(state.x+1)%width;', "globalThis.validateGameState=()=>{};state.actorId='leo';"));
  await assert.rejects(gameStep(stateBundle, { actorId: actor.id, x: 0 }, { type: 'tick', deltaMs: 50 }, actor), /actor|owner|participant/i);
  const viewBundle = await compileGameModule(source.replace('view(state){return', 'view(state){globalThis.validateGameView=()=>{};return').replace("fill:'#ffff00'", "fill:'url(https://example.com)'") );
  await assert.rejects(gameView(viewBundle, { actorId: actor.id, x: 0 }, actor), /color|fill|url/i);
});

test('standalone view serialization stays bounded and cannot mutate game input', async () => {
  const base = `export const game={init(saved,actor){return {actorId:actor.id}},step(state){return state},view(state){RETURN}};`;
  const mutation = await compileGameModule(base.replace('RETURN', 'return {toJSON(){state.x++;return {width:100,height:100,objects:[]}}}'));
  await assert.rejects(gameView(mutation, { actorId: actor.id, x: 0 }, actor), /rendering must not change/);
  const oversized = await compileGameModule(base.replace('RETURN', "return {width:100,height:100,objects:[],extra:'x'.repeat(210000)}"));
  await assert.rejects(gameView(oversized, { actorId: actor.id, x: 0 }, actor), /200000 JSON bytes/);
});

test('invalid game output independently blocks publication even if authored tests return true', async () => {
  const invalid = source.replace("fill:'#ffff00'", "fill:'url(https://example.com)'");
  const result = await verifyModule(invalid, 'export function runTests(){return [{name:"Pretend",ok:true}]}', liveState());
  assert.equal(result.ok, false);
  assert.ok(result.checks.some(check => /game.*safely/.test(check.name) && !check.ok));
});

test('public game code cannot import dependencies or use host network, timers, credentials, or time', async () => {
  for (const prefix of ["import x from 'node:fs';", "import './secret.js';", "const load=()=>import('./secret.js');"]) {
    await assert.rejects(compileGameModule(prefix + source), /[Ii]mports/);
  }
  const bundle = await compileGameModule(source.replace('values:{score:state.x}', 'values:{process:typeof process,fetch:typeof fetch,socket:typeof WebSocket,timer:typeof setTimeout,date:typeof Date,performance:typeof performance}'));
  const view = await gameView(bundle, { actorId: actor.id, x: 0 }, actor);
  assert.deepEqual(Object.values(view.values), Array(6).fill('undefined'));
});

test('game feature helpers hide clocks without changing ordinary page rendering or its tests', async () => {
  const hybrid = source.replace('const width = 260;', 'const width = 260; const gameClock = typeof Date;')
    .replace("return '<section", "return '<p>'+new Date(0).getUTCFullYear()+'</p><section")
    .replace('values:{score:state.x}', 'values:{score:state.x,initialClock:gameClock,callClock:typeof Date}');
  const tests = `export function runTests(api) {
    const actor={id:'mira',name:'Mira'};
    const before=api.render(api.initialState,actor);
    const view=api.gameView(api.gameInit(null,actor),actor);
    const after=api.render(api.initialState,actor);
    return [
      {name:'Page clock behavior is preserved',ok:before.includes('1970') && before===after},
      {name:'Game clocks are unavailable during initialization and calls',ok:view.values.initialClock==='undefined' && view.values.callClock==='undefined'}
    ];
  }`;
  const result = await verifyModule(hybrid, tests, liveState());
  assert.equal(result.ok, true, JSON.stringify(result.checks));
});

test('feature-test reducers reject oversized saved game output, not only the incoming checkpoint', async () => {
  const oversized = source.replace('[actor.id]:action.game', "[actor.id]:{...action.game,board:'x'.repeat(33000)}");
  const tests = `export function runTests(api) {
    let rejected=false;
    try {api.reduce(api.initialState,{type:'save_game',game:{actorId:'mira',x:1}},{id:'mira',name:'Mira'});}
    catch(error){rejected=/32000|32,000|size|large|bytes/i.test(error.message);}
    return [{name:'Oversized reducer output is rejected',ok:rejected}];
  }`;
  const result = await verifyModule(oversized, tests, liveState());
  assert.equal(result.ok, false, 'The host also rejects an oversized checkpoint before publication');
  assert.ok(result.checks.some(check => check.name === 'Oversized reducer output is rejected' && check.ok), JSON.stringify(result.checks));
  assert.ok(result.checks.some(check => /game checkpoints/.test(check.name) && !check.ok && /32000/.test(check.message)), JSON.stringify(result.checks));
});

test('publication supports multi-frame game simulations while retaining all scene checks', async () => {
  const scene = source.replace("objects:[{id:'player',type:'circle',x:state.x,y:30,radius:8,fill:'#ffff00'}]",
    "objects:Array.from({length:60},(_,i)=>({id:'piece-'+i,type:'circle',x:state.x+i,y:30,radius:8,fill:'#ffff00'}))");
  const tests = `export function runTests(api) {
    const actor={id:'simulation',name:'Player'};
    let state=api.gameInit(null,actor),correct=true;
    for(let frame=1;frame<=20;frame++) {
      state=api.gameStep(state,{type:'tick',deltaMs:50},actor);
      const view=api.gameView(state,actor);
      correct=correct && state.x===frame && view.objects.length===60 && view.objects[59].x===frame+59;
    }
    return [{name:'Every simulated frame follows the current state',ok:correct}];
  }`;
  const result = await verifyModule(scene, tests, liveState());
  assert.equal(result.ok, true, JSON.stringify(result.checks));
});

test('runaway game steps are interrupted and the runtime remains usable', async () => {
  const bad = await compileGameModule(source.replace('state.x=(state.x+1)%width;', 'while(true){}'));
  await assert.rejects(gameStep(bad, { actorId: actor.id, x: 0 }, { type: 'tick', deltaMs: 50 }, actor), /time limit/);
  const good = await compileGameModule(source);
  assert.equal((await gameInit(good, null, actor)).x, 0);
});
