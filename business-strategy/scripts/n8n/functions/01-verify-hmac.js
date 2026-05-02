// n8n Function node — verifyHmac
// Validates X-TPS-Signature against HMAC-SHA256 of the RAW request body.
//
// CRITICAL: HMAC must be computed over the exact bytes the sender signed.
// Re-serializing parsed JSON ($json) is unsafe — JSON.stringify can produce
// different whitespace, key ordering, or number formatting than the wire
// bytes, causing verification to silently fail for every request.
//
// Configure the upstream n8n Webhook node ONE of these two ways:
//   Options > Binary Data: true   → raw bytes at $binary.data.data (base64)
//   Options > Raw Body:    true   → raw string at $json.__rawBody
//
// Inputs: raw webhook payload + X-TPS-Signature header
// Outputs: parsed $json on success
// Env: INTAKE_WEBHOOK_SECRET

const crypto = require('crypto');

const secret = $env.INTAKE_WEBHOOK_SECRET;
const rawSig = $headers['x-tps-signature'];

if (!secret) throw new Error('INTAKE_WEBHOOK_SECRET not configured');
if (!rawSig) throw new Error('Missing X-TPS-Signature header');

// Resolve the wire bytes the sender hashed.
let bodyBytes;
if ($binary && $binary.data && typeof $binary.data.data === 'string') {
  // Binary Data mode — preferred. n8n stores the raw body as base64.
  bodyBytes = Buffer.from($binary.data.data, 'base64');
} else if ($json && typeof $json.__rawBody === 'string') {
  // Raw Body mode — n8n exposes the wire string at $json.__rawBody.
  bodyBytes = Buffer.from($json.__rawBody, 'utf8');
} else {
  throw new Error(
    'verifyHmac: raw body unavailable. Configure the upstream Webhook node ' +
    'with "Options > Binary Data: true" so $binary.data exposes the wire ' +
    'bytes. Re-serializing parsed JSON is unsafe and will silently fail ' +
    'verification when whitespace or key ordering drifts.'
  );
}

// Accept both bare hex (HubSpot custom-code default) and "sha256=<hex>"
// (Quo / GitHub-style — see quo-bridge-spec.md §3).
const sig = rawSig.startsWith('sha256=') ? rawSig.slice('sha256='.length) : rawSig;

const expected = crypto.createHmac('sha256', secret).update(bodyBytes).digest('hex');

const a = Buffer.from(sig, 'utf8');
const b = Buffer.from(expected, 'utf8');

// Length-guard required: timingSafeEqual throws RangeError on length mismatch.
const ok = a.length === b.length && crypto.timingSafeEqual(a, b);
if (!ok) throw new Error('INVALID_SIGNATURE');

return $json;
