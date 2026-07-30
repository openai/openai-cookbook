# AUMARA Daily Ops Dashboard v1

## Purpose

Daily Ops is the read-only operating screen for AUMARA and EL CID. It combines
reviewed outputs from the existing source paths into one current snapshot and
an optional append-only history.

It does **not** create another monitor, scheduler or operational database.

```text
existing Gmail summary ─┐
existing Beds24 read ───┼─> daily_ops_snapshot.py ─> latest.json ─> Control Tower
existing EPOS export ───┤                          └> history/YYYY-MM-DD/*.json
existing B24 read ──────┘
```

## Source-of-truth rules

| Source | Authoritative for | Not used for |
| --- | --- | --- |
| Gmail | guest events, verified SENT replies, drafts, bounce/DSN, response exceptions | booking revenue |
| Beds24 | bookings, modifications, cancellations, stay dates, occupancy and booked-value movement | restaurant sales |
| Epos Now | restaurant sales, VAT, cash/card tenders and refunds | hotel revenue |
| Bitrix24 (B24) | operational task state, owners, deadlines and completion | booking or sales truth |

Overlapping values are not added together. Missing or blocked sources remain
`null`; the dashboard must never display an unavailable source as zero
activity.

## Canonical snapshot

The builder emits `aumara-daily-ops-v1` with:

- `businessDate` in `Europe/Madrid`;
- source freshness and explicit `healthy`, `stale`, `blocked` or `unavailable`
  state;
- metrics grouped into guest operations, bookings/value, restaurant and B24
  execution;
- one deduplicated event list;
- a data-quality status of `ready`, `partial` or `blocked`.

The server recalculates source freshness on every authenticated read. An old
snapshot cannot remain visually `ready` merely because the snapshot builder
stopped.

Private production snapshots are runtime data. Do not commit them, upload them
as public CI artifacts or paste them into pull requests.

All files under `fixtures/daily-ops/` are synthetic `TEST_ONLY` regression data.
They must never be replaced with production exports or real guest, booking,
task, revenue or tender data.

## Existing source contracts

### Gmail

The existing `Сводка ответов гостям` task is the Gmail reader. Its reviewed JSON
output uses:

```json
{
  "schema": "aumara-gmail-daily-v1",
  "generatedAtUtc": "ISO-8601",
  "businessDate": "YYYY-MM-DD",
  "counters": {
    "eventsReceived": 0,
    "confirmedSentReplies": 0,
    "cancellationFollowUps": 0,
    "opsLogged": 0,
    "needsDecision": 0,
    "beds24NotesPending": 0,
    "lostReplies": 0,
    "deliveryErrors": 0,
    "draftReplies": 0
  },
  "events": []
}
```

`DRAFT` is never counted as SENT.

Gmail labels are applied to individual messages, so raw label totals are not
event totals. The existing summary must group by thread/booking event, verify a
later message in `SENT`, check the exact recipient and empty CC/BCC, and
deduplicate grouped Booking notifications before producing the counters above.

### Beds24

The builder accepts the redacted
`aumara-beds24-guest-message-ingest-v1` artifact from PR #15 and the enriched
`aumara-beds24-daily-v1` summary when booking/value metrics are available. A
`BLOCKED` artifact stays blocked and does not generate zero booking metrics.
Passing deterministic tests without running the credential-backed proof is not
enough to mark Beds24 healthy.

### Epos Now

The existing `scripts/eposnow_reporting_export.py` directory is consumed
directly:

- `manifest.json` provides sales, VAT and transaction counts;
- `tenders.csv` provides cash/card/refund mix.

No additional EPOS connector is introduced.

### Bitrix24

The builder accepts the reviewed output of the existing read-only B24
connection:

```json
{
  "schema": "aumara-b24-task-status-v1",
  "status": "OK",
  "generatedAtUtc": "ISO-8601",
  "summary": {
    "openTasks": 0,
    "closedToday": 0,
    "overdueTasks": 0
  },
  "events": []
}
```

This PR does not create or replace a B24 webhook. Until the existing connection
produces this snapshot, B24 is shown as unavailable.

## Build a snapshot

```bash
python scripts/daily_ops_snapshot.py \
  --date 2026-07-30 \
  --gmail /approved/source/gmail.json \
  --beds24 /approved/source/beds24.json \
  --epos-dir /approved/source/epos \
  --b24 /approved/source/b24.json \
  --output /var/lib/aumara-control-tower/daily-ops/latest.json \
  --history-dir /var/lib/aumara-control-tower/daily-ops/history
```

The `latest.json` update is atomic. History files are append-only and fail
closed if the same timestamp already exists with different content.

## Serve the dashboard

The existing Control Tower server exposes:

- `GET /daily-ops` — data-free dashboard shell;
- `GET /api/daily-ops/latest` — authenticated read-only snapshot.

Runtime configuration:

```text
AUMARA_DASHBOARD_TOKEN=<separate strong viewer token>
AUMARA_DAILY_OPS_SNAPSHOT=/var/lib/aumara-control-tower/daily-ops/latest.json
```

The API is disabled when either value is missing. It never accepts POST, PUT,
PATCH or DELETE. The viewer token is separate from the webhook token so opening
the dashboard cannot disclose the webhook credential.

If a browser refresh fails, the screen replaces its quality badge with
`REFRESH FAILED`; it does not silently preserve a formerly healthy state.

## Deployment boundary

This PR contains no deployment, schedule, external write or credential change.
Production cutover requires the existing Control Tower runtime to provide:

1. a durable approved snapshot directory;
2. a separate dashboard viewer token in the existing secret manager;
3. reviewed source snapshots from the existing Gmail, Beds24, EPOS and B24
   paths;
4. an access-controlled internal URL.

Until all four sources are proven, the dashboard is intentionally `partial`
rather than presenting invented completeness.
