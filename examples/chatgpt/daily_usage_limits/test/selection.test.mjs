import test from 'node:test';
import assert from 'node:assert/strict';
import { resolveCohort, normalizeCohort, validateCurrentCohort } from '../src/selection.mjs';
import { exampleConfig, createSyntheticApi } from '../src/synthetic.mjs';
import { captureEnrollment, approveEnrollment, validateEnrollment } from '../src/enrollment.mjs';
import { approvalWindowMs, validateConfig, planTarget, DAY } from '../src/policy.mjs';

const START='2030-01-02T00:00:00.000Z';
const configFor=cohort=>({...exampleConfig({now:START,intervalHours:168}),cohort});
const apiFor=config=>createSyntheticApi({config,clock:()=>START});

test('selected IDs, normalized emails and overlapping groups form a deterministic union',async()=>{
  const config=configFor({mode:'selected',userIds:['synthetic-user-c','synthetic-user-c'],
    emails:[' SYNTHETIC-USER-A@EXAMPLE.INVALID ','synthetic-user-a@example.invalid'],groupIds:['synthetic-group-b','synthetic-group-a']});
  const resolved=await resolveCohort({config,api:apiFor(config)});
  assert.deepEqual(resolved.userIds,['synthetic-user-a','synthetic-user-b','synthetic-user-c']);
  assert.deepEqual(resolved.selection.emailBindings,[{email:'synthetic-user-a@example.invalid',userId:'synthetic-user-a'}]);
  assert.deepEqual(resolved.selection.groupBindings.map(group=>group.groupId),['synthetic-group-a','synthetic-group-b']);
});

test('unmatched or ambiguous emails and missing, empty or inactive groups stop capture',async()=>{
  for(const scenario of ['email_missing','email_ambiguous','group_missing','group_empty','group_inactive','user_inactive']) {
    const config=configFor({mode:'selected',userIds:scenario==='user_inactive'?['missing-user']:[],
      emails:scenario.startsWith('email')?['synthetic-user-a@example.invalid']:[],groupIds:scenario.startsWith('group')?['synthetic-group-a']:[]});
    const api=apiFor(config);
    if(scenario==='email_missing')delete api.users['synthetic-user-a'];
    if(scenario==='email_ambiguous')api.users['synthetic-user-b'].email=api.users['synthetic-user-a'].email;
    if(scenario==='group_missing')delete api.groups['synthetic-group-a'];
    if(scenario==='group_empty')api.groups['synthetic-group-a']=[];
    if(scenario==='group_inactive')api.groups['synthetic-group-a'].push('missing-user');
    await assert.rejects(captureEnrollment({config,api,now:START}),{code:{email_missing:'EMAIL_NOT_FOUND',
      email_ambiguous:'EMAIL_RESOLUTION_AMBIGUOUS',group_missing:'GROUP_NOT_FOUND',group_empty:'SELECTED_GROUP_EMPTY',
      group_inactive:'SELECTED_USER_NOT_ACTIVE_MEMBER',user_inactive:'SELECTED_USER_NOT_ACTIVE_MEMBER'}[scenario]});
    assert.equal(api.writes.length,0);
  }
});

test('email and group bindings are reviewed and changes stop new grants while restore keeps original IDs',async()=>{
  for(const kind of ['email','group']) {
    const config=configFor({mode:'selected',userIds:[],emails:kind==='email'?['synthetic-user-a@example.invalid']:[],
      groupIds:kind==='group'?['synthetic-group-a']:[]});
    const api=apiFor(config);
    const captured=await captureEnrollment({config,api,now:START});
    const enrollment=approveEnrollment(captured.enrollment,captured.hash,START);
    validateEnrollment(config,enrollment,START,true);
    assert.deepEqual((await validateCurrentCohort(config,enrollment,api)).userIds,enrollment.members.map(member=>member.userId));
    if(kind==='email') {
      api.users['synthetic-user-a'].email='renamed@example.invalid';
      api.users['synthetic-user-c'].email='synthetic-user-a@example.invalid';
    } else api.groups['synthetic-group-a'].push('synthetic-user-c');
    await assert.rejects(validateCurrentCohort(config,enrollment,api),{code:'COHORT_SELECTION_CHANGED'});
    assert.deepEqual((await validateCurrentCohort(config,enrollment,api,{restore:true})).userIds,enrollment.members.map(member=>member.userId));
    const tampered=structuredClone(enrollment);
    tampered.selection.resolvedUserIds.push('synthetic-user-c');
    assert.throws(()=>validateEnrollment(config,tampered,START,true),{code:'COHORT_REVIEW_MISMATCH'});
  }
});

test('all-workspace membership changes are reported without changing the reviewed members',async()=>{
  const config=configFor({mode:'all',userIds:[],emails:[],groupIds:[]});
  const api=apiFor(config);
  const {enrollment}=await captureEnrollment({config,api,now:START});
  delete api.users['synthetic-user-a'];
  api.users['synthetic-user-d']={...api.users['synthetic-user-c'],userId:'synthetic-user-d'};
  const current=await validateCurrentCohort(config,enrollment,api);
  assert.deepEqual(current.activeUserIds,['synthetic-user-b','synthetic-user-c','synthetic-user-d']);
  assert.deepEqual(enrollment.members.map(member=>member.userId),['synthetic-user-a','synthetic-user-b','synthetic-user-c']);
});

test('population limits and request fanout are configurable positive safe integers',()=>{
  const config=exampleConfig({now:START});
  assert.equal(config.maxMembers,null);
  for(const maxMembers of [null,501,50000,Number.MAX_SAFE_INTEGER])validateConfig({...config,maxMembers},START);
  for(const maxMembers of [0,-1,1.5,Number.MAX_SAFE_INTEGER+1])assert.throws(()=>validateConfig({...config,maxMembers},START),{code:'MAX_MEMBERS_INVALID'});
  validateConfig({...config,concurrency:100,captureConcurrency:50,apiLimits:{maxPages:5000,maxRows:1000000}},START);
  assert.throws(()=>validateConfig({...config,captureConcurrency:0},START),{code:'CAPTURE_CONCURRENCY_INVALID'});
  assert.throws(()=>validateConfig({...config,apiLimits:{maxRows:0}},START),{code:'API_LIMITS_INVALID'});
  assert.throws(()=>validateConfig({...config,apiLimits:{allowWrites:true}},START),{code:'API_LIMITS_INVALID'});
  assert.throws(()=>normalizeCohort({mode:'all',emails:['member@example.invalid']}),{code:'COHORT_IDS_INVALID'});
});

test('initial review age is explicit, hash-bound and limited to the verified period',async()=>{
  const config=exampleConfig({now:START});
  assert.equal(approvalWindowMs(config),15*60_000);
  assert.equal(approvalWindowMs({...config,initialReviewMaxAgeMinutes:120}),120*60_000);
  for(const value of [0,-1,1.5,32*DAY/60000])assert.throws(()=>validateConfig({...config,initialReviewMaxAgeMinutes:value},START),{code:'INITIAL_REVIEW_WINDOW_INVALID'});
  const api=apiFor(config),captured=await captureEnrollment({config,api,now:START});
  assert.throws(()=>validateEnrollment({...config,initialReviewMaxAgeMinutes:120},captured.enrollment,START),{code:'ENROLLMENT_POLICY_MISMATCH'});
});

test('per-member policy calculation does not revisit a large selector list',async()=>{
  const config=exampleConfig({now:START}),api=apiFor(config);
  const before=await api.readSnapshot('synthetic-user-a');
  Object.defineProperty(config,'cohort',{get(){throw new Error('SELECTORS_REVISITED');}});
  assert.equal(planTarget(config,before,START).amount,'67');
});
