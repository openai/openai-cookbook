# AUMARA / EL CID coordinated work orders — 16 July 2026

## Command rule

Do not treat conversational memory as operational state. Read this file, the Systems Registry, current Beds24 evidence and the canonical website source before acting. Preserve non-secret evidence in the repository and Airtable. Never commit guest access codes, phone numbers, passwords or tokens.

---

## WO-1 — P0: TTLock guest-entry automation

### Current facts
- Canonical Beds24 booking: `89850330`.
- Property: AUMARA.
- Room: Superior Chalet, Unit 1 (green house).
- Check-in: 2026-07-18.
- Check-out: 2026-07-20.
- Beds24 generated a `LOCK_PIN` booking info code.
- A physical test was performed on 2026-07-16, before the booking access period, and the PIN was rejected.
- Verified Beds24 TTLock property settings on 2026-07-16:
  - Passcode Strategy: `Offline`.
  - Start Time: `16:00`.
  - End Time: `12:00`.
  - Days in Advance: `3`.
  - Synchronize: enabled for Chalet and Superior Chalet.
  - Chalet room `674465`: Unit 1 -> lock `23903424`; Unit 2 -> `23903418`; Unit 3 -> `23903386`.
  - Superior Chalet room `674466`: Unit 1 -> lock `23903314`; Unit 2 -> `23903360`.

### Correct diagnosis
Beds24 TTLock codes can only be used during the booking period. `Days in Advance = 3` means Beds24 generates/sends the offline credential three days before arrival; it does **not** make the code physically valid three days early. For booking `89850330`, the generated offline PIN is expected to become valid at 16:00 on 2026-07-18 and stop at 12:00 on 2026-07-20.

With `Offline` strategy, TTLock generates a unique 6–9 digit code. It cannot be customised, updated, deleted or forced to remain the same across bookings. It must be used at least once within 24 hours after its start time or it becomes invalid. Therefore a fixed repeated PIN or “last phone digits” strategy is not available until the mapped locks are online through commissioned gateways.

### Interim operating policy — no gateways

**UPDATE 2026-08-03:** shared permanent guest PIN **`1531`** (+ `#`) for every AUMARA house.
See `systems/aumara-fixed-guest-pin.md` and `systems/ttlock-lock-registry.md`.
Offline unique TTLock codes are no longer the guest-message source of truth.

1. Keep Passcode Strategy = `Offline`.
2. Keep Start Time = `16:00`, End Time = `12:00`, Days in Advance = `3`.
3. Do not manually replace the generated `LOCK_PIN` and do not promise one permanent common guest code.
4. Auto-send the generated per-booking PIN using `[BOOKINGINFOCODETEXT:LOCK_PIN]` only after the PIN exists and before check-in. Default target: one Spanish access message 24 hours before arrival.
5. Require first physical use of every offline PIN within 24 hours after its start time.
6. Keep the mechanical-key/manual-access fallback for every arrival.
7. Duplicate booking `89851675` must be cancelled; offline credentials cannot be remotely revoked, so duplicate prevention is mandatory.
8. Test the current guest PIN only at or after 16:00 on 2026-07-18. Do not interpret an earlier rejection as a defect.

### Immediate action
1. Confirm duplicate booking `89851675` is cancelled and cannot retain a second active access credential.
2. Verify Auto Action email/SMS template contains `[BOOKINGINFOCODETEXT:LOCK_PIN]`, the map/address, check-in 16:00, check-out 12:00 and monitored support contact.
3. Schedule the guest-access message for 24 hours before check-in, after code generation.
4. At 16:00 on 2026-07-18, test the guest PIN on Superior Chalet Unit 1 / lock `23903314`.
5. Record physical-open result and first-use timestamp.
6. If the PIN fails within its valid window, use the mechanical key/manual procedure and inspect mapping, lock clock, room/unit assignment and offline-code collision.

### Permanent target
- Two TTLock gateways commissioned and monitored.
- Online PIN strategy: last 6 valid guest-phone digits, with random fallback when phone data is invalid.
- Instant `Export to TTLock` after booking, room, date or contact changes.
- Cancellation revokes the online PIN.
- End-to-end evidence: booking -> PIN -> correct physical house -> checkout expiry -> cancellation revoke.

### Definition of done
- Guest PIN opens only in the correct validity window.
- First use occurs within 24 hours of the start time.
- One booking maps to one house and one active access credential.
- Guest message contains the actual generated PIN and arrival instructions.
- Non-secret evidence is stored in Control Tower.

---

## WO-2 — P1: Restore EL CID Country Club website as a separate product

### Architecture guardrail
AUMARA and EL CID Country Club are distinct products. Do not replace AUMARA branding with EL CID or merge both into an undifferentiated root page.

### Required work
1. Audit current production root, `/aumara/`, `elcid-site/`, deployment workflows and Nominalia target paths.
2. Recover the last approved full EL CID Country Club site source and assets.
3. Search the canonical Google Drive asset folders for:
   - EL CID brandbook;
   - official logo variants;
   - hotel-room photos;
   - restaurant / pool / territory photos;
   - approved contact and address data.
4. Build a review-only EL CID site with:
   - official logo and brandbook typography;
   - hotel overview and room types;
   - Wabi-Sabi restaurant;
   - territory / pool / location;
   - direct booking CTA to Beds24;
   - phone, email, map and WhatsApp actions;
   - mobile-first performance and image optimisation.
5. Keep AUMARA at its own canonical route and preserve its interactive walkthrough.
6. Do not deploy production until review screenshots, link tests, Beds24 CTA test and explicit approval exist.

### Agent delegation
GitHub Copilot coding agent may implement the review branch and tests from this work order. Claude may review information architecture, copy consistency and visual hierarchy, but its output must return to GitHub as a review note or patch; no operational state may live only in a Claude conversation.

### Definition of done
- EL CID review branch and preview exist.
- Official assets are used, not placeholders.
- No AUMARA regression.
- Direct booking and contact actions are tested.
- Production deployment remains gated by approval.

---

## WO-3 — P1: EL CID Booking.com -> Beds24 distribution recovery

### Current known failure
The El Cid Country Club channel has reported `HOTEL_ACCESS_DENIED` for Booking.com hotel id `7090541` and affected room IDs including `674484` and `674485`.

### Required work
1. Preserve Booking.com as the current source of truth until a controlled Beds24 sync test succeeds.
2. Inventory the EL CID property in Beds24:
   - four double rooms with terrace;
   - one triple room without terrace;
   - separate studio with kitchen if maintained as a separate sellable unit.
3. Compare against Booking.com room names, occupancy, rates, policies, photos, availability and property content.
4. Re-authorise or remap Booking.com hotel `7090541` in Beds24.
5. Run one controlled reservation -> modification -> cancellation test and prove identical inventory and status in both systems.
6. Only after the test, enable ongoing channel control in Beds24.
7. Record the canonical property ID, room IDs and mapping table in Control Tower.

### Definition of done
- No `HOTEL_ACCESS_DENIED`.
- Exact room mapping documented.
- Controlled end-to-end channel test passed.
- No oversell and no manual/automatic split-brain inventory.

---

## Execution priority
1. Current guest physical access and fallback.
2. EL CID Booking.com/Beds24 channel recovery.
3. EL CID review website using approved assets.
4. Reporting pack after critical guest-access and distribution risks are contained.
