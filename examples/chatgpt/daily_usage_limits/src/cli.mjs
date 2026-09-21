import { parseArgs } from 'node:util';
import { readFile, writeFile, mkdir, readdir } from 'node:fs/promises';
import { dirname, resolve, join } from 'node:path';
import { fileURLToPath } from 'node:url';
import { createAdminApi } from './admin-api.mjs';
import { exampleConfig, createSyntheticApi } from './synthetic.mjs';
import { captureEnrollment, approveEnrollment, enrollmentHash } from './enrollment.mjs';
import { execute } from './controller.mjs';
import { FileStore, atomicJson } from './file-store.mjs';
import { renderLocal } from './local-templates.mjs';
import { requireThat, validateConfig, approvalWindowMs } from './policy.mjs';
import { normalizeCohort, resolveCohort } from './selection.mjs';

async function json(path) {requireThat(path, 'FILE_ARGUMENT_REQUIRED');return JSON.parse(await readFile(path,'utf8'));}
async function createPrivate(path, value) {
  await mkdir(dirname(resolve(path)),{recursive:true,mode:0o700});
  await writeFile(path,JSON.stringify(value,null,2)+'\n',{flag:'wx',mode:0o600});
}
export async function main(args = process.argv.slice(2)) {
  const {values:v,positionals} = parseArgs({args,allowPositionals:true,strict:true,options:{
    dir:{type:'string'},config:{type:'string'},enrollment:{type:'string'},out:{type:'string'},hash:{type:'string'},state:{type:'string'},
    pattern:{type:'string',default:'fixed_release'},cohort:{type:'string',default:'selected'},unit:{type:'string',default:'credit'},
    'interval-hours':{type:'string',default:'24'},'interval-minutes':{type:'string',default:'60'},node:{type:'string'},
    'credential-provider':{type:'string'},'keychain-service':{type:'string'},'keychain-account':{type:'string'},'encrypted-credential':{type:'string'},
    synthetic:{type:'boolean',default:false},apply:{type:'boolean',default:false},help:{type:'boolean',default:false},
    'allow-initial-reduction':{type:'boolean',default:false},
    'workspace-id':{type:'string'},'user-id':{type:'string',multiple:true},email:{type:'string',multiple:true},'group-id':{type:'string',multiple:true},
    'max-members':{type:'string'},concurrency:{type:'string'},'capture-concurrency':{type:'string'},
    'initial-review-max-age-minutes':{type:'string'},'api-max-pages':{type:'string'},'api-max-rows':{type:'string'},
  }});
  const command = positionals[0];
  requireThat(positionals.length <= 1, 'UNEXPECTED_ARGUMENT');
  requireThat(!v['allow-initial-reduction'] || command==='init', 'INITIAL_REDUCTION_OPTION_IS_INIT_ONLY');
  const initOptions=['workspace-id','user-id','email','group-id','max-members','concurrency','capture-concurrency',
    'initial-review-max-age-minutes','api-max-pages','api-max-rows'];
  requireThat(command==='init' || initOptions.every(key=>v[key]===undefined), 'CONFIGURATION_OPTIONS_ARE_INIT_ONLY');
  if (v.help || !command) return {commands:['init','snapshot','approve','run','restore','resume-auth','cancel-initial','inspect','render-local'],
    help:'See README.md. --synthetic never contacts OpenAI. Live mutations require --apply, config.liveWrites=true and a reviewed enrollment hash.'};
  requireThat(process.platform !== 'win32', 'MACOS_OR_LINUX_REQUIRED_FOR_PRIVATE_STATE');
  if (command === 'init') {
    requireThat(v.dir,'DIR_REQUIRED');
    const config = exampleConfig({pattern:v.pattern,cohort:v.cohort,unit:v.unit,intervalHours:Number(v['interval-hours']),synthetic:v.synthetic});
    config.allowInitialReduction=v['allow-initial-reduction'];
    if(v['workspace-id']!==undefined) {
      requireThat(/^[A-Za-z0-9_-]{1,160}$/.test(v['workspace-id']), 'WORKSPACE_REQUIRED');
      requireThat(!v.synthetic || v['workspace-id']==='synthetic-workspace', 'SYNTHETIC_WORKSPACE_REQUIRED');
      config.workspaceId=v['workspace-id'];
    }
    if(v['user-id'] || v.email || v['group-id']) config.cohort={mode:v.cohort,userIds:v['user-id']??[],emails:v.email??[],groupIds:v['group-id']??[]};
    const normalized=normalizeCohort(config.cohort);
    config.cohort={mode:normalized.mode,...normalized.requested};
    const positiveInteger=(value,code)=>{const parsed=Number(value);requireThat(/^\d+$/.test(value)&&Number.isSafeInteger(parsed)&&parsed>0,code);return parsed;};
    if(v['max-members']!==undefined)config.maxMembers=v['max-members']==='none'?null:positiveInteger(v['max-members'],'MAX_MEMBERS_INVALID');
    for(const [flag,key,code] of [['concurrency','concurrency','CONCURRENCY_INVALID'],['capture-concurrency','captureConcurrency','CAPTURE_CONCURRENCY_INVALID'],
      ['initial-review-max-age-minutes','initialReviewMaxAgeMinutes','INITIAL_REVIEW_WINDOW_INVALID']]) {
      if(v[flag]!==undefined)config[key]=positiveInteger(v[flag],code);
    }
    for(const [flag,key] of [['api-max-pages','maxPages'],['api-max-rows','maxRows']]) {
      if(v[flag]!==undefined)config.apiLimits={...config.apiLimits,[key]:positiveInteger(v[flag],'API_LIMITS_INVALID')};
    }
    approvalWindowMs(config);
    await createPrivate(join(v.dir,'config.json'),config);
    return {created:resolve(v.dir,'config.json'),action:v.synthetic?'Run snapshot --synthetic.':'Review workspace and member selectors, policy amounts, and actual current period/counter scope in Admin Console. Fill evidence and counterScopeConfirmed before snapshot.'};
  }
  if (command === 'approve') {
    const enrollment = await json(v.enrollment);
    requireThat(v.hash,'REVIEW_HASH_REQUIRED');
    const approved = approveEnrollment(enrollment,v.hash);
    await atomicJson(resolve(v.enrollment),approved);
    return {approvedHash:approved.approval.hash,action:'Review run preview; initial application must remain within the configured review age from capture start and the same policy slot.'};
  }
  if (command === 'render-local') {
    requireThat(v.dir && v.node,'DIR_AND_NODE_REQUIRED');
    return {created:await renderLocal({directory:v.dir,nodePath:v.node,intervalMinutes:Number(v['interval-minutes']),synthetic:v.synthetic,
      credentialProvider:v['credential-provider'],keychainService:v['keychain-service'],keychainAccount:v['keychain-account'],encryptedCredential:v['encrypted-credential']}),installed:false,writes:false};
  }
  if (command === 'inspect') {
    requireThat(v.state,'STATE_REQUIRED');
    const directory = resolve(v.state);
    const names = (await readdir(directory)).filter(name=>name.endsWith('.latest-receipt.json'));
    return {receipts:await Promise.all(names.map(name=>json(join(directory,name))))};
  }
  requireThat(['snapshot','run','restore','resume-auth','cancel-initial'].includes(command),'UNKNOWN_COMMAND');
  if(['resume-auth','cancel-initial'].includes(command))requireThat(!v.apply,'RECOVERY_IS_READ_ONLY');
  const config = await json(v.config);
  validateConfig(config,new Date().toISOString());
  const enrollment = command === 'snapshot' ? null : await json(v.enrollment);
  const ids = enrollment ? enrollment.members.map(member=>member.userId) : [];
  let api;
  if (v.synthetic) {
    // A separate fake service file survives separate CLI invocations. It is never an API credential.
    const fakePath = join(dirname(resolve(v.config)),'synthetic-service.json');
    let saved;
    try {saved=await json(fakePath);} catch(error) {if(error.code!=='ENOENT')throw error;}
    api = createSyntheticApi({config,saved,persist:users=>atomicJson(fakePath,users)});
    if (!saved) await createPrivate(fakePath,api.users);
  } else {
    requireThat(process.env.CHATGPT_ADMIN_API_KEY,'CHATGPT_ADMIN_API_KEY_REQUIRED');
    // Empty allowlist is used only during all-members capture; re-create the adapter
    // with the complete explicit roster before reading per-user cap settings.
    const make = userIds => createAdminApi({apiKey:process.env.CHATGPT_ADMIN_API_KEY,workspaceId:config.workspaceId,userIds,
      allowWrites:v.apply && config.liveWrites===true,maxPages:config.apiLimits?.maxPages,maxRows:config.apiLimits?.maxRows});
    api=make(ids);
    if(command==='snapshot') api=make((await resolveCohort({config,api})).userIds);
  }
  if(command==='snapshot') {
    requireThat(v.out,'OUT_REQUIRED');
    const captured = await captureEnrollment({config,api});
    await createPrivate(v.out,captured.enrollment);
    return {path:resolve(v.out),hash:captured.hash,members:captured.enrollment.members,
      action:'Review every before value/source, usage, target, unit and ceiling. Approve this exact hash only if correct.'};
  }
  requireThat(v.state,'STATE_REQUIRED');
  const result = await execute({config,enrollment,api,store:new FileStore(v.state),apply:v.apply,restore:command==='restore',resumeAuth:command==='resume-auth',cancelInitial:command==='cancel-initial'});
  if(!result.ok)process.exitCode=2;
  return result;
}
if (process.argv[1] && resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  main().then(result=>console.log(JSON.stringify(result,null,2))).catch(error=>{
    console.error(JSON.stringify({ok:false,code:error.code??'COMMAND_FAILED',action:'See README troubleshooting. No credentials or API response bodies are printed.'}));process.exitCode=2;
  });
}
