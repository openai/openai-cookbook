(()=>{
  const API_MARKER='cguutkghsnhmwzghkmnc.supabase.co/functions/v1/aumara-staff-api';
  const BOOT_TIMEOUT_MS=12000;
  const DEFAULT_TIMEOUT_MS=25000;
  const nativeFetch=window.fetch.bind(window);

  window.fetch=function(input,init={}){
    const url=typeof input==='string'?input:(input&&input.url)||'';
    if(!url.includes(API_MARKER)||init.signal)return nativeFetch(input,init);
    let timeout=DEFAULT_TIMEOUT_MS;
    try{
      const payload=typeof init.body==='string'?JSON.parse(init.body):null;
      if(payload&&['getLoginOptions','resumeDeviceSession'].includes(payload.fn))timeout=BOOT_TIMEOUT_MS;
    }catch{}
    const controller=new AbortController();
    const timer=setTimeout(()=>controller.abort(),timeout);
    return nativeFetch(input,{...init,signal:controller.signal}).finally(()=>clearTimeout(timer));
  };

  const baseCtx=ctx;
  ctx=function(){return {...baseCtx(),pwaVersion:'2.3.1'}};

  const baseRenderAll=renderAll;
  renderAll=function(){
    baseRenderAll();
    const version=document.querySelector('#version');
    if(version)version.textContent='PWA 2.3.1';
  };

  function hydrateCachedState(){
    const cachedUser=get(LS.user);
    if(!cachedUser)return false;
    state.user=cachedUser;
    state.dashboard=loadSnapshot(LS.dashboard);
    state.team=loadSnapshot(LS.team);
    state.finance=loadSnapshot(LS.finance);
    state.tasks=loadSnapshot(LS.tasks);
    setAuthed(true);
    return true;
  }

  addEventListener('DOMContentLoaded',()=>{
    hydrateCachedState();
    const version=document.querySelector('#version');
    if(version)version.textContent='PWA 2.3.1';
  });
})();
