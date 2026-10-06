import test from 'node:test';
import assert from 'node:assert/strict';
import { paintingProposal } from '../server/painting/index.mjs';
import { compileModule, renderModule, reduceModule, verifyModule, projectStateForPublication } from '../server/runtime.mjs';

const a={id:'painter-a',name:'A'},b={id:'painter-b',name:'B'};
const initial=()=>({projects:[],contributions:[],extras:{canvas:{
  [a.id]:{actorId:a.id,color:1,marks:{0:[1,1],49:[4,2],1535:[2,3]}},
  [b.id]:{actorId:b.id,color:0,marks:{49:[0,4]}}
},notes:{untouched:{actorId:'other',text:'Keep this unrelated note'}}}});
const paint=(columns,rows,cells)=>({type:'paint_pixels',columns,rows,cells});
const field=html=>html.match(/data-paint-pixels="([^"]*)"/)[1];
const moduleAt=async(columns=48,rows=32)=>{
  const proposal=await paintingProposal({columns,rows});
  return {...proposal,...await compileModule(proposal.source)};
};

test('curated painting verifies and publication leaves all existing state byte-identical',async()=>{
  const proposal=await paintingProposal(),state=initial(),before=JSON.stringify(state);
  const result=await verifyModule(proposal.source,proposal.tests,state,{owner:a,visitor:b});
  assert.equal(result.ok,true,JSON.stringify(result.checks.filter(check=>!check.ok)));
  assert.equal(JSON.stringify(projectStateForPublication(result.meta,state)),before);
  assert.equal(JSON.stringify(state),before);
});

test('legacy pixels retain exact positions and palette on the original canvas',async()=>{
  const module=await moduleAt(),state=initial(),before=JSON.stringify(state);
  const html=await renderModule(module.bundle,state,a),pixels=field(html);
  assert.equal(pixels.length,1536);
  assert.equal(pixels[0],'1');assert.equal(pixels[49],'0');assert.equal(pixels[1535],'2');
  assert.equal(pixels.split('').filter(value=>value!=='.').length,3);
  assert.equal((html.match(/<canvas /g)||[]).length,1);
  assert.equal(html.includes('data-paint-cell='),false);
  assert.equal(JSON.stringify(state),before);
});

test('same actor upgrades only their layer, other layers and unrelated state remain unchanged',async()=>{
  const module=await moduleAt(),state=initial(),before=structuredClone(state);
  const next=await reduceModule(module.bundle,state,paint(48,32,[{cell:50,color:3}]),a);
  assert.equal(next.extras.canvas[a.id].format,2);
  assert.equal(next.extras.canvas[a.id].sequence,5);
  assert.deepEqual(next.extras.canvas[b.id],before.extras.canvas[b.id]);
  assert.deepEqual(next.extras.notes,before.extras.notes);
  assert.deepEqual(state,before);
  const pixels=field(await renderModule(module.bundle,next,a));
  assert.equal(pixels[0],'1');assert.equal(pixels[49],'0');assert.equal(pixels[50],'3');
  assert.equal(pixels[1535],'2');
});

test('repeated resolution increases preserve footprints and newest individual subpixels',async()=>{
  const medium=await moduleAt(96,64),large=await moduleAt(192,128),state=initial();
  const mediumPixels=field(await renderModule(medium.bundle,state,a));
  for(const cell of[0,1,96,97]) assert.equal(mediumPixels[cell],'1');
  for(const cell of[194,195,290,291]) assert.equal(mediumPixels[cell],'0');
  const updated=await reduceModule(medium.bundle,state,paint(96,64,[{cell:195,color:3}]),a);
  assert.deepEqual(updated.extras.canvas[a.id].planes.map(p=>[p.columns,p.rows]),[[48,32],[96,64]]);
  const largePixels=field(await renderModule(large.bundle,updated,a));
  assert.equal(largePixels[4*192+4],'0');
  for(const cell of[4*192+6,4*192+7,5*192+6,5*192+7]) assert.equal(largePixels[cell],'3');
  const final=await reduceModule(large.bundle,updated,paint(192,128,[{cell:4*192+7,color:7}]),b);
  const visible=field(await renderModule(large.bundle,final,b));
  assert.equal(visible[4*192+7],'7');assert.equal(visible[4*192+6],'3');
  const cleared=await reduceModule(large.bundle,final,{type:'clear_marks'},b);
  assert.equal(field(await renderModule(large.bundle,cleared,b))[4*192+7],'3');
  assert.deepEqual(cleared.extras.canvas[a.id],updated.extras.canvas[a.id]);
});

test('stale geometry, out of bounds, invalid colors and oversized batches reject atomically',async()=>{
  const module=await moduleAt(96,64),state=initial(),before=structuredClone(state);
  for(const action of[
    paint(48,32,[{cell:0,color:1}]),paint(96,32,[{cell:0,color:1}]),
    paint(96,64,[{cell:0,color:1},{cell:6144,color:2}]),paint(96,64,[{cell:0,color:8}]),
    paint(96,64,[]),paint(96,64,Array.from({length:121},()=>({cell:0,color:1}))),
    paint(96,64,[{cell:0,color:1,actorId:b.id}])
  ]) await assert.rejects(reduceModule(module.bundle,state,action,a));
  assert.deepEqual(state,before);
  await assert.rejects(paintingProposal({columns:257,rows:64}),/1 to 256/);
});

test('a visitor cannot adopt a record owned by another actor',async()=>{
  const module=await moduleAt(),state=initial();
  state.extras.canvas[a.id].actorId=b.id;
  await assert.rejects(reduceModule(module.bundle,state,paint(48,32,[{cell:0,color:2}]),a),/Not your layer/);
  await assert.rejects(reduceModule(module.bundle,state,{type:'clear_marks'},a),/Not your layer/);
});

function denseState(columns,rows) {
  const chunks={};
  for(let cy=0;cy<Math.ceil(rows/16);cy++) for(let cx=0;cx<Math.ceil(columns/16);cx++) {
    let data='';
    for(let i=0;i<256;i++) {
      const x=cx*16+i%16,y=cy*16+Math.floor(i/16);
      data+=x<columns&&y<rows?`${(x+y)%7}000001`:'.......';
    }
    chunks[cy*Math.ceil(columns/16)+cx]=data;
  }
  return {projects:[],contributions:[],extras:{canvas:{[a.id]:{actorId:a.id,format:2,color:0,sequence:1,planes:[{columns,rows,chunks}]}}}};
}

for(const [columns,rows] of[[96,64],[192,128],[96,96],[192,192],[256,256]]) {
  test(`dense ${columns}×${rows} canvas renders and accepts a new stroke within host limits`,async()=>{
    const module=await moduleAt(columns,rows),state=denseState(columns,rows);
    assert.ok(JSON.stringify(state).length<500000);
    const before=field(await renderModule(module.bundle,state,a));
    assert.equal(before.length,columns*rows);
    assert.equal(before.includes('.'),false);
    assert.equal(before.at(-1),String((columns+rows-2)%7));
    const updated=await reduceModule(module.bundle,state,paint(columns,rows,[{cell:columns*rows-1,color:7}]),a);
    const html=await renderModule(module.bundle,updated,a);
    assert.ok(html.length<180000);assert.equal(field(html).at(-1),'7');
    assert.equal(updated.extras.canvas[a.id].sequence,2);
  });
}

for(const [columns,rows] of[[192,128],[256,256]]) test(`dense ${columns}×${rows} published artwork remains verifiable without changing records`,async()=>{
  const proposal=await paintingProposal({columns,rows}),state=denseState(columns,rows),before=JSON.stringify(state);
  const verified=await verifyModule(proposal.source,proposal.tests,state,{owner:a,visitor:b});
  assert.equal(verified.ok,true,JSON.stringify(verified.checks.filter(check=>!check.ok)));
  assert.equal(JSON.stringify(state),before);
  assert.equal(JSON.stringify(verified.candidateState),before);
});
