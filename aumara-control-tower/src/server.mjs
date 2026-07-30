import { timingSafeEqual } from 'node:crypto';
import http from 'node:http';
import { pathToFileURL } from 'node:url';
import { readDailyOpsSnapshot } from './daily-ops.mjs';
import { dailyOpsPage } from './daily-ops-page.mjs';
import {
  eventIdempotencyKey,
  hashForAudit,
  MemoryIdempotencyStore
} from './idempotency.mjs';
import { guestAccessEmail } from './message-template.mjs';
import { loadRuntimeConfig } from './runtime-config.mjs';

class HttpError extends Error {
  constructor(status, message) {
    super(message);
    this.status = status;
  }
}

function json(res, status, body) {
  const data = JSON.stringify(body);
  res.writeHead(status, {
    'content-type': 'application/json; charset=utf-8',
    'cache-control': 'no-store',
    'x-content-type-options': 'nosniff'
  });
  res.end(data);
}

function html(res, status, body) {
  res.writeHead(status, {
    'content-type': 'text/html; charset=utf-8',
    'cache-control': 'no-store',
    'x-content-type-options': 'nosniff',
    'x-frame-options': 'DENY',
    'referrer-policy': 'no-referrer',
    'content-security-policy': [
      "default-src 'self'",
      "script-src 'self' 'unsafe-inline'",
      "style-src 'self' 'unsafe-inline'",
      "img-src 'self' data:",
      "connect-src 'self'",
      "frame-ancestors 'none'",
      "base-uri 'none'",
      "form-action 'self'"
    ].join('; ')
  });
  res.end(body);
}

async function readJson(req, maxBodyBytes) {
  const chunks = [];
  let size = 0;
  for await (const chunk of req) {
    size += chunk.length;
    if (size > maxBodyBytes) throw new HttpError(413, 'request body too large');
    chunks.push(chunk);
  }
  const raw = Buffer.concat(chunks).toString('utf8');
  if (!raw) return {};
  try {
    return JSON.parse(raw);
  } catch {
    throw new HttpError(400, 'invalid JSON');
  }
}

function secureEqual(left, right) {
  const leftBuffer = Buffer.from(String(left || ''));
  const rightBuffer = Buffer.from(String(right || ''));
  if (!leftBuffer.length || leftBuffer.length !== rightBuffer.length) return false;
  return timingSafeEqual(leftBuffer, rightBuffer);
}

function authorised(req, config) {
  if (!config.webhookToken) return false;
  return authorisedWithToken(req, config.webhookToken);
}

function authorisedWithToken(req, expectedToken) {
  if (!expectedToken) return false;
  const header = String(req.headers.authorization || '');
  const supplied = header.startsWith('Bearer ')
    ? header.slice(7)
    : req.headers['x-aumara-token'];
  return secureEqual(supplied, expectedToken);
}

function classifyAccessEvent(body, config) {
  const recipient = body.email || body.guestEmail || body.guest_email || body.mail;
  const bookingRef = body.bookingRef || body.booking_ref || body.reference || body.id;
  const eventType = body.eventType || body.event_type || body.kind || body.type;
  const accessCode = body.accessCode || body.access_code || body.pin || body.code;

  if (!recipient) return { action: 'ignored', reason: 'missing_recipient' };
  if (!bookingRef) return { action: 'manual_review', reason: 'missing_booking_reference' };
  if (!eventType) return { action: 'manual_review', reason: 'missing_event_type' };
  if (!['access_ready', 'pre_arrival_access'].includes(String(eventType))) {
    return { action: 'manual_review', reason: 'unsupported_event_type' };
  }
  if (!accessCode) return { action: 'manual_review', reason: 'missing_access_code' };
  if (!config.allowAccessCodes) {
    return { action: 'manual_review', reason: 'access_code_automation_disabled' };
  }
  return { action: 'candidate', reason: 'safe_access_event' };
}

function auditRecord(body, decision, mode, duplicate = false) {
  const recipient = body.email || body.guestEmail || body.guest_email || body.mail;
  const bookingRef = body.bookingRef || body.booking_ref || body.reference || body.id;
  const eventType = body.eventType || body.event_type || body.kind || body.type;
  return {
    schema: 'aumara-webhook-audit-v1',
    at: new Date().toISOString(),
    mode,
    action: duplicate ? 'duplicate' : decision.action,
    reason: duplicate ? 'idempotency_key_already_claimed' : decision.reason,
    recipientHash: hashForAudit(recipient),
    bookingHash: hashForAudit(bookingRef),
    eventType: eventType ? String(eventType) : null,
    containsAccessCode: Boolean(
      body.accessCode || body.access_code || body.pin || body.code
    ),
    emailSendRequested: mode === 'live' && decision.action === 'candidate' && !duplicate,
    bookingMutationRequested: false
  };
}

export function createRequestHandler({
  config,
  sendMail,
  idempotencyStore = new MemoryIdempotencyStore({
    ttlMs: config.idempotencyTtlMs
  }),
  dailyOpsReader = readDailyOpsSnapshot,
  auditSink = (record) => console.log(JSON.stringify(record))
}) {
  return async function handler(req, res) {
    try {
      const url = new URL(req.url, `http://${req.headers.host || 'localhost'}`);

      if (req.method === 'GET' && url.pathname === '/health') {
        return json(res, 200, {
          ok: true,
          service: 'aumara-control-tower',
          environment: config.environment,
          mode: config.mode,
          webhookAuthConfigured: Boolean(config.webhookToken),
          liveSendEnabled: config.mode === 'live' && config.liveSendConfirmed,
          dailyOpsConfigured: Boolean(
            config.dashboardToken && config.dailyOpsSnapshotPath
          ),
          idempotencyStore: 'memory'
        });
      }

      if (req.method === 'GET' && url.pathname === '/daily-ops') {
        return html(res, 200, dailyOpsPage());
      }

      if (req.method === 'GET' && url.pathname === '/api/daily-ops/latest') {
        if (!config.dashboardToken || !config.dailyOpsSnapshotPath) {
          return json(res, 503, {
            ok: false,
            code: 'dashboard_not_configured',
            error: 'Daily Ops dashboard is not configured'
          });
        }
        if (!authorisedWithToken(req, config.dashboardToken)) {
          return json(res, 401, {
            ok: false,
            code: 'unauthorised',
            error: 'Unauthorised'
          });
        }
        try {
          const snapshot = await dailyOpsReader(config.dailyOpsSnapshotPath);
          return json(res, 200, snapshot);
        } catch (error) {
          return json(res, 503, {
            ok: false,
            code: error.code || 'snapshot_unavailable',
            error: 'Daily Ops snapshot is unavailable'
          });
        }
      }

      if (req.method === 'POST' && url.pathname === '/send') {
        return json(res, 410, {
          ok: false,
          status: 'retired',
          reason: 'generic_send_endpoint_disabled'
        });
      }

      if (req.method === 'POST' && url.pathname === '/webhooks/beds24') {
        if (config.mode === 'off') {
          return json(res, 503, { ok: false, status: 'off' });
        }
        if (!authorised(req, config)) {
          return json(res, 401, { ok: false, error: 'unauthorised' });
        }

        const body = await readJson(req, config.maxBodyBytes);
        const decision = classifyAccessEvent(body, config);
        if (decision.action !== 'candidate') {
          const record = auditRecord(body, decision, config.mode);
          auditSink(record);
          return json(res, 202, { ok: true, status: decision.action, audit: record });
        }

        const key = eventIdempotencyKey(body);
        if (!key) {
          const incomplete = {
            action: 'manual_review',
            reason: 'insufficient_idempotency_fields'
          };
          const record = auditRecord(body, incomplete, config.mode);
          auditSink(record);
          return json(res, 202, { ok: true, status: 'manual_review', audit: record });
        }

        if (!idempotencyStore.claim(key)) {
          const record = auditRecord(body, decision, config.mode, true);
          auditSink(record);
          return json(res, 200, { ok: true, status: 'duplicate', audit: record });
        }

        if (config.mode === 'audit') {
          const record = auditRecord(body, decision, config.mode);
          record.action = 'would_send';
          record.emailSendRequested = false;
          auditSink(record);
          return json(res, 202, { ok: true, status: 'would_send', audit: record });
        }

        if (typeof sendMail !== 'function') {
          idempotencyStore.release(key);
          throw new Error('live mail transport is unavailable');
        }

        const recipient = body.email || body.guestEmail || body.guest_email || body.mail;
        const composed = guestAccessEmail(body);
        try {
          const data = await sendMail({
            to: recipient,
            subject: composed.subject,
            html: composed.html,
            text: composed.text,
            tags: [
              { name: 'project', value: 'aumara' },
              { name: 'source', value: 'beds24' }
            ],
            idempotencyKey: key
          });
          const record = auditRecord(body, decision, config.mode);
          record.action = 'sent';
          auditSink(record);
          return json(res, 200, { ok: true, status: 'sent', provider: 'resend', data });
        } catch (error) {
          idempotencyStore.release(key);
          throw error;
        }
      }

      return json(res, 404, { ok: false, error: 'not found' });
    } catch (error) {
      return json(res, error.status || 500, {
        ok: false,
        error: error.status ? error.message : 'internal error'
      });
    }
  };
}

export function createAumaraServer(options = {}) {
  const config = options.config || loadRuntimeConfig();
  const handler = createRequestHandler({ ...options, config });
  return http.createServer(handler);
}

async function start() {
  const config = loadRuntimeConfig();
  let sendMail;
  if (config.mode === 'live') {
    ({ sendMail } = await import('./mailer.mjs'));
  }
  const server = createAumaraServer({ config, sendMail });
  const port = Number(process.env.PORT || 8787);
  server.listen(port, () => {
    console.log(JSON.stringify({
      ok: true,
      service: 'aumara-control-tower',
      port,
      mode: config.mode
    }));
  });
}

if (process.argv[1] && import.meta.url === pathToFileURL(process.argv[1]).href) {
  await start();
}
