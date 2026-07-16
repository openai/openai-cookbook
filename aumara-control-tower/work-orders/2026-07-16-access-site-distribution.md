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

### Correct diagnosis
Beds24 TTLock codes can only be used during the booking period. PIN generation and guest-message timing are separate from physical validity. A rejection before check-in is expected and is not proof that the PIN is wrong.

Online PIN strategy requires the mapped TTLock to be connected to the internet through a commissioned gateway. Offline strategy does not require a gateway, but codes cannot be customised, updated or deleted and must first be used within 24 hours of their start time.

### Immediate action
1. In Beds24 TTLock settings record, without secrets:
   - lock mapped to Superior Chalet Unit 1;
   - current PIN strategy;
   - Start Time / End Time;
   - Days in Advance;
   - gateway/cloud state.
2. Create a separate temporary test PIN in TTLock valid immediately for 30 minutes. Do not modify or expose the guest PIN.
3. Test the physical green-house lock, revoke the temporary PIN and record the audit result.
4. If the gateway is not commissioned, use the offline-PIN runbook for the current arrival and retain the mechanical-key fallback.
5. At the configured start time on 2026-07-18, verify the booking PIN on the physical door.
6. Only after physical proof, send one Spanish guest-access message containing the PIN, map, address, check-in/check-out times and support contact.
7. Confirm duplicate booking `89851675` is cancelled and cannot retain a second active access credential.

### Permanent target
- Two TTLock gateways commissioned and monitored.
- Online PIN strategy: last 6 valid guest-phone digits, with random fallback when phone data is invalid.
- Instant `Export to TTLock` after booking, room, date or contact changes.
- Cancellation revokes the online PIN.
- End-to-end evidence: booking -> PIN -> correct physical house -> checkout expiry -> cancellation revoke.

### Definition of done
- Temporary PIN opens and is revoked.
- Guest PIN opens only in the correct validity window.
- One booking maps to one house and one active access credential.
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
