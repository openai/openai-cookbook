import assert from 'node:assert/strict';
import { once } from 'node:events';
import { test } from 'node:test';
import { createAumaraServer } from './server.mjs';
import { loadRuntimeConfig } from './runtime-config.mjs';

const TOKEN = 'a-long-test-token-with-at-least-32-characters';
const SAFE_EVENT = {
  eventType: 'access_ready',
  bookingRef: 'BOOKING-001',
  email: 'guest@example.test',
  accessCode: '123456',
  checkIn: '2026-08-01'
};

function config(mode, overrides = {}) {
  return {
    mode,
    environment: 'test',
    webhookToken: TOKEN,
    liveSendConfirmed: mode === 'live',
    allowAccessCodes: true,
    mailFrom: 'AUMARA <stay@example.test>',
    mailReplyTo: 'ops@example.test',
    maxBodyBytes: 65536,
    idempotencyTtlMs: 60000,
    ...overrides
  };
}

async function withServer(options, callback) {
  const server = createAumaraServer(options);
  server.listen(0, '127.0.0.1');
  await once(server, 'listening');
  const { port } = server.address();
  try {
    return await callback(`http://127.0.0.1:${port}`);
  } finally {
    server.close();
    await once(server, 'close');
  }
}

function post(base, path, body, token = TOKEN) {
  return fetch(`${base}${path}`, {
    method: 'POST',
    headers: {
      'content-type': 'application/json',
      authorization: `Bearer ${token}`
    },
    body: JSON.stringify(body)
  });
}

test('off mode cannot process webhook events', async () => {
  let sends = 0;
  await withServer({
    config: config('off', { webhookToken: '' }),
    sendMail: async () => { sends += 1; }
  }, async (base) => {
    const response = await post(base, '/webhooks/beds24', SAFE_EVENT);
    assert.equal(response.status, 503);
    assert.equal((await response.json()).status, 'off');
  });
  assert.equal(sends, 0);
});

test('missing or incorrect token fails closed', async () => {
  await withServer({ config: config('audit') }, async (base) => {
    const response = await post(base, '/webhooks/beds24', SAFE_EVENT, 'wrong');
    assert.equal(response.status, 401);
  });
});

test('audit mode records a redacted proposal and never sends', async () => {
  let sends = 0;
  const audit = [];
  await withServer({
    config: config('audit'),
    sendMail: async () => { sends += 1; },
    auditSink: (record) => audit.push(record)
  }, async (base) => {
    const response = await post(base, '/webhooks/beds24', SAFE_EVENT);
    const result = await response.json();
    assert.equal(response.status, 202);
    assert.equal(result.status, 'would_send');
    assert.equal(result.audit.emailSendRequested, false);
    assert.equal(JSON.stringify(result).includes(SAFE_EVENT.email), false);
    assert.equal(JSON.stringify(result).includes(SAFE_EVENT.accessCode), false);
  });
  assert.equal(sends, 0);
  assert.equal(audit.length, 1);
});

test('repeated event is deduplicated before transport', async () => {
  let sends = 0;
  let providerKey;
  await withServer({
    config: config('live'),
    sendMail: async (message) => {
      sends += 1;
      providerKey = message.idempotencyKey;
      return { id: 'mail-1' };
    },
    auditSink: () => {}
  }, async (base) => {
    const first = await post(base, '/webhooks/beds24', SAFE_EVENT);
    const second = await post(base, '/webhooks/beds24', SAFE_EVENT);
    assert.equal((await first.json()).status, 'sent');
    assert.equal((await second.json()).status, 'duplicate');
  });
  assert.equal(sends, 1);
  assert.match(providerKey, /^[a-f0-9]{64}$/);
});

test('access-code delivery is manual review unless explicitly enabled', async () => {
  let sends = 0;
  await withServer({
    config: config('live', { allowAccessCodes: false }),
    sendMail: async () => { sends += 1; },
    auditSink: () => {}
  }, async (base) => {
    const response = await post(base, '/webhooks/beds24', SAFE_EVENT);
    assert.equal((await response.json()).status, 'manual_review');
  });
  assert.equal(sends, 0);
});

test('generic send endpoint is permanently retired', async () => {
  await withServer({ config: config('live') }, async (base) => {
    const response = await post(base, '/send', {
      to: 'guest@example.test',
      subject: 'Arbitrary',
      html: '<p>Arbitrary</p>'
    });
    assert.equal(response.status, 410);
    assert.equal((await response.json()).status, 'retired');
  });
});

test('runtime configuration requires live confirmation and verified sender', () => {
  const base = {
    AUMARA_AUTOMATION_MODE: 'live',
    AUMARA_WEBHOOK_TOKEN: TOKEN,
    AUMARA_MAIL_FROM: 'AUMARA <stay@example.test>',
    AUMARA_MAIL_REPLY_TO: 'ops@example.test',
    RESEND_API_KEY: 'test-key'
  };
  assert.throws(() => loadRuntimeConfig(base), /LIVE_SEND_CONFIRMED/);
  assert.throws(() => loadRuntimeConfig({
    ...base,
    AUMARA_LIVE_SEND_CONFIRMED: 'true',
    AUMARA_MAIL_FROM: 'AUMARA <onboarding@resend.dev>'
  }), /onboarding sender/);
});
