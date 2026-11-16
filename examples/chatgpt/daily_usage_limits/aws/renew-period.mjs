import { readFile, mkdir, writeFile, access } from 'node:fs/promises';
import { join, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import { randomUUID } from 'node:crypto';
import { execFile } from 'node:child_process';
import { promisify } from 'node:util';
import { parseArgs } from 'node:util';
import { createDynamoStore, hash } from './store.mjs';
import { createControlLoader, encodeControl } from './control.mjs';
import { uploadControl } from './upload-control.mjs';
import { createAdminApi } from '../src/admin-api.mjs';
import { enrollmentHash, validateEnrollment } from '../src/enrollment.mjs';
import { approvalWindowMs, configDigest, requireThat, validatePolicy } from '../src/policy.mjs';
import { atomicJson } from '../src/file-store.mjs';
import { validateRenewalState } from '../src/renewal.mjs';

const json = async path => JSON.parse(await readFile(path, 'utf8'));
const stable = new Set(['CREATE_COMPLETE', 'UPDATE_COMPLETE', 'UPDATE_ROLLBACK_COMPLETE']);
const outputsRequired = ['FunctionName', 'StateTableName', 'ScheduleGroupName', 'ScheduleName', 'WorkMappingId', 'WorkQueueUrl'];
const gates = { ScheduleState: 'DISABLED', WorkProcessingEnabled: 'false', ApplyEnabled: 'false', AllowedWriteAction: 'none' };
const defaultCapture = async options => (await import('../src/renewal.mjs')).captureRenewal(options);
const sleepDefault = ms => new Promise(resolve => setTimeout(resolve, ms));
const privateWrite = (path, value) => writeFile(path, JSON.stringify(value, null, 2) + '\n', { mode: 0o600, flag: 'wx' });

async function describe(aws, stackName) {
  const response = await aws('cloudformation', 'describe-stacks', { StackName: stackName });
  requireThat(response.Stacks?.length === 1, 'RENEWAL_STACK_NOT_FOUND');
  const stack = response.Stacks[0];
  return { stack, parameters: Object.fromEntries((stack.Parameters ?? []).map(row => [row.ParameterKey, row.ParameterValue])),
    resources: Object.fromEntries((stack.Outputs ?? []).map(row => [row.OutputKey, row.OutputValue])) };
}

async function inspect(aws, stackName, stopped) {
  const current = await describe(aws, stackName);
  requireThat(stable.has(current.stack.StackStatus), 'RENEWAL_STACK_NOT_STABLE');
  requireThat(outputsRequired.every(key => typeof current.resources[key] === 'string') &&
    /^[a-z][a-z0-9-]{2,39}$/.test(current.parameters.DeploymentId ?? '') &&
    /^[a-f0-9]{64}$/.test(current.parameters.ControlSha256 ?? ''), 'RENEWAL_STACK_LAYOUT_UNSUPPORTED');
  const [fn, mapping, schedule] = await Promise.all([
    aws('lambda', 'get-function-configuration', { FunctionName: current.resources.FunctionName }),
    aws('lambda', 'get-event-source-mapping', { UUID: current.resources.WorkMappingId }),
    aws('scheduler', 'get-schedule', { Name: current.resources.ScheduleName, GroupName: current.resources.ScheduleGroupName }),
  ]);
  requireThat(fn.State === 'Active' && fn.LastUpdateStatus === 'Successful' && Number.isSafeInteger(fn.Timeout) &&
    fn.Timeout >= 1 && fn.Timeout <= 900 && typeof fn.CodeSha256 === 'string', 'RENEWAL_FUNCTION_NOT_READY');
  requireThat(fn.Environment?.Variables?.STATE_TABLE === current.resources.StateTableName &&
    fn.Environment.Variables.DEPLOYMENT_ID === current.parameters.DeploymentId &&
    fn.Environment.Variables.CONTROL_SHA256 === current.parameters.ControlSha256 &&
    mapping.FunctionArn === fn.FunctionArn && schedule.Target?.Arn === fn.FunctionArn, 'RENEWAL_RESOURCE_MISMATCH');
  if (stopped) requireThat(Object.entries(gates).every(([key, value]) => current.parameters[key] === value) &&
    fn.Environment.Variables.APPLY_ENABLED === 'false' && fn.Environment.Variables.ALLOWED_WRITE_ACTION === 'none' &&
    mapping.State === 'Disabled' && schedule.State === 'DISABLED', 'RENEWAL_REQUIRES_STOPPED_STACK');
  return { ...current, fn };
}

function sameResources(current, journal) {
  requireThat(current.stack.StackId === journal.stackId && current.parameters.DeploymentId === journal.deploymentId &&
    outputsRequired.every(key => current.resources[key] === journal.resources[key]) &&
    current.fn.CodeSha256 === journal.codeSha256, 'RENEWAL_RESOURCE_CHANGED');
}

const stoppedFingerprint = current => hash(JSON.stringify({ code: current.fn.CodeSha256,
  modified: current.fn.LastModified, timeout: current.fn.Timeout, parameters: current.parameters, resources: current.resources }));
function reviewFresh(config, enrollment, now) {
  requireThat(now.getTime() - Date.parse(enrollment.capturedAt) <= approvalWindowMs(config), 'RENEWAL_REVIEW_EXPIRED_RECAPTURE');
  const slot = validatePolicy(config, now.toISOString()).slot;
  requireThat(enrollment.members.every(member => member.plan.slot === slot), 'RENEWAL_SLOT_CHANGED_RECAPTURE');
}

const renewalParameters = (config, nextHash, cutoff) => ({ ...gates, ScheduledAction: 'preview',
  ControlSha256: nextHash, PilotExpiresAt: config.period.end.replace('.000Z', 'Z'), RunEventsNotBefore: cutoff });

function acceptsPrevious(installed, previousConfig, previousEnrollment, period) {
  if (configDigest(installed.config) === configDigest(previousConfig) &&
      enrollmentHash(installed.enrollment) === enrollmentHash(previousEnrollment)) return true;
  const proof = installed.enrollment.renewal;
  if (proof?.previousConfigDigest !== configDigest(previousConfig) ||
      proof.previousEnrollmentHash !== enrollmentHash(previousEnrollment)) return false;
  const expected = structuredClone(previousConfig);
  expected.period = structuredClone(period); expected.policy.anchor = period.start;
  // A wholly unstarted renewal can refresh evidence and capture time while
  // retaining the exact installed period, policy, unit, workspace and selectors.
  const comparable = config => {
    const result = structuredClone(config);
    delete result.period.verifiedAt; delete result.period.evidence;
    return configDigest(result);
  };
  return comparable(installed.config) === comparable(expected);
}

/** Read-only preparation. It never changes member settings or AWS state. */
export async function prepareRenewal({ stackName, previousConfig, previousEnrollment, period, directory,
  aws, store, api, capture = defaultCapture, clock = () => new Date(), sleep = sleepDefault }) {
  try { await access(directory); throw new Error('RENEWAL_DIRECTORY_EXISTS'); }
  catch (error) { if (error.code !== 'ENOENT') throw error; }
  const current = await inspect(aws, stackName, true);
  const installed = await createControlLoader({ store, controlSha256: current.parameters.ControlSha256 })();
  requireThat(acceptsPrevious(installed, previousConfig, previousEnrollment, period), 'RENEWAL_PREVIOUS_CONTROL_MISMATCH');
  const fingerprint = stoppedFingerprint(current);
  const drainUntil = new Date(clock().getTime() + current.fn.Timeout * 1000).toISOString();
  while (clock().getTime() < Date.parse(drainUntil)) await sleep(Math.min(10_000, Date.parse(drainUntil) - clock().getTime()));
  requireThat(stoppedFingerprint(await inspect(aws, stackName, true)) === fingerprint, 'RENEWAL_STACK_CHANGED_DURING_DRAIN');
  const captured = await capture({ previousConfig, previousEnrollment, period, api, store,
    clock: () => clock().toISOString() });
  requireThat(captured.config.liveWrites === false && captured.hash === enrollmentHash(captured.enrollment), 'RENEWAL_CAPTURE_INVALID');
  reviewFresh(captured.config, captured.enrollment, clock());
  await mkdir(directory, { mode: 0o700 });
  await privateWrite(join(directory, 'config.json'), captured.config);
  await privateWrite(join(directory, 'enrollment.json'), captured.enrollment);
  await privateWrite(join(directory, 'activation.json'), { version: 1, stage: 'prepared', stackId: current.stack.StackId,
    deploymentId: current.parameters.DeploymentId, resources: current.resources, codeSha256: current.fn.CodeSha256,
    previousControlSha256: current.parameters.ControlSha256, configDigest: configDigest(captured.config),
    enrollmentHash: captured.hash, requestToken: randomUUID(), preparedAt: clock().toISOString(),
    stoppedFingerprint: fingerprint, drainUntil });
  return { prepared: true, directory: resolve(directory), hash: captured.hash, members: captured.enrollment.members.length,
    capWrites: 0, action: 'Review config.json and every enrollment member, then approve the printed hash before activate.' };
}

async function writeControls(directory, config, enrollment, deploymentId) {
  const prepared = encodeControl(config, enrollment);
  try { await mkdir(directory, { mode: 0o700 }); } catch (error) { if (error.code !== 'EEXIST') throw error; }
  const item = (key, document) => ({ PK: { S: `CONTROL#${deploymentId}` }, SK: { S: key }, document: { S: document } });
  for (const [name, value] of [...prepared.parts.map(part => [`part-${String(part.index).padStart(8, '0')}.json`, item(`PART#${part.hash}`, part.document)]),
    ['manifest.json', item('REVIEWED', prepared.document)]]) {
    const path = join(directory, name);
    try { await privateWrite(path, value); }
    catch (error) {
      if (error.code !== 'EEXIST') throw error;
      requireThat(JSON.stringify(await json(path)) === JSON.stringify(value), 'RENEWAL_PREPARED_CONTROL_CHANGED');
    }
  }
  return prepared.hash;
}

async function waitStable(aws, stackName, clock, sleep) {
  const deadline = clock().getTime() + 20 * 60_000;
  for (;;) {
    const current = await describe(aws, stackName);
    if (stable.has(current.stack.StackStatus)) return;
    requireThat(current.stack.StackStatus === 'UPDATE_IN_PROGRESS' || current.stack.StackStatus === 'UPDATE_COMPLETE_CLEANUP_IN_PROGRESS',
      'RENEWAL_STACK_UPDATE_FAILED');
    requireThat(clock().getTime() < deadline, 'RENEWAL_STACK_UPDATE_PENDING');
    await sleep(10_000);
  }
}

/** Update only the existing stack's period/control parameters. Every gate stays off. */
export async function activateRenewal({ stackName, directory, aws, store, sendDynamo, upload = uploadControl,
  clock = () => new Date(), sleep = sleepDefault, saveJournal = atomicJson }) {
  const [config, enrollment, journal] = await Promise.all(['config.json', 'enrollment.json', 'activation.json'].map(name => json(join(directory, name))));
  requireThat(journal.version === 1 && typeof journal.requestToken === 'string' && config.liveWrites === false &&
    journal.configDigest === configDigest(config) && journal.enrollmentHash === enrollmentHash(enrollment) &&
    enrollment.renewal?.version === 1 && enrollment.members.every(member => member.renewal?.priorStateDigest), 'RENEWAL_FILES_CHANGED');
  validateEnrollment(config, enrollment, clock().toISOString(), true);
  const save = () => saveJournal(join(directory, 'activation.json'), journal);
  const finish = async () => {
    let reviewRequired = false;
    try { reviewFresh(config, enrollment, clock()); } catch { reviewRequired = true; }
    journal.stage = 'activated'; journal.activatedAt = clock().toISOString(); await save();
    return { activated: true, stackId: journal.stackId, controlSha256: journal.nextControlSha256, period: config.period,
      schedule: 'DISABLED', workers: 'Disabled', writes: false, capWrites: 0, reviewRequired,
      action: reviewRequired ? 'The update is confirmed with every gate off. Recapture an unstarted renewal before applying; keep existing files if any member has transitioned.' :
        'Use the existing preview and first-apply walkthrough with these renewed files and the same state table.' };
  };
  await waitStable(aws, stackName, clock, sleep);
  let current = await inspect(aws, stackName, true);
  sameResources(current, journal);
  const nextHash = await writeControls(join(directory, 'controls'), config, enrollment, journal.deploymentId);
  requireThat([journal.previousControlSha256, nextHash].includes(current.parameters.ControlSha256), 'RENEWAL_CURRENT_CONTROL_CHANGED');
  if (journal.cutoff && Object.entries(renewalParameters(config, nextHash, journal.cutoff)).every(([key, value]) => current.parameters[key] === value)) {
    // Reconcile an accepted update even if review expired while AWS completed it.
    // This branch reads only: it does not reupload controls or enable any gate.
    await createControlLoader({ store, controlSha256: nextHash })();
    journal.nextControlSha256 = nextHash;
    return finish();
  }
  const alreadyUploaded = hash(await store.getControl() ?? '') === nextHash;
  if (alreadyUploaded) await createControlLoader({ store, controlSha256: nextHash })();
  else reviewFresh(config, enrollment, clock());
  const fingerprint = stoppedFingerprint(current);
  if (journal.stoppedFingerprint !== fingerprint) {
    journal.stoppedFingerprint = fingerprint;
    journal.drainUntil = new Date(clock().getTime() + current.fn.Timeout * 1000).toISOString();
    journal.stage = 'draining'; await save();
  }
  while (clock().getTime() < Date.parse(journal.drainUntil)) await sleep(Math.min(10_000, Date.parse(journal.drainUntil) - clock().getTime()));
  current = await inspect(aws, stackName, true); sameResources(current, journal);
  requireThat(fingerprint === stoppedFingerprint(current), 'RENEWAL_STACK_CHANGED_DURING_DRAIN');
  validateEnrollment(config, enrollment, clock().toISOString(), true);
  // Capture is read-only and may precede stopping the stack. Recheck every saved
  // state after draining so a newly pending or changed intent blocks activation.
  let nextMember = 0;
  await Promise.all(Array.from({ length: Math.min(config.captureConcurrency ?? config.concurrency, enrollment.members.length) }, async () => {
    for (;;) {
      const member = enrollment.members[nextMember++]; if (!member) return;
      const state = await store.getState(`${config.workspaceId}:${member.userId}`);
      validateRenewalState(member, state);
    }
  }));
  if (!alreadyUploaded) reviewFresh(config, enrollment, clock());
  journal.cutoff ??= new Date(Math.ceil(clock().getTime() / 1000) * 1000).toISOString().replace('.000Z', 'Z');
  journal.nextControlSha256 = nextHash; journal.stage = alreadyUploaded ? 'confirming_controls' : 'uploading'; await save();
  if (alreadyUploaded) {
    // An upload may commit while its response is lost. Completing the stopped
    // stack update does not renew review or permit any cap change. Do not upload
    // again after expiry; independently revalidate the exact immutable controls.
    await createControlLoader({ store, controlSha256: nextHash })();
  } else {
    await upload({ directory: join(directory, 'controls'), tableName: journal.resources.StateTableName,
      controlSha256: nextHash, previousSha256: journal.previousControlSha256, send: sendDynamo, now: clock().toISOString() });
  }
  const replacements = renewalParameters(config, nextHash, journal.cutoff);
  requireThat(Object.keys(replacements).every(key => Object.hasOwn(current.parameters, key)), 'RENEWAL_PARAMETER_MISSING');
  if (!Object.entries(replacements).every(([key, value]) => current.parameters[key] === value)) {
    journal.stage = 'updating'; await save();
    try {
      await aws('cloudformation', 'update-stack', { StackName: journal.stackId, UsePreviousTemplate: true,
        ClientRequestToken: journal.requestToken, Capabilities: ['CAPABILITY_IAM'],
        Parameters: Object.keys(current.parameters).map(ParameterKey => Object.hasOwn(replacements, ParameterKey)
          ? { ParameterKey, ParameterValue: replacements[ParameterKey] } : { ParameterKey, UsePreviousValue: true }) });
    } catch { throw new Error('RENEWAL_UPDATE_UNCONFIRMED_RERUN_ACTIVATE'); }
    await waitStable(aws, stackName, clock, sleep);
  }
  const after = await inspect(aws, stackName, true); sameResources(after, journal);
  requireThat(Object.entries(replacements).every(([key, value]) => after.parameters[key] === value), 'RENEWAL_UPDATE_NOT_CONFIRMED');
  return finish();
}

async function awsCli(service, command, input) {
  try {
    const { stdout } = await promisify(execFile)('aws', [service, command, '--cli-input-json', JSON.stringify(input),
      '--output', 'json', '--no-cli-pager', '--cli-connect-timeout', '3', '--cli-read-timeout', '10'],
    { timeout: 30_000, maxBuffer: 4 * 1024 * 1024 });
    return stdout.trim() ? JSON.parse(stdout) : {};
  } catch { throw new Error('AWS_COMMAND_FAILED'); }
}

export async function main(args = process.argv.slice(2)) {
  const { positionals, values } = parseArgs({ args, allowPositionals: true, options: Object.fromEntries(
    ['stack', 'config', 'enrollment', 'period', 'out', 'dir'].map(key => [key, { type: 'string' }])) });
  requireThat(process.platform !== 'win32', 'MACOS_OR_LINUX_REQUIRED_FOR_PRIVATE_STATE');
  const action = positionals[0];
  requireThat(positionals.length === 1 && ['prepare', 'activate'].includes(action) && values.stack, 'RENEWAL_USAGE_REQUIRED');
  requireThat(action === 'prepare' ? values.config && values.enrollment && values.period && values.out && !values.dir :
    values.dir && !values.config && !values.enrollment && !values.period && !values.out, 'RENEWAL_ARGUMENTS_INVALID');
  const sdk = await import('@aws-sdk/client-dynamodb');
  const client = new sdk.DynamoDBClient({ maxAttempts: 2,
    requestHandler: { connectionTimeout: 3000, requestTimeout: 5000, throwOnRequestTimeout: true } });
  const sendDynamo = (operation, input) => client.send(new sdk[`${operation}Command`](input));
  const current = await describe(awsCli, values.stack);
  const doc = await import('@aws-sdk/lib-dynamodb');
  const ddb = doc.DynamoDBDocumentClient.from(client, { marshallOptions: { removeUndefinedValues: true } });
  const store = createDynamoStore({ tableName: current.resources.StateTableName, deploymentId: current.parameters.DeploymentId,
    send: (operation, input) => ddb.send(new doc[`${operation}Command`](input)) });
  if (action === 'activate') return activateRenewal({ stackName: values.stack, directory: values.dir, aws: awsCli, store, sendDynamo });
  requireThat(process.env.CHATGPT_ADMIN_API_KEY, 'CHATGPT_ADMIN_API_KEY_REQUIRED');
  const [previousConfig, previousEnrollment, period] = await Promise.all([values.config, values.enrollment, values.period].map(json));
  const api = createAdminApi({ apiKey: process.env.CHATGPT_ADMIN_API_KEY, workspaceId: previousConfig.workspaceId,
    userIds: previousEnrollment.members.map(member => member.userId), allowWrites: false,
    maxPages: previousConfig.apiLimits?.maxPages, maxRows: previousConfig.apiLimits?.maxRows });
  return prepareRenewal({ stackName: values.stack, previousConfig, previousEnrollment, period, directory: values.out, aws: awsCli, store, api });
}

if (process.argv[1] && resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  main().then(result => console.log(JSON.stringify(result, null, 2))).catch(error => {
    console.error(JSON.stringify({ ok: false, code: /^[A-Z][A-Z0-9_]{0,99}$/.test(error.code ?? error.message ?? '') ? error.code ?? error.message : 'RENEWAL_FAILED',
      action: 'Review the saved renewal directory and stack status. Rerun activate with the same directory after resolving the reported condition.' }));
    process.exitCode = 2;
  });
}
