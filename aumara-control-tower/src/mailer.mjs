import { Resend } from '@resend/node';

function env(name, fallback = undefined) {
  const value = process.env[name];
  if (value === undefined || value === null || String(value).trim() === '') {
    if (fallback !== undefined) return fallback;
    throw new Error(`Missing env: ${name}`);
  }
  return String(value).trim();
}

export function client() {
  return new Resend(env('RESEND_API_KEY'));
}

export async function sendMail({ to, subject, html, text, tags = [], idempotencyKey }) {
  if (String(process.env.AUMARA_AUTOMATION_MODE || '').toLowerCase() !== 'live') {
    throw new Error('Email send refused: AUMARA_AUTOMATION_MODE is not live');
  }
  if (!/^(1|true|yes)$/i.test(String(process.env.AUMARA_LIVE_SEND_CONFIRMED || ''))) {
    throw new Error('Email send refused: live send is not confirmed');
  }

  const from = env('AUMARA_MAIL_FROM');
  if (/onboarding@resend\.dev/i.test(from)) {
    throw new Error('Email send refused: Resend onboarding sender is forbidden');
  }
  if (!idempotencyKey || String(idempotencyKey).length > 256) {
    throw new Error('Email send refused: valid idempotency key is required');
  }

  const resend = client();
  const result = await resend.emails.send(
    {
      from,
      to: Array.isArray(to) ? to : [to],
      subject,
      html,
      text,
      reply_to: env('AUMARA_MAIL_REPLY_TO'),
      tags: tags.length ? tags : undefined
    },
    { idempotencyKey: String(idempotencyKey) }
  );

  if (result.error) {
    throw new Error(result.error.message || JSON.stringify(result.error));
  }

  return result.data;
}
