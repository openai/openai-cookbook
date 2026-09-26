import test from 'node:test';
import assert from 'node:assert/strict';
import { mkdtemp, readFile, writeFile, mkdir, rm, stat, access } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { execFile } from 'node:child_process';
import { promisify } from 'node:util';
import { fileURLToPath } from 'node:url';
import { FileStore } from '../src/file-store.mjs';
import { renderLocal } from '../src/local-templates.mjs';

const exec=promisify(execFile);
const localOnly={skip:process.platform==='win32'?'Live local storage and schedulers require macOS or Linux':false};
async function temporary(t){const dir=await mkdtemp(join(tmpdir(),'usage-limits-test-'));t.after(()=>rm(dir,{recursive:true,force:true}));return dir;}
test('fsynced journal is authoritative across process restart and state-cache corruption',localOnly,async t=>{
  const dir=await temporary(t),store=new FileStore(dir),key='synthetic:person';
  await store.withLock(key,()=>store.putState(key,{pending:{amount:'20'}}));
  await writeFile(store.paths(key).state,'broken cache');
  assert.equal((await new FileStore(dir).getState(key)).pending.amount,'20');
  assert.equal((await stat(store.paths(key).journal)).mode&0o077,0);
});
test('active and crash-left local locks cannot be stolen',localOnly,async t=>{
  const dir=await temporary(t),store=new FileStore(dir),key='synthetic:person';
  await store.withLock(key,()=>assert.rejects(new FileStore(dir).withLock(key,async()=>{}),{code:'LOCAL_LOCK_HELD_RECONCILE_BEFORE_REMOVAL'}));
  await mkdir(store.paths(key).lock,{mode:0o700});
  await assert.rejects(store.withLock(key,async()=>{}),{code:'LOCAL_LOCK_HELD_RECONCILE_BEFORE_REMOVAL'});
});
test('period transition retains history across restart and rejects a stale prior state',localOnly,async t=>{
  const directory=await temporary(t),store=new FileStore(directory),key='synthetic:person';
  const previous={enrollmentHash:'old',original:{settings:{override:null}},lastSlot:29};
  const next={enrollmentHash:'new',original:previous.original,pending:{amount:'500'}};
  await store.withLock(key,async()=>{
    await store.putState(key,previous);
    await store.transitionState(key,{previous,next});
    await assert.rejects(store.transitionState(key,{previous,next}),{code:'RENEWAL_PRIOR_STATE_CHANGED'});
  });
  const reopened=new FileStore(directory);
  assert.deepEqual(await reopened.getState(key),next);
  assert.deepEqual((await reopened.entries(key)).filter(entry=>entry.kind==='state').map(entry=>entry.value),[previous,next]);
});
test('partial journal blocks mutation instead of discarding crash evidence',localOnly,async t=>{
  const dir=await temporary(t),store=new FileStore(dir),key='synthetic:person';
  await writeFile(store.paths(key).journal,'{"partial":',{mode:0o600});
  await assert.rejects(store.withLock(key,()=>store.putState(key,{})),{code:'LOCAL_JOURNAL_INCOMPLETE_REVIEW_REQUIRED'});
});
test('local templates use escaped paths and contain preview only, no installation',localOnly,async t=>{
  const dir=join(await temporary(t),"folder's space");
  const files=await renderLocal({directory:dir,nodePath:process.execPath,synthetic:true});
  assert.equal(files.length,4);
  const shell=await readFile(join(dir,'run-preview.sh'),'utf8');assert.ok(!shell.includes('--apply'));assert.ok(shell.includes('--synthetic'));
  await exec('/bin/sh',['-n',join(dir,'run-preview.sh')]);
  if(process.platform==='darwin')await exec('/usr/bin/plutil',['-lint',join(dir,'launchd.plist.disabled')]);
  await assert.rejects(renderLocal({directory:dir,nodePath:process.execPath}),{code:'EEXIST'});
});
test('exact CLI offline path captures reviews previews applies replays inspects and restores',localOnly,async t=>{
  const dir=await temporary(t);
  const cli=fileURLToPath(new URL('../src/cli.mjs',import.meta.url));
  const run=async args=>JSON.parse((await exec(process.execPath,[cli,...args],{env:{...process.env,CHATGPT_ADMIN_API_KEY:''}})).stdout);
  await run(['init','--dir',dir,'--synthetic','--cohort','all','--interval-hours','168','--allow-initial-reduction']);
  const config=join(dir,'config.json'),enrollment=join(dir,'enrollment.json'),state=join(dir,'state');
  const snapshot=await run(['snapshot','--config',config,'--out',enrollment,'--synthetic']);
  assert.equal(snapshot.members[0].before.cap.amount,'2000');
  assert.equal(snapshot.members[0].plan.amount,'500');
  await run(['approve','--enrollment',enrollment,'--hash',snapshot.hash]);
  const args=['--config',config,'--enrollment',enrollment,'--state',state,'--synthetic'];
  assert.equal((await run(['run',...args])).results[0].status,'preview');
  assert.equal((await run(['run',...args,'--apply'])).results[0].status,'applied');
  assert.equal((await run(['run',...args,'--apply'])).results[0].status,'duplicate_slot');
  assert.equal((await run(['inspect','--state',state])).receipts.length,3);
  assert.equal((await run(['restore',...args])).results[0].status,'restore_preview');
  const restored=await run(['restore',...args,'--apply']);
  assert.equal(restored.results[0].status,'restored');
  assert.equal(restored.results[0].after.cap.amount,'2000');
  await run(['render-local','--dir',dir,'--node',process.execPath,'--synthetic']);
  const preview=JSON.parse((await exec('/bin/sh',[join(dir,'run-preview.sh')])).stdout);assert.equal(preview.results[0].status,'restored_stopped');
});

test('USD CLI setup preserves cents through capture, approval, apply, replay and restore',localOnly,async t=>{
  const dir=await temporary(t);
  const cli=fileURLToPath(new URL('../src/cli.mjs',import.meta.url));
  const run=async args=>JSON.parse((await exec(process.execPath,[cli,...args],{env:{...process.env,CHATGPT_ADMIN_API_KEY:''}})).stdout);
  await run(['init','--dir',dir,'--synthetic','--unit','usd','--cohort','all','--interval-hours','168','--allow-initial-reduction']);
  const configPath=join(dir,'config.json'),enrollment=join(dir,'enrollment.json'),state=join(dir,'state');
  const config=JSON.parse(await readFile(configPath,'utf8'));
  assert.equal(config.unit,'usd');
  assert.equal(config.policy.startCap,'50');
  assert.equal(config.policy.ceiling,'200');
  Object.assign(config.policy,{startCap:'1.01',increment:'0.10',ceiling:'20.55'});
  await writeFile(configPath,JSON.stringify(config),{mode:0o600});
  const snapshot=await run(['snapshot','--config',configPath,'--out',enrollment,'--synthetic']);
  assert.ok(snapshot.members.every(member=>member.before.unit==='usd'&&member.plan.unit==='usd'&&member.plan.amount==='1.01'));
  await run(['approve','--enrollment',enrollment,'--hash',snapshot.hash]);
  const args=['--config',configPath,'--enrollment',enrollment,'--state',state,'--synthetic'];
  const applied=await run(['run',...args,'--apply']);
  assert.ok(applied.results.every(row=>row.after.cap.unit==='usd'&&row.after.cap.amount==='1.01'));
  assert.ok((await run(['run',...args,'--apply'])).results.every(row=>row.status==='duplicate_slot'));
  assert.ok((await run(['restore',...args,'--apply'])).results.every(row=>row.after.unit==='usd'&&row.after.cap.amount==='200'));
});

test('CLI rejects invalid, missing or repeated units before creating config and rejects a later unit override',localOnly,async t=>{
  const dir=await temporary(t);
  const cli=fileURLToPath(new URL('../src/cli.mjs',import.meta.url));
  for(const flags of [['--unit','dollars'],['--unit','USD'],['--unit',''],['--unit'],
    ['--unit','usd','--unit','credit'],['--unit','dollars','--unit','usd']]) {
    const destination=join(dir,`absent-${flags.join('-').replaceAll('/','_')}`);
    await assert.rejects(exec(process.execPath,[cli,'init','--dir',destination,'--synthetic',...flags]),error=>{
      assert.equal(error.code,2);
      assert.match(error.stderr,/UNIT_INVALID|UNIT_OPTION_REPEATED|ERR_PARSE_ARGS_INVALID_OPTION_VALUE/);
      return true;
    });
    await assert.rejects(access(destination),{code:'ENOENT'});
  }
  for(const command of ['snapshot','run','restore']) {
    await assert.rejects(exec(process.execPath,[cli,command,'--config',join(dir,'absent.json'),'--unit','usd']),error=>{
      assert.equal(JSON.parse(error.stderr).code,'CONFIGURATION_OPTIONS_ARE_INIT_ONLY');return true;
    });
  }
});

test('Windows operational guards reject before filesystem access or API calls; CLI help remains available',async t=>{
  const directory=join(await temporary(t),'must-stay-absent');
  const script=`
    import assert from 'node:assert/strict';
    import { access } from 'node:fs/promises';
    import { join } from 'node:path';
    import { FileStore, atomicJson } from ${JSON.stringify(new URL('../src/file-store.mjs',import.meta.url).href)};
    import { renderLocal } from ${JSON.stringify(new URL('../src/local-templates.mjs',import.meta.url).href)};
    import { main } from ${JSON.stringify(new URL('../src/cli.mjs',import.meta.url).href)};
    import { main as renewMain } from ${JSON.stringify(new URL('../aws/renew-period.mjs',import.meta.url).href)};
    Object.defineProperty(process,'platform',{value:'win32'});
    globalThis.fetch=()=>{throw new Error('API_CALL_FORBIDDEN');};
    const directory=${JSON.stringify(directory)};
    assert.ok((await main(['--help'])).commands.includes('run'));
    await assert.rejects(main(['init','--dir',directory,'--synthetic']),
      {code:'MACOS_OR_LINUX_REQUIRED_FOR_PRIVATE_STATE'});
    await assert.rejects(main(['snapshot','--config',join(directory,'config.json'),'--out',join(directory,'enrollment.json')]),
      {code:'MACOS_OR_LINUX_REQUIRED_FOR_PRIVATE_STATE'});
    await assert.rejects(renewMain(['activate','--stack','fictional-stack','--dir',directory]),
      {code:'MACOS_OR_LINUX_REQUIRED_FOR_PRIVATE_STATE'});
    await assert.rejects(import(${JSON.stringify(new URL('../aws/prepare-control.mjs',import.meta.url).href)}),
      {code:'MACOS_OR_LINUX_REQUIRED_FOR_PRIVATE_STATE'});
    await assert.rejects(new FileStore(directory).withLock('fictional:user',()=>assert.fail('callback ran')),
      {code:'LOCAL_STORAGE_REQUIRES_MACOS_OR_LINUX'});
    await assert.rejects(atomicJson(join(directory,'state.json'),{fictional:true}),
      {code:'LOCAL_STORAGE_REQUIRES_MACOS_OR_LINUX'});
    await assert.rejects(renderLocal({directory,nodePath:process.execPath}),
      {code:'LOCAL_SCHEDULER_REQUIRES_MACOS_OR_LINUX'});
    await assert.rejects(access(directory),{code:'ENOENT'});
  `;
  await exec(process.execPath,['--input-type=module','--eval',script]);
});
