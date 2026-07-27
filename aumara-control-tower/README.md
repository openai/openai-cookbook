# AUMARA Control Tower

Staged transactional email/webhook service for AUMARA El Cid. It starts in
`off`, supports a zero-send `audit` stage, and requires a separately confirmed
`live` cutover.

## Run locally

```bash
cd aumara-control-tower
cp .env.example .env
npm install
npm test
npm start
```

## Endpoints

### GET /health

Returns the operating mode and safety status without exposing sender addresses,
tokens, booking references, or guest data.

### POST /send

Retired. It always returns HTTP 410 so arbitrary recipients, subjects, and HTML
cannot bypass the event policy.

### POST /webhooks/beds24

Beds24-style webhook receiver. Every non-off request requires
`Authorization: Bearer $AUMARA_WEBHOOK_TOKEN`. The only candidate event types
are `access_ready` and `pre_arrival_access`; they also require a recipient,
booking reference, and access code.

- `off`: HTTP 503; no processing.
- `audit`: redacted decision and TTL deduplication; mail transport is not loaded.
- `live`: additionally requires `AUMARA_LIVE_SEND_CONFIRMED=true`, a verified
  non-Resend-onboarding sender, a Resend key, and
  `AUMARA_ALLOW_ACCESS_CODES=true`.

Every candidate has a deterministic key. It is checked in-process and also sent
to Resend as an idempotency key, so concurrent/retried provider requests cannot
send a second copy during Resend's retention window.

The generic Beds24 auto-reply workflow is audit-only. Gmail is the sole current
live guest-reply path, preventing duplicate replies.

## Beds24 guest-note audit

`scripts/beds24_guest_note_sync.py` reads recent guest-side Beds24 messages,
classifies approved operational requests, resolves the existing booking with
`includeInfoItems=true`, and proposes a single `GUESTREQUEST` info item per
booking/request type. CI uses synthetic data only, receives no Beds24
credentials, makes no network call, and uploads no guest-data artifact. A
runtime that processes private Beds24 data is deliberately not scheduled until
that destination is explicitly approved.

The future write payload is deliberately limited to:

```json
[
  {
    "id": 1234567,
    "infoItems": [
      {
        "code": "GUESTREQUEST",
        "text": "[AUMARA:BED_REQUEST:...] BED REQUEST — ..."
      }
    ]
  }
]
```

Live note mode is not scheduled. It requires the booking-mutation kill switch
to be off, `AUMARA_LIVE_BOOKING_WRITES_CONFIRMED=true`, the exact
`AUMARA_BEDS24_NOTE_WRITE_CONFIRMATION=INFOITEMS_ONLY_PROPERTY_324903`, and an
explicit validated info code. It contains no guest-message send path.

## Guest-request dry run

The first automation stage creates reviewable reply and booking-note proposals
from a JSON snapshot. It cannot send mail or call Beds24: the Python worker has
no external-service client and refuses to run unless all three safety guards
are enabled.

```bash
export AUMARA_DRY_RUN=true
export AUMARA_DISABLE_EMAIL_SEND=true
export AUMARA_DISABLE_BOOKING_MUTATIONS=true

python scripts/guest_request_dry_run.py \
  --input fixtures/guest-request-dry-run.json \
  --output /tmp/aumara-guest-request-dry-run/report.json \
  --csv /tmp/aumara-guest-request-dry-run/audit.csv
```

The audit records classifications, deduplication, manual-review decisions,
proposed text, and proposed booking notes. Every row records
`email_send_requested=false` and `booking_mutation_requested=false`.

The legacy paid-booking recovery workflow is retired and hard-disabled. Its
safety check only writes a local artifact proving that no external network,
email, or booking action occurred.

## Current mail routing

- Provider: Resend
- Reply-to: `elcidspain@gmail.com`
- Test recipient: `elcidspain@gmail.com`
- The Resend onboarding sender is forbidden in live mode.

## Production next step

Before deployment, provision a durable external idempotency store. The in-memory
store is sufficient for local and single-instance audit validation but is not a
production cutover dependency.

After that dependency is reviewed, deploy this folder in `audit`, set
environment variables, then connect the Beds24 webhook to:

```text
POST https://YOUR-SERVICE/webhooks/beds24
Authorization: Bearer AUMARA_WEBHOOK_TOKEN
```

No booking mutation exists in this service. Live email execution requires a
separate reviewed configuration change and explicit approval.
