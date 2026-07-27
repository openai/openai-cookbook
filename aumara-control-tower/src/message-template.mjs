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
    'Your AUMARA El Cid access information is ready.',
    property ? `Property: ${property}` : null,
    checkIn ? `Check-in: ${checkIn}` : null,
    checkOut ? `Check-out: ${checkOut}` : null,
    `Access code: ${accessCode}`,
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
        <li><strong>Access code:</strong> ${escapeHtml(accessCode)}</li>
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
