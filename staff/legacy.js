(()=>{
  const LC={
    calendar:'aumara.pwa.calendar.v22',
    chatPrefix:'aumara.pwa.chat.v22.',
    audit:'aumara.pwa.audit.v22',
    devices:'aumara.pwa.devices.v22',
    tab:'aumara.pwa.tab.v22'
  };
  const LEGACY_TABS=new Set(['calendar','chat','audit','devices']);
  const baseShowTab=showTab;
  const baseRenderAll=renderAll;
  const baseSyncAll=syncAll;
  let calendarRange={from:addDays(today(),-7),to:addDays(today(),35)};
  let chatChannel='GENERAL';
  let loading={};

  function lget(k){try{const x=localStorage.getItem(k);return x?JSON.parse(x):null}catch{return null}}
  function lput(k,data){try{localStorage.setItem(k,JSON.stringify({savedAt:new Date().toISOString(),data}))}catch{}}
  function ldata(k){return lget(k)?.data||null}
  function fmtDate(v){if(!v)return '';const s=String(v);return s.length>=10?s.slice(0,10):s}
  function fmtDT(v){if(!v)return '';try{return new Date(v).toLocaleString('ru-RU',{timeZone:'Europe/Madrid',day:'2-digit',month:'2-digit',hour:'2-digit',minute:'2-digit'})}catch{return String(v)}}
  function roleAdmin(){const r=String(state.user?.accessRole||'').toUpperCase();return !!state.user?.isOwner||r==='OWNER'||r==='ADMIN'}
  function roleManager(){return !!state.user?.isManager||roleAdmin()}
  function cacheNote(key){const x=lget(key);return x?.savedAt?`срез ${fmtDT(x.savedAt)}`:'нет локального среза'}
  function setBusy(key,on){loading[key]=on;const n=document.querySelector(`[data-load-note="${key}"]`);if(n)n.textContent=on?'обновляю…':''}

  function injectStyles(){
    if(document.getElementById('legacyV22Styles'))return;
    const st=document.createElement('style');st.id='legacyV22Styles';st.textContent=`
      .cal-toolbar,.chat-toolbar{display:flex;gap:8px;flex-wrap:wrap;align-items:end;margin-bottom:12px}
      .cal-day{margin:12px 0 6px;font-size:17px;font-weight:900;color:#234f3f}
      .cal-row{display:grid;grid-template-columns:62px minmax(0,1fr) auto;gap:10px;align-items:center;padding:11px 0;border-bottom:1px solid #eee4d2}
      .cal-row:last-child{border-bottom:0}.cal-time{font-weight:900}.cal-person{font-weight:850}.cal-sub{font-size:12px;color:#707a75;margin-top:3px}
      .chat-channels{display:flex;gap:7px;overflow:auto;padding-bottom:8px;scrollbar-width:none}.chat-channels::-webkit-scrollbar{display:none}
      .chat-channel{white-space:nowrap;border:0;border-radius:999px;padding:8px 11px;background:#ece2d0;color:#315443;font-weight:800}.chat-channel.active{background:#315443;color:#fff}
      .chat-list{display:flex;flex-direction:column;gap:9px;max-height:58vh;overflow:auto;padding:3px}
      .msg{background:#fffdf8;border:1px solid #dfd4bf;border-radius:15px;padding:11px 12px}.msg.mine{background:#e8f2ed;margin-left:9%}.msg-head{display:flex;justify-content:space-between;gap:8px;font-size:11px;color:#707a75;margin-bottom:5px}.msg-text{white-space:pre-wrap;word-break:break-word}.msg-actions{display:flex;justify-content:flex-end;margin-top:7px}
      .chat-compose{position:sticky;bottom:0;background:#f5efe4;padding-top:10px}.chat-compose textarea{min-height:64px}
      .audit-row,.device-row,.request-row{background:#fffdf8;border:1px solid #dfd4bf;border-radius:14px;padding:11px;margin:8px 0}.audit-action{font-weight:900}.audit-meta{font-size:11px;color:#707a75;margin-top:4px}.audit-error{color:#9b3d35;font-size:12px;margin-top:5px}
      .legacy-head-actions{display:flex;gap:7px;align-items:center;flex-wrap:wrap}.legacy-count{font-size:12px;color:#80631c;font-weight:800}
      .request-row b{display:block}.request-actions{display:flex;gap:7px;margin-top:8px;flex-wrap:wrap}
      .device-current{border-color:#2c5b49;box-shadow:0 0 0 2px #2c5b4910}
    `;document.head.appendChild(st);
  }

  function addTab(nav,label,name,before){
    if(nav.querySelector(`[data-tab="${name}"]`))return nav.querySelector(`[data-tab="${name}"]`);
    const b=document.createElement('button');b.className='tab';b.dataset.tab=name;b.innerHTML=label;
    if(before)nav.insertBefore(b,before);else nav.appendChild(b);
    b.onclick=()=>showTab(name);
    return b;
  }
  function addSection(main,name,title,note){
    let s=document.getElementById(`sec-${name}`);if(s)return s;
    s=document.createElement('section');s.id=`sec-${name}`;s.className='section hidden';
    s.innerHTML=`<div class="section-head"><h2>${title}</h2><span class="syncnote" data-load-note="${name}">${note||''}</span></div><div id="${name}Body"></div>`;
    main.appendChild(s);return s;
  }
  function ensureUi(){
    injectStyles();
    const nav=document.querySelector('#app .tabs'),main=document.querySelector('#app .main');if(!nav||!main)return;
    const first=nav.querySelector('.tab');
    addTab(nav,'Календарь','calendar',first);
    addTab(nav,`Чат <span id="chatUnread"></span>`,'chat',first);
    addTab(nav,'Журнал','audit');
    addTab(nav,'Устройства','devices');
    addSection(main,'calendar','Календарь','локальный срез + фон');
    addSection(main,'chat','Чат','каналы команды');
    addSection(main,'audit','Журнал','последние события');
    addSection(main,'devices','Устройства','доверенные входы');
    const auditTab=nav.querySelector('[data-tab="audit"]');if(auditTab)auditTab.classList.toggle('hidden',!roleAdmin());
    const v=document.getElementById('version');if(v)v.textContent='PWA 2.2';
    const unread=Number(state.dashboard?.chat?.unread||0);const u=document.getElementById('chatUnread');if(u)u.textContent=unread?` ${unread}`:'';
  }

  async function routeTab(name){
    ensureUi();
    baseShowTab(name);
    try{localStorage.setItem(LC.tab,name)}catch{}
    if(LEGACY_TABS.has(name))await loadLegacy(name,false);
  }
  showTab=routeTab;
  renderAll=function(){baseRenderAll();ensureUi();const saved=localStorage.getItem(LC.tab);if(saved&&document.getElementById(`sec-${saved}`)&&state.active==='home'){setTimeout(()=>showTab(saved),0)}};
  syncAll=async function(force=false){const r=await baseSyncAll(force);ensureUi();if(LEGACY_TABS.has(state.active))await loadLegacy(state.active,true);return r};

  async function loadLegacy(name,force){
    if(name==='calendar')return loadCalendar(force);
    if(name==='chat')return loadChat(chatChannel,force);
    if(name==='audit')return loadAudit(force);
    if(name==='devices')return loadDevices(force);
  }

  function calendarSnapshot(){
    return ldata(LC.calendar)||{
      fromDate:calendarRange.from,toDate:calendarRange.to,
      teamShifts:state.dashboard?.manager?.teamShifts||state.dashboard?.upcomingShifts||[],
      pendingRequests:state.dashboard?.manager?.pendingRequests||[]
    };
  }
  async function loadCalendar(force=false){
    renderCalendar(calendarSnapshot());
    if(!navigator.onLine||loading.calendar)return;
    const c=ldata(LC.calendar);if(!force&&c&&Date.now()-new Date(lget(LC.calendar).savedAt).getTime()<120000)return;
    if(!(await ensureToken()))return;
    setBusy('calendar',true);
    try{const data=await rpc('getManagerCalendar',[state.token,calendarRange.from,calendarRange.to]);lput(LC.calendar,data);renderCalendar(data)}catch(e){toast(`Календарь: ${e.message}`,'error')}finally{setBusy('calendar',false)}
  }
  function renderCalendar(data){
    const root=document.getElementById('calendarBody');if(!root)return;
    const shifts=(data?.teamShifts||[]).slice().sort((a,b)=>`${a.date}${a.start}`.localeCompare(`${b.date}${b.start}`));
    const requests=data?.pendingRequests||[];
    const by={};shifts.forEach(s=>(by[s.date]||(by[s.date]=[])).push(s));
    const staff=state.dashboard?.manager?.staff||state.team?.people||[];
    const create=roleManager()?'<button class="btn sm" id="newShiftV22">+ Смена</button>':'';
    root.innerHTML=`<div class="cal-toolbar">
      <div class="field grow"><label>С</label><input id="calFrom" type="date" value="${esc(calendarRange.from)}"></div>
      <div class="field grow"><label>По</label><input id="calTo" type="date" value="${esc(calendarRange.to)}"></div>
      <button class="btn sm alt" id="calApply">Показать</button>${create}
    </div>
    <div class="small muted">${cacheNote(LC.calendar)} · ${shifts.length} смен</div>
    <div class="panel" style="padding:14px;margin-top:10px">${Object.keys(by).length?Object.keys(by).map(date=>`<div><div class="cal-day">${esc(date)}</div>${by[date].map(s=>`<div class="cal-row" data-shift-id="${esc(s.id||'')}"><div class="cal-time">${esc(s.start||'')}<br><span class="small muted">${esc(s.end||'')}</span></div><div><div class="cal-person">${esc(s.employee||'')}</div><div class="cal-sub">${esc(s.area||s.role||'')} · ${esc(s.status||'')}</div></div>${roleManager()?`<button class="btn sm outline" data-edit-shift="${esc(s.id||'')}">Изменить</button>`:''}</div>`).join('')}</div>`).join(''):'<div class="empty">Смен в выбранном периоде нет</div>'}</div>
    ${requests.length?`<div class="panel" style="padding:14px;margin-top:12px"><h2>Запросы</h2>${requests.map(r=>`<div class="request-row"><b>${esc(r.employee||'')}</b><div>${esc(r.type||'')} · ${esc(r.requestedChange||'')}</div><div class="small muted">${esc(r.reason||'')} · ${esc(r.urgency||'')}</div>${roleManager()?`<div class="request-actions"><button class="btn sm" data-request="${esc(r.id)}" data-decision="Approved">Одобрить</button><button class="btn sm danger" data-request="${esc(r.id)}" data-decision="Declined">Отклонить</button></div>`:''}</div>`).join('')}</div>`:''}`;
    document.getElementById('calApply').onclick=()=>{calendarRange={from:document.getElementById('calFrom').value,to:document.getElementById('calTo').value};loadCalendar(true)};
    document.getElementById('newShiftV22')?.addEventListener('click',()=>openNewShift(staff));
    root.querySelectorAll('[data-edit-shift]').forEach(b=>b.onclick=()=>openEditShift(shifts.find(s=>s.id===b.dataset.editShift)));
    root.querySelectorAll('[data-request]').forEach(b=>b.onclick=()=>decideReq(b.dataset.request,b.dataset.decision));
  }
  function staffOptions(staff,selected=''){return (staff||[]).map(p=>`<option value="${esc(p.staffId)}" ${p.staffId===selected?'selected':''}>${esc(p.name)} · ${esc(p.role||'')}</option>`).join('')}
  function openNewShift(staff){
    modal(`<h3>Новая смена</h3><div class="field"><label>Дата</label><input id="nsDate" type="date" value="${today()}"></div><div class="field"><label>Сотрудник</label><select id="nsStaff">${staffOptions(staff)}</select></div><div class="field"><label>Роль / зона</label><input id="nsRole" placeholder="Kitchen / Front Desk"></div><div class="row"><div class="field grow"><label>Начало</label><input id="nsStart" type="time" value="09:00"></div><div class="field grow"><label>Конец</label><input id="nsEnd" type="time" value="17:00"></div></div><div class="field"><label>Перерыв, мин</label><input id="nsBreak" inputmode="numeric" value="0"></div><div class="field"><label>Комментарий</label><textarea id="nsNote"></textarea></div><div class="footer-actions"><button class="btn alt" onclick="closeModal()">Отмена</button><button class="btn" id="nsSave">Опубликовать</button></div>`);
    document.getElementById('nsSave').onclick=saveNewShift;
  }
  async function saveNewShift(){
    if(!navigator.onLine)return toast('Создание смены требует интернет','warn');if(!(await ensureToken()))return;
    const payload={dates:[document.getElementById('nsDate').value],employeeStaffIds:[document.getElementById('nsStaff').value],role:document.getElementById('nsRole').value.trim(),area:document.getElementById('nsRole').value.trim(),start:document.getElementById('nsStart').value,end:document.getElementById('nsEnd').value,breakMinutes:Number(document.getElementById('nsBreak').value||0),note:document.getElementById('nsNote').value,publish:true};
    try{await rpc('createShiftsBatch',[state.token,payload,ctx()]);closeModal();await loadCalendar(true);state.dashboard=await rpc('getDashboard',[state.token]);saveSnapshot(LS.dashboard,state.dashboard);toast('Смена опубликована')}catch(e){toast(e.message,'error')}
  }
  function openEditShift(s){if(!s)return;const staff=state.dashboard?.manager?.staff||state.team?.people||[];modal(`<h3>Смена · ${esc(s.employee)}</h3><div class="field"><label>Дата</label><input id="esDate" type="date" value="${esc(s.date||'')}"></div><div class="field"><label>Сотрудник</label><select id="esStaff">${staffOptions(staff,s.employeeStaffId)}</select></div><div class="field"><label>Роль / зона</label><input id="esRole" value="${esc(s.area||s.role||'')}"></div><div class="row"><div class="field grow"><label>Начало</label><input id="esStart" type="time" value="${esc(s.start||'')}"></div><div class="field grow"><label>Конец</label><input id="esEnd" type="time" value="${esc(s.end||'')}"></div></div><div class="field"><label>Перерыв, мин</label><input id="esBreak" value="${Number(s.breakMinutes||0)}"></div><div class="field"><label>Комментарий</label><textarea id="esNote">${esc(s.note||'')}</textarea></div><div class="footer-actions"><button class="btn danger" id="esCancel">Отменить смену</button><button class="btn" id="esSave">Сохранить</button></div>`);document.getElementById('esSave').onclick=()=>saveEditShift(s.id);document.getElementById('esCancel').onclick=()=>cancelShift(s.id)}
  async function saveEditShift(id){if(!navigator.onLine)return toast('Изменение смены требует интернет','warn');try{await rpc('updateShift',[state.token,id,{date:document.getElementById('esDate').value,employeeStaffId:document.getElementById('esStaff').value,role:document.getElementById('esRole').value.trim(),area:document.getElementById('esRole').value.trim(),start:document.getElementById('esStart').value,end:document.getElementById('esEnd').value,breakMinutes:Number(document.getElementById('esBreak').value||0),note:document.getElementById('esNote').value,status:'Published'},ctx()]);closeModal();await loadCalendar(true);toast('Смена обновлена')}catch(e){toast(e.message,'error')}}
  async function cancelShift(id){if(!navigator.onLine)return toast('Отмена смены требует интернет','warn');try{await rpc('setShiftStatus',[state.token,id,'Cancelled',ctx()]);closeModal();await loadCalendar(true);toast('Смена отменена')}catch(e){toast(e.message,'error')}}
  async function decideReq(id,decision){if(!navigator.onLine)return toast('Решение требует интернет','warn');try{await rpc('decideRequest',[state.token,id,decision,'',ctx()]);await loadCalendar(true);toast(decision==='Approved'?'Запрос одобрен':'Запрос отклонён')}catch(e){toast(e.message,'error')}}

  function chatKey(channel){return LC.chatPrefix+channel}
  function defaultChannels(){return state.dashboard?.chat?.channels||[{id:'GENERAL',label:'Общий'}]}
  async function loadChat(channel=chatChannel,force=false){
    chatChannel=channel||'GENERAL';const c=ldata(chatKey(chatChannel));if(c)renderChat(c);else renderChat({channel:chatChannel,channels:defaultChannels(),messages:[]});
    if(!navigator.onLine||loading.chat)return;if(!force&&c&&Date.now()-new Date(lget(chatKey(chatChannel)).savedAt).getTime()<30000)return;if(!(await ensureToken()))return;
    setBusy('chat',true);try{const data=await rpc('getChat',[state.token,chatChannel,{limit:80}]);lput(chatKey(chatChannel),data);renderChat(data)}catch(e){toast(`Чат: ${e.message}`,'error')}finally{setBusy('chat',false)}
  }
  function renderChat(data){
    const root=document.getElementById('chatBody');if(!root)return;const channels=data?.channels||defaultChannels();const msgs=data?.messages||[];
    root.innerHTML=`<div class="chat-channels">${channels.map(c=>`<button class="chat-channel ${c.id===chatChannel?'active':''}" data-chat-channel="${esc(c.id)}">${esc(c.label||c.id)}</button>`).join('')}</div><div class="small muted" style="margin-bottom:8px">${cacheNote(chatKey(chatChannel))}</div><div class="chat-list">${msgs.length?msgs.map(m=>`<div class="msg ${m.senderStaffId===state.user?.staffId?'mine':''}"><div class="msg-head"><b>${esc(m.senderName||'')}</b><span>${esc(fmtDT(m.createdAt))}</span></div><div class="msg-text">${esc(m.text||'')}</div>${roleManager()?`<div class="msg-actions"><button class="btn sm outline" data-task-message="${esc(m.id)}">В работу</button></div>`:''}</div>`).join(''):'<div class="empty">Сообщений пока нет</div>'}</div><div class="chat-compose"><div class="field"><label>Сообщение</label><textarea id="chatText" placeholder="Написать в канал…"></textarea></div><button class="btn" id="chatSend">Отправить</button></div>`;
    root.querySelectorAll('[data-chat-channel]').forEach(b=>b.onclick=()=>loadChat(b.dataset.chatChannel,true));document.getElementById('chatSend').onclick=sendChat;root.querySelectorAll('[data-task-message]').forEach(b=>b.onclick=()=>openTaskFromMessage(msgs.find(m=>m.id===b.dataset.taskMessage)));
    setTimeout(()=>{const l=root.querySelector('.chat-list');if(l)l.scrollTop=l.scrollHeight},0);
  }
  async function sendChat(){const text=document.getElementById('chatText').value.trim();if(!text)return;if(!navigator.onLine)return toast('Отправка сообщения требует интернет','warn');if(!(await ensureToken()))return;try{const data=await rpc('sendChatMessage',[state.token,{channel:chatChannel,text},ctx()]);lput(chatKey(chatChannel),data);renderChat(data);toast('Отправлено')}catch(e){toast(e.message,'error')}}
  function openTaskFromMessage(m){if(!m)return;const team=state.tasks?.team||state.team?.people||[];modal(`<h3>В работу</h3><div class="small muted">Из сообщения ${esc(m.senderName||'')}</div><div class="field"><label>Задача</label><input id="tmTitle" value="${esc((m.text||'').slice(0,180))}"></div><div class="field"><label>Ответственный</label><select id="tmAssignee">${staffOptions(team)}</select></div><div class="row"><div class="field grow"><label>Срок</label><input id="tmDate" type="date" value="${addDays(today(),1)}"></div><div class="field grow"><label>Время</label><input id="tmTime" type="time" value="12:00"></div></div><div class="field"><label>Приоритет</label><select id="tmPriority"><option>NORMAL</option><option>HIGH</option><option>URGENT</option><option>LOW</option></select></div><div class="footer-actions"><button class="btn alt" onclick="closeModal()">Отмена</button><button class="btn" id="tmSave">В работу</button></div>`);document.getElementById('tmSave').onclick=()=>saveTaskFromMessage(m)}
  async function saveTaskFromMessage(m){if(!navigator.onLine)return toast('Создание задачи требует интернет','warn');try{await rpc('v19CreateTaskFromChat',[state.token,{sourceMessageId:m.id,sourceChannel:m.channel,sourceText:m.text,title:document.getElementById('tmTitle').value.trim(),assigneeStaffId:document.getElementById('tmAssignee').value,dueDate:document.getElementById('tmDate').value,dueTime:document.getElementById('tmTime').value,priority:document.getElementById('tmPriority').value},ctx()]);closeModal();state.tasks=await rpc('v19GetTaskBoard',[state.token,{}]);saveSnapshot(LS.tasks,state.tasks);renderTasks();toast('Задача создана')}catch(e){toast(e.message,'error')}}

  async function loadAudit(force=false){
    const c=ldata(LC.audit);if(c)renderAudit(c);else renderAudit(null);
    if(!roleAdmin())return;if(!navigator.onLine||loading.audit)return;if(!force&&c&&Date.now()-new Date(lget(LC.audit).savedAt).getTime()<120000)return;if(!(await ensureToken()))return;
    setBusy('audit',true);try{const data=await rpc('getAuditLog',[state.token,{limit:100}]);lput(LC.audit,data);renderAudit(data)}catch(e){toast(`Журнал: ${e.message}`,'error')}finally{setBusy('audit',false)}
  }
  function renderAudit(data){const root=document.getElementById('auditBody');if(!root)return;if(!roleAdmin()){root.innerHTML='<div class="empty">Журнал доступен владельцу и администратору</div>';return}const rows=data?.entries||[];root.innerHTML=`<div class="small muted">${cacheNote(LC.audit)} · последние ${rows.length}</div>${rows.length?rows.map(x=>`<div class="audit-row"><div class="audit-action">${esc(x.action||'')}</div><div>${esc(x.entityType||'')} ${esc(x.entityId||'')}</div><div class="audit-meta">${esc(fmtDT(x.createdAt))} · ${esc(x.actorName||x.actorStaffId||'')} · ${esc(x.result||'')}</div>${x.errorMessage?`<div class="audit-error">${esc(x.errorMessage)}</div>`:''}</div>`).join(''):'<div class="empty" style="margin-top:10px">Событий нет</div>'}`}

  async function loadDevices(force=false){
    const c=ldata(LC.devices);if(c)renderDevices(c);else renderDevices([]);
    if(!navigator.onLine||loading.devices)return;if(!force&&c&&Date.now()-new Date(lget(LC.devices).savedAt).getTime()<120000)return;if(!(await ensureToken()))return;
    setBusy('devices',true);try{const data=await rpc('listMyDevices',[state.token]);lput(LC.devices,data);renderDevices(data)}catch(e){toast(`Устройства: ${e.message}`,'error')}finally{setBusy('devices',false)}
  }
  function renderDevices(rows){const root=document.getElementById('devicesBody');if(!root)return;const current=get(LS.device);root.innerHTML=`<div class="small muted">${cacheNote(LC.devices)}</div>${(rows||[]).length?(rows||[]).map(d=>`<div class="device-row ${d.deviceId===current?'device-current':''}"><b>${esc(d.label||'Устройство')}</b>${d.deviceId===current?' <span class="badge ok">это устройство</span>':''}<div class="small muted">Последний вход: ${esc(fmtDT(d.lastUsedAt))}</div><div class="small muted">Действует до: ${esc(fmtDT(d.expiresAt))} · Home Screen: ${esc(d.standalone||'')}</div></div>`).join(''):'<div class="empty" style="margin-top:10px">Устройств нет</div>'}<div class="toolbar"><button class="btn danger" id="revokeThis">Отключить это устройство</button></div>`;document.getElementById('revokeThis').onclick=revokeThis}
  async function revokeThis(){if(!navigator.onLine)return toast('Нужен интернет','warn');try{await rpc('revokeCurrentDevice',[state.token,ctx()]);logout()}catch(e){toast(e.message,'error')}}

  addEventListener('online',()=>{if(LEGACY_TABS.has(state.active))loadLegacy(state.active,true)});
  addEventListener('DOMContentLoaded',()=>{ensureUi();const saved=localStorage.getItem(LC.tab);if(saved&&LEGACY_TABS.has(saved))setTimeout(()=>showTab(saved),50)});
})();