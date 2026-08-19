import assert from 'node:assert/strict';
import { mkdtemp, writeFile } from 'node:fs/promises';
import os from 'node:os';
import path from 'node:path';
import { test } from 'node:test';
import {
  DAILY_OPS_SCHEMA,
  readDailyOpsSnapshot,
  refreshDailyOpsFreshness,
  validateDailyOpsSnapshot
} from './daily-ops.mjs';
import { dailyOpsPage } from './daily-ops-page.mjs';

function snapshot(overrides = {}) {
  const metrics = Object.fromEntries([
    'guestEvents',
    'confirmedSentReplies',
    'cancellationFollowUps',
    'opsLogged',
    'needsDecision',
    'beds24NotesPending',
    'lostReplies',
    'deliveryErrors',
    'draftReplies',
    'newBookings',
    'modifiedBookings',
    'cancelledBookings',
    'bookedRevenueAddedEur',
    'bookedRevenueCancelledEur',
    'bookedRevenueNetEur',
    'arrivals',
    'departures',
    'occupiedRoomNights',
    'restaurantSalesGrossEur',
    'restaurantVatEur',
    'restaurantCashEur',
    'restaurantCardEur',
    'restaurantRefundsEur',
    'restaurantTransactions',
    'b24OpenTasks',
    'b24ClosedToday',
    'b24OverdueTasks'
  ].map(key => [key, null]));
  metrics.guestEvents = 3;

  return {
    schema: DAILY_OPS_SCHEMA,
    businessDate: '2026-07-30',
    timezone: 'Europe/Madrid',
    generatedAtUtc: '2026-07-30T21:00:00Z',
    dataQuality: {
      status: 'partial',
      duplicateEventsRemoved: 0,
      issues: ['b24 source is unavailable'],
      unavailableMetricsAreNull: true
    },
    sources: [
      {
        id: 'gmail',
        status: 'healthy',
        capturedAtUtc: '2026-07-30T20:45:00Z',
        freshnessSlaMinutes: 150
      },
      {
        id: 'beds24',
        status: 'healthy',
        capturedAtUtc: '2026-07-30T20:40:00Z',
        freshnessSlaMinutes: 150
      },
      {
        id: 'epos',
        status: 'healthy',
        capturedAtUtc: '2026-07-30T20:30:00Z',
        freshnessSlaMinutes: 1440
      },
      { id: 'b24', status: 'unavailable' }
    ],
    metrics,
    events: [
      {
        eventId: 'synthetic-event',
        source: 'gmail',
        type: 'guest_reply_sent',
        summary: 'Synthetic only'
      }
    ],
    ...overrides
  };
}

test('validates one canonical snapshot with explicit unavailable values', () => {
  const value = validateDailyOpsSnapshot(snapshot());
  assert.equal(value.metrics.guestEvents, 3);
  assert.equal(value.metrics.b24OpenTasks, null);
});

test('rejects duplicate events and missing source state', () => {
  assert.throws(
    () => validateDailyOpsSnapshot(snapshot({
      events: [
        { eventId: 'same', source: 'gmail' },
        { eventId: 'same', source: 'gmail' }
      ]
    })),
    /duplicate event/
  );
  assert.throws(
    () => validateDailyOpsSnapshot(snapshot({
      sources: [{
        id: 'gmail',
        status: 'healthy',
        capturedAtUtc: '2026-07-30T20:45:00Z',
        freshnessSlaMinutes: 150
      }]
    })),
    /missing source/
  );
});

test('rejects missing and non-finite metrics', () => {
  const missing = snapshot();
  delete missing.metrics.deliveryErrors;
  assert.throws(() => validateDailyOpsSnapshot(missing), /missing metric/);

  const invalid = snapshot();
  invalid.metrics.restaurantSalesGrossEur = Number.POSITIVE_INFINITY;
  assert.throws(() => validateDailyOpsSnapshot(invalid), /invalid metric/);
});

test('reads a bounded snapshot file and rejects invalid JSON', async () => {
  const directory = await mkdtemp(path.join(os.tmpdir(), 'aumara-daily-ops-'));
  const good = path.join(directory, 'good.json');
  const bad = path.join(directory, 'bad.json');
  await writeFile(good, JSON.stringify(snapshot()));
  await writeFile(bad, '{');

  assert.equal(
    (
      await readDailyOpsSnapshot(
        good,
        undefined,
        new Date('2026-07-30T21:00:00Z')
      )
    ).schema,
    DAILY_OPS_SCHEMA
  );
  await assert.rejects(readDailyOpsSnapshot(bad), /not valid JSON/);
});

test('recomputes freshness at read time instead of trusting an old ready state', () => {
  const value = snapshot({
    dataQuality: {
      status: 'ready',
      duplicateEventsRemoved: 0,
      issues: [],
      unavailableMetricsAreNull: true
    },
    sources: snapshot().sources.map(source => (
      source.id === 'b24'
        ? {
            id: 'b24',
            status: 'healthy',
            capturedAtUtc: '2026-07-30T20:50:00Z',
            freshnessSlaMinutes: 150
          }
        : source
    ))
  });
  const refreshed = refreshDailyOpsFreshness(
    validateDailyOpsSnapshot(value),
    new Date('2026-07-31T02:00:00Z')
  );

  assert.equal(refreshed.dataQuality.status, 'partial');
  assert.equal(
    refreshed.sources.find(source => source.id === 'gmail').status,
    'stale'
  );
  assert.match(refreshed.dataQuality.issues.join(' '), /gmail source is stale/);
});

test('dashboard shell contains no embedded operational snapshot or external runtime', () => {
  const page = dailyOpsPage();
  assert.match(page, /AUMARA Daily Ops/);
  assert.match(page, /\/api\/daily-ops\/latest/);
  assert.doesNotMatch(page, /Synthetic Guest/);
  assert.doesNotMatch(page, /https:\/\/cdn\./);
});
