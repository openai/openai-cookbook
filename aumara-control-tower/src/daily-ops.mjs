import { readFile, stat } from 'node:fs/promises';

export const DAILY_OPS_SCHEMA = 'aumara-daily-ops-v1';
const SOURCE_IDS = new Set(['gmail', 'beds24', 'epos', 'b24']);
const SOURCE_STATUSES = new Set(['healthy', 'stale', 'blocked', 'unavailable']);
const METRIC_KEYS = new Set([
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
]);
const MAX_SNAPSHOT_BYTES = 3 * 1024 * 1024;

export class DailyOpsError extends Error {
  constructor(code, message) {
    super(message);
    this.code = code;
  }
}

function isObject(value) {
  return Boolean(value) && typeof value === 'object' && !Array.isArray(value);
}

function validIsoTimestamp(value) {
  return typeof value === 'string' && value.length > 0 && !Number.isNaN(Date.parse(value));
}

export function validateDailyOpsSnapshot(value) {
  if (!isObject(value)) {
    throw new DailyOpsError('invalid_snapshot', 'Daily Ops snapshot must be an object');
  }
  if (value.schema !== DAILY_OPS_SCHEMA) {
    throw new DailyOpsError('invalid_schema', `Expected ${DAILY_OPS_SCHEMA}`);
  }
  if (!/^\d{4}-\d{2}-\d{2}$/.test(String(value.businessDate || ''))) {
    throw new DailyOpsError('invalid_business_date', 'businessDate must be YYYY-MM-DD');
  }
  if (value.timezone !== 'Europe/Madrid') {
    throw new DailyOpsError('invalid_timezone', 'timezone must be Europe/Madrid');
  }
  if (!validIsoTimestamp(value.generatedAtUtc)) {
    throw new DailyOpsError('invalid_generated_at', 'generatedAtUtc must be ISO-8601');
  }
  if (!isObject(value.metrics)) {
    throw new DailyOpsError('invalid_metrics', 'metrics must be an object');
  }
  for (const metric of METRIC_KEYS) {
    if (!(metric in value.metrics)) {
      throw new DailyOpsError('missing_metric', `missing metric: ${metric}`);
    }
    const metricValue = value.metrics[metric];
    if (
      metricValue !== null &&
      (typeof metricValue !== 'number' || !Number.isFinite(metricValue))
    ) {
      throw new DailyOpsError('invalid_metric', `invalid metric: ${metric}`);
    }
  }
  if (!isObject(value.dataQuality)) {
    throw new DailyOpsError('invalid_data_quality', 'dataQuality must be an object');
  }
  if (!['ready', 'partial', 'blocked'].includes(value.dataQuality.status)) {
    throw new DailyOpsError('invalid_data_quality_status', 'invalid dataQuality status');
  }
  if (!Array.isArray(value.dataQuality.issues)) {
    throw new DailyOpsError('invalid_data_quality_issues', 'dataQuality issues must be an array');
  }
  if (!Array.isArray(value.sources) || !Array.isArray(value.events)) {
    throw new DailyOpsError('invalid_collections', 'sources and events must be arrays');
  }

  const observedSources = new Set();
  for (const source of value.sources) {
    if (!isObject(source) || !SOURCE_IDS.has(source.id)) {
      throw new DailyOpsError('invalid_source', 'snapshot contains an unknown source');
    }
    if (observedSources.has(source.id)) {
      throw new DailyOpsError('duplicate_source', `duplicate source: ${source.id}`);
    }
    observedSources.add(source.id);
    if (!SOURCE_STATUSES.has(source.status)) {
      throw new DailyOpsError('invalid_source_status', `invalid ${source.id} status`);
    }
    if (['healthy', 'stale'].includes(source.status)) {
      if (!validIsoTimestamp(source.capturedAtUtc)) {
        throw new DailyOpsError(
          'invalid_source_capture',
          `${source.id} needs a valid capturedAtUtc`
        );
      }
      if (
        !Number.isSafeInteger(source.freshnessSlaMinutes) ||
        source.freshnessSlaMinutes <= 0
      ) {
        throw new DailyOpsError(
          'invalid_source_sla',
          `${source.id} needs a positive freshness SLA`
        );
      }
    }
  }
  for (const sourceId of SOURCE_IDS) {
    if (!observedSources.has(sourceId)) {
      throw new DailyOpsError('missing_source', `missing source: ${sourceId}`);
    }
  }

  const eventIds = new Set();
  for (const event of value.events) {
    if (!isObject(event) || typeof event.eventId !== 'string' || !event.eventId) {
      throw new DailyOpsError('invalid_event', 'every event needs a non-empty eventId');
    }
    if (eventIds.has(event.eventId)) {
      throw new DailyOpsError('duplicate_event', `duplicate event: ${event.eventId}`);
    }
    eventIds.add(event.eventId);
    if (!SOURCE_IDS.has(event.source)) {
      throw new DailyOpsError('invalid_event_source', `invalid event source: ${event.source}`);
    }
  }
  return value;
}

export function refreshDailyOpsFreshness(value, now = new Date()) {
  const nowMs = now instanceof Date ? now.getTime() : Number(now);
  if (!Number.isFinite(nowMs)) {
    throw new DailyOpsError('invalid_freshness_clock', 'freshness clock is invalid');
  }

  const snapshot = structuredClone(value);
  const issues = [...snapshot.dataQuality.issues];
  for (const source of snapshot.sources) {
    if (!['healthy', 'stale'].includes(source.status)) continue;
    const capturedAt = Date.parse(source.capturedAtUtc);
    const age = Math.max(0, Math.floor((nowMs - capturedAt) / 60000));
    source.freshnessMinutes = age;
    if (age > source.freshnessSlaMinutes) {
      source.status = 'stale';
      const issue = `${source.id} source is stale: freshness threshold exceeded`;
      if (!issues.includes(issue)) issues.push(issue);
    }
  }

  const available = snapshot.sources.filter(
    source => !['blocked', 'unavailable'].includes(source.status)
  );
  if (!available.length) {
    snapshot.dataQuality.status = 'blocked';
  } else if (
    snapshot.sources.some(source => source.status !== 'healthy') ||
    issues.length
  ) {
    snapshot.dataQuality.status = 'partial';
  } else {
    snapshot.dataQuality.status = 'ready';
  }
  snapshot.dataQuality.issues = issues;
  return snapshot;
}

export async function readDailyOpsSnapshot(
  path,
  maxBytes = MAX_SNAPSHOT_BYTES,
  now = new Date()
) {
  if (!path) {
    throw new DailyOpsError(
      'snapshot_not_configured',
      'AUMARA_DAILY_OPS_SNAPSHOT is not configured'
    );
  }
  let metadata;
  try {
    metadata = await stat(path);
  } catch {
    throw new DailyOpsError('snapshot_unavailable', 'Daily Ops snapshot is unavailable');
  }
  if (!metadata.isFile() || metadata.size <= 0 || metadata.size > maxBytes) {
    throw new DailyOpsError(
      'snapshot_size_invalid',
      'Daily Ops snapshot size is outside the allowed range'
    );
  }
  let parsed;
  try {
    parsed = JSON.parse(await readFile(path, 'utf8'));
  } catch {
    throw new DailyOpsError('snapshot_unreadable', 'Daily Ops snapshot is not valid JSON');
  }
  return refreshDailyOpsFreshness(validateDailyOpsSnapshot(parsed), now);
}
