const {test}=require('node:test');
const assert=require('node:assert/strict');
const vm=require('node:vm');
const fs=require('node:fs');
const path=require('node:path');
const context=vm.createContext({});
vm.runInContext(fs.readFileSync(path.join(__dirname,'../web/sequence-ui.js'),'utf8'),context);
const run=code=>JSON.parse(JSON.stringify(vm.runInContext(code,context)));

test('batch text styles respect scope and locks, preserve content/timing/word cues',()=>{
 const cue={id:'a',text:'Xin chào',start_ms:1200,duration_ms:800,word_cues:[{word:'Xin',start:0,end:400}],y:88};
 const doc={tracks:[{id:'one',kind:'text',clips:[cue,{...cue,id:'b'}]},{id:'two',kind:'text',clips:[{...cue,id:'c'}]},{id:'lock',kind:'text',locked:true,clips:[{...cue,id:'d'}]},{id:'v',kind:'video',clips:[{id:'video'}]}]};
 const call=(scope,patch,ids=[])=>run(`seqBatchText(${JSON.stringify(doc)},${JSON.stringify(scope)},${JSON.stringify(ids)},'one',${JSON.stringify(patch)})`);
 const all=call('all',{y:75,font_size:42,text_animation:'pop'});assert.equal(all.changed,3);assert.equal(all.skipped,1);assert.equal(all.doc.tracks[2].clips[0].y,88);assert.equal(all.doc.tracks[3].clips[0].y,undefined);
 assert.deepEqual(all.doc.tracks[0].clips[0].word_cues,cue.word_cues);assert.equal(all.doc.tracks[0].clips[0].start_ms,1200);assert.equal(all.doc.tracks[0].clips[0].text,cue.text);assert.equal(cue.y,88);
 assert.equal(call('track',{y:70}).changed,2);assert.equal(call('selected',{y:70},['c','video']).changed,1);
 for(const patch of [{},{font_size:9},{x:101},{text:'changed'},{text_animation:'unknown'}])assert.throws(()=>call('all',patch));
 assert.throws(()=>call('selected',{y:70},[]));assert.equal(call('all',{y:88}).changed,0);
 const long=structuredClone(doc);long.tracks[1].clips[0].text=Array(201).fill('word').join(' ');assert.throws(()=>run(`seqBatchText(${JSON.stringify(long)},'all',[],'one',{y:70,text_animation:'pop'})`),/200/);assert.equal(long.tracks[0].clips[0].y,88);
});

test('batch text background colors and opacity validate without touching content',()=>{
 const doc={tracks:[{id:'t',kind:'text',clips:[{id:'c',text:'Hello',start_ms:0,duration_ms:1000}]}]};
 const call=patch=>run(`seqBatchText(${JSON.stringify(doc)},'all',[],'t',${JSON.stringify(patch)})`);
 const result=call({box:true,box_color:'#ff0000',box_opacity:.3});assert.equal(result.doc.tracks[0].clips[0].box_color,'#ff0000');assert.equal(result.doc.tracks[0].clips[0].text,'Hello');
 for(const patch of [{box_color:'red'},{box_opacity:1.1},{box_opacity:-1}])assert.throws(()=>call(patch));
});

test('generated media uses probed duration, still images keep requested length',()=>{
  assert.equal(run("seqToolMediaClip({id:'x',kind:'video',duration_ms:1750},'Stage',2000,500,()=> 'c')").duration_ms,1750);
  assert.equal(run("seqToolMediaClip({id:'x',kind:'image',duration_ms:0},'Comic',2000,500,()=> 'c')").duration_ms,2000);
  assert.throws(()=>run("seqToolMediaClip({id:'x',kind:'video',duration_ms:80},'Stage',2000,0,()=> 'c')"),/100ms/);
});

test('source-bound repair preserves start and source in, trims keys/curve/fades without mutation',()=>{
  const c={id:'c',asset:'a',label:'Stage',start_ms:500,in_ms:100,duration_ms:2000,speed:2,fade_in_ms:100,fade_out_ms:900,audio_fade_out_ms:900,keyframes:[{ms:0,x:20,y:50},{ms:2000,x:80,y:50}]};
  const next=run(`seqFitClipToSource(${JSON.stringify(c)},{kind:'video',duration_ms:1700})`);assert.equal(next.duration_ms,800);assert.equal(next.start_ms,500);assert.equal(next.in_ms,100);assert.equal(next.keyframes.at(-1).ms,800);assert.equal(next.keyframes.at(-1).x,44);assert.ok(next.fade_in_ms+next.fade_out_ms<=800);assert.ok(next.fade_in_ms+next.audio_fade_out_ms<=800);assert.equal(c.duration_ms,2000);
  const curved={...c,speed:1,keyframes:[],speed_curve:[{ms:0,speed:.5},{ms:2000,speed:1.5}]},trim=run(`seqFitClipToSource(${JSON.stringify(curved)},{kind:'video',duration_ms:900})`);
  assert.ok(run(`seqSourceMs(${JSON.stringify(trim)},${trim.duration_ms})`)<=900);assert.equal(trim.speed_curve.at(-1).ms,trim.duration_ms);
  assert.throws(()=>run(`seqFitClipToSource(${JSON.stringify(c)},{kind:'video',duration_ms:150})`),/không tự xóa/);
});

test('karaoke adds at old 20-track boundary and reuses gap without consuming tracks',()=>{
  const doc={assets:[],tracks:Array.from({length:20},(_,i)=>({id:'t'+i,name:'Video '+i,kind:'video',clips:[]}))},r={start_ms:0,duration_ms:5000},words=[{word:'你好',start:100,end:700}];
  const call=(d,target='auto')=>run(`seqWordProposal(${JSON.stringify(d)},${JSON.stringify(r)},${JSON.stringify(words)},()=> 'new',${JSON.stringify(target)})`);
  const first=call(doc);assert.equal(first.tracks.length,21);assert.equal(doc.tracks.length,20);
  r.start_ms=5000;const second=call(first);assert.equal(second.tracks.length,21);assert.equal(second.tracks.at(-1).clips.length,2);assert.equal(first.tracks.at(-1).clips.length,1);
});

test('karaoke full 64-track reuse is safe; selected overlaps/hidden/locked reject atomically',()=>{
  const doc={assets:[],tracks:Array.from({length:64},(_,i)=>({id:'t'+i,name:'T'+i,kind:i===63?'text':'video',locked:false,hidden:false,clips:i===63?[{id:'old',start_ms:2000,duration_ms:1000,text:'Keep original'}]:[]}))},r={start_ms:0,duration_ms:5000},words=[{word:'Xin',start:100,end:700}];
  const call=(d,target='auto')=>run(`seqWordProposal(${JSON.stringify(d)},${JSON.stringify(r)},${JSON.stringify(words)},()=> 'new',${JSON.stringify(target)})`);
  const next=call(doc);assert.equal(next.tracks.length,64);assert.equal(next.tracks.at(-1).clips.length,2);assert.equal(next.tracks.at(-1).clips[1].text,'Keep original');assert.equal(doc.tracks.at(-1).clips.length,1);
  assert.throws(()=>call(doc,'new'),/64 track/);
  for(const flag of ['hidden','locked']){const d=structuredClone(doc);d.tracks.at(-1)[flag]=true;assert.throws(()=>call(d),/64 track/);assert.throws(()=>call(d,'t63'),/khóa\/ẩn/);}
  const collision=structuredClone(doc);collision.tracks.at(-1).clips[0].start_ms=0;assert.throws(()=>call(collision,'t63'),/chồng mốc/);assert.equal(collision.tracks.at(-1).clips.length,1);
});

test('audio word proposals preserve source and split/rebase onsets',()=>{
  const doc={tracks:[],assets:[]},result={duration_ms:2000,start_ms:5000},words=[{word:'Xin',start:300,end:600},{word:'chào',start:1000,end:1400}];
  const next=run(`seqWordProposal(${JSON.stringify(doc)},${JSON.stringify(result)},${JSON.stringify(words)},()=> 'a')`),clip=next.tracks[0].clips[0];
  assert.equal(doc.tracks.length,0);assert.equal(clip.start_ms,5300);assert.equal(clip.word_cues[1].start,700);
  const parts=run(`seqSplit(${JSON.stringify(clip)},5800,'b')`);assert.equal(parts[0].text,'Xin');assert.equal(parts[1].text,'chào');assert.equal(parts[1].word_cues[0].start,200);
  assert.throws(()=>run(`seqWordProposal(${JSON.stringify(doc)},${JSON.stringify(result)},[{word:'Bad',start:500,end:300}],()=> 'a')`),/Mỗi dòng/);
  assert.throws(()=>run(`seqMerge(${JSON.stringify(clip)},${JSON.stringify(clip)})`),/mốc từ/);
});
test('studio captions timing, style proposal and cut are non destructive',()=>{
  const words=run("seqWordTiming('Xin chào bạn',1200)");assert.equal(words[0].start,0);assert.equal(words.at(-1).end,1200);
  const doc={assets:['a'],tracks:[{id:'t',kind:'video',clips:[{id:'c',asset:'a',start_ms:1000,in_ms:0,duration_ms:2000,speed:1}]},{id:'x',kind:'text',clips:[{id:'s',text:'Xin chào',start_ms:0,duration_ms:2000}]}]};
  assert.equal(run(`seqStyleProposal(${JSON.stringify(doc)},'manga',[])`).tracks[1].clips[0].text_animation,'pop');assert.equal(doc.tracks[1].clips[0].text_animation,undefined);
  const cut=run(`seqCutProposal(${JSON.stringify(doc)},'c',[500,1000],()=> 'new')`);assert.equal(cut.tracks[0].clips.length,3);assert.equal(cut.tracks[0].clips[2].in_ms,1000);assert.equal(doc.tracks[0].clips.length,1);
  assert.throws(()=>run(`seqCutProposal(${JSON.stringify(doc)},'c',[NaN],()=> 'new')`),/Mốc/);
});
test('creative color matrix identity/intensity and merge retain filter settings',()=>{
  assert.deepEqual(run('seqFilterMatrix([.2126,.7152,.0722,.2126,.7152,.0722,.2126,.7152,.0722],0)'),[1,0,0,0,1,0,0,0,1]);
  const clip={asset:'a',in_ms:0,start_ms:0,duration_ms:1000};assert.throws(()=>run(`seqMerge(${JSON.stringify(clip)},${JSON.stringify({...clip,start_ms:1000,in_ms:1000,color_filter:'sepia'})})`),/bộ lọc/);
});
test('smooth speed integral, split and trim share exact source-time mapping',()=>{
  const clip={id:'a',asset:'x',start_ms:500,in_ms:100,duration_ms:4000,speed:1,speed_curve:[{ms:0,speed:.5},{ms:4000,speed:1.5}]};
  assert.equal(run(`seqSourceMs(${JSON.stringify(clip)},2000)`),1600);assert.equal(run(`seqSpeedAt(${JSON.stringify(clip)},2000)`),1);
  const parts=run(`seqSplit(${JSON.stringify(clip)},2500,'b')`);assert.equal(parts[1].in_ms,1600);assert.equal(parts[1].speed_curve[0].speed,1);assert.equal(parts[1].speed_curve.at(-1).ms,2000);
  assert.equal(run(`seqSourceMs(${JSON.stringify(parts[1])},2000)`),4100);
  const trimmed=run(`seqTrim(${JSON.stringify(clip)},500,'start',5000)`);assert.equal(trimmed.speed_curve[0].speed,.625);assert.equal(trimmed.in_ms,381);
  assert.throws(()=>run(`seqRetime(${JSON.stringify(clip)},2)`),/curve/);
});
test('visible output quality keeps portrait/landscape ratio and rejects oversize canvas',()=>{
  assert.deepEqual(run(`seqOutputSize(1280,720,'2160')`),{width:3840,height:2160});
  assert.deepEqual(run(`seqOutputSize(720,1280,'1440')`),{width:1440,height:2560});
  assert.deepEqual(run(`seqOutputSize(1080,1080,'1080')`),{width:1080,height:1080});
  assert.throws(()=>run(`seqOutputSize(3000,1000,'2160')`),/3840/);
});
test('segmented speed curve consumes source once and keeps contiguous output with bounded fades',()=>{
  const clip={id:'a',asset:'x',start_ms:1000,in_ms:200,duration_ms:5000,speed:1,fade_in_ms:100,fade_out_ms:200};
  const rows=run(`seqSpeedCurve(${JSON.stringify(clip)},[.5,.75,1,1.5,2],()=> 'new')`);
  assert.deepEqual(rows.map(c=>c.in_ms),[200,1200,2200,3200,4200]);assert.deepEqual(rows.map(c=>c.speed),[.5,.75,1,1.5,2]);assert.equal(rows[0].fade_in_ms,200);assert.equal(rows.at(-1).fade_out_ms,100);
  for(let i=1;i<rows.length;i++)assert.equal(rows[i].start_ms,rows[i-1].start_ms+rows[i-1].duration_ms);
  assert.throws(()=>run(`seqSpeedCurve(${JSON.stringify({...clip,duration_ms:300})},[.5,1,2,1,.5],()=> 'new')`),/ngắn/);
});
test('real transition overlaps two layers and never fades outgoing video through black',()=>{
  const doc={tracks:[{id:'t',kind:'video',clips:[{id:'a',asset:'x',start_ms:0,duration_ms:2000},{id:'b',asset:'y',start_ms:2000,duration_ms:2000}]}]};
  const r=run(`seqTransition(${JSON.stringify(doc)},'b','crossfade',500,()=> 'new')`);
  assert.equal(r.tracks.length,2);assert.equal(r.tracks[0].clips[0].audio_fade_out_ms,500);assert.equal(r.tracks[0].clips[0].fade_out_ms,undefined);assert.equal(r.tracks[1].clips[0].start_ms,1500);assert.equal(r.tracks[1].clips[0].transition_in,'crossfade');assert.equal(doc.tracks.length,1);
  assert.equal(run(`seqTransitionProgress(${JSON.stringify(r.tracks[1].clips[0])},250)`),.5);
  assert.equal(run(`seqWipeMask({transition_in:'wipeleft',flip_h:true},.25)`),'inset(0 0 0 75%)');
  assert.throws(()=>run(`seqTransition(${JSON.stringify(doc)},'a','wipeleft',500,()=> 'new')`),/liền/);
  assert.throws(()=>run(`seqSplit(${JSON.stringify(r.tracks[1].clips[0])},2500,'new')`),/chuyển cảnh/);
});
test('multi-track presets clone ids and retain relative layers without overwriting current tracks',()=>{
  const preset={timeline:{width:3840,height:2160,fps:30,assets:[],tracks:[{id:'a',kind:'text',clips:[{id:'b',start_ms:500,duration_ms:1000,text:'X'}]},{id:'c',kind:'blur',clips:[{id:'d',start_ms:0,duration_ms:2000}]}]}};
  const result=run(`(()=>{let n=0;return seqApplyTrackPreset({tracks:[],assets:[],width:1280,height:720},${JSON.stringify(preset)},2000,()=>String(++n));})()`);
  assert.equal(result.width,3840);assert.equal(result.tracks[0].clips[0].start_ms,2500);assert.equal(result.tracks[1].clips[0].start_ms,2000);assert.equal(result.tracks[0].id,'1');assert.equal(preset.timeline.tracks[0].id,'a');
  assert.throws(()=>run(`seqApplyTrackPreset({tracks:[],assets:[]},${JSON.stringify(preset)},3599000,()=>"id")`),/60/);
});
test('complete transform keyframes interpolate, autokey and rebase every property',()=>{
  const c={start_ms:0,in_ms:0,duration_ms:1000,keyframes:[{ms:0,x:50,y:50,scale:.2,rotation:0,opacity:.4},{ms:1000,x:60,y:50,scale:.6,rotation:90,opacity:1}]};
  const t=run(`seqAnimatedTransform(${JSON.stringify(c)},500)`);assert.equal(t.scale,.4);assert.equal(t.rotation,45);assert.equal(t.opacity,.7);
  const parts=run(`seqSplit(${JSON.stringify(c)},500,'b')`);assert.equal(parts[1].keyframes[0].rotation,45);assert.equal(parts[0].keyframes.at(-1).scale,.4);
  const key=run(`(()=>{const c=${JSON.stringify(c)};seqSetPosition(c,500,{scale:.5});return c.keyframes[1]})()`);assert.equal(key.scale,.5);assert.equal(key.rotation,45);assert.equal(key.opacity,.7);
});
test('mirror interval only flips middle, retains timeline source and animation fades',()=>{
  const c={id:'a',asset:'src',start_ms:1000,in_ms:500,duration_ms:3000,speed:2,fade_in_ms:200,fade_out_ms:300};
  const r=run(`seqFlipRange(${JSON.stringify(c)},2000,3000,'flip_h',['b','c'])`);
  assert.deepEqual(r.clips.map(c=>c.start_ms),[1000,2000,3000]);assert.deepEqual(r.clips.map(c=>c.in_ms),[500,2500,4500]);
  assert.deepEqual(r.clips.map(c=>!!c.flip_h),[false,true,false]);assert.equal(r.selected,'b');
  assert.equal(r.clips[0].fade_in_ms,200);assert.equal(r.clips[2].fade_out_ms,300);assert.equal(r.clips[1].fade_in_ms,0);assert.equal(r.clips[1].fade_out_ms,0);
  assert.equal(run(`seqFlipRange(${JSON.stringify(c)},1000,4000,'flip_v',['b','c'])`).clips.length,1);
  assert.throws(()=>run(`seqFlipRange(${JSON.stringify(c)},1050,3000,'flip_h',['b','c'])`),/0,1/);
  assert.throws(()=>run(`seqFlipRange(${JSON.stringify(c)},0,3000,'flip_h',['b','c'])`));
  assert.throws(()=>run(`seqMerge(${JSON.stringify({...c,duration_ms:1000,fade_in_ms:0,fade_out_ms:0})},${JSON.stringify({...c,id:'b',start_ms:2000,in_ms:2500,duration_ms:1000,fade_in_ms:0,fade_out_ms:0,flip_h:true})})`),/lật/);
});
test('speed retimes source, keys and fades without moving other clips',()=>{
  const c={start_ms:500,in_ms:1000,duration_ms:2000,speed:1,fade_in_ms:400,fade_out_ms:200,keyframes:[{ms:0,x:0,y:50},{ms:2000,x:100,y:50}]};
  const r=run(`seqRetime(${JSON.stringify(c)},2)`);
  assert.equal(r.duration_ms,1000);assert.equal(r.start_ms,500);assert.equal(r.in_ms,1000);assert.equal(r.keyframes[1].ms,1000);assert.equal(r.fade_in_ms,200);assert.equal(r.fade_out_ms,100);
  assert.equal(run(`seqSourceMs(${JSON.stringify(r)},500)`),2000);
  assert.throws(()=>run(`seqRetime(${JSON.stringify(c)},0)`));
  assert.throws(()=>run(`seqRetime(${JSON.stringify({...c,keyframes:[{ms:0,x:0,y:0},{ms:1,x:1,y:1}]})},4)`),/trùng/);
});
test('speed split trim merge and filmstrip retain source coordinates',()=>{
  const c={id:'a',asset:'src',start_ms:1000,in_ms:1000,duration_ms:2000,speed:2,volume:1};
  const parts=run(`seqSplit(${JSON.stringify(c)},2000,'b')`);assert.equal(parts[1].in_ms,3000);
  assert.equal(run(`seqMerge(${JSON.stringify(parts[0])},${JSON.stringify(parts[1])})`).duration_ms,2000);
  assert.throws(()=>run(`seqMerge(${JSON.stringify(parts[0])},${JSON.stringify({...parts[1],speed:1})})`));
  assert.equal(run(`seqTrim(${JSON.stringify(c)},-2000,'start',6000)`).in_ms,0);
  assert.equal(run(`seqTrim(${JSON.stringify(c)},10000,'end',6000)`).duration_ms,2500);
  assert.equal(run(`seqThumbnail({thumbnails:[{ms:1000,url:'a'},{ms:3000,url:'b'}]},${JSON.stringify(c)},1000)`),'b');
  assert.equal(run(`seqSplit(${JSON.stringify({...c,in_ms:0,speed:1})},2000,'b',true)`)[1].in_ms,0);
});
test('smooth cubic phase survives split and repeated trim exactly; hold boundaries agree',()=>{
  const c={start_ms:0,in_ms:0,duration_ms:1000,asset:'src',motion_easing:'smooth',keyframes:[{ms:0,x:0,y:0},{ms:1000,x:100,y:100}]};
  assert.equal(run(`seqPosition(${JSON.stringify(c)},250)`).x,15.625);
  assert.equal(run(`seqPosition(${JSON.stringify({...c,motion_easing:'hold'})},999)`).x,0);
  assert.equal(run(`seqPosition(${JSON.stringify({...c,motion_easing:'hold'})},1000)`).x,100);
  const trimmed=run(`seqTrim(${JSON.stringify(c)},100,'start',1000)`),parts=run(`seqSplit(${JSON.stringify(c)},500,'b')`);
  for(let ms=0;ms<=900;ms+=10)assert.ok(Math.abs(run(`seqPosition(${JSON.stringify(trimmed)},${ms})`).x-run(`seqPosition(${JSON.stringify(c)},${ms+100})`).x)<1e-9);
  for(let ms=0;ms<=500;ms+=10)for(let i=0;i<2;i++)assert.ok(Math.abs(run(`seqPosition(${JSON.stringify(parts[i])},${ms})`).x-run(`seqPosition(${JSON.stringify(c)},${ms+500*i})`).x)<1e-9);
  const twice=run(`seqTrim(${JSON.stringify(trimmed)},100,'start',1000)`);assert.ok(Math.abs(run(`seqPosition(${JSON.stringify(twice)},250)`).x-run(`seqPosition(${JSON.stringify(c)},450)`).x)<1e-9);
});
test('smooth split preserves every transform, including zoom rotation and opacity',()=>{
  const c={start_ms:700,in_ms:0,duration_ms:2000,asset:'src',motion_easing:'smooth',keyframes:[{ms:200,x:20,y:40,scale:.5,rotation:-90,opacity:.1},{ms:1800,x:80,y:60,scale:2,rotation:90,opacity:1}]};
  const parts=run(`seqSplit(${JSON.stringify(c)},1400,'b')`);
  for(let i=0;i<2;i++)for(let ms=0;ms<=parts[i].duration_ms;ms+=17){const a=run(`seqMotionValues(${JSON.stringify(parts[i])},${ms})`),b=run(`seqMotionValues(${JSON.stringify(c)},${ms+(i?700:0)})`);for(const key of Object.keys(a))assert.ok(Math.abs(a[key]-b[key])<1e-9);}
});
test('motion holds endpoints and interpolates relative to clip time',()=>{
  const clip={start_ms:500,duration_ms:2000,keyframes:[{ms:200,x:20,y:40},{ms:1000,x:60,y:80}]};
  assert.deepEqual(run(`seqPosition(${JSON.stringify(clip)},-50)`),{x:20,y:40});
  assert.deepEqual(run(`seqPosition(${JSON.stringify(clip)},600)`),{x:40,y:60});
  assert.equal(run(`seqAnimatedTransform(${JSON.stringify(clip)},1100)`).x,40);
  assert.deepEqual(run(`seqPosition(${JSON.stringify(clip)},9000)`),{x:60,y:80});
});
test('fade envelope is bounded and respects both edges',()=>{
  assert.equal(run('seqEnvelope({duration_ms:1000,fade_in_ms:200,fade_out_ms:200},100)'),.5);
  assert.equal(run('seqEnvelope({duration_ms:1000,fade_in_ms:200,fade_out_ms:200},900)'),.5);
  assert.equal(run('seqEnvelope({duration_ms:1000,fade_in_ms:200},-100)'),0);
});
test('split and trim rebase animation with interpolated boundary positions',()=>{
  const c={id:'a',asset:'src',start_ms:0,in_ms:0,duration_ms:2000,keyframes:[{ms:0,x:0,y:50},{ms:2000,x:100,y:50}]};
  const parts=run(`seqSplit(${JSON.stringify(c)},1000,'b')`);
  assert.equal(parts[0].keyframes.at(-1).x,50);assert.equal(parts[1].keyframes[0].x,50);assert.equal(parts[1].keyframes.at(-1).ms,1000);
  const trimmed=run(`seqTrim(${JSON.stringify(c)},500,'start',2000)`);assert.equal(trimmed.keyframes[0].x,25);assert.equal(trimmed.keyframes.at(-1).ms,1500);
  assert.throws(()=>run(`seqMerge(${JSON.stringify(parts[0])},${JSON.stringify(parts[1])})`));
});
const groupDoc={tracks:[{id:'t',locked:false,clips:[{id:'a',start_ms:1000,duration_ms:500},{id:'b',start_ms:2000,duration_ms:500},{id:'c',start_ms:4000,duration_ms:500}]},{id:'u',locked:false,clips:[{id:'d',start_ms:1500,duration_ms:1000}]}]};
test('group move retains offsets and source document, clamps whole group',()=>{
  const result=run(`seqGroupEdit(${JSON.stringify(groupDoc)},['a','b','d'],-5000)`);
  assert.deepEqual(result.tracks[0].clips.map(c=>c.start_ms),[0,1000,4000]);assert.equal(result.tracks[1].clips[0].start_ms,500);
  assert.equal(groupDoc.tracks[0].clips[0].start_ms,1000);
});
test('group collision and locked member reject operation atomically',()=>{
  assert.throws(()=>run(`seqGroupEdit(${JSON.stringify(groupDoc)},['a','b'],2000)`),/vướng/);
  const locked=structuredClone(groupDoc);locked.tracks[1].locked=true;
  assert.throws(()=>run(`seqGroupEdit(${JSON.stringify(locked)},['a','d'],100)`),/khóa/);
  assert.throws(()=>run(`seqGroupEdit(${JSON.stringify(locked)},['a','d'],null,true)`),/khóa/);
  assert.throws(()=>run(`seqGroupEdit(${JSON.stringify(groupDoc)},['a'],NaN)`));
});
test('group delete ripple removes each selected interval per track',()=>{
  const result=run(`seqGroupEdit(${JSON.stringify(groupDoc)},['a','b','d'],null,true)`);
  assert.equal(result.tracks[0].clips.length,1);assert.equal(result.tracks[0].clips[0].start_ms,3000);assert.equal(result.tracks[1].clips.length,0);
  assert.equal(run(`seqGroupEdit(${JSON.stringify(groupDoc)},['a','b'],null,false)`).tracks[0].clips[0].start_ms,4000);
});
test('filmstrip chooses the source frame at source-in plus local offset',()=>{
  const item={thumbnail:'old',thumbnails:[{ms:0,url:'red'},{ms:1000,url:'blue'},{ms:2000,url:'green'}]};
  assert.equal(run(`seqThumbnail(${JSON.stringify(item)},{in_ms:1000,duration_ms:1000},0)`),'blue');
  assert.equal(run(`seqThumbnail(${JSON.stringify(item)},{in_ms:1000,duration_ms:1000},9000)`),'green');
  assert.equal(run(`seqThumbnail({thumbnail:'fallback'},{in_ms:0,duration_ms:1000},0)`),'fallback');
});
test('merge protects fill and blending modes',()=>{
  const a={asset:'a',start_ms:0,in_ms:0,duration_ms:1000,volume:1},b={...a,start_ms:1000,in_ms:1000,blend:'screen'};
  assert.throws(()=>run(`seqMerge(${JSON.stringify(a)},${JSON.stringify(b)})`));
  assert.throws(()=>run(`seqMerge(${JSON.stringify(a)},${JSON.stringify({...b,blend:'normal',fit:'cover'})})`));
});
test('split preserves source and timeline continuity',()=>{
  const parts=run('seqSplit({id:"a",start_ms:1000,in_ms:4000,duration_ms:3000},2500,"b")');
  assert.equal(parts[0].duration_ms,1500);assert.equal(parts[1].start_ms,2500);assert.equal(parts[1].in_ms,5500);assert.equal(parts[1].duration_ms,1500);
  assert.throws(()=>run('seqSplit({start_ms:1000,duration_ms:3000},1050,"b")'));
});
test('trim stays within source and retains minimum duration',()=>{
  assert.deepEqual(run('seqTrim({start_ms:1000,in_ms:500,duration_ms:2000},-2000,"start",5000)'),{start_ms:500,in_ms:0,duration_ms:2500});
  assert.equal(run('seqTrim({start_ms:1000,in_ms:500,duration_ms:2000},9000,"end",5000)').duration_ms,4500);
  assert.equal(run('seqTrim({start_ms:1000,in_ms:500,duration_ms:2000},-9000,"end",5000)').duration_ms,100);
  assert.equal(run('seqTrim({start_ms:1000,in_ms:0,duration_ms:2000},-1000,"start",0,true)').in_ms,0);
});
test('snap considers both edges; adjacent clips do not overlap',()=>{
  assert.equal(run('seqSnap(990,500,[1500],15)'),1000);
  assert.equal(run('seqSnap(990,500,[1500],5)'),990);
  assert.equal(run('seqOverlap({clips:[{id:"a",start_ms:0,duration_ms:1000}]},{start_ms:1000,duration_ms:500},"")'),false);
  assert.equal(run('seqOverlap({clips:[{id:"a",start_ms:0,duration_ms:1000}]},{start_ms:900,duration_ms:500},"")'),true);
});
test('merge requires contiguous source and timeline, same asset and gain',()=>{
  const clip={id:'a',asset:'source',start_ms:0,in_ms:2000,duration_ms:1000,volume:1};
  const right={...clip,id:'b',start_ms:1000,in_ms:3000};
  assert.equal(run(`seqMerge(${JSON.stringify(clip)},${JSON.stringify(right)})`).duration_ms,2000);
  assert.throws(()=>run(`seqMerge(${JSON.stringify(clip)},${JSON.stringify({...right,in_ms:5000})})`));
});
test('legacy layout defaults match renderer; merge never drops transforms',()=>{
  assert.deepEqual(run('seqTransform({})'),{x:50,y:50,scale:1,rotation:0,opacity:1});
  const left={asset:'a',start_ms:0,in_ms:0,duration_ms:1000,volume:1};
  assert.throws(()=>run(`seqMerge(${JSON.stringify(left)},${JSON.stringify({...left,start_ms:1000,in_ms:1000,scale:2})})`));
  assert.equal(run(`seqMerge(${JSON.stringify(left)},${JSON.stringify({...left,start_ms:1000,in_ms:1000,x:50})})`).duration_ms,2000);
});
test('text and mask split retain zero source in, merge rejects different text',()=>{
  assert.equal(run('seqSplit({asset:"",start_ms:0,in_ms:0,duration_ms:1000,text:"A"},500,"b")')[1].in_ms,0);
  assert.throws(()=>run('seqMerge({asset:"",start_ms:0,in_ms:0,duration_ms:500,text:"A"},{asset:"",start_ms:500,in_ms:0,duration_ms:500,text:"B"})'));
});
test('canvas zoom uses radial ratio and obeys renderer bounds',()=>{
  assert.equal(run('seqPointerTransform({scale:1,rotation:0},"se",{x:10,y:10},{x:20,y:20},{x:0,y:0})').scale,2);
  assert.equal(run('seqPointerTransform({scale:1,rotation:0},"nw",{x:10,y:10},{x:0,y:0},{x:0,y:0})').scale,.05);
  assert.equal(run('seqPointerTransform({scale:1,rotation:0},"sw",{x:1,y:1},{x:1000,y:1000},{x:0,y:0})').scale,4);
});
test('canvas rotation is continuous across angle boundary and can snap',()=>{
  assert.equal(run('seqPointerTransform({scale:1,rotation:0},"rotate",{x:10,y:0},{x:0,y:10},{x:0,y:0})').rotation,90);
  assert.equal(run('seqPointerTransform({scale:1,rotation:170},"rotate",{x:10,y:0},{x:0,y:10},{x:0,y:0})').rotation,-100);
  assert.equal(run('seqPointerTransform({scale:1,rotation:0},"rotate",{x:10,y:0},{x:10,y:3},{x:0,y:0},true)').rotation,15);
});
