(()=>{
  if(!window.__aumaraNativeMutationObserver)return;
  window.MutationObserver=window.__aumaraNativeMutationObserver;
  delete window.__aumaraNativeMutationObserver;
})();
