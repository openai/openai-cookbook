import { createHmac, timingSafeEqual } from "node:crypto";

export function verifyTwilioSignature({ authToken, params = {}, signature, url }) {
  if (!authToken || !signature || !url) {
    return false;
  }

  const data =
    url +
    Object.keys(params)
      .sort()
      .map((key) => `${key}${stringValue(params[key])}`)
      .join("");

  const expected = createHmac("sha1", authToken).update(data).digest("base64");
  return safeEqual(signature, expected);
}

export function validateTwilioRequest(request, env = process.env, options = {}) {
  if (env.SKIP_TWILIO_SIGNATURE_VALIDATION === "true") {
    return true;
  }

  if (!env.TWILIO_AUTH_TOKEN) {
    return true;
  }

  return verifyTwilioSignature({
    authToken: env.TWILIO_AUTH_TOKEN,
    params: request.body ?? {},
    signature: twilioSignatureHeader(request),
    url: publicWebhookUrl(request, env, options),
  });
}

export function publicWebhookUrl(request, env = process.env, options = {}) {
  const base = env.PUBLIC_URL
    ? new URL(env.PUBLIC_URL)
    : new URL(`${request.protocol ?? "https"}://${request.headers.host}`);

  if (options.protocol) {
    base.protocol = `${options.protocol}:`;
  }

  return new URL(request.url, base).toString();
}

export function isAllowedCaller(from, allowList) {
  const allowed = parseAllowList(allowList);
  if (allowed.size === 0) {
    return true;
  }
  return allowed.has(normalizePhone(from));
}

export function maxActiveCallers(env = process.env) {
  const parsed = Number.parseInt(env.MAX_ACTIVE_CALLERS ?? "", 10);
  return Number.isFinite(parsed) && parsed > 0 ? parsed : Infinity;
}

function parseAllowList(value) {
  return new Set(
    String(value ?? "")
      .split(",")
      .map(normalizePhone)
      .filter(Boolean),
  );
}

function normalizePhone(value) {
  return String(value ?? "").replace(/[^\d+]/g, "");
}

function twilioSignatureHeader(request) {
  return (
    request.headers["x-twilio-signature"] ??
    request.headers["X-Twilio-Signature"] ??
    ""
  );
}

function stringValue(value) {
  if (Array.isArray(value)) {
    return value.join("");
  }
  return String(value ?? "");
}

function safeEqual(left, right) {
  const leftBuffer = Buffer.from(left);
  const rightBuffer = Buffer.from(right);
  return (
    leftBuffer.length === rightBuffer.length &&
    timingSafeEqual(leftBuffer, rightBuffer)
  );
}
