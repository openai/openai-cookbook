export function runTests(api) {
  const a={id:'painting-check-a',name:'A'},b={id:'painting-check-b',name:'B'},out=[];
  const check=(name,ok)=>out.push({name,ok:!!ok});
  const config=api.meta.agent.actions[0].parameters.properties;
  const columns=config.columns.minimum,rows=config.rows.minimum,total=columns*rows;
  const paint=cells=>({type:'paint_pixels',columns,rows,cells});
  const rejects=(state,action)=>{try{api.reduce(state,action,a);return false;}catch{return true;}};
  // The host separately verifies both current views and publication preservation.
  // Exercise mutation semantics on a bounded fixture rather than copying a full
  // high-resolution public painting for every independent assertion.
  const initial={projects:[],contributions:[],extras:{
    canvas:{'painting-existing':{actorId:'painting-existing',color:1,marks:{49:[1,1]}}},
    notes:{preserved:{actorId:'painting-existing',text:'Keep this note'}}
  }},before=JSON.stringify(initial),liveBefore=JSON.stringify(api.initialState);
  let state=api.reduce(initial,{type:'select_color',color:2},a);
  state=api.reduce(state,paint([{cell:0,color:2},{cell:total-1,color:4}]),a);
  const pixels=html=>html.match(/data-paint-pixels="([^"]*)"/)[1];
  const html=api.render(state,a),first=pixels(html);
  check('Current dimensions drive rendering and actions',first.length===total&&first[0]==='2'&&first[total-1]==='4'&&config.cells.items.properties.cell.maximum===total-1);
  check('One compact native painting surface',(html.match(/<canvas /g)||[]).length===1&&!html.includes('data-paint-cell=')&&html.length<180000&&html.includes('data-paint-grid='));
  const overlapped=api.reduce(state,paint([{cell:0,color:7}]),b);
  const cleared=api.reduce(overlapped,{type:'clear_marks'},b);
  check('White paint overlays and clearing reveals other artwork',pixels(api.render(overlapped,b))[0]==='7'&&pixels(api.render(cleared,b))[0]==='2');
  check('Only the acting layer changes',JSON.stringify(cleared.extras.canvas[a.id])===JSON.stringify(state.extras.canvas[a.id])&&Object.entries(initial.extras.canvas||{}).filter(([id])=>id!==a.id&&id!==b.id).every(([id,record])=>JSON.stringify(cleared.extras.canvas[id])===JSON.stringify(record)));
  check('Unrelated data remains intact',JSON.stringify(initial.projects)===JSON.stringify(cleared.projects)&&JSON.stringify(initial.contributions)===JSON.stringify(cleared.contributions)&&Object.keys(initial.extras).filter(key=>key!=='canvas').every(key=>JSON.stringify(initial.extras[key])===JSON.stringify(cleared.extras[key])));
  const snapshot=JSON.stringify(state);
  check('Stale geometry and malformed batches are rejected atomically',rejects(state,{...paint([{cell:0,color:1}]),columns:columns+1})&&rejects(state,{...paint([{cell:0,color:1}]),rows:rows+1})&&rejects(state,paint([{cell:0,color:1},{cell:total,color:1}]))&&rejects(state,paint([]))&&rejects(state,paint([{cell:-1,color:1}]))&&rejects(state,paint([{cell:0,color:8}]))&&JSON.stringify(state)===snapshot);
  check('Unknown actions are rejected',rejects(initial,{type:'global_clear'}));
  const filled=api.reduce(state,{type:'fill_canvas',columns,rows,color:3},a);
  check('A single fill covers the entire canvas without discarding other layers',pixels(api.render(filled,a))==='3'.repeat(total)&&Object.entries(state.extras.canvas).filter(([id])=>id!==a.id).every(([id,record])=>JSON.stringify(filled.extras.canvas[id])===JSON.stringify(record)));
  check('Painting agents can use fills and shapes instead of enumerating large areas',['fill_canvas','paint_shapes','flood_fill'].every(name=>api.meta.agent.actions.some(action=>action.name===name)));
  check('Real AI and manual controls remain available',html.includes('data-service="space-agent"')&&html.includes('data-service-operation="cancel"')&&html.includes('Clear my marks')&&html.includes('Paint with words'));
  check('Input state remains unchanged',JSON.stringify(initial)===before&&JSON.stringify(api.initialState)===liveBefore);
  return out;
}
