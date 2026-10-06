export function runTests(api) {
  const a = {id:'test-alpha',name:'<Alpha>'}, b = {id:'test-beta',name:'Beta'};
  const initial = api.initialState, before = JSON.stringify(initial);
  const first = api.reduce(initial,{type:'saveWish',text:'  A moonlit library  '},a);
  const second = api.reduce(first,{type:'saveWish',text:'A quiet workshop'},b);
  const updated = api.reduce(second,{type:'saveWish',text:'<a little garden>'},a);
  const records = updated.extras.wishGarden;
  let rejects = 0;
  for (const action of [{type:'saveWish',text:' '},{type:'saveWish',text:'x'.repeat(181)},{type:'saveWish',text:4},{type:'unknown'},{type:'saveWish',text:'Override',actorId:b.id}]) {
    try { api.reduce(updated,action,a); } catch { rejects++; }
  }
  const liveHtml = api.render(initial,a), html = api.render(updated,a);
  return [
    {name:'First wish is trimmed and stored for the visitor',ok:first.extras.wishGarden['visitor:test-alpha'].text === 'A moonlit library'},
    {name:'Updating replaces only your own wish',ok:records['visitor:test-alpha'].text === '<a little garden>' && Object.keys(records).length === Object.keys(second.extras.wishGarden).length},
    {name:'Another visitor remains untouched',ok:JSON.stringify(records['visitor:test-beta']) === JSON.stringify(second.extras.wishGarden['visitor:test-beta'])},
    {name:'Invalid inputs and spoofed ownership are rejected',ok:rejects === 5},
    {name:'Projects, contributions, and unrelated extras survive',ok:JSON.stringify(updated.projects) === JSON.stringify(initial.projects) && JSON.stringify(updated.contributions) === JSON.stringify(initial.contributions) && Object.keys(initial.extras).filter(k=>k !== 'wishGarden').every(k=>JSON.stringify(updated.extras[k]) === JSON.stringify(initial.extras[k]))},
    {name:'Current live state renders without mutation',ok:liveHtml.includes('The wish garden') && liveHtml.includes('name="text"') && JSON.stringify(initial) === before},
    {name:'All saved wishes render with escaped user content',ok:html.includes('&lt;a little garden&gt;') && !html.includes('<a little garden>') && html.includes('&lt;Alpha&gt;') && html.includes('A quiet workshop')}
  ];
}
