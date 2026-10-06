import test from 'node:test';
import assert from 'node:assert/strict';
import { countOutputTokens, createOutputThroughput } from '../server/output-throughput.mjs';

test('normal deltas are batched before tokenization and rate uses arrival time', () => {
  let time = 1000;
  const counted = [];
  const meter = createOutputThroughput({ now: () => time, countTokens: text => { counted.push(text); return text.length; } });
  assert.deepEqual(meter.sample(), { tokens: 0, durationMs: 0, rate: 0, sampledAt: 1000, lastDeltaAt: null, state: 'waiting', estimated: true });
  meter.append('text:0', 'ab');
  time = 1100;
  meter.append('text:0', 'cd');
  assert.deepEqual(counted, [], 'no tokenization per ordinary provider delta');
  assert.equal(meter.dirty, true);
  assert.deepEqual(meter.sample(), { tokens: 4, durationMs: 250, rate: 16, sampledAt: 1100, lastDeltaAt: 1100, state: 'streaming', estimated: true });
  assert.equal(meter.dirty, false);
  assert.deepEqual(counted, ['abcd', 'abcd']);
  time = 1500;
  meter.append('text:0', 'ef');
  const later = meter.sample();
  assert.equal(later.tokens, 6);
  assert.equal(later.durationMs, 500);
  assert.equal(later.rate, 12);
});

test('independent output items do not share token boundaries', () => {
  const counted = [];
  const meter = createOutputThroughput({ now: () => 1000, countTokens: text => { counted.push(text); return text.length; } });
  meter.append('text:0', 'answer');
  meter.append('tool:1', 'patch');
  assert.equal(meter.sample().tokens, 11);
  assert.deepEqual(counted, ['answer', 'answer', 'patch', 'patch']);
});

test('stalls and repeated samples do not invent output; completion keeps the measured interval', () => {
  let time = 1000;
  const meter = createOutputThroughput({ now: () => time, countTokens: text => text.length });
  meter.append('tool', 'a'.repeat(100));
  meter.sample();
  time = 1500;
  meter.append('tool', 'b'.repeat(100));
  assert.equal(meter.sample().rate, 400);
  time = 2100;
  assert.equal(meter.sample().rate, 100, 'only the latest output burst remains in the rolling window');
  time = 2600;
  assert.equal(meter.sample().rate, 0);
  meter.finish();
  const complete = meter.sample();
  assert.equal(complete.tokens, 200);
  assert.equal(complete.durationMs, 500);
  assert.equal(complete.lastDeltaAt, 1500);
  assert.equal(complete.state, 'complete');
  assert.equal(complete.rate, 0);
  assert.equal(meter.append('tool', 'late'), false);
  assert.deepEqual(meter.sample(), complete);
});

test('an empty completed response has no manufactured throughput', () => {
  const meter = createOutputThroughput({ now: () => 1000 });
  assert.equal(meter.append('empty', ''), false);
  assert.equal(meter.append('invalid', null), false);
  meter.finish();
  assert.deepEqual(meter.sample(), { tokens: 0, durationMs: 0, rate: 0, sampledAt: 1000, lastDeltaAt: null, state: 'complete', estimated: true });
});

test('large bursts spill in bounded chunks without losing text or splitting surrogate pairs', () => {
  let biggest = 0;
  const meter = createOutputThroughput({ now: () => 1000, maxBufferChars: 32, contextChars: 8, countTokens: text => {
    biggest = Math.max(biggest, text.length);
    assert.ok(text.isWellFormed());
    return text.length;
  } });
  const text = 'a😀'.repeat(10_000);
  meter.append('tool', text);
  const sample = meter.sample();
  assert.equal(sample.tokens, text.length);
  assert.ok(biggest <= 40, `largest tokenizer input was ${biggest}`);
});

test('retained boundary context does not grow with the generated file', () => {
  let biggest = 0, time = 1000;
  const meter = createOutputThroughput({ now: () => time, contextChars: 8, countTokens: text => {
    biggest = Math.max(biggest, text.length);
    return text.length;
  } });
  for (let index = 0; index < 200; index++) {
    meter.append('tool', 'x'.repeat(20));
    time += 90;
    meter.sample();
  }
  assert.equal(meter.sample().tokens, 4000);
  assert.ok(biggest <= 28);
});

test('the output channel map is bounded and each response owns its counters', () => {
  const first = createOutputThroughput({ now: () => 1000, countTokens: text => text.length, maxChannels: 2 });
  const second = createOutputThroughput({ now: () => 1000, countTokens: text => text.length });
  assert.equal(first.append('0', 'a'), true);
  assert.equal(first.append('1', 'b'), true);
  assert.equal(first.append('2', 'ignored'), false);
  assert.equal(first.sample().tokens, 2);
  assert.equal(second.sample().tokens, 0);
});

test('the public tokenizer counts code and Unicode without interpreting special token strings', () => {
  assert.equal(countOutputTokens('Hello world!'), 3);
  assert.ok(countOutputTokens('const n = 42;\n') > 1);
  assert.ok(countOutputTokens('你好 🌱') > 0);
  assert.ok(countOutputTokens('<|endoftext|>') > 0);
  const meter = createOutputThroughput({ now: () => 1000 });
  meter.append('0', 'Hello');
  meter.sample();
  meter.append('0', ' world!');
  assert.equal(meter.sample().tokens, countOutputTokens('Hello world!'));
});

test('long repeated strings are bounded and token-counter failures cannot break a build', () => {
  assert.equal(countOutputTokens('a'.repeat(8192)), 1024);
  let broken = true;
  const meter = createOutputThroughput({ now: () => 1000, countTokens: text => {
    if (broken) throw new Error('counter unavailable');
    return text.length;
  } });
  meter.append('tool', 'first');
  assert.doesNotThrow(() => meter.sample());
  broken = false;
  meter.append('tool', 'later');
  assert.equal(meter.sample().tokens, 5);
  meter.finish();
  assert.equal(meter.sample().state, 'complete');
});
