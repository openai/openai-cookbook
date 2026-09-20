import { createDynamoStore, hash } from './store.mjs';

const ACTIONS = new Set(['probe', 'preview', 'apply', 'restore', 'resume_auth', 'cancel_initial']);
const MAX_EVENT_AGE_MS = 2 * 60 * 60 * 1000;
const FAILURE_CODES = new Set(['PILOT_EXPIRED', 'INVALID_EVENT', 'CONTROL_HASH_MISMATCH',
  'PERIOD_REVIEW_REQUIRED', 'WRITES_DISABLED', 'TIME_BUDGET_EXHAUSTED', 'CONTROLLER_NEEDS_ATTENTION',
  'COHORT_TOO_LARGE_FOR_LAMBDA', 'INVALID_SECRET_FORMAT']);

/** Dependencies are injected so this exact handler can run without AWS or credentials. */
export function createHandler({ store, execute, apiFactory, secretProvider, putMetric,
  deploymentId, controlSha256, pilotExpiresAt, applyEnabled = false,
  clock = () => new Date(), log = line => console.log(line) }) {
  return async function handle(event, context = {}) {
    const now = clock();
    const scheduled = Date.parse(event?.scheduledAt);
    const runId = hash(`${deploymentId}:${event?.scheduledAt}:${event?.action}`);
    let result;
    try {
      // Check expiry before reading controls or credentials, even for manual or delayed invocation.
      if (!Number.isFinite(Date.parse(pilotExpiresAt)) || now.getTime() >= Date.parse(pilotExpiresAt)) {
        throw new Error('PILOT_EXPIRED');
      }
      if (event?.version !== 1 || !ACTIONS.has(event?.action) || !Number.isFinite(scheduled) ||
          scheduled > now.getTime() + 60_000 || now.getTime() - scheduled > MAX_EVENT_AGE_MS ||
          Object.keys(event).some(key => !['version', 'action', 'scheduledAt'].includes(key))) {
        throw new Error('INVALID_EVENT');
      }
      if (event.action === 'probe') {
        result = { ok: true, mode: 'probe', results: [], apiAccessed: false, capWrites: 0 };
      } else {
        const document = await store.getControl();
        if (typeof document !== 'string' || Buffer.byteLength(document) > 300_000 ||
            !/^[a-f0-9]{64}$/.test(controlSha256 ?? '') || hash(document) !== controlSha256) {
          throw new Error('CONTROL_HASH_MISMATCH');
        }
        const { config, enrollment } = JSON.parse(document);
        if (!config || !enrollment || Date.parse(config.period?.start) > now.getTime() ||
            !Number.isFinite(Date.parse(config.period?.end)) || Date.parse(config.period.end) <= now.getTime()) {
          throw new Error('PERIOD_REVIEW_REQUIRED');
        }
        if (!Array.isArray(enrollment.members) || enrollment.members.length > 25) {
          throw new Error('COHORT_TOO_LARGE_FOR_LAMBDA');
        }
        const apply = event.action === 'apply' || event.action === 'restore';
        if (apply && !(applyEnabled === true && config.liveWrites === true)) {
          throw new Error('WRITES_DISABLED');
        }
        const remainingTimeMs = () => Math.min(context.getRemainingTimeInMillis?.() ?? Infinity,
          Date.parse(pilotExpiresAt) - clock().getTime(), Date.parse(config.period.end) - clock().getTime());
        if (remainingTimeMs() <= 45_000) {
          throw new Error('TIME_BUDGET_EXHAUSTED');
        }
        const api = apiFactory({ apiKey: await secretProvider(), workspaceId: config.workspaceId,
          userIds: enrollment.members.map(member => member.userId),
          allowWrites: apply, timeoutMs: 10_000, clock: () => clock().toISOString(),
          remainingTimeMs });
        result = await execute({ config, enrollment, api, store, clock: () => clock().toISOString(), apply,
          restore: event.action === 'restore',
          resumeAuth: event.action === 'resume_auth', cancelInitial: event.action === 'cancel_initial',
          shouldContinue: () => remainingTimeMs() > 45_000 });
      }
      await store.putReceipt({ kind: 'aws_invocation', runId, checkedAt: now.toISOString(),
        action: event.action, ok: result.ok, memberReceipts: result.results?.length ?? 0,
        lambdaRequestId: context.awsRequestId ?? 'offline' });
      await putMetric('ControllerIssue', result.ok ? 0 : 1);
      if (!result.ok) throw new Error('CONTROLLER_NEEDS_ATTENTION');
      await putMetric('SuccessfulInvocation', 1);
      log(JSON.stringify({ event: 'usage_controller_complete', runId, action: event.action,
        members: result.results?.length ?? 0 }));
      // Logs and the async response omit IDs, settings, history, and credentials.
      return { ok: true, runId, action: event.action, members: result.results?.length ?? 0 };
    } catch (error) {
      try {
        await store.putReceipt({ kind: 'aws_invocation', runId, checkedAt: now.toISOString(),
          status: 'runtime_failure', code: FAILURE_CODES.has(error?.message) ? error.message : 'RUNTIME_OR_DEPENDENCY_FAILURE',
          nextAction: 'Inspect private member receipts, reviewed controls, expiry, and AWS permissions.' });
      } catch { /* Lambda Errors and its failure destination cover a state-store outage. */ }
      try { await putMetric('ControllerIssue', 1); } catch { /* Lambda Errors is independent. */ }
      log(JSON.stringify({ event: 'usage_controller_failed', runId }));
      // Never expose an SDK/API error body, the event, or the secret in the thrown message.
      throw new Error('USAGE_CONTROLLER_FAILED: inspect private receipts and deployment health');
    }
  };
}

export function createSecretProvider({ secretArn, sendGetSecret }) {
  if (!/^arn:[^:]+:secretsmanager:[^:]+:\d{12}:secret:.+$/.test(secretArn ?? '')) {
    throw new Error('INVALID_SECRET_ARN');
  }
  return async () => {
    const response = await sendGetSecret(secretArn);
    let value;
    try { value = JSON.parse(response.SecretString); } catch { throw new Error('INVALID_SECRET_FORMAT'); }
    if (typeof value.apiKey !== 'string' || value.apiKey.length < 10) throw new Error('INVALID_SECRET_FORMAT');
    return value.apiKey;
  };
}

// Keep SDK imports lazy: unit tests need neither npm dependencies nor an AWS identity.
let liveHandler;
export async function handler(event, context) {
  if (!liveHandler) {
    const [{ DynamoDBClient }, doc, { SecretsManagerClient, GetSecretValueCommand },
      { CloudWatchClient, PutMetricDataCommand }, { execute }, { createAdminApi }] = await Promise.all([
      import('@aws-sdk/client-dynamodb'), import('@aws-sdk/lib-dynamodb'),
      import('@aws-sdk/client-secrets-manager'), import('@aws-sdk/client-cloudwatch'),
      import('../src/controller.mjs'), import('../src/admin-api.mjs'),
    ]);
    const deploymentId = process.env.DEPLOYMENT_ID;
    const sdkOptions = { maxAttempts: 2,
      requestHandler: { connectionTimeout: 3000, requestTimeout: 5000, throwOnRequestTimeout: true } };
    const ddb = doc.DynamoDBDocumentClient.from(new DynamoDBClient(sdkOptions),
      { marshallOptions: { removeUndefinedValues: true } });
    const store = createDynamoStore({ tableName: process.env.STATE_TABLE, deploymentId,
      receiptRetentionDays: Number(process.env.RECEIPT_RETENTION_DAYS ?? 30),
      send: (operation, input) => ddb.send(new doc[`${operation}Command`](input)) });
    const secrets = new SecretsManagerClient(sdkOptions);
    const metrics = new CloudWatchClient(sdkOptions);
    liveHandler = createHandler({ store, execute, apiFactory: createAdminApi, deploymentId,
      controlSha256: process.env.CONTROL_SHA256, pilotExpiresAt: process.env.PILOT_EXPIRES_AT,
      applyEnabled: process.env.APPLY_ENABLED === 'true',
      secretProvider: createSecretProvider({ secretArn: process.env.ADMIN_SECRET_ARN,
        sendGetSecret: SecretId => secrets.send(new GetSecretValueCommand({ SecretId })) }),
      putMetric: (name, value) => metrics.send(new PutMetricDataCommand({ Namespace: 'CookbookUsageLimits',
        MetricData: [{ MetricName: name, Dimensions: [{ Name: 'Deployment', Value: deploymentId }],
          Value: value, Unit: 'Count' }] })),
    });
  }
  return liveHandler(event, context);
}
