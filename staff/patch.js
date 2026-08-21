(()=>{
  function ensureTeamAdd(){
    const head=document.querySelector('#sec-team .section-head');
    if(!head||document.getElementById('addStaffPwa'))return;
    const b=document.createElement('button');b.id='addStaffPwa';b.className='btn sm';b.textContent='+ Сотрудник';b.onclick=()=>{
      if(!state?.user?.isOwner)return toast('Доступ владельца','warn');
      modal(`<h3>Добавить сотрудника</h3>
        <div class="field"><label>Имя и фамилия</label><input id="aName"></div>
        <div class="field"><label>Роль / должность</label><input id="aRole" value="Staff"></div>
        <div class="field"><label>Email</label><input id="aEmail" type="email"></div>
        <div class="field"><label>Телефон</label><input id="aPhone" type="tel"></div>
        <div class="field"><label>Часы по договору / нед.</label><input id="aHours" inputmode="decimal"></div>
        <div class="footer-actions"><button class="btn alt" onclick="closeModal()">Отмена</button><button class="btn" onclick="saveNewStaff()">Сохранить</button></div>`);
    };
    head.appendChild(b);
  }
  window.saveNewStaff=async function(){
    if(!navigator.onLine)return toast('Добавление сотрудника требует интернет','warn');
    const name=document.getElementById('aName')?.value.trim(), role=document.getElementById('aRole')?.value.trim()||'Staff';
    if(!name)return toast('Введите имя','warn');
    try{
      const r=await rpc('addStaffMember',[state.token,{fullName:name,jobRole:role,email:document.getElementById('aEmail')?.value.trim()||'',phone:document.getElementById('aPhone')?.value.trim()||'',contractHoursWeek:document.getElementById('aHours')?.value||'',language:'RU'},ctx()]);
      closeModal();
      await syncAll(true);
      modal(`<h3>Сотрудник создан</h3><p><b>${esc(r.fullName||name)}</b></p><div class="field"><label>Одноразовый PIN — сохраните сейчас</label><input readonly value="${esc(r.pin||'')}"></div><div class="footer-actions"><button class="btn" onclick="closeModal()">Готово</button></div>`);
    }catch(e){toast(e.message,'error')}
  };

  function financeLookup(button){
    const details=button.closest('details.person'); if(!details)return null;
    const people=[...document.querySelectorAll('#financeBody > details.person')];
    const pi=people.indexOf(details); if(pi<0)return null;
    const rows=[...details.querySelectorAll('.exception-row')];
    const ei=rows.indexOf(button.closest('.exception-row')); if(ei<0)return null;
    const p=state.finance?.people?.[pi], x=p?.exceptions?.[ei];
    return p&&x?{p,x}:null;
  }
  document.addEventListener('click',e=>{
    const b=e.target.closest?.('.exception-row button');
    if(!b||String(b.textContent||'').trim()!=='Проверить')return;
    e.preventDefault();e.stopImmediatePropagation();
    const o=financeLookup(b); if(!o)return toast('Не удалось открыть проверку','error');
    const {p,x}=o; window.__aumaraReview={p,x};
    const suggested=Number(x.correctedHours??x.hours??x.actualHours??x.plannedHours??0)||0;
    modal(`<h3>Проверка · ${esc(p.name)}</h3>
      <div class="small muted">${esc(x.label||x.code||'Требует проверки')}</div>
      <div class="small" style="margin:8px 0">${esc(x.detail||'')}</div>
      <div class="field"><label>Верные часы</label><input id="mHours2" inputmode="decimal" value="${suggested}"></div>
      <div class="field"><label><input id="mChecked2" type="checkbox" checked> Проверено</label></div>
      <div class="field"><label>Комментарий</label><textarea id="mReviewNote2"></textarea></div>
      <div class="footer-actions"><button class="btn alt" onclick="closeModal()">Отмена</button><button class="btn" onclick="saveReview2()">Сохранить и пересчитать</button></div>`);
  },true);
  window.saveReview2=async function(){
    if(!navigator.onLine)return toast('Проверка требует интернет','warn');
    const o=window.__aumaraReview;if(!o)return;
    const {p,x}=o, per=financePeriod(), correctedHours=Number(document.getElementById('mHours2')?.value||0), checked=!!document.getElementById('mChecked2')?.checked;
    try{
      await rpc('v18SaveAttendanceReview',[state.token,{staffId:p.staffId,fromDate:per.fromDate,toDate:per.toDate,code:x.code||'REVIEW_REQUIRED',workLogId:x.workLogId||'',shiftId:x.shiftId||'',decision:checked?'CONFIRMED_OK':'DISCREPANCY',note:document.getElementById('mReviewNote2')?.value||'',correctedHours,includeInPayroll:checked,evidence:{correctedHours,source:'AUMARA_PWA_2.1'}},ctx()]);
      closeModal();window.__aumaraReview=null;await loadFinance();toast('Проверено и пересчитано');
    }catch(e){toast(e.message,'error')}
  };
  const obs=new MutationObserver(()=>ensureTeamAdd());obs.observe(document.documentElement,{childList:true,subtree:true});
  addEventListener('DOMContentLoaded',ensureTeamAdd);
})();