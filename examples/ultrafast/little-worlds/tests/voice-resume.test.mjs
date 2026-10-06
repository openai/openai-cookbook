import test from 'node:test';
import assert from 'node:assert/strict';
import { build } from 'esbuild';

const compiled = await build({ entryPoints: [new URL('../src/voice-resume.ts', import.meta.url).pathname], bundle: true, write: false, format: 'esm' });
const { takeVoiceResume, saveVoiceResume, canResumeVoice } = await import(`data:text/javascript;base64,${Buffer.from(compiled.outputFiles[0].text).toString('base64')}`);
const key = 'little-worlds:live-resume';
const fixture = () => {
  const entries = new Map();
  return { entries, getItem: key => entries.get(key) ?? null, setItem: (key, value) => entries.set(key, value), removeItem: key => entries.delete(key) };
};

test('same-tab resume saves only identity and microphone preference, and is consumed once', () => {
  const storage = fixture();
  const intent = { identity: 'mira', muted: true, savedAt: 10000 };
  saveVoiceResume(intent, storage);
  assert.deepEqual(JSON.parse(storage.entries.get(key)), { version: 1, ...intent });
  assert.deepEqual(takeVoiceResume(storage, 11000), intent);
  assert.equal(takeVoiceResume(storage, 11000), null);
  saveVoiceResume(intent, storage);
  saveVoiceResume(null, storage);
  assert.equal(storage.entries.size, 0);
});

test('a pre-rename voice handoff keeps its identity and mute setting and is consumed once', () => {
  const storage = fixture();
  const intent = { identity: 'mira', muted: true, savedAt: 10000 };
  storage.setItem('living-spaces:live-resume', JSON.stringify({ version: 1, ...intent }));
  assert.deepEqual(takeVoiceResume(storage, 11000), intent);
  assert.equal(takeVoiceResume(storage, 11000), null);
  assert.equal(storage.entries.size, 0);
});

test('stale, future, malformed, and non-boolean microphone handoffs never resume', () => {
  const valid = { version: 1, identity: null, muted: false, savedAt: 10000 };
  for (const value of [null, [], {}, { ...valid, version: 2 }, { ...valid, muted: 'false' }, { ...valid, identity: {} }, { ...valid, savedAt: -200000 }, { ...valid, savedAt: 20000 }]) {
    const storage = fixture(); storage.setItem(key, JSON.stringify(value));
    assert.equal(takeVoiceResume(storage, 11000), null);
    assert.equal(storage.entries.size, 0);
  }
  const storage = fixture(); storage.setItem(key, '{');
  assert.equal(takeVoiceResume(storage), null);
});

test('blocked storage does not prevent normal Live use', () => {
  const storage = { getItem() { throw new Error('blocked'); }, setItem() { throw new Error('blocked'); }, removeItem() { throw new Error('blocked'); } };
  assert.equal(takeVoiceResume(storage), null);
  assert.doesNotThrow(() => saveVoiceResume({ identity: null, muted: false, savedAt: 0 }, storage));
  assert.doesNotThrow(() => saveVoiceResume(null, storage));
});

test('automatic resume requires the same identity and an existing microphone grant', async () => {
  const intent = { identity: 'mira', muted: true, savedAt: Date.now() };
  let calls = 0;
  const permissions = { query: async descriptor => { calls++; assert.equal(descriptor.name, 'microphone'); return { state: 'granted' }; } };
  assert.equal(await canResumeVoice(intent, 'mira', permissions), true);
  assert.equal(await canResumeVoice(intent, 'sol', permissions), false);
  assert.equal(await canResumeVoice(intent, null, permissions), false);
  assert.equal(await canResumeVoice({ ...intent, savedAt: 10000 }, 'mira', permissions), false);
  assert.equal(calls, 1);
  for (const state of ['prompt', 'denied']) assert.equal(await canResumeVoice(intent, 'mira', { query: async () => ({ state }) }), false);
  assert.equal(await canResumeVoice(intent, 'mira', { query: async () => { throw new Error('unsupported'); } }), false);
  assert.equal(await canResumeVoice(intent, 'mira', null), false);
});
