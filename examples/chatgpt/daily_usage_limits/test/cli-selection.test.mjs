import test from 'node:test';
import assert from 'node:assert/strict';
import { mkdtemp, readFile, rm, access } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { main } from '../src/cli.mjs';

const localOnly={skip:process.platform==='win32'?'Saved enrollment CLI requires macOS or Linux':false};
async function temporary(t) {
  const directory=await mkdtemp(join(tmpdir(),'usage-selector-test-'));
  t.after(()=>rm(directory,{recursive:true,force:true}));
  return directory;
}

test('CLI selector flags capture and approve one canonical union without API access',localOnly,async t=>{
  const directory=await temporary(t);
  await main(['init','--dir',directory,'--synthetic','--workspace-id','synthetic-workspace',
    '--cohort','selected','--user-id','synthetic-user-b','--email',' SYNTHETIC-USER-C@EXAMPLE.INVALID ',
    '--group-id','synthetic-group-a','--max-members','none','--concurrency','3','--capture-concurrency','2',
    '--initial-review-max-age-minutes','60','--api-max-pages','2000','--api-max-rows','200000',
    '--interval-hours','168','--allow-initial-reduction']);
  const configPath=join(directory,'config.json'),enrollmentPath=join(directory,'enrollment.json');
  const config=JSON.parse(await readFile(configPath,'utf8'));
  assert.deepEqual(config.cohort,{mode:'selected',userIds:['synthetic-user-b'],emails:['synthetic-user-c@example.invalid'],groupIds:['synthetic-group-a']});
  assert.equal(config.maxMembers,null);
  assert.equal(config.captureConcurrency,2);
  assert.equal(config.initialReviewMaxAgeMinutes,60);
  assert.deepEqual(config.apiLimits,{maxPages:2000,maxRows:200000});
  const captured=await main(['snapshot','--config',configPath,'--out',enrollmentPath,'--synthetic']);
  assert.deepEqual(captured.members.map(member=>member.userId),['synthetic-user-a','synthetic-user-b','synthetic-user-c']);
  await main(['approve','--enrollment',enrollmentPath,'--hash',captured.hash]);
  const enrolled=JSON.parse(await readFile(enrollmentPath,'utf8'));
  assert.equal(enrolled.approval.hash,captured.hash);
  assert.equal(enrolled.selection.emailBindings[0].userId,'synthetic-user-c');
});

test('CLI rejects conflicting or invalid selectors and limits before writing configuration',localOnly,async t=>{
  const directory=await temporary(t);
  for(const extra of [['--cohort','all','--email','person@example.invalid'],['--email','invalid'],
    ['--max-members','0'],['--capture-concurrency','1.5'],['--api-max-pages','-2']]) {
    const target=join(directory,'must-stay-absent');
    await assert.rejects(main(['init','--dir',target,'--synthetic',...extra]));
    await assert.rejects(access(target),{code:'ENOENT'});
  }
  await assert.rejects(main(['snapshot','--email','person@example.invalid']),{code:'CONFIGURATION_OPTIONS_ARE_INIT_ONLY'});
});
