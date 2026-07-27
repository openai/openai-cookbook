# AUMARA Control Tower

Working transactional email/webhook service for AUMARA El Cid.

## Run locally

```bash
cd aumara-control-tower
cp .env.example .env
npm install
npm run health
npm run test:email
npm start
```

## Endpoints

### GET /health

Returns service status.

### POST /send

Generic send endpoint. Auth: `Authorization: Bearer $AUMARA_WEBHOOK_TOKEN`.

```bash
curl -X POST http://localhost:8787/send \
  -H "content-type: application/json" \
  -H "authorization: Bearer change-this-token" \
  -d '{
    "to":"elcidspain@gmail.com",
    "guestName":"Test Guest",
    "property":"AUMARA El Cid",
    "checkIn":"2026-07-10",
    "checkOut":"2026-07-12",
    "accessCode":"123456",
    "bookingRef":"TEST-001"
  }'
```

### POST /webhooks/beds24

Beds24-style webhook receiver. It accepts flexible fields: `email`, `guestEmail`, `guest_email`, `mail`, `guestName`, `property`, `checkIn`, `checkOut`, `accessCode`, `pin`, `code`, `bookingRef`.

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
- Temporary sender: `AUMARA El Cid <onboarding@resend.dev>` until the domain sender is verified.

## Production next step

Deploy this folder as a Node service, set environment variables, then connect Beds24 action/webhook to:

```text
POST https://YOUR-SERVICE/webhooks/beds24
Authorization: Bearer AUMARA_WEBHOOK_TOKEN
```

The guest-request classifier is not yet authorized for production sends or
booking mutations. Live execution requires a separate reviewed change and
explicit approval.
