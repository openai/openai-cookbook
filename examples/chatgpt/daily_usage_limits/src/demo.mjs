import assert from 'node:assert/strict';
import { mkdtemp, rm } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { exampleConfig, createSyntheticApi } from './synthetic.mjs';
import { FileStore } from './file-store.mjs';
import { captureEnrollment, approveEnrollment } from './enrollment.mjs';
import { execute } from './controller.mjs';

// All dates, identities, usage, responses and failures here are fictional.
let now='2030-01-02T00:00:00.000Z';
const directory=await mkdtemp(join(tmpdir(),'chatgpt-usage-limit-demo-'));
try {
  const config=exampleConfig({now,cohort:'all',intervalHours:168});
  // The fictional operator approves restricting the original monthly cap before capture.
  config.allowInitialReduction=true;
  const api=createSyntheticApi({config,clock:()=>now});
  const {enrollment:captured,hash}=await captureEnrollment({config,api,now});
  const enrollment=approveEnrollment(captured,hash,now);
  const run=(options={})=>execute({config,enrollment,api,store:new FileStore(directory),now,...options});
  const preview=await run();
  console.log('Demo: 2,000 credits per person per month; release 500 weekly.');
  console.log('Simulated workspace: a full monthly allowance can be used early. This reviewed policy releases it in steps.');
  console.table(preview.results.map(row=>({user:row.userId,unit:row.unit,before:row.before.cap.amount,source:row.before.cap.source,after:row.plan.amount,headroom:row.plan.headroom,ceiling:row.plan.ceiling})));
  assert.ok(preview.results.every(row=>row.before.cap.amount==='2000'&&row.plan.amount==='500'&&row.plan.ceiling==='2000'));
  api.injectFault({userId:'synthetic-user-b',type:'after'});
  const partial=await run({apply:true});assert.equal(partial.ok,false);
  console.log('Partial batch:',partial.results.map(row=>`${row.userId}=${row.status}`).join(', '));
  const recovered=await run({apply:true});assert.equal(recovered.ok,true);
  console.log('Replay:',recovered.results.map(row=>`${row.userId}=${row.status}`).join(', '));
  assert.equal(api.writes.length,3);
  now='2030-01-09T00:00:00.000Z';
  const next=await run({apply:true});assert.equal(next.ok,true);
  assert.ok(next.results.every(row=>row.after.cap.amount==='1000'));
  console.log('Next weekly release:',next.results.map(row=>`${row.userId}=${row.after.cap.amount}`).join(', '));
  api.users['synthetic-user-a'].settings.effective.source.changedBy='synthetic-other-admin';
  const conflict=await run({apply:true,restore:true});assert.equal(conflict.ok,false);
  assert.equal(conflict.results[0].code,'MANUAL_ADMIN_CHANGE_CONFLICT');
  console.log('Restore with manual conflict:',conflict.results.map(row=>`${row.userId}=${row.code??row.status}`).join(', '));
  // Undo only the synthetic test injection, simulating the operator resolving the conflict.
  delete api.users['synthetic-user-a'].settings.effective.source.changedBy;
  assert.equal((await run({apply:true,restore:true})).ok,true);
  assert.ok(Object.values(api.users).every(user=>user.cap.amount==='2000'&&user.cap.source==='workspace_default'));
  console.log('Restored the original inherited 2,000-credit cap for every fictional user. Durable local journals exercised.');
} finally {
  await rm(directory,{recursive:true,force:true});
  console.log('Temporary demo files removed.');
}
