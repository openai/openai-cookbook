import test from 'node:test';
import assert from 'node:assert/strict';
import { compileModule, reduceModule, verifyModule } from '../server/runtime.mjs';

const mira = { id: 'mira', name: 'Mira' };
const leo = { id: 'leo', name: 'Leo' };
const state = () => ({
  projects: [], contributions: [], extras: {
    garden: {
      mira: { actorId: 'mira', name: 'Mira', text: 'A moonlit library' },
      leo: { actorId: 'leo', name: 'Leo', text: 'A listening room' },
    },
    keptNote: { text: 'An untouched legacy record' },
  },
});

const source = body => `
export const meta = { title:'Garden', subtitle:'', accent:'#687957' };
export function render(state, actor) { return '<p>Garden</p>'; }
export function reduce(state, action, actor) { ${body}; return state; }
`;

async function apply(body, input = state(), actor = mira) {
  const { bundle } = await compileModule(source(body));
  return reduceModule(bundle, input, { type: 'save' }, actor);
}

test('feature records allow own create, update, and deletion while retaining other people and legacy data', async () => {
  const original = state();
  const next = await apply(`
    state.extras.garden.mira.text = 'A library with a garden';
    state.extras.garden['mira-second'] = {actorId:actor.id, text:'An extra idea', details:{colors:['sage']}};
    state.extras.newFeature = {first:{actorId:actor.id, title:'A new feature'}};
  `, original);
  assert.deepEqual(next.extras.garden.leo, original.extras.garden.leo);
  assert.deepEqual(next.extras.keptNote, original.extras.keptNote);
  assert.equal(original.extras.garden.mira.text, 'A moonlit library');
  assert.equal(next.extras.newFeature.first.actorId, mira.id);
  const removed = await apply('delete state.extras.garden.mira; delete state.extras.newFeature;', next);
  assert.equal(removed.extras.garden.mira, undefined);
  assert.deepEqual(removed.extras.garden.leo, original.extras.garden.leo);
  assert.equal(removed.extras.newFeature, undefined);
});

test('a hostile feature cannot overwrite, delete, rename, or take ownership of another person’s record', async () => {
  const attacks = [
    `state.extras.garden.leo.text = 'Overwritten'`,
    `state.extras.garden.leo.name = 'Mira'`,
    `state.extras.garden.leo.actorId = actor.id`,
    `delete state.extras.garden.leo`,
    `delete state.extras.garden`,
    `state.extras.garden = {}`,
    `state.extras = {}`,
    `state.extras.garden['new-leo'] = {actorId:'leo', text:'Forged'}`,
    `state.extras.stolen = state.extras.garden; delete state.extras.garden`,
    `state.extras.garden['renamed-leo'] = state.extras.garden.leo; delete state.extras.garden.leo`,
  ];
  for (const attack of attacks) {
    await assert.rejects(apply(attack), /own space records/, attack);
  }
});

test('feature collections reject shared scalars, missing owners, arrays, and ownership reassignment', async () => {
  const attacks = [
    `state.extras.sharedCount = 1`,
    `state.extras.sharedCount = {value:1}`,
    `state.extras.newFeature = {record:{text:'Missing owner'}}`,
    `state.extras.garden = []`,
    `state.extras.garden.mira = ['Not a record']`,
    `state.extras.garden.mira.actorId = 'leo'`,
    `state.extras.garden.mira = null`,
    `state.extras.keptNote.text = 'Attempt to edit legacy data'`,
  ];
  for (const attack of attacks) {
    await assert.rejects(apply(attack), /own space records|participant-owned records/, attack);
  }
});

test('record ownership follows the trusted actor, independent of record names', async () => {
  const created = await apply(`state.extras.garden = {mira:{actorId:actor.id, text:'Own opaque key'}};`, {
    projects:[], contributions:[], extras:{},
  }, leo);
  assert.equal(created.extras.garden.mira.actorId, 'leo');
  await assert.rejects(apply(`state.extras.garden.mira.text='Not mine';`, created, mira), /own space records/);
});

test('unchanged legacy values survive and blank states remain valid', async () => {
  const existing = state();
  existing.extras.legacyScalar = 'Keep as-is';
  assert.deepEqual(await apply('', existing), existing);
  const blank = {projects:[], contributions:[], extras:{}};
  assert.deepEqual(await apply('', blank), blank);
});

test('top-level fields cannot bypass participant-owned feature collections', async () => {
  const existing = state();
  existing.legacy = {note:'Keep as-is'};
  assert.deepEqual(await apply('', existing), existing);
  for (const body of [
    `state.sharedCount=1`,
    `state.legacy.note='Changed'`,
    `delete state.legacy`,
  ]) {
    await assert.rejects(apply(body, existing), /participant-owned extras/);
  }
});

test('host checks still reject cross-actor mutations if generated code replaces interpreter validation', async () => {
  const malicious = `${source(`state.extras.garden.leo.text='Overwritten'`)}\nglobalThis.validateExtraTransition=()=>{};`;
  const { bundle } = await compileModule(malicious);
  await assert.rejects(reduceModule(bundle, state(), {type:'save'}, mira), /own space records/);
});

test('verification renders with the actual owner and visitor identities', async () => {
  const personalized = source('').replace("return '<p>Garden</p>';", "if(!['new-owner','verification-visitor'].includes(actor.id)) throw new Error('Wrong identity'); return '<p>Garden</p>';");
  const checks = 'export function runTests(){return [{name:"Module ready",ok:true}]}';
  const result = await verifyModule(personalized, checks, {projects:[], contributions:[], extras:{}}, {
    owner: {id:'new-owner', name:'A new person'}, visitor: {id:'verification-visitor', name:'Visitor'},
  });
  assert.equal(result.ok, true, JSON.stringify(result.checks));
});
