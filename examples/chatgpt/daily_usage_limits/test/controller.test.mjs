import test from 'node:test';
import assert from 'node:assert/strict';
import { exampleConfig, createSyntheticApi, creditReleaseForInterval, MemoryStore } from '../src/synthetic.mjs';
import { captureEnrollment, approveEnrollment } from '../src/enrollment.mjs';
import { execute } from '../src/controller.mjs';
import { DAY, HOUR, configDigest, planTarget, validateConfig, amount, format, capAmount } from '../src/policy.mjs';
import { settingsEquivalent } from '../src/admin-api.mjs';

const START = '2030-01-02T00:00:00.000Z';
async function setup(options = {}, alter) {
  let now = START;
  const config = exampleConfig({now,...options});
  // Failure/recovery fixtures intentionally keep their small amounts independent
  // of the customer-facing 2,000-credit example defaults.
  if (config.unit === 'credit') Object.assign(config.policy,{startCap:'20',increment:'20',ceiling:'200'});
  else Object.assign(config.policy,{startCap:'2',increment:'2',ceiling:'20'});
  if(alter)alter(config);
  const api=createSyntheticApi({config,clock:()=>now,initialCap:config.unit==='credit'?'10':'1'});
  const captured=await captureEnrollment({config,api,now});
  const enrollment=approveEnrollment(captured.enrollment,captured.hash,now);
  const store=new MemoryStore();
  return {config,api,enrollment,store,setTime(value){now=value;},
    run: (args={})=>execute({config,enrollment,api,store,now,apply:true,...args})};
}
test('credit example uses a 2,000 monthly ceiling and deliberate cadence presets with reductions off',async()=>{
  for(const [intervalHours,release] of [[24,'67'],[168,'500'],[336,'1000'],[1,'3'],[72,'200'],[720,'2000'],[744,'2000']]) {
    const config=exampleConfig({now:START,intervalHours});
    assert.equal(config.policy.startCap,release);
    assert.equal(config.policy.increment,release);
    assert.equal(config.policy.ceiling,'2000');
    assert.equal(config.allowInitialReduction,false);
    assert.equal(config.liveWrites,false);
    assert.equal(creditReleaseForInterval(intervalHours),release);
  }
  const daily=exampleConfig({now:START});
  assert.equal(daily.policy.intervalHours,24);
  assert.equal(daily.policy.startCap,'67');
  const api=createSyntheticApi({config:daily,clock:()=>START});
  assert.equal((await api.readSnapshot('synthetic-user-a')).cap.amount,'2000');
  const captured=await captureEnrollment({config:daily,api,now:START});
  const enrollment=approveEnrollment(captured.enrollment,captured.hash,START);
  const result=await execute({config:daily,enrollment,api,store:new MemoryStore(),now:START,apply:true});
  assert.equal(result.results[0].code,'INITIAL_REDUCTION_REQUIRES_REVIEWED_OPT_IN');
  assert.equal(api.writes.length,0);
  const usd=exampleConfig({now:START,unit:'usd',intervalHours:168});
  assert.equal(usd.policy.startCap,'50');assert.equal(usd.policy.increment,'50');assert.equal(usd.policy.ceiling,'200');
});
test('reviewed weekly example releases 500 through 2,000 and never exceeds the monthly ceiling',async()=>{
  let now=START;
  const config=exampleConfig({now,intervalHours:168});
  config.allowInitialReduction=true;
  const api=createSyntheticApi({config,clock:()=>now});
  const captured=await captureEnrollment({config,api,now});
  const enrollment=approveEnrollment(captured.enrollment,captured.hash,now);
  const store=new MemoryStore();
  for(const [date,cap] of [['2030-01-02','500'],['2030-01-09','1000'],['2030-01-16','1500'],
    ['2030-01-23','2000'],['2030-01-30','2000']]) {
    now=`${date}T00:00:00.000Z`;
    const args={config,enrollment,api,store,now,apply:true};
    const result=await execute(args);
    assert.equal(result.ok,true);
    assert.equal(api.users['synthetic-user-a'].cap.amount,cap);
    const writes=api.writes.length;
    assert.ok((await execute(args)).results.every(row=>row.status==='duplicate_slot'));
    assert.equal(api.writes.length,writes);
  }
  assert.equal((await execute({config,enrollment,api,store,now,apply:true,restore:true})).ok,true);
  assert.equal(api.users['synthetic-user-a'].cap.amount,'2000');
  assert.equal(api.users['synthetic-user-a'].cap.source,'workspace_default');
});
for (const pattern of ['fixed_release','observed_headroom']) {
  for (const intervalHours of [1,24,168,72]) {
    for (const cohort of ['selected','all']) {
      for (const unit of ['credit','usd']) {
        test(`${pattern}: ${intervalHours}h / ${cohort} / ${unit}: apply replay next slot restore`,async()=>{
          const s=await setup({pattern,intervalHours,cohort,unit});
          assert.equal((await s.run()).ok,true);
          const firstWrites=s.api.writes.length;
          assert.equal(firstWrites,cohort==='all'?3:2);
          const again=await s.run();
          assert.ok(again.results.every(result=>result.status==='duplicate_slot'));
          assert.equal(s.api.writes.length,firstWrites);
          s.setTime(new Date(Date.parse(START)+intervalHours*HOUR).toISOString());
          assert.equal((await s.run()).ok,true);
          const cap=s.api.users['synthetic-user-a'].cap.amount;
          assert.equal(cap,pattern==='fixed_release'?(unit==='credit'?'40':'4'):(unit==='credit'?'30':'3'));
          const end=await s.run({restore:true});
          assert.equal(end.ok,true);
          for(const member of s.enrollment.members) assert.ok(settingsEquivalent(s.api.users[member.userId].settings,member.before.settings,unit));
          assert.ok((await s.run()).results.every(row=>row.status==='restored_stopped'));
        });
      }
    }
  }
}
test('preview cannot write or enroll without review',async()=>{
  const s=await setup(); delete s.enrollment.approval;
  assert.equal((await s.run({apply:false})).ok,true);
  assert.equal(s.api.writes.length,0); assert.equal(s.store.states.size,0);
  await assert.rejects(s.run(),{code:'ENROLLMENT_APPROVAL_REQUIRED'});
});
test('initial lower cap is denied unless captured with explicit opt-in; stale restriction blocked',async()=>{
  const s=await setup({},config=>{config.policy.startCap='5';});
  assert.equal((await s.run()).results[0].code,'INITIAL_REDUCTION_REQUIRES_REVIEWED_OPT_IN');
  assert.equal(s.api.writes.length,0);
  const allowed=await setup({},config=>{config.policy.startCap='5';config.allowInitialReduction=true;});
  allowed.api.users['synthetic-user-a'].usage='1';
  const result=await allowed.run();
  assert.equal(result.ok,false);assert.equal(result.results[0].code,'RESTRICTION_USAGE_CHANGED_RECAPTURE');
  assert.equal(result.results[1].status,'applied');
});
test('unlimited and persistent before sources are exactly restored',async()=>{
  const s=await setup({},c=>{c.allowInitialReduction=true;});
  const rule={type:'unlimited'};
  const user=s.api.users['synthetic-user-a'];
  user.cap={type:'unlimited',unit:'credit',source:'individual_override'};
  user.settings={...user.settings,override:[rule],effective:{limit:rule,source:{kind:'individual_override'}}};
  const captured=await captureEnrollment({config:s.config,api:s.api,now:START});
  const enrollment=approveEnrollment(captured.enrollment,captured.hash,START);
  const args={config:s.config,enrollment,api:s.api,store:s.store,now:START,apply:true};
  assert.equal((await execute(args)).ok,true);
  assert.equal((await execute({...args,restore:true})).ok,true);
  assert.equal(s.api.users['synthetic-user-a'].cap.type,'unlimited');
});
test('fixed catch-up is absolute, carries unused entitlement and respects ceiling',async()=>{
  const s=await setup({},c=>{c.policy.startCap='100';c.policy.increment='10';c.policy.ceiling='125';});
  await s.run(); s.api.users['synthetic-user-a'].usage='80';
  s.setTime('2030-01-03T00:00:00.000Z');
  const day2=await s.run();assert.equal(day2.results[0].plan.amount,'110');assert.equal(day2.results[0].plan.headroom,'30');
  s.setTime('2030-01-05T00:00:00.000Z');
  const catchup=await s.run();assert.equal(catchup.results[0].plan.amount,'125');assert.equal(catchup.results[0].plan.shortfall,'5');
});
test('interval boundary uses elapsed UTC duration; missed headroom slots are not multiplied',async()=>{
  const s=await setup({pattern:'observed_headroom',intervalHours:24});await s.run();
  s.setTime('2030-01-02T23:59:59.999Z');assert.equal((await s.run()).results[0].status,'duplicate_slot');
  s.setTime('2030-01-05T00:00:00.000Z');s.api.users['synthetic-user-a'].usage='25';
  const result=await s.run();assert.equal(result.results[0].plan.amount,'55');
});
test('late history correction cannot rerun consumed slot',async()=>{
  const s=await setup({pattern:'observed_headroom'});await s.run();
  s.api.readHistory=async()=>{throw new Error('must not refetch consumed slot');};
  assert.equal((await s.run()).results[0].status,'duplicate_slot');
});
test('ambiguous after-write result reconciles without another PATCH, including partial cohorts',async()=>{
  const s=await setup({cohort:'all'});s.api.injectFault({userId:'synthetic-user-b',type:'after'});
  const first=await s.run();assert.equal(first.ok,false);
  assert.equal(first.results[0].status,'applied');assert.equal(first.results[1].status,'attention');assert.equal(first.results[2].status,'applied');
  const writes=s.api.writes.length;const retry=await s.run();assert.equal(retry.ok,true);assert.equal(retry.results[1].status,'reconciled');assert.equal(s.api.writes.length,writes);
});
test('before-write transient failure retries saved absolute target even after next slot',async()=>{
  const s=await setup();s.api.injectFault({userId:'synthetic-user-a',type:'before'});
  assert.equal((await s.run()).ok,false);s.setTime('2030-01-03T00:00:00.000Z');
  assert.equal((await s.run()).ok,true);assert.equal(s.api.users['synthetic-user-a'].cap.amount,'20');
  assert.equal((await s.run()).ok,true);assert.equal(s.api.users['synthetic-user-a'].cap.amount,'40');
});
test('429 deferral is durable and 403 halts repeated writes',async()=>{
  const s=await setup();s.api.injectFault({userId:'synthetic-user-a',type:'before',status:429,retryAfterMs:3_600_000});
  await s.run();assert.equal((await s.run()).results[0].code,'RETRY_AFTER_NOT_REACHED');
  s.setTime('2030-01-02T01:00:00.000Z');assert.equal((await s.run()).ok,true);
  const auth=await setup();auth.api.injectFault({userId:'synthetic-user-a',type:'before',status:403});await auth.run();
  assert.equal((await auth.run()).results[0].code,'AUTH_FAILURE_HALTED_REVIEW_REQUIRED');
  assert.equal((await auth.run({apply:false,resumeAuth:true})).results[0].status,'auth_resumed');
  assert.equal((await auth.run()).ok,true);
});
test('expired unapplied initial restriction never retries, but committed restriction reconciles',async()=>{
  for(const fault of ['before','after']) {
    const s=await setup({intervalHours:1},c=>{c.policy.startCap='5';c.allowInitialReduction=true;});
    s.api.injectFault({userId:'synthetic-user-a',type:fault});await s.run();
    const writes=s.api.writes.length;s.setTime('2030-01-02T01:00:00.000Z');
    const result=await s.run();
    if(fault==='before') {
      assert.equal(result.results[0].code,'INITIAL_RESTRICTION_PREVIEW_EXPIRED_CANCEL_AND_REVIEW');
      assert.equal(s.api.users['synthetic-user-a'].cap.amount,'10');
      const cancel=await s.run({apply:false,cancelInitial:true});assert.equal(cancel.results[0].status,'initial_intent_cancelled');
      assert.equal((await s.run()).results[0].status,'restored_stopped');
    } else assert.equal(result.results[0].status,'reconciled');
    // Only the unaffected member gets a legitimate next-slot raise.
    assert.equal(s.api.writes.length,writes+1);
  }
});
test('journal failure prevents a write',async()=>{
  const s=await setup();s.store.putState=async()=>{throw new Error('disk full');};
  assert.equal((await s.run()).ok,false);assert.equal(s.api.writes.length,0);
});
test('Retry-After starts at the time a slow failed write returns',async()=>{
  let clockTime=Date.parse(START);const clock=()=>new Date(clockTime).toISOString();
  const s=await setup();const set=s.api.setCap;
  s.api.setCap=async(id,target)=>{if(id==='synthetic-user-a') {clockTime+=60_000;s.setTime(clock());throw Object.assign(new Error('slow429'),{code:'SLOW_429',status:429,retryAfterMs:60_000});} return set(id,target);};
  const args={config:s.config,enrollment:s.enrollment,api:s.api,store:s.store,clock,apply:true};
  await execute(args);
  const saved=await s.store.getState('synthetic-workspace:synthetic-user-a');
  assert.equal(saved.notBefore,'2030-01-02T00:02:00.000Z');
  s.api.setCap=set;
  assert.equal((await execute(args)).results[0].code,'RETRY_AFTER_NOT_REACHED');
  clockTime+=60_000;s.setTime(clock());assert.equal((await execute(args)).ok,true);
});
test('inherited fallback change during PATCH is visible and cannot be silently restored',async()=>{
  const s=await setup();const set=s.api.setCap;
  s.api.setCap=async(id,target)=>{await set(id,target);s.api.users[id].settings.inherited.limit.limit_amount.amount='999';};
  const result=await s.run();assert.equal(result.results[0].code,'WRITE_READBACK_MISMATCH');
  assert.equal((await s.run()).results[0].code,'PENDING_WRITE_CONFLICT');
});
test('manual edits conflict on restore and pending retry',async()=>{
  const s=await setup();await s.run();
  s.api.users['synthetic-user-a'].settings.effective.source={kind:'individual_override',changedBy:'another-admin'};
  const writes=s.api.writes.length;const result=await s.run({restore:true});
  assert.equal(result.ok,false);assert.equal(result.results[0].code,'MANUAL_ADMIN_CHANGE_CONFLICT');assert.equal(s.api.writes.length,writes+1);
});
test('period boundary, unit transition and counter drop stop writes',async()=>{
  const s=await setup();await s.run();s.api.users['synthetic-user-a'].usage='10';
  s.setTime('2030-01-03T00:00:00.000Z');await s.run();s.api.users['synthetic-user-a'].usage='9';
  s.setTime('2030-01-04T00:00:00.000Z');assert.equal((await s.run()).results[0].code,'COUNTER_DECREASE_REQUIRES_PERIOD_REVIEW');
  s.api.users['synthetic-user-b'].unit='usd';assert.equal((await s.run()).results[1].code,'UNIT_TRANSITION_REQUIRES_REENROLLMENT');
  s.setTime('2030-02-01T00:00:00.000Z');await assert.rejects(s.run(),{code:'OUTSIDE_VERIFIED_PERIOD'});
});
test('roster additions remain unenrolled; removals are visible attention',async()=>{
  const s=await setup({cohort:'all'});await s.run();
  s.api.users['synthetic-new']=structuredClone(s.api.users['synthetic-user-c']);delete s.api.users['synthetic-user-a'];
  const result=await s.run();assert.equal(result.addedMembersNotEnrolled,1);assert.equal(result.ok,false);assert.equal(result.results[0].code,'MEMBER_REMOVED_OR_INELIGIBLE');
});
test('policy revision cannot erase ledger',async()=>{
  const s=await setup();await s.run();s.config.policy.increment='50';
  await assert.rejects(s.run(),{code:'ENROLLMENT_POLICY_MISMATCH'});
});
test('missing and duplicate history is unknown; explicit zero is allowed',async()=>{
  const s=await setup({pattern:'observed_headroom'});const snap=await s.api.readSnapshot('synthetic-user-a');
  const history=await s.api.readHistory(snap.userId,{start:'2029-12-26T00:00:00.000Z',end:START,unit:'credit'});
  history.days.pop();assert.throws(()=>planTarget(s.config,snap,START,history),{code:'MISSING_HISTORY_DAYS'});
  history.days.push(history.days[0]);assert.throws(()=>planTarget(s.config,snap,START,history),{code:'DUPLICATE_HISTORY_DAY'});
});
test('invalid cadence, decimals, cents and timestamps are rejected',()=>{
  for(const intervalHours of [0,-1,1.5,745])assert.throws(()=>validateConfig(exampleConfig({now:START,intervalHours}),START));
  for(const value of ['-1','NaN','1e3','0.0000001',1])assert.throws(()=>amount(value));
  assert.throws(()=>capAmount('1.2','credit'));assert.throws(()=>capAmount('1.001','usd'));
  assert.equal(format(amount('0.1')+amount('0.2')),'0.3');
});
test('billing-cycle period supported only with explicit counter-scope confirmation',async()=>{
  const s=await setup({},c=>{c.period.kind='billing_cycle';c.period.start='2029-12-15T00:00:00.000Z';c.period.end='2030-01-15T00:00:00.000Z';});
  assert.equal((await s.run()).ok,true);
  s.config.period.counterScopeConfirmed=false;assert.throws(()=>validateConfig(s.config,START),{code:'COUNTER_PERIOD_SCOPE_CONFIRMATION_REQUIRED'});
});
test('moving clock sampled after reads allows real-world response latency',async()=>{
  let clockTime=Date.parse(START);
  const clock=()=>new Date(clockTime).toISOString();
  const config=exampleConfig({now:clock()});
  Object.assign(config.policy,{startCap:'20',increment:'20',ceiling:'200'});
  const api=createSyntheticApi({config,clock,initialCap:'10'});
  const read=api.readSnapshot;api.readSnapshot=async id=>{clockTime+=250;return read(id);};
  const captured=await captureEnrollment({config,api,clock});
  const enrollment=approveEnrollment(captured.enrollment,captured.hash,clock());
  const result=await execute({config,enrollment,api,store:new MemoryStore(),clock,apply:true});
  assert.equal(result.ok,true);
});
test('crossing slot during final read saves intent but does not PATCH',async()=>{
  const s=await setup({intervalHours:1});let clockTime=Date.parse(START)+HOUR-1000;
  // Capture a fresh reviewed snapshot at the end of slot zero.
  s.setTime(new Date(clockTime).toISOString());
  const clock=()=>new Date(clockTime).toISOString();
  const captured=await captureEnrollment({config:s.config,api:s.api,now:clock()});
  const enrollment=approveEnrollment(captured.enrollment,captured.hash,clock());
  const read=s.api.readSnapshot;let reads=0;s.api.readSnapshot=async id=>{if(++reads===2)clockTime+=2000;s.setTime(clock());return read(id);};
  const result=await execute({config:s.config,enrollment,api:s.api,store:s.store,clock,apply:true});
  assert.equal(result.results[0].code,'SLOT_CHANGED_DURING_RUN');assert.equal(s.api.writes.length,0);
});
