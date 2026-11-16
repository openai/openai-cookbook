import test from 'node:test';
import assert from 'node:assert/strict';
import { execFile } from 'node:child_process';
import { promisify } from 'node:util';
import { fileURLToPath } from 'node:url';

const exec=promisify(execFile);
const demo=new URL('../src/demo.mjs',import.meta.url);
const source=fileURLToPath(new URL('../src/',import.meta.url));

for(const unit of ['credit','usd'])test(`${unit} fictional demo completes recovery and restore with filesystem writes denied and fetch blocked`,async()=>{
  const script=`
    globalThis.fetch=()=>{throw new Error('DEMO_NETWORK_FORBIDDEN');};
    process.argv=['node','demo.mjs','--unit',${JSON.stringify(unit)}];
    await import(${JSON.stringify(demo.href)});
  `;
  const {stdout}=await exec(process.execPath,
    ['--permission',`--allow-fs-read=${source}`,'--input-type=module','--eval',script],
    {env:{...process.env,CHATGPT_ADMIN_API_KEY:''}});
  assert.match(stdout,unit==='credit'?/Demo: 2,000 credits per person per month; release 500 weekly\./:
    /Demo: \$200\.00 USD per person per month; release \$50\.00 weekly\./);
  assert.match(stdout,/synthetic-user-b=attention/);
  assert.match(stdout,/synthetic-user-b=reconciled/);
  assert.match(stdout,unit==='credit'?/Next weekly release: synthetic-user-a=1000, synthetic-user-b=1000, synthetic-user-c=1000/:
    /Next weekly release: synthetic-user-a=\$100\.00, synthetic-user-b=\$100\.00, synthetic-user-c=\$100\.00/);
  assert.match(stdout,/MANUAL_ADMIN_CHANGE_CONFLICT/);
  assert.match(stdout,unit==='credit'?/Restored the original inherited 2,000-credit cap for every fictional user\./:
    /Restored the original inherited \$200\.00 USD cap for every fictional user\./);
  if(unit==='usd')assert.doesNotMatch(stdout,/credit/);
  assert.match(stdout,/All simulated state stayed in memory\./);
});

test('demo defaults to credits and rejects invalid, missing, duplicate or unrelated options',async()=>{
  const {stdout}=await exec(process.execPath,[fileURLToPath(demo)]);
  assert.match(stdout,/Demo: 2,000 credits/);
  for(const args of [['--unit','dollars'],['--unit'],['--unit','credit','--unit','usd'],['--apply']]) {
    await assert.rejects(exec(process.execPath,[fileURLToPath(demo),...args]),error=>{
      assert.equal(error.code,1);
      assert.equal(error.stdout,'');
      return true;
    });
  }
});
