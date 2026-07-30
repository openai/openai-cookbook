const MODES = new Set(['off', 'audit', 'live']);

function truthy(value) {
  return /^(1|true|yes)$/i.test(String(value || '').trim());
}

function positiveInteger(value, fallback, name) {
  const parsed = Number(value || fallback);
  if (!Number.isSafeInteger(parsed) || parsed <= 0) {
    throw new Error(`${name} must be a positive integer`);
  }
  return parsed;
}

export function loadRuntimeConfig(env = process.env) {
  const mode = String(env.AUMARA_AUTOMATION_MODE || 'off').trim().toLowerCase();
  if (!MODES.has(mode)) {
    throw new Error('AUMARA_AUTOMATION_MODE must be off, audit, or live');
  }

  const config = {
    mode,
    environment: String(env.AUMARA_ENV || 'local').trim(),
    webhookToken: String(env.AUMARA_WEBHOOK_TOKEN || '').trim(),
    liveSendConfirmed: truthy(env.AUMARA_LIVE_SEND_CONFIRMED),
    allowAccessCodes: truthy(env.AUMARA_ALLOW_ACCESS_CODES),
    mailFrom: String(env.AUMARA_MAIL_FROM || '').trim(),
    mailReplyTo: String(env.AUMARA_MAIL_REPLY_TO || '').trim(),
    dashboardToken: String(env.AUMARA_DASHBOARD_TOKEN || '').trim(),
    dailyOpsSnapshotPath: String(env.AUMARA_DAILY_OPS_SNAPSHOT || '').trim(),
    maxBodyBytes: positiveInteger(
      env.AUMARA_MAX_BODY_BYTES,
      65536,
      'AUMARA_MAX_BODY_BYTES'
    ),
    idempotencyTtlMs: positiveInteger(
      env.AUMARA_IDEMPOTENCY_TTL_SECONDS,
      604800,
      'AUMARA_IDEMPOTENCY_TTL_SECONDS'
    ) * 1000
  };

  if (
    config.dashboardToken &&
    (config.dashboardToken.length < 32 || config.dashboardToken === 'change-this-token')
  ) {
    throw new Error('AUMARA_DASHBOARD_TOKEN must be a strong token');
  }

  if (mode !== 'off' && !config.webhookToken) {
    throw new Error('AUMARA_WEBHOOK_TOKEN is required outside off mode');
  }

  if (mode === 'live') {
    if (!config.liveSendConfirmed) {
      throw new Error('AUMARA_LIVE_SEND_CONFIRMED=true is required in live mode');
    }
    if (config.webhookToken.length < 32 || config.webhookToken === 'change-this-token') {
      throw new Error('AUMARA_WEBHOOK_TOKEN must be a strong live token');
    }
    if (!config.mailFrom || !config.mailFrom.includes('@')) {
      throw new Error('AUMARA_MAIL_FROM must be a verified domain sender in live mode');
    }
    if (/onboarding@resend\.dev/i.test(config.mailFrom)) {
      throw new Error('The Resend onboarding sender is forbidden in live mode');
    }
    if (!String(env.RESEND_API_KEY || '').trim()) {
      throw new Error('RESEND_API_KEY is required in live mode');
    }
    if (!config.mailReplyTo || !config.mailReplyTo.includes('@')) {
      throw new Error('AUMARA_MAIL_REPLY_TO is required in live mode');
    }
  }

  return Object.freeze(config);
}
