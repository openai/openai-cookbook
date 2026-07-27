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
