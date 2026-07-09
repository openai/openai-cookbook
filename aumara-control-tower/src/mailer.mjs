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

export async function sendMail({ to, subject, html, text, tags = [] }) {
  const resend = client();
  const result = await resend.emails.send({
    from: env('AUMARA_MAIL_FROM', 'AUMARA El Cid <onboarding@resend.dev>'),
    to: Array.isArray(to) ? to : [to],
    subject,
    html,
    text,
    reply_to: env('AUMARA_MAIL_REPLY_TO', 'elcidspain@gmail.com'),
    tags: tags.length ? tags : undefined
  });

  if (result.error) {
    throw new Error(result.error.message || JSON.stringify(result.error));
  }

  return result.data;
}

export function guestAccessEmail(payload) {
  const guestName = payload.guestName || payload.guest_name || payload.name || 'Guest';
  const property = payload.property || payload.propertyName || 'AUMARA El Cid';
  const checkIn = payload.checkIn || payload.check_in || payload.arrival || '';
  const checkOut = payload.checkOut || payload.check_out || payload.departure || '';
  const accessCode = payload.accessCode || payload.access_code || payload.pin || payload.code || '';
  const bookingRef = payload.bookingRef || payload.booking_ref || payload.reference || payload.id || '';

  const subject = `AUMARA El Cid — access information${bookingRef ? ` / ${bookingRef}` : ''}`;

  const text = [
    `Hello ${guestName},`,
    '',
    `Your AUMARA El Cid access information is ready.`,
    property ? `Property: ${property}` : null,
    checkIn ? `Check-in: ${checkIn}` : null,
    checkOut ? `Check-out: ${checkOut}` : null,
    accessCode ? `Access code: ${accessCode}` : 'Access code: pending confirmation',
    '',
    'If you have any question, reply to this email.',
    '',
    'AUMARA El Cid'
  ].filter(Boolean).join('\n');

  const html = `
    <div style="font-family:Arial,sans-serif;line-height:1.45;color:#111">
      <h2>AUMARA El Cid</h2>
      <p>Hello ${escapeHtml(guestName)},</p>
      <p>Your access information is ready.</p>
      <ul>
        ${property ? `<li><strong>Property:</strong> ${escapeHtml(property)}</li>` : ''}
        ${checkIn ? `<li><strong>Check-in:</strong> ${escapeHtml(checkIn)}</li>` : ''}
        ${checkOut ? `<li><strong>Check-out:</strong> ${escapeHtml(checkOut)}</li>` : ''}
        <li><strong>Access code:</strong> ${accessCode ? escapeHtml(accessCode) : 'pending confirmation'}</li>
      </ul>
      <p>If you have any question, reply to this email.</p>
      <p>AUMARA El Cid</p>
    </div>`;

  return { subject, text, html };
}

function escapeHtml(value) {
  return String(value)
    .replaceAll('&', '&amp;')
    .replaceAll('<', '&lt;')
    .replaceAll('>', '&gt;')
    .replaceAll('"', '&quot;')
    .replaceAll("'", '&#039;');
}
