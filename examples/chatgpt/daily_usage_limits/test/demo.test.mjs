import test from 'node:test';
import assert from 'node:assert/strict';
import { execFile } from 'node:child_process';
import { promisify } from 'node:util';
import { fileURLToPath } from 'node:url';

const exec=promisify(execFile);
const demo=new URL('../src/demo.mjs',import.meta.url);
const source=fileURLToPath(new URL('../src/',import.meta.url));

test('fictional demo completes recovery and restore with filesystem writes denied and fetch blocked',async()=>{
  const script=`
    globalThis.fetch=()=>{throw new Error('DEMO_NETWORK_FORBIDDEN');};
    await import(${JSON.stringify(demo.href)});
  `;
  const {stdout}=await exec(process.execPath,
    ['--permission',`--allow-fs-read=${source}`,'--input-type=module','--eval',script],
    {env:{...process.env,CHATGPT_ADMIN_API_KEY:''}});
  assert.match(stdout,/Demo: 2,000 credits per person per month; release 500 weekly\./);
  assert.match(stdout,/synthetic-user-b=attention/);
  assert.match(stdout,/synthetic-user-b=reconciled/);
  assert.match(stdout,/Next weekly release: synthetic-user-a=1000, synthetic-user-b=1000, synthetic-user-c=1000/);
  assert.match(stdout,/MANUAL_ADMIN_CHANGE_CONFLICT/);
  assert.match(stdout,/Restored the original inherited 2,000-credit cap for every fictional user\./);
  assert.match(stdout,/All simulated state stayed in memory\./);
});
