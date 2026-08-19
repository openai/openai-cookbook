# AUMARA post-stay feedback and transferable discount v1

## Operating rule

AUMARA does not send checkout reminders asking a guest to leave or release a house. After a completed stay, the only lifecycle message is one personalised feedback request.

## Guest flow

1. Confirm the booking belongs to AUMARA property `324882`, is not cancelled, and the departure date is in the past.
2. Open the unique survey URL. The bearer token is placed in the URL fragment (`#t=...`), so it is not sent to the web server; the database stores only its SHA-256 hash.
3. The guest completes the approximately one-minute survey.
4. The API atomically records one response and reveals one transferable discount code.
5. After submission, the public offer link and QR code can be shared with another person. The QR PNG is generated dynamically by the Edge Function and is not stored in the public repository.
6. The booking link opens Beds24 with `voucher`, `referer`, five nights, mobile view and guest language prefilled.

## Discount rule

- 10% off an AUMARA accommodation stay.
- Minimum five nights.
- One redemption.
- Transferable.
- Additional to other active AUMARA offers.
- The code must be activated in Beds24 before any guest message is sent.

## Components

- Static guest interface: `/aumara/feedback.html`
- Dynamic QR endpoint: `aumara-feedback?action=qr&code=...`
- Edge API: `aumara-feedback`
- Database tables:
  - `public.aumara_feedback_codes`
  - `public.aumara_guest_feedback`
  - `public.aumara_feedback_events`
- Transactional RPC: `public.aumara_submit_feedback`
- Policy: `aumara-control-tower/policies/aumara-poststay-followup.json`

## Beds24 activation gate

Beds24 voucher settings are UI-only. For each issued code, add the code as a one-time-use 10% voucher under the AUMARA property booking page, then set `beds24_status` to `active` in `public.aumara_feedback_codes`. Until both steps are complete, the public booking redirect returns HTTP 409 and the page does not show a booking button.

## Duplicate protection

- One code per `booking_ref`.
- One survey row per `discount_code`.
- One follow-up per `propertyId:bookingRef:templateVersion`.
- Existing completed or cancelled conversations are never re-answered as if they were current.

## Security boundary

- Raw survey tokens and guest-specific QR files are never committed to GitHub.
- The survey RPC is executable only by `service_role`; anonymous clients call the Edge Function, not Postgres directly.
- Public offer, QR and booking routes remain closed until the survey is submitted.
- The booking redirect remains closed until the same code is activated in Beds24 and `beds24_status` is set to `active`.
