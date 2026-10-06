import test from 'node:test';
import assert from 'node:assert/strict';
import { EventEmitter } from 'node:events';
import { createEventStreamLifecycle } from '../server/event-stream.mjs';

function fixture(t) {
  const timers = [];
  t.mock.method(globalThis, 'setInterval', (callback, delay) => {
    const timer = { callback, delay, cleared: false, unref() {} };
    timers.push(timer);
    return timer;
  });
  t.mock.method(globalThis, 'clearInterval', timer => { if (timer) timer.cleared = true; });
  const controller = new AbortController();
  let active = true;
  const principal = { signal: controller.signal, active: () => active };
  const response = Object.assign(new EventEmitter(), {
    writableEnded: false, destroyed: false, writes: [], ends: 0,
    write(value) {
      assert.equal(this.writableEnded || this.destroyed, false, 'write after end');
      this.writes.push(value);
      return true;
    },
    // Model a buffered response: close/finish do not occur until later.
    end() { this.ends++; this.writableEnded = true; },
    destroy() { this.destroyed = true; },
  });
  const stream = createEventStreamLifecycle(response, principal);
  return { stream, response, timers, controller, expire: () => { active = false; } };
}

test('ending an authenticated stream stops producers before the buffered response closes', t => {
  const { stream, response, timers } = fixture(t);
  let subscriptions = 1;
  stream.onCleanup(() => { subscriptions--; });
  stream.startHeartbeat(() => response.write('heartbeat'));
  assert.equal(timers[0].delay, 15_000);
  timers[0].callback();
  assert.deepEqual(response.writes, ['heartbeat']);
  stream.end();
  assert.equal(subscriptions, 0);
  assert.equal(timers[0].cleared, true);
  // A callback that was already queued must also be harmless.
  timers[0].callback();
  assert.equal(stream.writable(), false);
  stream.end(); response.emit('finish'); response.emit('close');
  assert.equal(response.ends, 1);
  assert.equal(subscriptions, 0);
  assert.deepEqual(response.writes, ['heartbeat']);
});

test('an already-closed feed can end synchronously during subscription setup', t => {
  const { stream, response, timers } = fixture(t);
  let disposed = 0;
  const subscribe = onClose => { onClose(); return () => { disposed++; }; };
  stream.onCleanup(subscribe(stream.end));
  stream.startHeartbeat(() => response.write('late heartbeat'));
  assert.equal(disposed, 1);
  assert.equal(timers.length, 0);
  assert.equal(response.ends, 1);
});

for (const termination of ['finish', 'close', 'error', 'abort', 'expired', 'ended', 'destroyed']) {
  test(`${termination} prevents subsequent heartbeat writes and releases subscriptions`, t => {
    const { stream, response, timers, controller, expire } = fixture(t);
    let disposed = 0;
    stream.onCleanup(() => { disposed++; });
    stream.startHeartbeat(() => response.write('heartbeat'));
    if (termination === 'abort') controller.abort();
    else if (termination === 'expired') expire();
    else if (termination === 'ended') response.writableEnded = true;
    else if (termination === 'destroyed') response.destroyed = true;
    else response.emit(termination, termination === 'error' ? new Error('socket closed') : undefined);
    timers[0].callback();
    assert.equal(stream.writable(), false);
    assert.equal(disposed, 1);
    assert.equal(timers[0].cleared, true);
    assert.deepEqual(response.writes, []);
    // An in-flight write can report its failure asynchronously after cleanup.
    assert.doesNotThrow(() => response.emit('error', new Error('late socket error')));
    assert.equal(disposed, 1);
  });
}
