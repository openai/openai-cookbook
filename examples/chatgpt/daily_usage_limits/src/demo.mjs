import assert from 'node:assert/strict';
import { parseArgs } from 'node:util';
import { exampleConfig, createSyntheticApi, MemoryStore } from './synthetic.mjs';
import { captureEnrollment, approveEnrollment } from './enrollment.mjs';
import { execute } from './controller.mjs';
import { amount, format, requireThat } from './policy.mjs';

// All dates, identities, usage, responses and failures here are fictional.
const { values: { unit }, tokens } = parseArgs({ args: process.argv.slice(2), options: { unit: { type: 'string', default: 'credit' } }, strict: true, tokens: true });
requireThat(tokens.length <= 1, 'UNIT_OPTION_REPEATED');
requireThat(['credit', 'usd'].includes(unit), 'UNIT_INVALID');
const display = value => unit === 'usd' ? `$${Number(value).toFixed(2)}` : value;
let now='2030-01-02T00:00:00.000Z';
{
  const config=exampleConfig({now,cohort:'all',intervalHours:168,unit});
  const {startCap,increment,ceiling}=config.policy;
  // The fictional operator approves restricting the original monthly cap before capture.
  config.allowInitialReduction=true;
  const api=createSyntheticApi({config,clock:()=>now,initialCap:ceiling});
  const {enrollment:captured,hash}=await captureEnrollment({config,api,now});
  const enrollment=approveEnrollment(captured,hash,now);
  // This store lasts only for this fictional run. Live runners require durable storage.
  const store=new MemoryStore();
  const run=(options={})=>execute({config,enrollment,api,store,now,...options});
  const preview=await run();
  console.log(unit==='usd' ? 'Demo: $200.00 USD per person per month; release $50.00 weekly.' :
    'Demo: 2,000 credits per person per month; release 500 weekly.');
  console.log('Simulated workspace: a full monthly allowance can be used early. This reviewed policy releases it in steps.');
  console.table(preview.results.map(row=>({user:row.userId,unit:row.unit,before:display(row.before.cap.amount),source:row.before.cap.source,after:display(row.plan.amount),headroom:display(row.plan.headroom),ceiling:display(row.plan.ceiling)})));
  assert.ok(preview.results.every(row=>row.unit===unit&&row.before.cap.amount===ceiling&&row.plan.amount===startCap&&row.plan.ceiling===ceiling));
  api.injectFault({userId:'synthetic-user-b',type:'after'});
  const partial=await run({apply:true});assert.equal(partial.ok,false);
  console.log('Partial batch:',partial.results.map(row=>`${row.userId}=${row.status}`).join(', '));
  const recovered=await run({apply:true});assert.equal(recovered.ok,true);
  console.log('Replay:',recovered.results.map(row=>`${row.userId}=${row.status}`).join(', '));
  assert.equal(api.writes.length,3);
  now='2030-01-09T00:00:00.000Z';
  const next=await run({apply:true});assert.equal(next.ok,true);
  assert.ok(next.results.every(row=>row.after.cap.amount===format(amount(startCap)+amount(increment))));
  console.log('Next weekly release:',next.results.map(row=>`${row.userId}=${display(row.after.cap.amount)}`).join(', '));
  api.users['synthetic-user-a'].settings.effective.source.changedBy='synthetic-other-admin';
  const conflict=await run({apply:true,restore:true});assert.equal(conflict.ok,false);
  assert.equal(conflict.results[0].code,'MANUAL_ADMIN_CHANGE_CONFLICT');
  console.log('Restore with manual conflict:',conflict.results.map(row=>`${row.userId}=${row.code??row.status}`).join(', '));
  // Undo only the synthetic test injection, simulating the operator resolving the conflict.
  delete api.users['synthetic-user-a'].settings.effective.source.changedBy;
  assert.equal((await run({apply:true,restore:true})).ok,true);
  assert.ok(Object.values(api.users).every(user=>user.cap.amount===ceiling&&user.cap.unit===unit&&user.cap.source==='workspace_default'));
  console.log(unit==='usd' ? 'Restored the original inherited $200.00 USD cap for every fictional user.' :
    'Restored the original inherited 2,000-credit cap for every fictional user.');
  console.log('Demo complete. All simulated state stayed in memory.');
}
