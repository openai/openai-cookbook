import test from 'node:test';
import assert from 'node:assert/strict';
import { mkdtemp, mkdir, copyFile, symlink, writeFile, rm } from 'node:fs/promises';
import { spawnSync } from 'node:child_process';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { fileURLToPath, pathToFileURL } from 'node:url';

const project = fileURLToPath(new URL('..', import.meta.url));
const settingNames = ['OPENAI_API_KEY', 'LITTLE_WORLDS_MODEL', 'LITTLE_WORLDS_TIER', 'LITTLE_WORLDS_TRANSPORT', 'SPACE_ICON_MODEL'];

async function fixture(t, content) {
  const root = await mkdtemp(join(tmpdir(), 'little-worlds-env-test-'));
  t.after(() => rm(root, { recursive: true, force: true }));
  const app = join(root, 'app');
  const cwd = join(root, 'elsewhere');
  await mkdir(join(app, 'server'), { recursive: true });
  await mkdir(cwd);
  await symlink(join(project, 'node_modules'), join(app, 'node_modules'), 'junction');
  for (const file of ['responses.mjs', 'responses-websocket.mjs', 'environment.mjs']) {
    await copyFile(join(project, 'server', file), join(app, 'server', file));
  }
  if (content !== undefined) await writeFile(join(app, '.env'), content);
  await writeFile(join(cwd, '.env'), 'OPENAI_API_KEY=wrong-working-directory\n');
  await writeFile(join(app, 'server', 'consumer.mjs'), `
    export * from './responses.mjs';
    export const importedModel = process.env.LITTLE_WORLDS_MODEL;
  `);
  return { app, cwd };
}

function run({ app, cwd }, body, overrides = {}) {
  const env = { ...process.env };
  for (const name of settingNames) { delete env[name]; delete env[name.replace('LITTLE_WORLDS_', 'LIVING_SPACES_')]; }
  Object.assign(env, overrides);
  const program = `
    import assert from 'node:assert/strict';
    import { writeFileSync } from 'node:fs';
    import { loadApiKey, createResponsesAdapter, importedModel } from ${JSON.stringify(pathToFileURL(join(app, 'server', 'consumer.mjs')).href)};
    ${body}
  `;
  const result = spawnSync(process.execPath, ['--input-type=module', '-e', program], { cwd, env, encoding: 'utf8' });
  assert.equal(result.status, 0, result.stderr);
  assert.equal(result.stdout, '', 'Environment loading must not log configuration or credentials.');
  assert.equal(result.stderr, '');
}

test('loads example-local server settings before importer defaults, independent of cwd', async t => {
  const files = await fixture(t, `
OPENAI_API_KEY=" fixture-api-key "
LITTLE_WORLDS_MODEL=fixture-model
LITTLE_WORLDS_TIER=fixture-tier
LITTLE_WORLDS_TRANSPORT=http
SPACE_ICON_MODEL=fixture-image-model
  `);
  run(files, `
    assert.equal(await loadApiKey(), 'fixture-api-key');
    assert.equal(importedModel, 'fixture-model');
    const adapter = createResponsesAdapter();
    assert.equal(adapter.model, 'fixture-model');
    assert.equal(adapter.tier, 'fixture-tier');
    assert.equal(adapter.transport, 'http');
    assert.equal(process.env.SPACE_ICON_MODEL, 'fixture-image-model');
    adapter.close();
  `);
});

test('explicit process settings, including empty credentials, override .env', async t => {
  const files = await fixture(t, 'OPENAI_API_KEY=fixture-file-key\nLITTLE_WORLDS_MODEL=file-model\nLITTLE_WORLDS_TIER=file-tier\nLITTLE_WORLDS_TRANSPORT=http\n');
  const body = `
    assert.equal(await loadApiKey(), 'process-key');
    assert.equal(importedModel, 'process-model');
    const adapter = createResponsesAdapter();
    assert.equal(adapter.model, 'process-model');
    assert.equal(adapter.tier, 'process-tier');
    assert.equal(adapter.transport, 'websocket');
    adapter.close();
  `;
  run(files, body, { OPENAI_API_KEY: ' process-key ', LITTLE_WORLDS_MODEL: 'process-model', LITTLE_WORLDS_TIER: 'process-tier', LITTLE_WORLDS_TRANSPORT: 'websocket' });
  run(files, "assert.equal(await loadApiKey(), '');", { OPENAI_API_KEY: '' });
});

test('missing repository .env is allowed and never reads the working-directory .env', async t => {
  const files = await fixture(t);
  run(files, "assert.equal(await loadApiKey(), ''); assert.equal(importedModel, undefined);");
});

test('legacy .env settings still configure the actual adapter', async t => {
  const files = await fixture(t, 'LIVING_SPACES_MODEL=legacy-model\nLIVING_SPACES_TIER=legacy-tier\nLIVING_SPACES_TRANSPORT=http\n');
  run(files, `
    const adapter = createResponsesAdapter();
    assert.equal(adapter.model, 'legacy-model');
    assert.equal(adapter.tier, 'legacy-tier');
    assert.equal(adapter.transport, 'http');
    adapter.close();
  `);
});

test('process aliases override file settings while current names win within a source', async t => {
  const files = await fixture(t, 'LITTLE_WORLDS_MODEL=current-file\nLIVING_SPACES_MODEL=legacy-file\nLITTLE_WORLDS_TRANSPORT=http\n');
  const check = expected => `const adapter = createResponsesAdapter(); assert.equal(adapter.model, '${expected}'); adapter.close();`;
  run(files, check('current-file'));
  run(files, check('legacy-process'), { LIVING_SPACES_MODEL: 'legacy-process' });
  run(files, check('current-process'), { LIVING_SPACES_MODEL: 'legacy-process', LITTLE_WORLDS_MODEL: 'current-process' });
  run(files, check('gpt-6-astra'), { LITTLE_WORLDS_MODEL: '', LIVING_SPACES_MODEL: 'legacy-process' });
  run(files, check('gpt-6-astra'), { LIVING_SPACES_MODEL: '' });
});

test('server configuration is loaded once rather than re-reading credentials for each request', async t => {
  const files = await fixture(t, 'OPENAI_API_KEY=fixture-first-key\n');
  run(files, `
    assert.equal(await loadApiKey(), 'fixture-first-key');
    writeFileSync(${JSON.stringify(join(files.app, '.env'))}, 'OPENAI_API_KEY=fixture-next-key\\n');
    assert.equal(await loadApiKey(), 'fixture-first-key');
  `);
});

test('latency benchmark requires an explicit input before loading credentials or making requests', () => {
  const result = spawnSync(process.execPath, [join(project, 'scripts', 'benchmark-latency.mjs')], { encoding: 'utf8' });
  assert.notEqual(result.status, 0);
  assert.match(result.stderr, /Supply --seed PATH or --space-file PATH/);
  assert.equal(result.stdout, '');
});
