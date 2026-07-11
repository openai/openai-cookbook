# AUMARA Control Tower

Working transactional email/webhook service for AUMARA El Cid, plus a Threads Insights collector for the Content Studio.

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

## Threads Content Studio automation

The collector reads the account's own Threads posts and insights, separates content views from profile views, calculates the remaining pace for the 100,000-view sprint, writes a verified checkpoint to the Airtable `Threads Metrics` table, and emails a concise metric summary.

Required Meta permissions:

- `threads_basic`
- `threads_manage_insights`

Configure the Threads and Airtable values in `.env`, then run:

```bash
npm run threads:daily
```

The script is read-only toward Threads. It does not publish, reply, like, follow, unfollow, archive or delete anything.

For production, schedule `npm run threads:daily` once per day after the Threads token and Airtable PAT are installed as secrets. The sprint dates are anchored by default to 26 June–25 July 2026 and can be changed through environment variables.

## Current mail routing

- Provider: Resend
- Reply-to: `elcidspain@gmail.com`
- Test recipient: `elcidspain@gmail.com`
- Temporary sender: `AUMARA El Cid <onboarding@resend.dev>` until the domain sender is verified.

## Production next step

Deploy this folder as a Node service, set environment variables, connect the Beds24 action/webhook, and add a daily scheduler for `npm run threads:daily`.

```text
POST https://YOUR-SERVICE/webhooks/beds24
Authorization: Bearer AUMARA_WEBHOOK_TOKEN
```
