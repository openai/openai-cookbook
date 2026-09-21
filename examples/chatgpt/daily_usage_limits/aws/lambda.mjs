import { createDynamoStore, hash } from './store.mjs';
import { createControlLoader } from './control.mjs';

const ACTIONS = new Set(['probe', 'preview', 'apply', 'restore', 'resume_auth', 'cancel_initial']);
const MAX_EVENT_AGE_MS = 2 * 60 * 60 * 1000;
const safeCode = value => /^[A-Z][A-Z0-9_]{0,99}$/.test(value ?? '') ? value : 'RUNTIME_OR_DEPENDENCY_FAILURE';

export function runProgress(run, now = new Date()) {
  return { runId: run.runId, total: run.total, queued: run.cursor, completed: run.completed,
    succeeded: run.succeeded, attention: run.attention, outstanding: run.total - run.completed,
    status: run.cancelled ? 'cancelled' : run.completed === run.total ? (run.attention ? 'completed_with_attention' : 'completed') :
      Date.parse(run.validUntil) <= now.getTime() ? 'expired' : run.cursor < run.total ? 'dispatching' : 'processing' };
}

/** Scheduler/manual calls create durable runs. SQS records resume bounded dispatch or one member. */
export function createHandler({ store, execute, createExecutionContext, validateCurrentCohort,
  apiFactory, secretProvider, putMetric, queue, queueArn,
  deploymentId, controlSha256, pilotExpiresAt, applyEnabled = false, allowedWriteAction = 'none',
  runEventsNotBefore = '1970-01-01T00:00:00Z',
  dispatchBatchSize = 100, recordConcurrency = 1, maxReceiveCount = 10,
  clock = () => new Date(), log = line => console.log(line) }) {
  if (![dispatchBatchSize, recordConcurrency, maxReceiveCount].every(value => Number.isSafeInteger(value) && value > 0) ||
      recordConcurrency > 10 || !['none', 'apply', 'restore'].includes(allowedWriteAction) ||
      !Number.isFinite(Date.parse(runEventsNotBefore))) throw new Error('INVALID_QUEUE_CONFIGURATION');
  const loadControl = createControlLoader({ store, controlSha256 });
  let executionContext;
  let enrolledUserIds;
  let activeContext = {};
  let secretForInvocation;
  let cachedApiKey;
  const apiCache = new Map();
  async function controls() {
    const control = await loadControl();
    executionContext ??= createExecutionContext({ ...control, now: clock().toISOString() });
    enrolledUserIds ??= control.enrollment.members.map(member => member.userId);
    return { ...control, executionContext };
  }
  function remaining(context, validUntil = pilotExpiresAt) {
    return Math.min(context?.getRemainingTimeInMillis?.() ?? (context ? Infinity : 0),
      Date.parse(pilotExpiresAt) - clock().getTime(), Date.parse(validUntil) - clock().getTime());
  }
  function checkExpiry(validUntil = pilotExpiresAt) {
    if (!Number.isFinite(Date.parse(pilotExpiresAt)) || !Number.isFinite(Date.parse(validUntil)) ||
        clock().getTime() >= Math.min(Date.parse(pilotExpiresAt), Date.parse(validUntil))) throw new Error('PILOT_EXPIRED');
  }
  function checkPolicy(config, action) {
    checkExpiry(config.period?.end);
    if (Date.parse(config.period?.start) > clock().getTime()) throw new Error('PERIOD_REVIEW_REQUIRED');
    const apply = action === 'apply' || action === 'restore';
    if (apply && !(applyEnabled && config.liveWrites && allowedWriteAction === action)) throw new Error('WRITES_DISABLED');
    return apply;
  }
  async function apiFor(config, userIds, apply, context) {
    if (remaining(context, config.period.end) <= 55_000) throw new Error('TIME_BUDGET_EXHAUSTED');
    secretForInvocation ??= secretProvider();
    const apiKey = await secretForInvocation;
    if (cachedApiKey !== apiKey) { apiCache.clear(); cachedApiKey = apiKey; }
    if (apiCache.has(apply)) return apiCache.get(apply);
    const api = apiFactory({ apiKey, workspaceId: config.workspaceId, userIds: enrolledUserIds,
      allowWrites: apply, timeoutMs: 10_000, maxPages: config.apiLimits?.maxPages,
      maxRows: config.apiLimits?.maxRows, clock: () => clock().toISOString(),
      remainingTimeMs: () => remaining(activeContext, config.period.end) });
    apiCache.set(apply, api);
    return api;
  }
  async function start(event, context) {
    if (event?.version === 1 && event.action === 'cancel_run' && /^[a-f0-9]{64}$/.test(event.runId ?? '') &&
        Object.keys(event).every(key => ['version', 'action', 'runId', 'scheduledAt'].includes(key))) {
      const run = await store.getRun(event.runId);
      if (!run) throw new Error('RUN_NOT_FOUND');
      await store.cancelRun(run.runId);
      await store.putReceipt({ kind: 'aws_run_cancelled', runId: run.runId, checkedAt: clock().toISOString() });
      return { ok: true, ...runProgress({ ...run, cancelled: true }, clock()) };
    }
    checkExpiry();
    const scheduled = Date.parse(event?.scheduledAt);
    if (event?.version !== 1 || !ACTIONS.has(event?.action) || !Number.isFinite(scheduled) ||
        scheduled < Date.parse(runEventsNotBefore) || scheduled > clock().getTime() + 60_000 || clock().getTime() - scheduled > MAX_EVENT_AGE_MS ||
        Object.keys(event).some(key => !['version', 'action', 'scheduledAt'].includes(key))) throw new Error('INVALID_EVENT');
    const runId = hash(`${deploymentId}:${controlSha256}:${event.scheduledAt}:${event.action}`);
    if (event.action === 'probe') {
      await store.putReceipt({ kind: 'aws_probe', runId, checkedAt: clock().toISOString(), ok: true });
      return { ok: true, runId, action: 'probe', apiAccessed: false, capWrites: 0 };
    }
    const { config, enrollment } = await controls();
    checkPolicy(config, event.action);
    await store.withLock(`start:${deploymentId}:${runId}`, async () => {
      if (await store.getRun(runId)) return;
      const api = await apiFor(config, enrollment.members.map(member => member.userId), false, context);
      await validateCurrentCohort(config, enrollment, api,
        { restore: ['restore', 'resume_auth', 'cancel_initial'].includes(event.action) });
      checkPolicy(config, event.action);
      await store.createRun({ runId, controlSha256, action: event.action, scheduledAt: event.scheduledAt,
        total: enrollment.members.length, createdAt: clock().toISOString(),
        validUntil: new Date(Math.min(Date.parse(pilotExpiresAt), Date.parse(config.period.end))).toISOString() });
    });
    await queue.send([{ version: 1, kind: 'feed', runId }]);
    const progress = runProgress(await store.getRun(runId), clock());
    await store.putReceipt({ kind: 'aws_run_started', ...progress, action: event.action, checkedAt: clock().toISOString() });
    await putMetric('SuccessfulInvocation', 1);
    log(JSON.stringify({ event: 'usage_controller_run_started', action: event.action, ...progress }));
    return { ok: true, ...progress };
  }
  async function getRun(runId) {
    const run = await store.getRun(runId);
    const inactive = run?.cancelled === true ||
      (Number.isFinite(Date.parse(run?.scheduledAt)) && Date.parse(run.scheduledAt) < Date.parse(runEventsNotBefore));
    if (!run || (!inactive && run.controlSha256 !== controlSha256)) throw new Error('RUN_CONTROL_MISMATCH');
    return run;
  }
  async function feed(message, context) {
    const lease = `feed:${deploymentId}:${message.runId}`;
    await store.withLock(lease, async () => {
      const run = await getRun(message.runId);
      if (Date.parse(run.scheduledAt) < Date.parse(runEventsNotBefore)) { await store.cancelRun(run.runId); return; }
      if (run.cancelled) return;
      checkExpiry(run.validUntil);
      if (run.cursor >= run.total) return;
      const end = Math.min(run.total, run.cursor + dispatchBatchSize);
      let cursor = run.cursor;
      while (cursor < end && remaining(context, run.validUntil) > 15_000) {
        const until = Math.min(end, cursor + 10);
        await queue.send(Array.from({ length: until - cursor }, (_, offset) =>
          ({ version: 1, kind: 'member', runId: run.runId, index: cursor + offset })));
        cursor = until;
        // Send first, checkpoint second. An uncertain send can duplicate work but cannot lose it.
        await store.setRunCursor(run.runId, cursor, lease);
      }
      if (cursor < run.total) await queue.send([{ version: 1, kind: 'feed', runId: run.runId }]);
      await putMetric('DispatchProgress', cursor - run.cursor);
    });
  }
  async function retry(run, index, record, delayMs, code) {
    const notBefore = new Date(clock().getTime() + Math.max(1000, delayMs)).toISOString();
    if (Date.parse(notBefore) >= Date.parse(run.validUntil) || Number(record.attributes?.ApproximateReceiveCount ?? 1) >= maxReceiveCount) {
      await store.completeMember(run.runId, index, { ok: false, code: Date.parse(notBefore) >= Date.parse(run.validUntil) ? 'RETRY_EXCEEDS_EXPIRY' : 'RETRY_LIMIT_REACHED' });
      await putMetric('ControllerIssue', 1);
      return false;
    }
    await store.putRetry(run.runId, index, notBefore);
    if (code === 'ADMIN_HTTP_429') await store.pauseRun(run.runId, notBefore);
    await queue.defer(record.receiptHandle, Math.max(1, Math.min(43_200, Math.ceil((Date.parse(notBefore) - clock().getTime()) / 1000))));
    return true;
  }
  async function member(message, record, context) {
    return store.withLock(`work:${deploymentId}:${message.runId}:${message.index}`, async () => {
      if (await store.getMemberResult(message.runId, message.index)) return false;
      const run = await getRun(message.runId);
      if (!Number.isSafeInteger(message.index) || message.index < 0 || message.index >= run.total) throw new Error('INVALID_MEMBER_INDEX');
      if (run.cancelled || Date.parse(run.scheduledAt) < Date.parse(runEventsNotBefore)) {
        if (!run.cancelled) await store.cancelRun(run.runId);
        await store.completeMember(run.runId, message.index, { ok: false, code: 'RUN_CANCELLED' });
        return false;
      }
      if (remaining(context, run.validUntil) <= 0) {
        await store.completeMember(run.runId, message.index, { ok: false, code: 'PILOT_EXPIRED' });
        await putMetric('ControllerIssue', 1);
        return false;
      }
      const notBefore = Math.max(Date.parse(run.notBefore ?? '') || 0, Date.parse(await store.getRetry(run.runId, message.index)) || 0);
      if (notBefore > clock().getTime()) {
        await queue.defer(record.receiptHandle, Math.min(43_200, Math.ceil((notBefore - clock().getTime()) / 1000)));
        return true;
      }
      if (remaining(context, run.validUntil) <= 55_000) return retry(run, message.index, record, 30_000, 'TIME_BUDGET_EXHAUSTED');
      const { config, enrollment, executionContext } = await controls();
      if (run.total !== enrollment.members.length) throw new Error('RUN_MEMBER_COUNT_MISMATCH');
      const apply = checkPolicy(config, run.action);
      const selected = enrollment.members[message.index];
      const api = await apiFor(config, [selected.userId], apply, context);
      const result = await execute({ executionContext, memberIds: [selected.userId], api, store,
        clock: () => clock().toISOString(), apply, restore: run.action === 'restore',
        resumeAuth: run.action === 'resume_auth', cancelInitial: run.action === 'cancel_initial',
        shouldContinue: () => remaining(context, run.validUntil) > 55_000 });
      const outcome = result.results?.[0];
      if (!outcome || result.results.length !== 1) throw new Error('INVALID_MEMBER_RESULT');
      if (!outcome.ok && outcome.retryable) return retry(run, message.index, record,
        outcome.retryAfterMs ?? Math.min(300_000, 1000 * 2 ** Math.min(Number(record.attributes?.ApproximateReceiveCount ?? 1), 8)), outcome.code);
      const recorded = await store.completeMember(run.runId, message.index,
        { ok: outcome.ok, code: safeCode(outcome.code), status: outcome.status });
      await putMetric('ControllerIssue', outcome.ok ? 0 : 1);
      if (recorded) await putMetric('MemberCompleted', 1);
      return false;
    });
  }
  return async function handle(event, context = {}) {
    // Lambda invokes each warm process serially. Records in one batch share this deadline.
    activeContext = context;
    secretForInvocation = undefined;
    try {
    if (Array.isArray(event?.Records)) {
      const failures = [];
      let next = 0;
      await Promise.all(Array.from({ length: Math.min(recordConcurrency, event.Records.length) }, async () => {
        for (;;) {
          const record = event.Records[next++];
          if (!record) return;
          try {
            if (record.eventSource !== 'aws:sqs' || record.eventSourceARN !== queueArn) throw new Error('INVALID_QUEUE_SOURCE');
            const message = JSON.parse(record.body);
            const allowed = message.kind === 'member' ? ['version', 'kind', 'runId', 'index'] : ['version', 'kind', 'runId'];
            if (message.version !== 1 || !['feed', 'member'].includes(message.kind) || !/^[a-f0-9]{64}$/.test(message.runId ?? '') ||
                Object.keys(message).some(key => !allowed.includes(key))) throw new Error('INVALID_WORK_MESSAGE');
            if (message.kind === 'feed') await feed(message, context);
            else if (await member(message, record, context)) failures.push({ itemIdentifier: record.messageId });
          } catch {
            failures.push({ itemIdentifier: record.messageId });
            try { await putMetric('ControllerIssue', 1); } catch { /* Queue redrive remains independent. */ }
          }
        }
      }));
      return { batchItemFailures: failures };
    }
    try { return await start(event, context); }
    catch (error) {
      try { await store.putReceipt({ kind: 'aws_start_failed', code: safeCode(error.message), checkedAt: clock().toISOString() }); } catch { /* Async failure destination remains independent. */ }
      try { await putMetric('ControllerIssue', 1); } catch { /* Lambda Errors remains independent. */ }
      log(JSON.stringify({ event: 'usage_controller_failed' }));
      throw new Error('USAGE_CONTROLLER_FAILED: inspect private receipts and deployment health');
    }
    } finally { activeContext = undefined; secretForInvocation = undefined; }
  };
}

export function createSecretProvider({ secretArn, sendGetSecret }) {
  if (!/^arn:[^:]+:secretsmanager:[^:]+:\d{12}:secret:.+$/.test(secretArn ?? '')) throw new Error('INVALID_SECRET_ARN');
  return async () => {
    const response = await sendGetSecret(secretArn);
    let value;
    try { value = JSON.parse(response.SecretString); } catch { throw new Error('INVALID_SECRET_FORMAT'); }
    if (typeof value.apiKey !== 'string' || value.apiKey.length < 10) throw new Error('INVALID_SECRET_FORMAT');
    return value.apiKey;
  };
}

let liveHandler;
export async function handler(event, context) {
  if (!liveHandler) {
    const [{ DynamoDBClient }, doc, { SecretsManagerClient, GetSecretValueCommand },
      { CloudWatchClient, PutMetricDataCommand }, sqs, core, { createAdminApi }, selection] = await Promise.all([
      import('@aws-sdk/client-dynamodb'), import('@aws-sdk/lib-dynamodb'),
      import('@aws-sdk/client-secrets-manager'), import('@aws-sdk/client-cloudwatch'),
      import('@aws-sdk/client-sqs'), import('../src/controller.mjs'), import('../src/admin-api.mjs'), import('../src/selection.mjs'),
    ]);
    const deploymentId = process.env.DEPLOYMENT_ID;
    const sdkOptions = { maxAttempts: 2,
      requestHandler: { connectionTimeout: 3000, requestTimeout: 5000, throwOnRequestTimeout: true } };
    const ddb = doc.DynamoDBDocumentClient.from(new DynamoDBClient(sdkOptions), { marshallOptions: { removeUndefinedValues: true } });
    const store = createDynamoStore({ tableName: process.env.STATE_TABLE, deploymentId,
      leaseSeconds: Number(process.env.LEASE_SECONDS ?? 180),
      receiptRetentionDays: Number(process.env.RECEIPT_RETENTION_DAYS ?? 30),
      send: (operation, input) => ddb.send(new doc[`${operation}Command`](input)) });
    const secrets = new SecretsManagerClient(sdkOptions);
    const metrics = new CloudWatchClient(sdkOptions);
    const messages = new sqs.SQSClient(sdkOptions);
    const queue = {
      async send(batch) {
        const response = await messages.send(new sqs.SendMessageBatchCommand({ QueueUrl: process.env.WORK_QUEUE_URL,
          Entries: batch.map((body, index) => ({ Id: String(index), MessageBody: JSON.stringify(body) })) }));
        if (response.Failed?.length) throw new Error('QUEUE_PARTIAL_SEND_FAILED');
      },
      async defer(ReceiptHandle, VisibilityTimeout) {
        await messages.send(new sqs.ChangeMessageVisibilityCommand({ QueueUrl: process.env.WORK_QUEUE_URL, ReceiptHandle, VisibilityTimeout }));
      },
    };
    liveHandler = createHandler({ store, ...core, validateCurrentCohort: selection.validateCurrentCohort,
      apiFactory: createAdminApi, deploymentId, queue,
      queueArn: process.env.WORK_QUEUE_ARN, dispatchBatchSize: Number(process.env.DISPATCH_BATCH_SIZE ?? 100),
      recordConcurrency: Number(process.env.RECORD_CONCURRENCY ?? 1), maxReceiveCount: Number(process.env.MAX_RECEIVE_COUNT ?? 10),
      controlSha256: process.env.CONTROL_SHA256, pilotExpiresAt: process.env.PILOT_EXPIRES_AT,
      applyEnabled: process.env.APPLY_ENABLED === 'true',
      allowedWriteAction: process.env.ALLOWED_WRITE_ACTION ?? 'none',
      runEventsNotBefore: process.env.RUN_EVENTS_NOT_BEFORE ?? '1970-01-01T00:00:00Z',
      secretProvider: createSecretProvider({ secretArn: process.env.ADMIN_SECRET_ARN,
        sendGetSecret: SecretId => secrets.send(new GetSecretValueCommand({ SecretId })) }),
      putMetric: (name, value) => metrics.send(new PutMetricDataCommand({ Namespace: 'CookbookUsageLimits',
        MetricData: [{ MetricName: name, Dimensions: [{ Name: 'Deployment', Value: deploymentId }], Value: value, Unit: 'Count' }] })),
    });
  }
  return liveHandler(event, context);
}
