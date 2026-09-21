import test from 'node:test';
import assert from 'node:assert/strict';
import { exampleConfig, createSyntheticApi } from '../src/synthetic.mjs';
import { captureEnrollment, approveEnrollment, validateEnrollment } from '../src/enrollment.mjs';

const START='2030-01-02T00:00:00.000Z';
function largeFixture(count,concurrency=4) {
  const config=exampleConfig({now:START,cohort:'all',intervalHours:168});
  config.captureConcurrency=concurrency;
  const api=createSyntheticApi({config,clock:()=>START});
  const original=api.users['synthetic-user-a'];
  for(const id of Object.keys(api.users))delete api.users[id];
  for(let index=0;index<count;index++) {
    const userId=`fictional-user-${String(index).padStart(5,'0')}`;
    api.users[userId]={...structuredClone(original),userId,email:`${userId}@example.invalid`};
  }
  return {config,api};
}

test('an entire 2,001-member workspace captures without a fixed population ceiling',async()=>{
  const {config,api}=largeFixture(2001);
  const captured=await captureEnrollment({config,api,now:START});
  assert.equal(captured.enrollment.members.length,2001);
  assert.deepEqual(captured.enrollment.selection.resolvedUserIds,Object.keys(api.users).sort());
  validateEnrollment(config,approveEnrollment(captured.enrollment,captured.hash,START),START,true);
  config.maxMembers=2000;
  await assert.rejects(captureEnrollment({config,api,now:START}),{code:'COHORT_SIZE_INVALID'});
  assert.equal(api.writes.length,0);
});

test('capture fanout respects the configured concurrency and preserves deterministic member order',async()=>{
  const {config,api}=largeFixture(11,3);
  const original=api.readSnapshot;
  let active=0,peak=0;
  api.readSnapshot=async id=>{
    peak=Math.max(peak,++active);
    try{await new Promise(resolve=>setTimeout(resolve,2));return await original(id);}finally{active--;}
  };
  const {enrollment}=await captureEnrollment({config,api,now:START});
  assert.equal(peak,3);
  assert.deepEqual(enrollment.members.map(member=>member.userId),Object.keys(api.users).sort());
});

test('long capture preserves its start time and requires an explicitly sufficient review window',async()=>{
  for(const minutes of [15,30]) {
    let now=Date.parse(START);const clock=()=>new Date(now).toISOString();
    const config=exampleConfig({now:START,intervalHours:168});
    config.initialReviewMaxAgeMinutes=minutes;
    const api=createSyntheticApi({config,clock}),read=api.readSnapshot;
    api.readSnapshot=async id=>{now+=8*60_000;return read(id);};
    if(minutes===15)await assert.rejects(captureEnrollment({config,api,clock}),{code:'CAPTURE_REVIEW_WINDOW_EXPIRED'});
    else {
      const {enrollment}=await captureEnrollment({config,api,clock});
      assert.equal(enrollment.capturedAt,START);
      assert.equal(enrollment.completedAt,'2030-01-02T00:16:00.000Z');
      assert.equal(enrollment.members[0].before.observedAt,'2030-01-02T00:08:00.000Z');
    }
  }
});

test('capture cannot mix policy slots even when its review window is long enough',async()=>{
  let now=Date.parse(START);const clock=()=>new Date(now).toISOString();
  const config=exampleConfig({now:START,intervalHours:1});
  config.initialReviewMaxAgeMinutes=120;
  const api=createSyntheticApi({config,clock}),read=api.readSnapshot;
  api.readSnapshot=async id=>{now+=31*60_000;return read(id);};
  await assert.rejects(captureEnrollment({config,api,clock}),{code:'CAPTURE_SLOT_CHANGED_RECAPTURE'});
  assert.equal(api.writes.length,0);
});
