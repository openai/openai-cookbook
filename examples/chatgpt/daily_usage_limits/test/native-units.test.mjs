import test from 'node:test';
import assert from 'node:assert/strict';
import { exampleConfig, createSyntheticApi, MemoryStore, usdReleaseForInterval } from '../src/synthetic.mjs';
import { captureEnrollment, approveEnrollment } from '../src/enrollment.mjs';
import { captureRenewal } from '../src/renewal.mjs';
import { execute } from '../src/controller.mjs';
import { settingsEquivalent } from '../src/admin-api.mjs';
import { amount, capAmount, quantum } from '../src/policy.mjs';

const START='2030-01-02T00:00:00.000Z';
const NEXT='2030-02-01T00:00:00.000Z';
const approve=captured=>approveEnrollment(captured.enrollment,captured.hash,captured.enrollment.completedAt);
const tagged=value=>({type:'limited',limit_amount:{amount:value,unit:'usd'}});
const effective=(value,source)=>({limit:tagged(value),source});
const clone=value=>structuredClone(value);

function applySettings(user,settings) {
  user.settings=clone(settings);
  const rule=settings.effective?.limit;
  user.cap=rule?{type:'limited',amount:rule.limit_amount.amount,unit:'usd',source:settings.effective.source.kind,
    ...(rule.limit_expires_at?{expiresAt:rule.limit_expires_at}:{})}:{type:'unset',unit:'usd'};
}

for(const pattern of ['fixed_release','observed_headroom','individual_staircase']) {
  for(const cohort of ['selected','all'])test(`native USD ${pattern}/${cohort}: cents, replay, ceiling, renewal and exact original restore`,async()=>{
    let now=START;
    const config=exampleConfig({now,unit:'usd',pattern,cohort,intervalHours:24});
    Object.assign(config.policy,{increment:'0.10',ceiling:'0.55',lookbackDays:2,coverageHours:24,multiplierBps:15000});
    if(pattern==='individual_staircase')Object.assign(config.policy,{initialHeadroom:'0.10',minimumInitialHeadroom:'0.01'});
    else config.policy.startCap='0.10';
    config.allowInitialReduction=true;
    if(cohort==='selected')config.cohort={mode:'selected',userIds:['synthetic-user-c'],
      emails:[' SYNTHETIC-USER-A@EXAMPLE.INVALID '],groupIds:['synthetic-group-b']};
    const api=createSyntheticApi({config,clock:()=>now});
    const ids=Object.keys(api.users).sort();
    const fallbackAmount=pattern==='observed_headroom'?'0.13':'9.99';
    const originalAmount=pattern==='observed_headroom'?'0.12':'1.23';
    const fallback=effective(fallbackAmount,{kind:'group_default',group_id:'fictional-usd-group'});
    applySettings(api.users[ids[0]],{override:null,effective:null,inherited:null});
    const original=tagged(originalAmount);
    applySettings(api.users[ids[1]],{override:[original],effective:{limit:original,source:{kind:'individual_override'}},inherited:fallback});
    applySettings(api.users[ids[2]],{override:null,effective:fallback,inherited:null});
    for(const user of Object.values(api.users))user.usage='0.071';
    const originalSettings=ids.map(id=>clone(api.users[id].settings));
    const setCap=api.setCap.bind(api);
    api.setCap=async(id,target)=>{
      const before=clone(api.users[id].settings);
      await setCap(id,target);
      api.users[id].settings.inherited=before.override?.length?before.inherited:before.effective;
    };
    const readHistory=api.readHistory.bind(api);
    api.readHistory=async(id,range)=>{
      const history=await readHistory(id,range);
      return {...history,days:history.days.map(day=>({...day,amount:'0.071'}))};
    };
    const captured=await captureEnrollment({config,api,now}),enrollment=approve(captured),store=new MemoryStore();
    assert.deepEqual(enrollment.members.map(member=>member.userId),ids);
    assert.ok(enrollment.members.every(member=>member.before.unit==='usd'&&member.plan.unit==='usd'));
    assert.ok(enrollment.members.every(member=>member.plan.amount===(pattern==='fixed_release'?'0.1':'0.18')));
    if(pattern==='individual_staircase')assert.deepEqual(enrollment.members.map(member=>member.startCap),['0.18','0.18','0.18']);
    const run=(options={})=>execute({config,enrollment,api,store,now,apply:true,...options});
    api.injectFault({userId:ids[1],type:'after'});
    assert.equal((await run()).ok,false);
    assert.equal(api.writes.length,3);
    assert.equal((await run()).results[1].status,'reconciled');
    assert.equal(api.writes.length,3,'ambiguous response must not grant again');
    now='2030-01-03T00:00:00.000Z';
    for(const user of Object.values(api.users))user.usage='0.081';
    assert.equal((await run()).ok,true);
    const second={fixed_release:'0.2',observed_headroom:'0.19',individual_staircase:'0.28'}[pattern];
    assert.deepEqual(ids.map(id=>api.users[id].cap.amount),[second,second,second]);
    now='2030-01-08T00:00:00.000Z';
    for(const user of Object.values(api.users))user.usage='0.54';
    assert.equal((await run()).ok,true);
    assert.ok(ids.every(id=>api.users[id].cap.amount==='0.55'));
    assert.ok(api.writes.every(write=>write.unit==='usd'&&amount(write.amount)<=amount('0.55')&&amount(write.amount)%10000n===0n));

    // Explicit fixture event models the confirmed next period and API expiry.
    now=NEXT;
    for(const [index,id] of ids.entries()) {
      applySettings(api.users[id],{override:null,effective:api.users[id].settings.inherited,inherited:null});
      api.users[id].usage=pattern==='individual_staircase'&&index===2?'0.101':'0.002';
    }
    const writeCount=api.writes.length;
    const renewed=await captureRenewal({previousConfig:config,previousEnrollment:enrollment,api,store,now,
      period:{kind:'calendar_month',start:NEXT,end:'2030-03-01T00:00:00.000Z',verifiedAt:NEXT,
        evidence:'Fictional USD counter period independently verified.',counterScopeConfirmed:true}});
    assert.equal(api.writes.length,writeCount,'renewal capture is read-only');
    assert.equal(renewed.config.unit,'usd');
    if(pattern==='individual_staircase')assert.deepEqual(renewed.enrollment.members.map(member=>member.startCap),['0.11','0.11','0.21']);
    const nextArgs={config:renewed.config,enrollment:approve(renewed),api,store,now,apply:true};
    assert.equal((await execute(nextArgs)).ok,true);
    assert.equal(store.archives.size,3);
    const afterRenewal=api.writes.length;
    assert.ok((await execute(nextArgs)).results.every(row=>row.status==='duplicate_slot'));
    assert.equal(api.writes.length,afterRenewal);
    assert.equal((await execute({...nextArgs,restore:true})).ok,true);
    for(const [index,id] of ids.entries())assert.ok(settingsEquivalent(api.users[id].settings,originalSettings[index],'usd'));
    assert.equal(api.users[ids[0]].cap.type,'unset');
    assert.equal(api.users[ids[1]].cap.amount,originalAmount);
    assert.equal(api.users[ids[2]].cap.amount,fallbackAmount);
  });
}

test('changing the selected unit cannot reinterpret a reviewed enrollment or renew it',async()=>{
  let now=START;
  const config=exampleConfig({now,unit:'usd',intervalHours:168}),api=createSyntheticApi({config,clock:()=>now}),store=new MemoryStore();
  const enrollment=approve(await captureEnrollment({config,api,now}));
  const changed={...config,unit:'credit'};
  await assert.rejects(execute({config:changed,enrollment,api,store,now,apply:true}),{code:'ENROLLMENT_POLICY_MISMATCH'});
  for(const user of Object.values(api.users))user.unit='credit';
  assert.ok((await execute({config,enrollment,api,store,now,apply:true})).results.every(row=>row.code==='UNIT_TRANSITION_REQUIRES_REENROLLMENT'));
  now=NEXT;
  await assert.rejects(captureRenewal({previousConfig:config,previousEnrollment:enrollment,api,store,now,
    period:{kind:'calendar_month',start:NEXT,end:'2030-03-01T00:00:00.000Z',verifiedAt:NEXT,
      evidence:'Fictional period.',counterScopeConfirmed:true}}),{code:'UNIT_TRANSITION_REQUIRES_REENROLLMENT'});
  assert.equal(api.writes.length,0);
});

test('unit helpers and example setup reject unsupported currency names instead of treating them as USD',()=>{
  for(const unit of ['dollars','USD','eur','',null]) {
    assert.throws(()=>exampleConfig({now:START,unit}),{code:'UNIT_INVALID'});
    assert.throws(()=>quantum(unit),{code:'UNIT_INVALID'});
    assert.throws(()=>capAmount('0.01',unit),{code:'UNIT_INVALID'});
  }
  assert.equal(capAmount('0.10','usd')+capAmount('0.20','usd'),capAmount('0.30','usd'));
  assert.throws(()=>capAmount('0.01','credit'),{code:'CAP_PRECISION_INVALID'});
  assert.throws(()=>capAmount('0.001','usd'),{code:'CAP_PRECISION_INVALID'});
});

test('USD example presets use an independent $200 budget and round custom schedules upward to cents',()=>{
  for(const [intervalHours,release] of [[1,'0.28'],[24,'6.67'],[72,'20'],[168,'50'],[336,'100'],[720,'200'],[744,'200']]) {
    const config=exampleConfig({now:START,unit:'usd',intervalHours});
    assert.equal(usdReleaseForInterval(intervalHours),release);
    assert.equal(config.policy.startCap,release);
    assert.equal(config.policy.increment,release);
    assert.equal(config.policy.ceiling,'200');
    assert.equal(config.allowInitialReduction,false);
    assert.equal(config.liveWrites,false);
    assert.equal(createSyntheticApi({config}).users['synthetic-user-a'].cap.amount,'200');
  }
  for(const intervalHours of [0,-1,0.5,745,NaN])assert.throws(()=>usdReleaseForInterval(intervalHours),{code:'INTERVAL_INVALID'});
});

test('initial USD headroom uses sub-cent consumption at the final read without rounding it downward',async()=>{
  for(const [usage,allowed] of [['0.17',true],['0.170001',false]]) {
    const config=exampleConfig({now:START,unit:'usd',pattern:'individual_staircase'});
    config.cohort={mode:'selected',userIds:['synthetic-user-a'],emails:[],groupIds:[]};
    Object.assign(config.policy,{initialHeadroom:'0.10',minimumInitialHeadroom:'0.01',increment:'0.10',ceiling:'1'});
    const api=createSyntheticApi({config,clock:()=>START,initialCap:'0.05'});
    api.users['synthetic-user-a'].usage='0.071';
    const enrollment=approve(await captureEnrollment({config,api,now:START}));
    assert.equal(enrollment.members[0].startCap,'0.18');
    const read=api.readSnapshot.bind(api);let reads=0;
    api.readSnapshot=async id=>{
      if(++reads===2)api.users[id].usage=usage;
      return read(id);
    };
    const result=await execute({config,enrollment,api,store:new MemoryStore(),now:START,apply:true});
    assert.equal(result.ok,allowed);
    assert.equal(api.writes.length,allowed?1:0);
    if(allowed)assert.equal(api.writes[0].expectedUsage,'0.17');
    else assert.equal(result.results[0].code,'INITIAL_HEADROOM_TOO_LOW_RECAPTURE');
  }
});
