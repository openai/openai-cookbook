import test from 'node:test';
import assert from 'node:assert/strict';
import { mkdtempSync, readFileSync, rmSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { fileURLToPath } from 'node:url';
import { spawnSync } from 'node:child_process';

function intrinsic(value, parameters) {
  if (Array.isArray(value)) return value.map(item => intrinsic(item, parameters));
  if (value === null || typeof value !== 'object') return value;
  if (Object.hasOwn(value, 'Ref')) return parameters[value.Ref];
  const [name, arguments_] = Object.entries(value)[0];
  const args = intrinsic(arguments_, parameters);
  if (name === 'Fn::Join') return args[1].join(args[0]);
  if (name === 'Fn::Split') return args[1].split(args[0]);
  if (name === 'Fn::Select') return args[1][args[0]];
  throw new Error(`Unsupported intrinsic: ${name}`);
}

test('deployed Scheduler EndDate contains milliseconds while runtime keeps the exact pilot deadline', () => {
  const template = readFileSync(new URL('../aws/template.yaml', import.meta.url), 'utf8');
  const expression = JSON.parse(template.match(/^      EndDate: (.+)$/m)[1]);
  for (const pilot of ['2030-05-01T00:00:00Z', '2030-12-31T23:59:59Z']) {
    const endDate = intrinsic(expression, { PilotExpiresAt: pilot });
    assert.equal(endDate, pilot.slice(0, -1) + '.000Z');
    assert.equal(endDate, new Date(pilot).toISOString());
    assert.equal(Date.parse(endDate), Date.parse(pilot));
  }
  assert.match(template, /PILOT_EXPIRES_AT: !Ref PilotExpiresAt/);
  assert.match(template, /PilotExpiresAt:\n    Type: String\n    AllowedPattern: '\[0-9\]\{4\}-\[0-9\]\{2\}-\[0-9\]\{2\}T\[0-9\]\{2\}:\[0-9\]\{2\}:\[0-9\]\{2\}Z'/);
});

test('event helper emits only the requested connection identity and rejects missing or extra arguments', () => {
  const directory = mkdtempSync(join(tmpdir(), 'usage-connection-event-'));
  const helper = fileURLToPath(new URL('../aws/event.mjs', import.meta.url));
  const output = join(directory, 'event.json');
  try {
    const run = (...args) => spawnSync(process.execPath, [helper, ...args], { encoding: 'utf8' });
    assert.equal(run('check_connection', output, 'workspace-example').status, 0);
    const event = JSON.parse(readFileSync(output, 'utf8'));
    assert.deepEqual(event, { version: 1, action: 'check_connection', workspaceId: 'workspace-example', scheduledAt: event.scheduledAt });
    assert.equal(new Date(event.scheduledAt).toISOString(), event.scheduledAt);
    for (const args of [['check_connection', output], ['check_connection', output, '../other'],
      ['check_connection', output, 'workspace-example', 'extra'], ['probe', output, 'workspace-example'],
      ['cancel_run', output, 'workspace-example']]) assert.notEqual(run(...args).status, 0);
    assert.equal(run('cancel_run', output, 'a'.repeat(64)).status, 0);
    assert.equal(JSON.parse(readFileSync(output, 'utf8')).runId, 'a'.repeat(64));
  } finally { rmSync(directory, { recursive: true, force: true }); }
});
