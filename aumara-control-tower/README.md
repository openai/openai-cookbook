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

### GET /daily-ops

Data-free shell for the internal AUMARA / EL CID operating dashboard. The page
requests the separate dashboard viewer token and reads only the authenticated
snapshot API.

### GET /api/daily-ops/latest

Returns the latest validated `aumara-daily-ops-v1` snapshot. It is disabled
unless both `AUMARA_DASHBOARD_TOKEN` and `AUMARA_DAILY_OPS_SNAPSHOT` are
configured. It has no write method and does not reuse the webhook token.

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

## Daily Ops dashboard

Dashboard v1 reuses the existing Gmail summary, Beds24 reads, Epos Now export
and Bitrix24 task read. It creates no new monitoring or database and reports
missing sources as unavailable instead of zero.

Build a synthetic local preview:

```bash
python scripts/daily_ops_snapshot.py \
  --date 2026-07-30 \
  --now 2026-07-30T21:00:00Z \
  --gmail fixtures/daily-ops/gmail.json \
  --beds24 fixtures/daily-ops/beds24.json \
  --epos-dir fixtures/daily-ops/epos \
  --b24 fixtures/daily-ops/b24.json \
  --output /tmp/aumara-daily-ops/latest.json \
  --history-dir /tmp/aumara-daily-ops/history
```

Then point `AUMARA_DAILY_OPS_SNAPSHOT` at `latest.json`, configure a separate
strong `AUMARA_DASHBOARD_TOKEN`, start the existing service and open
`/daily-ops`.

The complete source contract and production boundary are documented in
[`docs/daily-ops-dashboard-v1.md`](docs/daily-ops-dashboard-v1.md).

## Beds24 continuous guest notes

The scheduled `AUMARA Beds24 continuous guest notes` workflow runs hourly and
uses the existing refresh credential. It processes three independent,
fail-closed workers sequentially: direct guest-message requests, safe cot
requests with room/infant/occupancy proof, and recent combined bed/non-smoking
booking requests. Every run is bounded and idempotent, changes only
`infoItems`, and requires an exact GET read-back after each successful POST.
Zero-candidate runs are successful. CI pull-request runs use synthetic data
only and receive no Beds24 credential.

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

The direct-message worker accepts only explicit bed, pet, parking, early
check-in, late check-in and late check-out requests on active EL CID bookings.
Cot requests are excluded from that generic worker and handled only by the
stricter cot policy. Unsupported, ambiguous, financial and access-code cases
remain outside the writer. None of these workers contains a guest-message send
path.

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
- Reply-to: configured only through the approved secret/runtime environment.
- Test recipient: configured only through the approved secret/runtime
  environment.
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
