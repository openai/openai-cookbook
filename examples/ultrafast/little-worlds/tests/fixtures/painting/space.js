// Change these together to change logical resolution. Existing layers keep their own basis.
const COLUMNS = 48;
const ROWS = 32;
const PALETTE = ['#3153be','#ef7966','#e4b94e','#899b77','#30332f','#aca0cc','#85b9c6','#ffffff'];
const NAMES = ['Cobalt','Coral','Yellow','Sage','Charcoal','Lilac','Sky','White eraser'];
const SYMBOLS = '0123456789abcdefghijklmnopqrstuv';
const CHUNK = 16;
const STRIDE = 7;
const EMPTY_CHUNK = '.'.repeat(CHUNK * CHUNK * STRIDE);
const MAX_SEQUENCE = 2176782335;

export const meta = {
  title: 'The shared canvas', subtitle: 'Iris / painter', accent: '#3153be', layout: 'canvas', capabilities: ['space-agent'],
  agent: {
    paintContext: {canvasKey:'painting',namespace:'canvas'},
    instructions: `Paint the user's complete requested result using real tools. Canvas width ${COLUMNS}, height ${ROWS}, top-left origin, cell=y*${COLUMNS}+x, bounds 0..${COLUMNS*ROWS-1}. Exact palette: ${NAMES.map((name,i)=>`${i} ${name} ${PALETTE[i]}`).join(', ')}. Blank pixels are white. Every tool requires columns:${COLUMNS},rows:${ROWS}. Choose efficient primitives, never enumerate a large area as individual pixels: fill_canvas paints EVERY visible pixel in one action and is mandatory for requests such as "paint the whole canvas green" (Sage, color 3). It intentionally covers existing artwork without deleting anyone's saved layer. flood_fill paints only the four-connected region of the visible color at x,y; use it for a background or enclosed region when other art should remain visible. paint_shapes draws up to 32 ordered rect, ellipse or line shapes in one action; x1,y1,x2,y2 are inclusive canvas coordinates, filled controls rect/ellipse interior, width 1..32 is outline/line thickness (ignored for a filled shape). Larger shapes go first, details last. Shape bounding boxes together may cover up to eight canvases per action; split an unusually complex scene into a few batches. paint_pixels batches of 1..120 cells are for small final details and manual brush strokes only. Plan the entire composition, block in large areas with fills/shapes, then add details within the available action budget. Preserve surrounding art unless the user asks to cover or replace it. extras.canvas is a visible-composite projection: pixels is a row-major string, dot means unpainted background, and 0..7 index the palette. Inspect the returned current projection to verify the request is fully satisfied; a thin strip is not a full-canvas fill. Stop early when complete. The server retains actor-owned layers and rescales earlier coordinate systems without altering their records. Paint only the current visitor layer. White is opaque paint; clearing removes only that visitor's marks. No global clear or fake success. After checking the result, give one brief confirmation; if unfinished, state that honestly. Never persist conversation.`,
    actions: [{name:'paint_pixels',description:'Paint a batch at the current canvas resolution.',parameters:{type:'object',properties:{
      columns:{type:'integer',minimum:COLUMNS,maximum:COLUMNS},rows:{type:'integer',minimum:ROWS,maximum:ROWS},
      cells:{type:'array',minItems:1,maxItems:120,items:{type:'object',properties:{cell:{type:'integer',minimum:0,maximum:COLUMNS*ROWS-1},color:{type:'integer',minimum:0,maximum:PALETTE.length-1}},required:['cell','color'],additionalProperties:false}}
    },required:['columns','rows','cells'],additionalProperties:false}},
    {name:'fill_canvas',description:'Cover the entire visible canvas with one palette color in ONE action, including existing artwork. Keeps other visitors\' saved layers intact.',parameters:{type:'object',properties:{
      columns:{type:'integer',minimum:COLUMNS,maximum:COLUMNS},rows:{type:'integer',minimum:ROWS,maximum:ROWS},color:{type:'integer',minimum:0,maximum:PALETTE.length-1}
    },required:['columns','rows','color'],additionalProperties:false}},
    {name:'paint_shapes',description:'Draw ordered filled or outlined rectangles/ellipses and thick lines. Use large shapes for large areas, not individual pixels. Inclusive endpoints. Up to eight canvases of total bounding-box work.',parameters:{type:'object',properties:{
      columns:{type:'integer',minimum:COLUMNS,maximum:COLUMNS},rows:{type:'integer',minimum:ROWS,maximum:ROWS},
      shapes:{type:'array',minItems:1,maxItems:32,items:{type:'object',properties:{
        kind:{type:'string',enum:['rect','ellipse','line']},x1:{type:'integer',minimum:0,maximum:COLUMNS-1},y1:{type:'integer',minimum:0,maximum:ROWS-1},x2:{type:'integer',minimum:0,maximum:COLUMNS-1},y2:{type:'integer',minimum:0,maximum:ROWS-1},color:{type:'integer',minimum:0,maximum:PALETTE.length-1},filled:{type:'boolean'},width:{type:'integer',minimum:1,maximum:32}
      },required:['kind','x1','y1','x2','y2','color','filled','width'],additionalProperties:false}}
    },required:['columns','rows','shapes'],additionalProperties:false}},
    {name:'flood_fill',description:'Fill the four-connected visible-color region containing x,y in ONE action. White paint and blank white background connect. Leaves differently colored artwork visible.',parameters:{type:'object',properties:{
      columns:{type:'integer',minimum:COLUMNS,maximum:COLUMNS},rows:{type:'integer',minimum:ROWS,maximum:ROWS},x:{type:'integer',minimum:0,maximum:COLUMNS-1},y:{type:'integer',minimum:0,maximum:ROWS-1},color:{type:'integer',minimum:0,maximum:PALETTE.length-1}
    },required:['columns','rows','x','y','color'],additionalProperties:false}}]
  }
};

function esc(value) { return String(value).replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c])); }
function json(value) { return esc(JSON.stringify(value)); }
function validSize(columns, rows) { return Number.isInteger(columns)&&Number.isInteger(rows)&&columns>=1&&rows>=1&&columns<=256&&rows<=256; }
function checkDimensions() { if(!validSize(COLUMNS,ROWS)) throw Error('Canvas dimensions must be 1–256.'); }

// Existing chunks remain readable. Runs keep a solid high-resolution fill small
// without retaining an ever-growing operation history or rewriting other layers.
function decodeChunk(data) {
  if(typeof data!=='string') throw Error('Invalid saved painting chunk.');
  if(data[0]!=='@') {
    if(data.length!==CHUNK*CHUNK*STRIDE) throw Error('Invalid saved painting chunk.');
    return data;
  }
  let raw='';
  for(let offset=1;offset<data.length;offset+=STRIDE+2) {
    const count=parseInt(data.slice(offset,offset+2),36),word=data.slice(offset+2,offset+2+STRIDE);
    if(!Number.isInteger(count)||count<1||count>CHUNK*CHUNK||word.length!==STRIDE||raw.length+count*STRIDE>CHUNK*CHUNK*STRIDE) throw Error('Invalid saved painting run.');
    raw+=word.repeat(count);
  }
  if(raw.length!==CHUNK*CHUNK*STRIDE) throw Error('Invalid saved painting chunk.');
  return raw;
}

function visitMarks(record, visit, visitSpan) {
  if(record.format !== 2) {
    for(const [key,mark] of Object.entries(record.marks||{})) {
      const cell=Number(key);
      if(Number.isInteger(cell)&&cell>=0&&cell<48*32&&Array.isArray(mark)&&Number.isInteger(mark[0])&&mark[0]>=0&&mark[0]<PALETTE.length&&Number.isSafeInteger(mark[1])&&mark[1]>0)
        visit(cell%48,Math.floor(cell/48),mark[0],mark[1],48,32);
    }
    return;
  }
  for(const plane of record.planes||[]) {
    if(!validSize(plane.columns,plane.rows)) throw Error('Invalid saved canvas dimensions.');
    const across=Math.ceil(plane.columns/CHUNK);
    for(const [key,saved] of Object.entries(plane.chunks||{})) {
      const index=Number(key),left=(index%across)*CHUNK,top=Math.floor(index/across)*CHUNK;
      if(!Number.isInteger(index)||index<0) throw Error('Invalid saved painting chunk.');
      const data=decodeChunk(saved);
      const solid=data===data.slice(0,STRIDE).repeat(CHUNK*CHUNK);
      for(let offset=0;offset<CHUNK*CHUNK;) {
        const word=data.slice(offset*STRIDE,(offset+1)*STRIDE);
        let end=solid?CHUNK*CHUNK:offset+1;
        if(!solid) while(end<CHUNK*CHUNK&&data.slice(end*STRIDE,(end+1)*STRIDE)===word) end++;
        const color=SYMBOLS.indexOf(word[0]),sequence=parseInt(word.slice(1),36);
        if(color>=0&&color<PALETTE.length&&Number.isInteger(sequence)&&sequence>0) {
          if(visitSpan&&end-offset>1) {
            for(let cell=offset;cell<end;) {
              const x=left+cell%CHUNK,y=top+Math.floor(cell/CHUNK),length=Math.min(end-cell,CHUNK-cell%CHUNK);
              if(x<plane.columns&&y<plane.rows) visitSpan(x,y,Math.min(length,plane.columns-x),color,sequence,plane.columns,plane.rows);
              cell+=length;
            }
          } else for(let cell=offset;cell<end;cell++) {
              const x=left+cell%CHUNK,y=top+Math.floor(cell/CHUNK);
              if(x<plane.columns&&y<plane.rows) visit(x,y,color,sequence,plane.columns,plane.rows);
          }
        }
        offset=end;
      }
    }
  }
}

function composite(state) {
  checkDimensions();
  const pixels=Array(COLUMNS*ROWS).fill('.'),sequences=new Uint32Array(COLUMNS*ROWS);
  const paintSpan=(x,y,length,color,stamp,width,height)=>{
    const left=width===COLUMNS?x:Math.ceil(x*COLUMNS/width),right=width===COLUMNS?x+length:Math.ceil((x+length)*COLUMNS/width);
    const top=height===ROWS?y:Math.ceil(y*ROWS/height),bottom=height===ROWS?y+1:Math.ceil((y+1)*ROWS/height),symbol=SYMBOLS[color];
    for(let row=top;row<bottom;row++) for(let cell=row*COLUMNS+left,end=row*COLUMNS+right;cell<end;cell++) {
      if(stamp>sequences[cell]) {sequences[cell]=stamp;pixels[cell]=symbol;}
    }
  };
  const paintCell=(x,y,color,stamp,width,height)=>{
    if(width===COLUMNS&&height===ROWS) {
      const cell=y*COLUMNS+x;
      if(stamp>sequences[cell]) {sequences[cell]=stamp;pixels[cell]=SYMBOLS[color];}
      return;
    }
    // Inverse nearest-neighbour bounds preserve positions and old pixel footprints.
    const left=Math.ceil(x*COLUMNS/width),right=Math.ceil((x+1)*COLUMNS/width);
    const top=Math.ceil(y*ROWS/height),bottom=Math.ceil((y+1)*ROWS/height);
    for(let row=top;row<bottom;row++) for(let column=left;column<right;column++) {
      const cell=row*COLUMNS+column;
      if(stamp>sequences[cell]) { sequences[cell]=stamp;pixels[cell]=SYMBOLS[color]; }
    }
  };
  const paintCurrentPlane=plane=>{
    const across=Math.ceil(COLUMNS/CHUNK);
    let lastStamp='',stamp=0;
    for(const [key,saved] of Object.entries(plane.chunks||{})) {
      const index=Number(key),left=(index%across)*CHUNK,top=Math.floor(index/across)*CHUNK;
      if(!Number.isInteger(index)||index<0) throw Error('Invalid saved painting chunk.');
      const data=decodeChunk(saved),right=Math.min(CHUNK,COLUMNS-left),bottom=Math.min(CHUNK,ROWS-top);
      const firstWord=data.slice(0,STRIDE);
      if(data===firstWord.repeat(CHUNK*CHUNK)) {
        const symbol=firstWord[0],solidStamp=parseInt(firstWord.slice(1),36);
        if(symbol>='0'&&symbol<='7') for(let row=0;row<bottom;row++) {
          for(let cell=(top+row)*COLUMNS+left,end=cell+right;cell<end;cell++) {
            if(solidStamp>sequences[cell]) {sequences[cell]=solidStamp;pixels[cell]=symbol;}
          }
        }
        continue;
      }
      // A dense drawing usually shares a stamp across many differently colored
      // cells. Decode that stamp once and avoid a callback for every subpixel.
      for(let row=0;row<bottom;row++) {
        let cell=(top+row)*COLUMNS+left,offset=row*CHUNK*STRIDE;
        for(let column=0;column<right;column++,cell++,offset+=STRIDE) {
          const symbol=data[offset];
          if(symbol==='.') continue;
          const encodedStamp=data.slice(offset+1,offset+STRIDE);
          if(encodedStamp!==lastStamp) {lastStamp=encodedStamp;stamp=parseInt(encodedStamp,36);}
          if(stamp>sequences[cell]&&symbol>='0'&&symbol<='7') {sequences[cell]=stamp;pixels[cell]=symbol;}
        }
      }
    }
  };
  for(const record of Object.values(state.extras.canvas||{})) {
    if(record.format!==2) visitMarks(record,paintCell,paintSpan);
    else for(const plane of record.planes||[]) {
      if(plane.columns===COLUMNS&&plane.rows===ROWS) paintCurrentPlane(plane);
      else visitMarks({format:2,planes:[plane]},paintCell,paintSpan);
    }
  }
  return {pixels:pixels.join('')};
}

function latestSequence(state) {
  let sequence=0;
  for(const record of Object.values(state.extras.canvas||{})) {
    if(record.format===2&&Number.isSafeInteger(record.sequence)&&record.sequence>=0) sequence=Math.max(sequence,record.sequence);
    else visitMarks(record,(_x,_y,_color,stamp)=>{sequence=Math.max(sequence,stamp);});
  }
  return sequence;
}

function setMark(plane,cell,color,sequence) {
  const x=cell%plane.columns,y=Math.floor(cell/plane.columns),across=Math.ceil(plane.columns/CHUNK);
  const key=String(Math.floor(y/CHUNK)*across+Math.floor(x/CHUNK));
  const offset=((y%CHUNK)*CHUNK+x%CHUNK)*STRIDE,data=decodeChunk(plane.chunks[key]||EMPTY_CHUNK);
  const encoded=SYMBOLS[color]+sequence.toString(36).padStart(6,'0');
  plane.chunks[key]=data.slice(0,offset)+encoded+data.slice(offset+STRIDE);
}

function applyPixels(plane, pixels, sequence, coverage, fillColor) {
  const across=Math.ceil(plane.columns/CHUNK),encoded=PALETTE.map((_color,index)=>SYMBOLS[index]+sequence.toString(36).padStart(6,'0'));
  for(let top=0;top<plane.rows;top+=CHUNK) for(let left=0;left<plane.columns;left+=CHUNK) {
    const key=String(Math.floor(top/CHUNK)*across+Math.floor(left/CHUNK));
    if(coverage?.[key]===Math.min(CHUNK,plane.columns-left)*Math.min(CHUNK,plane.rows-top)) {
      plane.chunks[key]='@'+(CHUNK*CHUNK).toString(36).padStart(2,'0')+encoded[fillColor];
      continue;
    }
    let changed=false;
    for(let y=top;y<Math.min(top+CHUNK,plane.rows)&&!changed;y++) for(let x=left;x<Math.min(left+CHUNK,plane.columns);x++) if(pixels[y*plane.columns+x]>=0) {changed=true;break;}
    if(!changed) continue;
    const raw=decodeChunk(plane.chunks[key]||EMPTY_CHUNK);
    let runs='@',previous='',count=0,plain='';
    for(let offset=0;offset<CHUNK*CHUNK;offset++) {
      const x=left+offset%CHUNK,y=top+Math.floor(offset/CHUNK),color=x<plane.columns&&y<plane.rows?pixels[y*plane.columns+x]:-1;
      const word=color>=0?encoded[color]:raw.slice(offset*STRIDE,(offset+1)*STRIDE);
      plain+=word;
      if(word===previous) count++;
      else {if(count) runs+=count.toString(36).padStart(2,'0')+previous;previous=word;count=1;}
    }
    runs+=count.toString(36).padStart(2,'0')+previous;
    plane.chunks[key]=runs.length<plain.length?runs:plain;
  }
}

function fillPlane(plane,color,sequence) {
  const across=Math.ceil(plane.columns/CHUNK),down=Math.ceil(plane.rows/CHUNK),run='@'+(CHUNK*CHUNK).toString(36).padStart(2,'0')+SYMBOLS[color]+sequence.toString(36).padStart(6,'0');
  plane.chunks={};
  for(let index=0;index<across*down;index++) plane.chunks[String(index)]=run;
}

function span(pixels,y,left,right,color) {
  if(y<0||y>=ROWS) return;
  const start=y*COLUMNS+Math.max(0,left),end=y*COLUMNS+Math.min(COLUMNS-1,right)+1;
  if(end>start) pixels.fill(color,start,end);
}

function shapeBounds(shape) {
  const extra=shape.kind==='line'?Math.ceil(shape.width/2):0;
  return {left:Math.max(0,Math.min(shape.x1,shape.x2)-extra),right:Math.min(COLUMNS-1,Math.max(shape.x1,shape.x2)+extra),top:Math.max(0,Math.min(shape.y1,shape.y2)-extra),bottom:Math.min(ROWS-1,Math.max(shape.y1,shape.y2)+extra)};
}

function paintShape(pixels,shape) {
  const {left,right,top,bottom}=shapeBounds(shape),color=shape.color,width=shape.width;
  if(shape.kind==='rect') {
    for(let y=top;y<=bottom;y++) {
      if(shape.filled||y<top+width||y>bottom-width) span(pixels,y,left,right,color);
      else {span(pixels,y,left,Math.min(right,left+width-1),color);span(pixels,y,Math.max(left,right-width+1),right,color);}
    }
  } else if(shape.kind==='ellipse') {
    const cx=(left+right)/2,cy=(top+bottom)/2,rx=(right-left+1)/2,ry=(bottom-top+1)/2,ix=rx-width,iy=ry-width;
    for(let y=top;y<=bottom;y++) {
      const extent=rx*Math.sqrt(Math.max(0,1-((y-cy)/ry)**2)),a=Math.ceil(cx-extent),b=Math.floor(cx+extent);
      if(shape.filled||ix<=0||iy<=0||Math.abs(y-cy)>=iy) span(pixels,y,a,b,color);
      else {
        const inner=ix*Math.sqrt(Math.max(0,1-((y-cy)/iy)**2));
        span(pixels,y,a,Math.ceil(cx-inner)-1,color);span(pixels,y,Math.floor(cx+inner)+1,b,color);
      }
    }
  } else {
    // Each row of a round-ended stroke is one interval. Intersect the line's
    // infinite strip with its endpoint projection range, then include its caps.
    // This avoids per-pixel work even for a full batch of very thick lines.
    const dx=shape.x2-shape.x1,dy=shape.y2-shape.y1,length=dx*dx+dy*dy,radius=width/2,epsilon=1e-9;
    const stripWidth=radius*Math.sqrt(length);
    for(let y=top;y<=bottom;y++) {
      let a=Infinity,b=-Infinity;
      for(const [cx,cy] of [[shape.x1,shape.y1],[shape.x2,shape.y2]]) {
        const square=radius*radius-(y-cy)**2;
        if(square>=-epsilon) {const cap=Math.sqrt(Math.max(0,square));a=Math.min(a,cx-cap);b=Math.max(b,cx+cap);}
      }
      if(length) {
        const offsetY=y-shape.y1;
        let bodyLeft=-Infinity,bodyRight=Infinity,inside=true;
        if(dy) {
          const center=shape.x1+dx*offsetY/dy,extent=stripWidth/Math.abs(dy);
          bodyLeft=center-extent;bodyRight=center+extent;
        } else if(Math.abs(offsetY)>radius+epsilon) inside=false;
        if(dx) {
          const start=shape.x1-dy*offsetY/dx,end=shape.x1+(length-dy*offsetY)/dx;
          bodyLeft=Math.max(bodyLeft,Math.min(start,end));bodyRight=Math.min(bodyRight,Math.max(start,end));
        } else if(dy*offsetY<-epsilon||dy*offsetY>length+epsilon) inside=false;
        if(inside&&bodyLeft<=bodyRight+epsilon) {a=Math.min(a,bodyLeft);b=Math.max(b,bodyRight);}
      }
      if(a<=b) span(pixels,y,Math.max(left,Math.ceil(a-epsilon)),Math.min(right,Math.floor(b+epsilon)),color);
    }
  }
}

function floodPixels(state,x,y,color,pixels) {
  let visible=composite(state).pixels;
  const start=y*COLUMNS+x,target=visible[start]==='.'?'7':visible[start];
  if(target==='7') visible=visible.replace(/\./g,'7');
  if(new RegExp('^'+target+'+$').test(visible)) {pixels.fill(color);return {count:pixels.length};}
  const stack=[start];
  const across=Math.ceil(COLUMNS/CHUNK),coverage=new Uint16Array(across*Math.ceil(ROWS/CHUNK));let count=0;
  while(stack.length) {
    const cell=stack.pop();
    if(pixels[cell]>=0||visible[cell]!==target) continue;
    const rowStart=cell-cell%COLUMNS,rowEnd=rowStart+COLUMNS-1;
    let left=cell,right=cell;
    while(left>rowStart&&pixels[left-1]<0&&visible[left-1]===target) left--;
    while(right<rowEnd&&pixels[right+1]<0&&visible[right+1]===target) right++;
    pixels.fill(color,left,right+1);count+=right-left+1;
    const from=left-rowStart,to=right-rowStart,chunkRow=Math.floor(rowStart/COLUMNS/CHUNK)*across;
    for(let chunk=Math.floor(from/CHUNK);chunk<=Math.floor(to/CHUNK);chunk++) coverage[chunkRow+chunk]+=Math.min(to,(chunk+1)*CHUNK-1)-Math.max(from,chunk*CHUNK)+1;
    // Enqueue one seed per neighboring horizontal run, not four per pixel.
    for(const offset of [-COLUMNS,COLUMNS]) {
      if(left+offset<0||right+offset>=pixels.length) continue;
      let inside=false;
      for(let next=left+offset;next<=right+offset;next++) {
        const eligible=pixels[next]<0&&visible[next]===target;
        if(eligible&&!inside) stack.push(next);
        inside=eligible;
      }
    }
  }
  return {count,coverage};
}

function ownRecord(previous,actorId) {
  if(previous&&previous.actorId!==actorId) throw Error('Not your layer.');
  if(previous?.format===2) return {...previous,planes:previous.planes.map(plane=>({...plane,chunks:{...plane.chunks}}))};
  const record={...previous,actorId,format:2,color:previous?.color||0,sequence:0,planes:[]};
  delete record.marks;
  if(previous) {
    const plane={columns:48,rows:32,chunks:{}};
    visitMarks(previous,(x,y,color,sequence)=>{
      if(sequence>MAX_SEQUENCE) throw Error('Painting sequence limit reached.');
      record.sequence=Math.max(record.sequence,sequence);
      setMark(plane,y*48+x,color,sequence);
    });
    if(Object.keys(plane.chunks).length) record.planes.push(plane);
  }
  return record;
}

function hasMarks(record) {
  return record?.format===2 ? record.planes.some(plane=>Object.keys(plane.chunks).length>0) : Object.keys(record?.marks||{}).length>0;
}

export function reduce(state,action,actor) {
  checkDimensions();
  if(!actor||typeof actor.id!=='string'||!actor.id||['__proto__','constructor','prototype'].includes(actor.id)||!action) throw Error('Invalid request.');
  const records=state.extras.canvas||{},previous=Object.prototype.hasOwnProperty.call(records,actor.id)?records[actor.id]:undefined;
  const record=ownRecord(previous,actor.id);
  const validColor=color=>Number.isInteger(color)&&color>=0&&color<PALETTE.length;
  const fields={select_color:['type','color'],clear_marks:['type'],paint_pixels:['type','columns','rows','cells'],fill_canvas:['type','columns','rows','color'],paint_shapes:['type','columns','rows','shapes'],flood_fill:['type','columns','rows','x','y','color']}[action.type];
  if(!fields||Object.keys(action).some(key=>!fields.includes(key))) throw Error('Unknown action or argument.');
  if(action.type==='select_color') {
    if(!validColor(action.color)) throw Error('Invalid color.');
    record.color=action.color;
  } else if(action.type==='clear_marks') record.planes=[];
  else {
    if(action.columns!==COLUMNS||action.rows!==ROWS) throw Error('The canvas resolution changed. Refresh before painting.');
    const coordinate=(value,size)=>Number.isInteger(value)&&value>=0&&value<size;
    if(action.type==='paint_pixels') {
      if(!Array.isArray(action.cells)||action.cells.length<1||action.cells.length>120) throw Error('Use 1–120 pixels.');
      for(const mark of action.cells) if(!mark||typeof mark!=='object'||Array.isArray(mark)||Object.keys(mark).some(key=>key!=='cell'&&key!=='color')||!coordinate(mark.cell,COLUMNS*ROWS)||!validColor(mark.color)) throw Error('Invalid pixel.');
    } else if(action.type==='fill_canvas') {
      if(!validColor(action.color)) throw Error('Invalid color.');
    } else if(action.type==='paint_shapes') {
      if(!Array.isArray(action.shapes)||action.shapes.length<1||action.shapes.length>32) throw Error('Use 1–32 shapes.');
      let work=0;
      for(const shape of action.shapes) {
        if(!shape||typeof shape!=='object'||Array.isArray(shape)||Object.keys(shape).some(key=>!['kind','x1','y1','x2','y2','color','filled','width'].includes(key))||!['rect','ellipse','line'].includes(shape.kind)||!coordinate(shape.x1,COLUMNS)||!coordinate(shape.x2,COLUMNS)||!coordinate(shape.y1,ROWS)||!coordinate(shape.y2,ROWS)||!validColor(shape.color)||typeof shape.filled!=='boolean'||!Number.isInteger(shape.width)||shape.width<1||shape.width>32) throw Error('Invalid shape.');
        const bounds=shapeBounds(shape);work+=(bounds.right-bounds.left+1)*(bounds.bottom-bounds.top+1);
      }
      if(work>COLUMNS*ROWS*8) throw Error('Split this scene into batches covering at most eight canvas areas each.');
    } else if(action.type==='flood_fill') {
      if(!coordinate(action.x,COLUMNS)||!coordinate(action.y,ROWS)||!validColor(action.color)) throw Error('Invalid fill.');
    }
    const sequence=latestSequence(state)+1;
    if(sequence>MAX_SEQUENCE) throw Error('Painting sequence limit reached.');
    const pixels=new Int16Array(COLUMNS*ROWS);pixels.fill(-1);let wholeCanvas=action.type==='fill_canvas',coverage;
    if(action.type==='paint_pixels') for(const mark of action.cells) pixels[mark.cell]=mark.color;
    else if(action.type==='fill_canvas') pixels.fill(action.color);
    else if(action.type==='paint_shapes') for(const shape of action.shapes) paintShape(pixels,shape);
    else {const filled=floodPixels(state,action.x,action.y,action.color,pixels);wholeCanvas=filled.count===pixels.length;coverage=filled.coverage;}
    let plane=record.planes.find(item=>item.columns===COLUMNS&&item.rows===ROWS);
    if(!plane) { plane={columns:COLUMNS,rows:ROWS,chunks:{}};record.planes.push(plane); }
    if(wholeCanvas) fillPlane(plane,action.color,sequence);
    else applyPixels(plane,pixels,sequence,coverage,action.color);
    record.sequence=sequence;
  }
  return {...state,extras:{...state.extras,canvas:{...records,[actor.id]:record}}};
}

export function render(state,actor){
 const {pixels}=composite(state),records=state.extras.canvas||{},mine=Object.prototype.hasOwnProperty.call(records,actor.id)?records[actor.id]:null,color=mine?mine.color:0;
 return `<style>
 .studio{padding:16px;background:#000000;color:#ffffff;font-family:system-ui,Arial,sans-serif;min-height:80vh}.studio *{box-sizing:border-box}
 .heading{display:flex;align-items:baseline;justify-content:space-between;gap:16px;margin:0 0 22px}.heading h1{font-size:36px;font-weight:400;line-height:1.1;letter-spacing:-.035em;margin:0}.heading small{font-size:10px;white-space:nowrap;color:#a0a0a0}.heading small:after{content:"DevDay [2026]";display:block;margin-top:7px;color:#57dc8c;font-size:9px;letter-spacing:.05em}
 .layout{display:grid;grid-template-columns:minmax(0,1fr) 200px;gap:24px;align-items:start}.painting{min-width:0;margin:0}.grid{display:block;image-rendering:pixelated;width:100%;aspect-ratio:3/2;gap:0;border:1px solid #303030;box-shadow:0 5px 18px #00000033;background:#ffffff;touch-action:none;user-select:none}.grid button{appearance:none;width:100%;height:100%;min-width:0;min-height:0;padding:0;border:0;border-radius:0;cursor:crosshair;animation:none;transition:none;transform:none}
 .studio button:focus-visible,.studio input:focus-visible{outline:2px solid #924ff7;outline-offset:3px}.grid button:focus-visible{outline:2px solid #006aff;outline-offset:-1px;position:relative;z-index:1}.caption{font-size:10px;color:#a0a0a0;margin-top:8px}.tools{min-width:0}.swatches{display:flex;flex-wrap:wrap;gap:12px}.swatch{width:32px;height:32px;min-width:32px;max-width:32px;flex:0 0 32px;padding:0;border-radius:50%;aspect-ratio:1;border:1px solid #a0a0a0;cursor:pointer;transition:outline-color .15s}.swatch[aria-pressed=true]{outline:2px solid #04b84c;outline-offset:3px}.swatch:hover{outline:2px solid #b58cff;outline-offset:3px}
 .clear{padding:5px 0;background:none;border:0;border-bottom:1px solid #303030;font:inherit;font-size:11px;color:#a0a0a0;margin-top:17px;cursor:pointer;transition:color .15s}.clear:hover:not(:disabled){color:#ffffff}.clear:disabled{color:#a0a0a0;opacity:.65;cursor:default}.chat{margin-top:28px;border-top:1px solid #303030;padding-top:18px}.chat h2{font-size:18px;font-weight:400;margin:0 0 12px}.chat h2 small{font-size:9px;color:#b58cff;margin-left:4px}.chat input{width:100%;min-width:0;padding:10px 8px;border:1px solid #303030;border-radius:3px;background:#111111;font:inherit;font-size:12px;color:#ffffff}.chat input::placeholder{color:#a0a0a0;opacity:1}.commands{display:flex;gap:8px;margin-top:8px}.commands button{font:inherit;font-size:11px;padding:7px 12px;border-radius:3px;cursor:pointer;transition:background .15s,border-color .15s}.submit{background:#04b84c;color:#000000;border:1px solid #04b84c}.stop{background:#111111;color:#ffffff;border:1px solid #303030}.submit:hover{background:#57dc8c;border-color:#57dc8c}.stop:hover{background:#191919;border-color:#a0a0a0}.commands button:disabled{background:#191919;color:#a0a0a0;border-color:#303030;cursor:default}
 [data-service-error]{font-size:11px;color:#ff8549;overflow-wrap:anywhere}[data-service-status]{font-size:11px;color:#b58cff;margin-top:8px}.chat [hidden]{display:none!important}.chat [data-service-text]{font-size:clamp(12px,1vw,15px);line-height:1.45;margin-top:8px;color:#a0a0a0;overflow-wrap:anywhere}.chat[data-service-state="loading"] [data-service-text]{display:none}.projects{display:flex;flex-wrap:wrap;gap:20px;margin-top:24px}.projects article{max-width:240px;overflow-wrap:anywhere;font-size:12px;background:#111111;border:1px solid #303030;padding:16px}.projects h2{font-size:18px;font-weight:400}.projects p{color:#a0a0a0}
 .heading{animation:studio-enter .25s ease-out}@keyframes studio-enter{from{opacity:0;transform:translateY(3px)}to{opacity:1;transform:none}}@media(max-width:700px){.layout{grid-template-columns:minmax(0,1fr);gap:18px}.tools{grid-row:1;display:grid;grid-template-columns:minmax(0,1fr) minmax(0,1fr);gap:18px}.chat{margin:0;padding-top:0;border-top:0}.swatches{gap:10px}.heading{align-items:flex-start}.heading small{padding-top:7px}}@media(max-width:380px){.heading{flex-direction:column;gap:6px}.heading small{padding:0}.heading small:after{display:inline;margin-left:12px}.tools{gap:12px}.swatches{gap:8px}}@media(prefers-reduced-motion:reduce){.studio *{animation:none!important;transition:none!important}}
 </style><main class="studio"><header class="heading"><h1>The shared canvas.</h1><small>Iris / painter</small></header><div class="layout"><figure class="painting"><canvas class="grid" width="${COLUMNS}" height="${ROWS}" tabindex="0" aria-label="Shared painting, ${COLUMNS} columns by ${ROWS} rows. Use arrow keys to move and Space to paint." data-key="painting" data-paint-grid="${json({action:'paint_pixels',columns:COLUMNS,rows:ROWS,color,colorValue:PALETTE[color],palette:PALETTE,background:'#ffffff'})}" data-paint-pixels="${pixels}">Shared painting</canvas><figcaption class="caption">Drag to paint</figcaption></figure><aside class="tools"><div><div class="swatches" aria-label="Paint colors">${PALETTE.map((p,i)=>`<button type="button" class="swatch" style="background:${p}" aria-label="${NAMES[i]}" aria-pressed="${color===i}" data-action="${json({type:'select_color',color:i})}"></button>`).join('')}</div><button class="clear" type="button" data-action="${json({type:'clear_marks'})}" ${!hasMarks(mine)?'disabled':''}>Clear my marks</button></div><section class="chat" data-service="space-agent"><h2>Paint with words <small>AI</small></h2><form><input name="message" maxlength="1200" aria-label="Describe what to paint" placeholder="A little wildflower…" required><div class="commands"><button class="submit" type="submit">Paint</button><button class="stop" type="button" data-service-operation="cancel">Stop</button></div></form><div data-service-messages hidden></div><template data-service-message><p data-field="content"></p></template><div data-service-error></div><div data-service-text aria-live="polite"></div><div data-service-note hidden></div><div data-service-status="loading" hidden>Painting…</div></section></aside></div>${state.projects.length?`<section class="projects">${state.projects.map(p=>`<article><h2>${esc(p.title)}</h2><p>${esc(p.description)}</p></article>`).join('')}</section>`:''}</main>`;
}
