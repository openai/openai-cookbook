// n8n Function node — verifyHmac
// Validates the X-TPS-Signature header against INTAKE_WEBHOOK_SECRET.
// Throws on mismatch so the workflow halts before scoring/routing runs.
//
// Inputs:  raw webhook payload from HubSpot
// Outputs: same payload, untouched, on success
// Env:     INTAKE_WEBHOOK_SECRET

const crypto = require('crypto');

const secret = $env.INTAKE_WEBHOOK_SECRET;
const rawSig = $headers['x-tps-signature'];
const body = JSON.stringify($json);

if (!secret) throw new Error('INTAKE_WEBHOOK_SECRET not configured');
if (!rawSig) throw new Error('Missing X-TPS-Signature header');

// Accept both bare hex (HubSpot-style) and "sha256=<hex>" (Quo / GitHub-style).
// quo-bridge-spec.md §3 documents the prefixed form; HubSpot's "Send a webhook"
// custom-code action emits bare hex by default. Strip the prefix if present so
// either source verifies correctly.
const sig = rawSig.startsWith('sha256=') ? rawSig.slice('sha256='.length) : rawSig;

const expected = crypto.createHmac('sha256', secret).update(body).digest('hex');

const a = Buffer.from(sig, 'utf8');
const b = Buffer.from(expected, 'utf8');

// Length-guard required: timingSafeEqual throws RangeError on length mismatch.
const ok = a.length === b.length && crypto.timingSafeEqual(a, b);
if (!ok) throw new Error('INVALID_SIGNATURE');

return $json;
