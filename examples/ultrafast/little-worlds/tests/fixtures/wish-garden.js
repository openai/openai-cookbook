export const meta = { title: "A tiny wish garden", subtitle: "One wish each. Room to grow.", accent: "#d6ee96" };

function escape(value) {
  return String(value == null ? '' : value).replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
}
function wishes(state) { return (state.extras && state.extras.wishGarden) || {}; }
function key(id) { return 'visitor:' + id; }

export function render(state, actor) {
  const records = wishes(state);
  const own = actor && records[key(actor.id)];
  const entries = Object.values(records);
  const items = entries.map(w => '<li><p>' + escape(w.text) + '</p><span>' + escape(w.name) + '</span></li>').join('');
  return `<style>
  .garden{color:#23251f;background:transparent;font:inherit;margin-top:20px}
  .garden-grid{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:20px}
  .garden section{min-width:0}.garden h2{font-size:15px;font-weight:600;margin:0 0 12px}
  .garden p{margin:0 0 10px;line-height:1.5}.garden label{display:block;font-size:13px;margin-bottom:8px}
  .garden textarea{box-sizing:border-box;width:100%;min-height:96px;resize:vertical;border:1px solid #b7bcae;border-radius:7px;background:#f5f2e9;color:#23251f;font:inherit;padding:9px}
  .garden button{font:inherit;font-size:13px;border:0;border-radius:6px;padding:8px 12px;background:#d6ee96;color:#23251f;cursor:pointer;margin-top:8px;white-space:normal}
  .garden button:hover{background:#c8e581}.garden button:focus-visible,.garden textarea:focus-visible{outline:2px solid #23251f;outline-offset:3px}
  .garden ul{list-style:none;padding:0;margin:0}.garden li{padding:0 0 12px;margin:0 0 12px;border-bottom:1px solid #dcded2}
  .garden li p{white-space:pre-wrap;overflow-wrap:anywhere;font-size:14px}.garden span,.garden .quiet{color:#727469;font-size:12px;overflow-wrap:anywhere}
  .garden .status{font-size:12px;color:#727469;margin-top:14px}
  @media(max-width:600px){.garden-grid{gap:10px}.garden h2{font-size:13px}.garden label,.garden li p,.garden textarea{font-size:12px}.garden button{font-size:12px;padding:7px 8px}}
  @media(prefers-reduced-motion:reduce){.garden *{transition:none;animation:none}}
  </style><div class="garden"><div class="garden-grid">
  <section aria-label="Leave a wish"><h2>${own ? 'Tend your wish' : 'Plant a wish'}</h2><form data-action='{"type":"saveWish"}'><label for="garden-wish">What should we make next?</label><textarea id="garden-wish" name="text" maxlength="180" required aria-label="Your wish, up to 180 characters">${escape(own ? own.text : '')}</textarea><button type="submit" aria-label="${own ? 'Update your wish' : 'Save your wish'}">${own ? 'Update wish' : 'Save wish'}</button></form></section>
  <section aria-label="Your saved wish"><h2>Your little seed</h2>${own ? '<p style="white-space:pre-wrap;overflow-wrap:anywhere">' + escape(own.text) + '</p><p class="quiet">You can change it anytime.</p>' : '<p class="quiet">One short wish, up to 180 characters.</p>'}</section>
  <section aria-label="All saved wishes"><h2>The wish garden</h2>${items ? '<ul>' + items + '</ul>' : '<p class="quiet">Be the first to plant a wish.</p>'}</section>
  </div><p class="status">${entries.length} ${entries.length === 1 ? 'wish' : 'wishes'} planted · ${own ? 'Your wish is saved.' : 'Yours is welcome.'}</p></div>`;
}

export function reduce(state, action, actor) {
  if (!actor || typeof actor.id !== 'string' || !actor.id.trim()) throw new Error('A visitor is required.');
  if (!action || action.type !== 'saveWish' || Object.keys(action).some(k => k !== 'type' && k !== 'text')) throw new Error('Unknown action or input.');
  if (typeof action.text !== 'string') throw new Error('Write a short wish.');
  const text = action.text.trim();
  if (!text || text.length > 180) throw new Error('Use 1–180 characters.');
  const name = typeof actor.name === 'string' && actor.name.trim() ? actor.name.trim().slice(0, 60) : 'Visitor';
  return { ...state, extras: { ...state.extras, wishGarden: { ...wishes(state), [key(actor.id)]: { actorId: actor.id, name, text } } } };
}
