# Beds24 continuity record

Last verified: 2026-07-14

## Canonical account map

- Beds24 account: EL CID / AUMARA
- Owner ID: 165022
- AUMARA property ID: 324882
- AUMARA Chalet room ID: 674465
- AUMARA Superior Chalet room ID: 674466
- Booking.com AUMARA working property: 16137893
- Booking.com AUMARA legacy/duplicate: 14953869
- El Cid Country Club Beds24 property: 324903
- Booking.com El Cid hotel ID: 7090541

## Authentication architecture

Beds24 API V2 uses a permanent refresh token generated from a one-time invite code.

1. Open Beds24 API V2 settings: https://beds24.com/control3.php?pagetype=apiv2
2. Generate an invite code with scopes:
   - bookings
   - bookings-personal
   - bookings-financial
   - properties
   - inventory
3. Exchange the invite code once through GET /api/v2/authentication/setup using header `code`.
4. Store the returned refresh token only as GitHub Actions secret `BEDS24_REFRESH_TOKEN`.
5. Never store the invite code, refresh token or short-lived token in repository files, email, Airtable or logs.
6. Use the refresh token at least once every 30 days so it remains valid.

## Current verified credential state

A sanitized GitHub Actions probe on 2026-07-14 found no Beds24 credential secret under any of these historical candidate names:

- BEDS24_REFRESH_TOKEN
- BEDS24_API_TOKEN
- BEDS24_TOKEN
- BEDS24_API_KEY
- BEDS24_INVITE_CODE
- BEDS24_REFRESH

Evidence: `aumara-control-tower/evidence/beds24-secret-presence.json`.

Therefore the former API connection was not preserved as a reusable secret in the current repository. The operational configuration in Beds24 and the TTLock marketplace connection are real, but they are not equivalent to an external API credential.

## Booking creation control

Direct booking creation uses:

- `GET https://beds24.com/api/v2/authentication/token` with header `refreshToken`
- `POST https://beds24.com/api/v2/bookings` with header `token`

A new reservation must contain at minimum:

- roomId
- status
- arrival
- departure
- firstName
- lastName

For paid bank-transfer reservations add two invoice items:

- charge for the total stay
- payment for the amount received

Always set a unique `apiReference` to prevent accidental duplicate creation and immediately read the created booking back by `apiReference`.

## Maria Elvira booking packet

- Guest: Maria Elvira Medina Arocas
- Property: AUMARA
- Room: Superior Chalet
- Room ID: 674466
- Arrival: 2026-07-18
- Departure: 2026-07-20
- Total: EUR 660
- Paid: EUR 660 by bank transfer
- Status: confirmed
- API reference: AUMARA-MEDINA-20260718-660

Do not execute this packet twice. First search by `apiReference`; create only when no match exists.

## Ownership

- Business owner: Ilya
- System owner: AI Ops
- Credential owner: Ilya / GitHub repository secrets
- Fallback while API credential is absent: manual reservation in Beds24 calendar and immediate calendar reconciliation

## Recovery acceptance

The Beds24 API connector is GREEN only after all of the following pass:

1. secret `BEDS24_REFRESH_TOKEN` exists;
2. token exchange succeeds;
3. property/room read succeeds for property 324882 and room 674466;
4. idempotency search by apiReference succeeds;
5. controlled booking creation succeeds;
6. created booking reads back with dates, guest, room, charge and payment;
7. corresponding inventory is blocked.
