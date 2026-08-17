# AUMARA / EL CID guest-service journey v1

## Decision

The existing Control Tower remains the policy and audit boundary. Make.com is
not introduced as a second reply brain. Shadow execution remains proposal-only.
The live boundary is a separate, manual AUMARA-only canary.

## Enabled proposal moments

1. `post_checkin`: one care check from 60 to 180 minutes after verified
   check-in, only while the booking is in house.
2. `first_morning`: one comfort check on the first morning, 08:30-11:30 local
   time, only for stays of at least two nights and never on departure day.

Both moments support English, Spanish, French, German and Dutch. Unsupported
languages fall back to English.

## Beds24 shadow feed

The scheduled shadow workflow reuses the existing Beds24 V2 authentication
boundary, reads active bookings and message history for both properties, and
feeds normalized events into this runtime. It uploads only aggregate counts and
reasons: no booking reference, guest name or guest-message text is retained in
the artifact.

The El Cid query is property-scoped (`propertyId=324903`) and deliberately has
no `roomId` filter. It therefore covers every room under the property, including
the currently registered room IDs `674484`, `674485` and `674486`; the legacy
module name `beds24_elcid_studio_audit.py` does not narrow the shadow feed to the
Studio.

## GitHub Copilot MCP

`config/copilot-mcp.json` is the canonical repository-level MCP configuration.
It exposes two allowlisted read-only Beds24 tools and a read-only filesystem
view of policies, docs and checkpoints. The local Python server implements MCP
over stdio; every command-based `mcpServers` entry explicitly uses
`"type": "stdio"`, and `--mcp` is not passed to the shadow CLI.

The GitHub Copilot Agents secret must be named
`COPILOT_MCP_BEDS24_REFRESH_CREDENTIAL`. It is separate from the GitHub Actions
secret and is referenced as `$COPILOT_MCP_BEDS24_REFRESH_CREDENTIAL`; no secret
value belongs in the repository or MCP JSON.

## Hard safety rules

- Checkout, departure-deadline and vacate messages are blocked.
- One stable booking/event key protects each lifecycle moment across policy
  snapshot updates; duplicate proposals in the same batch are suppressed.
- Cancelled, completed, no-show and non-in-house bookings are skipped.
- An open incident or negative guest signal suppresses routine copy and routes
  the stay to human review.
- Safety, access and payment signals are urgent; ordinary service problems are
  high priority.
- Structured issue flags take precedence over lifecycle deduplication, so a new
  complaint always reaches human review.
- No rating or public-review request is included during the stay.
- The runtime has no Beds24, Gmail, WhatsApp, HTTP or database client.

## Live Beds24 sender boundary

`scripts/beds24_guest_journey_live.py` is a separate execution boundary. The
workflow is `workflow_dispatch` only and accepts only property `324882`. That
property is fetched without a `roomId` filter and covers six physical AUMARA
units: four SL and two Chalet Super. Property `324903` remains shadow-only.

The sender reads current bookings and recent messages through the GET-only
requester, requires an actual Beds24 check-in timestamp, reuses
`guest_service_journey.build_report()`, and accepts only its `proposal`
decisions for `post_checkin` and `first_morning`.

Before each POST it writes
`324882:{booking_ref.lower()}:{event_type}` to DynamoDB table
`aumara-guest-journey-claims` with one conditional `PutItem`:

- partition key `dedupe_key` (String);
- `created_at` (UTC ISO timestamp);
- `ttl` (epoch seconds, seven days after creation);
- condition `attribute_not_exists(dedupe_key)`.

A conditional conflict skips the send. Any other claim failure aborts before
the POST. There is no local-file or `/tmp` fallback.

Live execution fails closed unless all guards are exact:

- `BEDS24_GUEST_JOURNEY_MODE=live`
- `BEDS24_LIVE_SEND_AUTHORIZED=true`
- `AUMARA_DISABLE_GUEST_SEND=false`
- `AUMARA_DISABLE_EMAIL_SEND=true`
- `AUMARA_DISABLE_BOOKING_MUTATIONS=true`

The only mutation endpoint is Beds24 `POST /bookings/messages`, using the
official array payload with `bookingId` and `message`. Checkout-pressure events,
rating/review language, response-time promises, and mattress/linen/satin claims
are rejected before the claim or POST boundary. Logs and output contain only
aggregate counters.

The manual workflow additionally requires confirmation text
`AUMARA-324882-LIVE`, repository secrets `BEDS24_REFRESH_CREDENTIAL`,
`AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`, and `DYNAMODB_TABLE`, plus the
repository variable `AWS_REGION`. The table must already exist with TTL enabled
on attribute `ttl`; this repository workflow does not create infrastructure or
credentials.

## Source boundary

The attached mattress, linen, response-time and amenity claims are not emitted
by v1. They require property-specific proof before they can become guest-facing
facts. The current copy sells responsiveness and local care without inventing
service guarantees.

## Cutover gate

Live delivery is manual and AUMARA-only. EL CID expansion, scheduling, table
creation, secret creation, IAM changes, and automatic retries remain separate
authorized cutovers.
