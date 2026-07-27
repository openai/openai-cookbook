import { createHash } from 'node:crypto';

function hash(value) {
  return createHash('sha256').update(String(value)).digest('hex');
}

export function eventIdempotencyKey(payload) {
  const bookingRef = payload.bookingRef || payload.booking_ref || payload.reference || payload.id;
  const recipient = payload.email || payload.guestEmail || payload.guest_email || payload.mail;
  const eventType = payload.eventType || payload.event_type || payload.kind || payload.type;
  const checkIn = payload.checkIn || payload.check_in || payload.arrival;

  if (!bookingRef || !recipient || !eventType) return null;
  return hash([
    'aumara-guest-event-v1',
    bookingRef,
    String(recipient).trim().toLowerCase(),
    eventType,
    checkIn || ''
  ].join('|'));
}

export class MemoryIdempotencyStore {
  constructor({ ttlMs = 604800000, clock = () => Date.now() } = {}) {
    this.ttlMs = ttlMs;
    this.clock = clock;
    this.claims = new Map();
  }

  claim(key) {
    this.purge();
    if (this.claims.has(key)) return false;
    this.claims.set(key, this.clock() + this.ttlMs);
    return true;
  }

  release(key) {
    this.claims.delete(key);
  }

  purge() {
    const now = this.clock();
    for (const [key, expiresAt] of this.claims) {
      if (expiresAt <= now) this.claims.delete(key);
    }
  }
}

export function hashForAudit(value) {
  if (!value) return null;
  return hash(String(value).trim().toLowerCase()).slice(0, 16);
}
