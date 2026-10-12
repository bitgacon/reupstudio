"use strict";
// Pure edit primitives are shared by the UI and node regression tests.
const SEQ_MAX_TRACKS=64;
function seqId(){return crypto.randomUUID().replaceAll("-","");}
function seqCopy(value){return JSON.parse(JSON.stringify(value));}
function seqApplyTrackPreset(doc,preset,offset,newId){
  if(!Number.isFinite(offset)||offset<0)throw Error('Con trỏ không hợp lệ.');offset=Math.round(offset);
  const result=seqCopy(doc),tracks=seqCopy(preset.timeline.tracks);
  if(result.tracks.length+tracks.length>SEQ_MAX_TRACKS)throw Error('Preset làm vượt 64 track.');
  for(const t of tracks){t.id=newId();for(const c of t.clips){c.id=newId();c.start_ms+=offset;if(c.start_ms+c.duration_ms>3_600_000)throw Error('Preset vượt 60 phút tại con trỏ này.');}}
  result.tracks.push(...tracks);result.assets=[...new Set([...result.assets,...preset.timeline.assets,...tracks.flatMap(t=>t.clips.map(c=>c.asset).filter(Boolean))])];
  if(result.assets.length>200||result.tracks.flatMap(t=>t.clips).length>500||result.tracks.filter(t=>['video','audio'].includes(t.kind)).flatMap(t=>t.clips).length>100)throw Error('Preset vượt giới hạn media/clip.');
  if(!doc.tracks.some(t=>t.clips.length)){result.width=preset.timeline.width;result.height=preset.timeline.height;result.fps=preset.timeline.fps;}
  return result;
}
function seqLength(doc){return Math.max(0,...doc.tracks.flatMap(t=>t.clips.map(c=>c.start_ms+c.duration_ms)));}
function seqOutputSize(width,height,quality){
  if(quality==='canvas')return {width,height};const short=Number(quality);
  if(![720,1080,1440,2160].includes(short)||!Number.isFinite(width)||!Number.isFinite(height)||Math.min(width,height)<=0)throw Error('Chất lượng xuất không hợp lệ.');
  const factor=short/Math.min(width,height),w=Math.round(width*factor/2)*2,h=Math.round(height*factor/2)*2;
  if(Math.max(w,h)>3840)throw Error('Tỷ lệ này vượt canvas 3840px; chọn chất lượng thấp hơn hoặc tỷ lệ 16:9/9:16.');return {width:w,height:h};
}
function seqSpeedAt(clip,ms){const keys=clip.speed_curve||[];if(!keys.length)return clip.speed??1;for(let i=1;i<keys.length;i++)if(ms<=keys[i].ms){const a=keys[i-1],b=keys[i];return a.speed+(b.speed-a.speed)*Math.max(0,(ms-a.ms)/(b.ms-a.ms));}return keys.at(-1).speed;}
function seqSourceMs(clip,offset){
  if(!clip.speed_curve?.length)return clip.in_ms+Math.round(offset*(clip.speed??1));
  let total=0;for(let i=1;i<clip.speed_curve.length;i++){const a=clip.speed_curve[i-1],b=clip.speed_curve[i],dt=Math.max(0,Math.min(offset,b.ms)-a.ms);total+=a.speed*dt+(b.speed-a.speed)*dt*dt/(2*(b.ms-a.ms));}return clip.in_ms+Math.round(total);
}
function seqCurveRange(clip,from,to){if(!clip.speed_curve?.length)return {};if(from<0||to>clip.duration_ms)throw Error('Curve chỉ trim trong clip, không kéo dài nguồn.');const points=[{ms:0,speed:seqSpeedAt(clip,from)},...clip.speed_curve.filter(p=>p.ms>from&&p.ms<to).map(p=>({...p,ms:p.ms-from})),{ms:to-from,speed:seqSpeedAt(clip,to)}];if(points.length>16)throw Error('Trim vượt 16 mốc tốc độ; xóa bớt mốc trước.');return {speed_curve:points};}
function seqSmoothCurve(clip,kind){
  if((clip.transition_in||'none')!=='none')throw Error('Bỏ chuyển cảnh trước khi dùng curve.');
  const factors={ramp:[.5,1.5],down:[1.5,.5],pulse:[1.5,.5,1.5]}[kind];if(!factors)throw Error('Curve không hợp lệ.');
  const points=factors.map((rate,i)=>({ms:Math.round(clip.duration_ms*i/(factors.length-1)),speed:rate*(clip.speed??1)}));
  if(points.some(p=>p.speed<.25||p.speed>4))throw Error('Curve vượt 0,25–4×; đặt tốc độ nền gần 1× trước.');return points;
}
function seqTransition(doc,id,kind,ms,newId){
  if(!['crossfade','wipeleft','wiperight'].includes(kind)||!Number.isInteger(ms)||ms<100||ms>10000)throw Error('Chuyển cảnh cần 0,1–10s.');
  const result=seqCopy(doc),track=result.tracks.find(t=>t.clips.some(c=>c.id===id)),clip=track?.clips.find(c=>c.id===id);
  if(!clip||track.kind!=='video'||track.locked||result.tracks.length>=SEQ_MAX_TRACKS)throw Error('Chọn video trên track chưa khóa; cần chỗ cho track chuyển cảnh.');
  if(clip.speed_curve?.length)throw Error('Bỏ curve mượt trên clip vào trước khi thêm chuyển cảnh.');
  const previous=track.clips.find(c=>c.id!==id&&c.start_ms+c.duration_ms===clip.start_ms);
  if(!previous||ms>clip.duration_ms||ms>previous.duration_ms-(previous.fade_in_ms||0))throw Error('Cần hai clip liền nhau; thời gian chuyển phải nằm trong cả hai clip.');
  if((previous.transition_in||'none')!=='none'||(clip.transition_in||'none')!=='none')throw Error('Xóa chuyển cảnh cũ trước khi nối lại.');
  if(previous.fade_out_ms)throw Error('Bỏ fade hình ra của clip trước để crossfade không đi qua nền đen.');
  previous.audio_fade_out_ms=ms;clip.start_ms-=ms;Object.assign(clip,{transition_in:kind,transition_ms:ms,fade_in_ms:0,keyframes:[],x:50,y:50,scale:1,rotation:0,opacity:1,fit:'cover',blend:'normal'});
  track.clips=track.clips.filter(c=>c.id!==id);result.tracks.splice(result.tracks.indexOf(track)+1,0,{id:newId(),name:'Chuyển cảnh · '+clip.label,kind:'video',locked:false,hidden:false,muted:track.muted,clips:[clip]});
  return result;
}
function seqTransitionProgress(clip,ms){return (clip.transition_in||'none')==='none'?1:Math.max(0,Math.min(1,ms/clip.transition_ms));}
function seqWipeMask(clip,progress){const right=(clip.transition_in==='wiperight')!==!!clip.flip_h;if(!['wipeleft','wiperight'].includes(clip.transition_in))return 'none';return right?`inset(0 0 0 ${(1-progress)*100}%)`:`inset(0 ${(1-progress)*100}% 0 0)`;}
function seqRetime(clip,speed){
  if(clip.speed_curve?.length)throw Error('Bỏ curve mượt trước khi đổi tốc độ cố định.');
  if((clip.transition_in||'none')!=='none')throw Error('Xóa chuyển cảnh trước khi đổi tốc độ.');
  if(!Number.isFinite(speed)||speed<.25||speed>4)throw Error("Tốc độ phải từ 0,25 đến 4 lần.");
  const ratio=(clip.speed??1)/speed,duration=Math.round(clip.duration_ms*ratio);
  if(duration<100||clip.start_ms+duration>3_600_000)throw Error("Tốc độ làm clip quá ngắn hoặc vượt 60 phút.");
  const keys=(clip.keyframes||[]).map(p=>({...p,ms:Math.min(duration,Math.round(p.ms*ratio))}));
  if(new Set(keys.map(p=>p.ms)).size!==keys.length)throw Error("Tốc độ làm trùng mốc; xóa bớt keyframe trước.");
  const fadeIn=Math.min(duration,Math.round((clip.fade_in_ms||0)*ratio),10000);
  return {...clip,speed,duration_ms:duration,keyframes:keys,fade_in_ms:fadeIn,fade_out_ms:Math.min(duration-fadeIn,Math.round((clip.fade_out_ms||0)*ratio),10000),...(clip.audio_fade_out_ms!==undefined?{audio_fade_out_ms:Math.min(duration-fadeIn,Math.round(clip.audio_fade_out_ms*ratio),10000)}:{})};
}
function seqSpeedCurve(clip,rates,newId){
  if(!clip.asset||(clip.transition_in||'none')!=='none'||!Array.isArray(rates)||rates.length<2||rates.length>12||rates.some(r=>!Number.isFinite(r)||r<.25||r>4))throw Error('Speed curve cần media, 2–12 đoạn, tốc độ 0,25–4× và chưa có chuyển cảnh.');
  const rows=[];let start=clip.start_ms;
  for(let i=0;i<rates.length;i++){
    const from=Math.round(clip.duration_ms*i/rates.length),to=Math.round(clip.duration_ms*(i+1)/rates.length);
    if(to-from<100)throw Error('Clip quá ngắn cho số đoạn tốc độ này.');
    let piece={...clip,...seqAnimationRange(clip,from,to),id:i?newId():clip.id,start_ms:start,in_ms:seqSourceMs(clip,from),duration_ms:to-from,fade_in_ms:i?0:clip.fade_in_ms||0,fade_out_ms:i===rates.length-1?clip.fade_out_ms||0:0,audio_fade_out_ms:i===rates.length-1?clip.audio_fade_out_ms||0:0};
    piece=seqRetime(piece,rates[i]);piece.label=clip.label+' · curve '+(i+1);piece.audio_fade_out_ms=Math.min(piece.duration_ms-piece.fade_in_ms,Math.round((piece.audio_fade_out_ms||0)*(clip.speed??1)/rates[i]));rows.push(piece);start+=piece.duration_ms;
  }
  return rows;
}
function seqSplit(clip,ms,id,image=false){
  if((clip.transition_in||'none')!=='none')throw Error('Xóa chuyển cảnh trước khi chia/trim/ghép.');
  const offset=Math.round(ms-clip.start_ms);
  if(offset<100||clip.duration_ms-offset<100)throw Error("Chia clip phải cách mỗi đầu ít nhất 0,1 giây.");
  const left={...clip,...seqAnimationRange(clip,0,offset),duration_ms:offset},right={...clip,...seqAnimationRange(clip,offset,clip.duration_ms),id,start_ms:clip.start_ms+offset,in_ms:clip.asset===""||image?clip.in_ms:seqSourceMs(clip,offset),duration_ms:clip.duration_ms-offset};
  if(clip.fade_out_ms)left.fade_out_ms=0;if(clip.fade_in_ms)right.fade_in_ms=0;
  if(clip.audio_fade_out_ms)left.audio_fade_out_ms=0;
  return [left,right];
}
function seqFlipRange(clip,begin,end,key,ids,image=false){
  if(!['flip_h','flip_v'].includes(key)||!Number.isFinite(begin)||!Number.isFinite(end))throw Error("Chọn hướng và thời gian hợp lệ.");
  begin=Math.round(begin);end=Math.round(end);
  if(begin<clip.start_ms||end>clip.start_ms+clip.duration_ms||end-begin<100)throw Error("Đoạn lật phải nằm trong clip và dài ít nhất 0,1 giây.");
  let middle={...clip},rows=[];
  if(begin>middle.start_ms){const split=seqSplit(middle,begin,ids[0],image);rows.push(split[0]);middle=split[1];}
  let tail=null;
  if(end<middle.start_ms+middle.duration_ms){const split=seqSplit(middle,end,ids[1],image);middle=split[0];tail=split[1];}
  middle[key]=!middle[key];rows.push(middle);if(tail)rows.push(tail);
  return {clips:rows,selected:middle.id};
}
function seqMerge(left,right){
  if(left.word_cues?.length||right?.word_cues?.length)throw Error('Không ghép đoạn có mốc từ; giữ track karaoke để không mất căn chữ.');
  if(left.speed_curve?.length||right?.speed_curve?.length)throw Error('Bỏ curve mượt trước khi ghép.');
  if(left.audio_fade_out_ms||right?.audio_fade_out_ms)throw Error('Bỏ fade audio chuyển cảnh trước khi ghép.');
  if([left,right].some(c=>c&&(c.transition_in||'none')!=='none'))throw Error('Xóa chuyển cảnh trước khi ghép.');
  if(left.keyframes?.length||right?.keyframes?.length||left.fade_in_ms||left.fade_out_ms||right?.fade_in_ms||right?.fade_out_ms)throw Error("Bỏ keyframe/hiệu ứng vào ra trước khi ghép để tránh mất chuyển động.");
  if(!right||left.asset!==right.asset||left.start_ms+left.duration_ms!==right.start_ms||(left.asset&&seqSourceMs(left,left.duration_ms)!==right.in_ms)||left.volume!==right.volume||(left.speed??1)!==(right.speed??1))throw Error("Chỉ ghép hai đoạn nguồn liền nhau của cùng file, cùng âm lượng và tốc độ.");
  for(const key of ["x","y","scale","rotation","opacity"])if((left[key]??seqTransformDefaults[key])!==(right[key]??seqTransformDefaults[key]))throw Error("Hai đoạn có bố cục khác nhau; không ghép để tránh mất thiết lập.");
  for(const key of ["text","font","font_size","color","box","region_w","region_h","blur"])if(left[key]!==right[key])throw Error("Hai đoạn có nội dung hoặc kiểu khác nhau.");
  if((left.box_color??'#000000')!==(right.box_color??'#000000')||(left.box_opacity??.6)!==(right.box_opacity??.6))throw Error('Hai đoạn có nền hộp khác nhau.');
  for(const [key,fallback] of [["fit","contain"],["blend","normal"]])if((left[key]??fallback)!==(right[key]??fallback))throw Error("Hai đoạn có kiểu lấp khung/hòa trộn khác nhau.");
  for(const key of ['flip_h','flip_v'])if(!!left[key]!==!!right[key])throw Error("Hai đoạn có hướng lật khác nhau.");
  if((left.color_filter||'none')!==(right.color_filter||'none')||(left.filter_strength??1)!==(right.filter_strength??1))throw Error('Hai clip khác bộ lọc; không ghép để mất thiết lập.');
  if((left.text_animation||'none')!==(right.text_animation||'none'))throw Error('Hai đoạn khác chữ động.');
  return {...left,duration_ms:left.duration_ms+right.duration_ms};
}
const seqTransformDefaults={x:50,y:50,scale:1,rotation:0,opacity:1};
function seqTransform(clip){return {x:clip.x??50,y:clip.y??50,scale:clip.scale??1,rotation:clip.rotation??0,opacity:clip.opacity??1};}
function seqEase(point,f){const a=point.ease_start??0,b=point.ease_end??1,s=u=>u*u*(3-2*u);return (s(a+(b-a)*f)-s(a))/(s(b)-s(a));}
function seqMotionValues(clip,ms){
  const points=clip.keyframes||[],base=seqTransform(clip),values=p=>Object.fromEntries(Object.keys(base).map(k=>[k,p[k]??base[k]]));if(!points.length)return base;
  if(ms<=points[0].ms)return values(points[0]);
  for(let i=1;i<points.length;i++)if(ms<=points[i].ms){const a=values(points[i-1]),b=values(points[i]);let f=(ms-points[i-1].ms)/(points[i].ms-points[i-1].ms);if(clip.motion_easing==="smooth")f=seqEase(points[i-1],f);else if(clip.motion_easing==="hold")f=ms<points[i].ms?0:1;return Object.fromEntries(Object.keys(base).map(k=>[k,a[k]+(b[k]-a[k])*f]));}
  return values(points.at(-1));
}
function seqPosition(clip,ms){const p=seqMotionValues(clip,ms);return {x:p.x,y:p.y};}
function seqEnvelope(clip,ms){return Math.max(0,Math.min(1,clip.fade_in_ms?ms/clip.fade_in_ms:1,clip.fade_out_ms?(clip.duration_ms-ms)/clip.fade_out_ms:1));}
function seqAnimatedTransform(clip,time){const p=seqMotionValues(clip,time-clip.start_ms);return {...p,opacity:p.opacity*seqEnvelope(clip,time-clip.start_ms)};}
function seqRecordPosition(clip,ms,position){
  ms=Math.max(0,Math.min(clip.duration_ms,Math.round(ms)));const points=(clip.keyframes||[]).map(p=>({...p})),existing=points.find(p=>p.ms===ms);
  if(existing)Object.assign(existing,position);else{if(points.length>=64)throw Error("Tối đa 64 mốc vị trí mỗi clip.");points.push({ms,...position});}
  clip.keyframes=points.sort((a,b)=>a.ms-b.ms);
}
function seqSetPosition(clip,time,position){if((clip.transition_in||'none')!=='none')throw Error('Bỏ chuyển cảnh trước khi đổi bố cục clip này.');if(clip.keyframes?.length)seqRecordPosition(clip,time-clip.start_ms,{...seqMotionValues(clip,time-clip.start_ms),...position});else Object.assign(clip,position);}
function seqAnimationRange(clip,from,to){
  const result=seqCurveRange(clip,from,to);
  if(clip.word_cues?.length){result.word_cues=clip.word_cues.filter(w=>w.end>from&&w.start<to).map(w=>({...w,start:Math.max(0,w.start-from),end:Math.min(to,w.end)-from}));if(!result.word_cues.length)throw Error('Đoạn cắt không có từ; bỏ mốc từ trước khi giữ đoạn im lặng.');result.text=result.word_cues.map(w=>w.word).join(' ');result.label=result.text.slice(0,80);}
  if(clip.keyframes?.length){const points=[{ms:0,...seqMotionValues(clip,from)},...clip.keyframes.filter(p=>p.ms>from&&p.ms<to).map(p=>({...p,ms:p.ms-from})),{ms:to-from,...seqMotionValues(clip,to)}];if(points.length>64)throw Error("Trim vượt giới hạn keyframe; xóa bớt mốc trước.");result.keyframes=points;}
  if(clip.motion_easing==='smooth'&&result.keyframes){
    // Restrict the original cubic phase instead of easing each cut segment anew.
    for(let i=0;i<result.keyframes.length-1;i++){
      const p=result.keyframes[i],begin=from+p.ms,end=from+result.keyframes[i+1].ms;
      const j=clip.keyframes.findIndex((k,n)=>n<clip.keyframes.length-1&&begin>=k.ms&&end<=clip.keyframes[n+1].ms);
      if(j<0){p.ease_start=0;p.ease_end=1;continue;}const a=clip.keyframes[j],b=clip.keyframes[j+1],lo=a.ease_start??0,span=(a.ease_end??1)-lo;
      p.ease_start=lo+span*(begin-a.ms)/(b.ms-a.ms);p.ease_end=lo+span*(end-a.ms)/(b.ms-a.ms);
    }
  }
  if(!clip.asset&&clip.region_w&&result.keyframes)result.keyframes=result.keyframes.map(p=>({ms:p.ms,x:p.x,y:p.y,...(p.ease_start!==undefined?{ease_start:p.ease_start,ease_end:p.ease_end}:{})}));
  if(clip.fade_in_ms!==undefined||clip.fade_out_ms!==undefined){result.fade_in_ms=Math.min(clip.fade_in_ms||0,to-from);result.fade_out_ms=Math.min(clip.fade_out_ms||0,to-from-result.fade_in_ms);}
  return result;
}
function seqPointerTransform(initial,mode,start,point,center,snap=false){
  if(mode==="rotate"){
    const a=Math.atan2(start.y-center.y,start.x-center.x),b=Math.atan2(point.y-center.y,point.x-center.x);
    const delta=Math.atan2(Math.sin(b-a),Math.cos(b-a))*180/Math.PI;
    let rotation=(initial.rotation+delta+540)%360-180;if(snap)rotation=Math.round(rotation/15)*15;
    return {rotation};
  }
  const radius=Math.max(1,Math.hypot(start.x-center.x,start.y-center.y));
  return {scale:Math.max(.05,Math.min(4,initial.scale*Math.hypot(point.x-center.x,point.y-center.y)/radius))};
}
function seqTrim(clip,delta,edge,sourceDuration,image=false){
  if(edge&&(clip.transition_in||'none')!=='none')throw Error('Xóa chuyển cảnh trước khi trim.');
  const result={...clip};delta=Math.round(delta);
  if(edge==="start"){
    delta=Math.max(-clip.start_ms,image?-clip.start_ms:-Math.floor(clip.in_ms/(clip.speed??1)),Math.min(clip.duration_ms-100,delta));
    result.start_ms+=delta;result.duration_ms-=delta;if(!image)result.in_ms=seqSourceMs(clip,delta);
  }else if(edge==="end")result.duration_ms=Math.max(100,Math.min(3_600_000-clip.start_ms,image?3_600_000:Math.floor((sourceDuration-clip.in_ms)/(clip.speed??1)),clip.duration_ms+delta));
  else result.start_ms=Math.max(0,Math.min(3_600_000-clip.duration_ms,clip.start_ms+delta));
  if(edge)Object.assign(result,seqAnimationRange(clip,result.start_ms-clip.start_ms,result.start_ms-clip.start_ms+result.duration_ms));
  return result;
}
function seqSnap(start,duration,points,threshold){
  let correction=0,best=threshold+1;
  for(const point of points)for(const edge of [start,start+duration]){const d=point-edge;if(Math.abs(d)<best){best=Math.abs(d);correction=d;}}
  return Math.max(0,start+(best<=threshold?correction:0));
}
function seqOverlap(track,clip,ignore){return track.clips.some(c=>c.id!==ignore&&clip.start_ms<c.start_ms+c.duration_ms&&clip.start_ms+clip.duration_ms>c.start_ms);}
function seqThumbnail(item,clip,offset){
  const ms=seqSourceMs(clip,Math.max(0,Math.min(clip.duration_ms,offset)));
  return item?.thumbnails?.reduce((best,row)=>!best||Math.abs(row.ms-ms)<Math.abs(best.ms-ms)?row:best,null)?.url||item?.thumbnail;
}
function seqGroupEdit(doc,ids,delta=null,ripple=false){
  const result=seqCopy(doc),keys=new Set(ids),rows=result.tracks.flatMap(t=>t.clips.filter(c=>keys.has(c.id)).map(c=>({track:t,clip:c})));
  if(!rows.length)throw Error("Chọn clip trên timeline trước.");
  if(rows.some(r=>r.track.locked))throw Error("Nhóm có clip thuộc track bị khóa.");
  if(delta!==null){
    if(!Number.isFinite(delta))throw Error("Khoảng dịch không hợp lệ.");
    delta=Math.round(delta);const first=Math.min(...rows.map(r=>r.clip.start_ms)),last=Math.max(...rows.map(r=>r.clip.start_ms+r.clip.duration_ms));
    delta=Math.max(-first,Math.min(3_600_000-last,delta));
    for(const r of rows)r.clip.start_ms+=delta;
    for(const track of result.tracks){const clips=[...track.clips].sort((a,b)=>a.start_ms-b.start_ms);if(clips.some((c,i)=>i&&clips[i-1].start_ms+clips[i-1].duration_ms>c.start_ms))throw Error("Nhóm vướng clip khác trên cùng track.");}
  }else{
    for(const track of result.tracks){
      const removed=track.clips.filter(c=>keys.has(c.id));track.clips=track.clips.filter(c=>!keys.has(c.id));
      if(ripple)for(const clip of track.clips)clip.start_ms-=removed.filter(c=>c.start_ms+c.duration_ms<=clip.start_ms).reduce((sum,c)=>sum+c.duration_ms,0);
    }
  }
  return result;
}
const sequence={id:"",doc:null,media:new Map(),undo:[],redo:[],selected:"",dirty:false,saving:null,blocked:false,
  generation:0,time:0,playing:false,playToken:0,clock:0,zoom:24,nodes:new Map(),timer:null,busy:false,rendered:null,projectsSignature:"",proxies:new Map(),proxyFailures:new Set()};

function seqButton(text,fn){const button=element("button","",text);button.onclick=()=>Promise.resolve().then(fn).catch(e=>toast(e.message,true));return button;}
let seqCreativeCatalog=null;
function seqFilterMatrix(values,strength){return values.map((v,i)=>(i%4===0?1:0)+(v-(i%4===0?1:0))*strength);}
function seqColorStyle(clip){
  const preset=seqCreativeCatalog?.filters.find(p=>p.id===clip.color_filter);if(!preset||preset.id==='none'||(clip.filter_strength??1)===0)return 'none';
  const ns='http://www.w3.org/2000/svg';let svg=$('seq-filter-defs');if(!svg){svg=document.createElementNS(ns,'svg');svg.id='seq-filter-defs';svg.style.cssText='position:absolute;width:0;height:0;pointer-events:none';document.body.append(svg);}
  const id='seq-color-'+clip.id;let filter=document.getElementById(id);if(!filter){filter=document.createElementNS(ns,'filter');filter.id=id;filter.setAttribute('color-interpolation-filters','sRGB');filter.append(document.createElementNS(ns,'feColorMatrix'));svg.append(filter);}
  const m=seqFilterMatrix(preset.matrix,clip.filter_strength??1);filter.firstChild.setAttribute('type','matrix');filter.firstChild.setAttribute('values',`${m.slice(0,3).join(' ')} 0 0 ${m.slice(3,6).join(' ')} 0 0 ${m.slice(6,9).join(' ')} 0 0 0 0 0 1 0`);return `url(#${id})`;
}
async function seqInsertCreative(item){
  seqRequire();if(sequence.busy||sequence.blocked)throw Error('Chờ tác vụ/lưu bản nháp trước.');
  if(sequence.doc.tracks.length>=SEQ_MAX_TRACKS||sequence.doc.assets.length>=200||sequence.doc.tracks.flatMap(t=>t.clips).length>=500||sequence.doc.tracks.filter(t=>['video','audio'].includes(t.kind)).flatMap(t=>t.clips).length>=100)throw Error('Timeline/thư viện đã đầy.');
  const project=sequence.id,at=Math.round(sequence.time);if(at+3000>3_600_000)throw Error('Không còn đủ 3s trên timeline.');
  $('seq-creative-dialog').close();sequence.busy=true;seqControls();
  try{const result=await seqJob('editor_creative',{creative_id:item.id});if(sequence.id!==project)throw Error('Dự án đã đổi; xem file trong Lịch sử.');
    sequence.media.set(result.media.id,result.media);sequence.busy=false;
    seqChange(()=>{const clip={id:seqId(),asset:result.media.id,label:item.name,start_ms:at,in_ms:0,duration_ms:item.kind==='magic'?Math.min(3000,result.media.duration_ms):3000,volume:0,...seqTransformDefaults,scale:item.kind==='sticker'?.25:1};sequence.doc.assets.push(result.media.id);sequence.doc.tracks.push({id:seqId(),name:item.name,kind:'video',locked:false,hidden:false,muted:true,clips:[clip]});sequence.selected=clip.id;});
    toast('Đã thêm lớp riêng tại con trỏ; kéo/zoom/xoay trên video, trim thời gian và Hoàn tác.');
  }finally{sequence.busy=false;seqControls();}
}
async function seqCreativeOpen(){
  seqCreativeCatalog=await api('creative/catalog');let dialog=$('seq-creative-dialog');if(!dialog){dialog=element('dialog');dialog.id='seq-creative-dialog';dialog.className='large-dialog';document.body.append(dialog);}
  dialog.replaceChildren();const head=element('div','actions'),title=element('strong','','Kho sáng tạo');head.append(title,seqButton('Đóng ✕',()=>dialog.close()));dialog.append(head);
  const controls=element('div','actions'),select=element('select'),search=element('input');search.placeholder='Tìm tên…';search.setAttribute('aria-label','Tìm tài nguyên');
  for(const [value,name] of [['filter','Bộ lọc'],['magic','Phép thuật động'],['sticker','Nhãn dán']]){const option=element('option','',name);option.value=value;select.append(option);}controls.append(select,search);dialog.append(controls);
  const pack=element('select');pack.setAttribute('aria-label','Nguồn tài nguyên');for(const [value,name] of [['','Mọi nguồn'],['Twemoji','Twemoji · nét phẳng'],['Fluent','Fluent · 3D / Flat'],['Reup','Reup · thiết kế riêng']]){const option=element('option','',name);option.value=value;pack.append(option);}controls.append(pack);
  const grid=element('div','creative-grid'),note=element('p','hint','Bộ lọc áp dụng clip đang chọn. Nhãn dán/phép thuật thêm lớp riêng 3s tại con trỏ. Fluent: MIT; Twemoji: CC BY 4.0. Giữ ATTRIBUTION.txt khi xuất. Không phải tài nguyên CapCut.');dialog.append(grid,note);
  const draw=()=>{pack.disabled=select.value==='filter';grid.replaceChildren();for(const item of [...seqCreativeCatalog.filters,...seqCreativeCatalog.media].filter(p=>p.kind===select.value&&(select.value==='filter'||!pack.value||p.pack===pack.value)&&p.name.toLocaleLowerCase('vi').includes(search.value.toLocaleLowerCase('vi')))){
    const button=seqButton('',()=>{if(item.kind==='filter'){seqEditSelected((t,c)=>{if(t.kind!=='video')throw Error('Chọn clip ảnh/video.');c.color_filter=item.id;c.filter_strength=1;});dialog.close();}else return seqInsertCreative(item);});button.className='creative-card';const img=element('img');img.src=item.thumb;img.alt=item.name;img.loading='eager';button.append(img,element('span','',item.name));button.title=item.license||'Xem ngay trên clip; Hoàn tác nếu không muốn';grid.append(button);
  }};select.onchange=pack.onchange=search.oninput=draw;dialog.onkeydown=e=>{if(e.key==='Escape')dialog.close();};draw();if(!dialog.open)dialog.show();
}
async function seqVisualAI(kind){
  const {track,clip}=seqSelection();if(!clip?.asset||track.kind!=='video'||track.locked)throw Error('Chọn hình/video trên track chưa khóa.');
  if(sequence.busy)throw Error('Chờ tác vụ hiện tại.');
  if(!confirm(kind==='face'?'Dò mặt theo mẫu ~1s (clip tối đa 60s). Sau khi dò bạn xác nhận thay keyframe/bố cục; có thể Hoàn tác. Không nhận diện danh tính. Tiếp tục?':'Tách nền CPU tạo media trong suốt riêng (ảnh tối đa 1536px, video nguồn tối đa 15s/720px/12fps, không audio). Có thể mất nhiều phút và tải model lần đầu. Tiếp tục?'))return;
  await seqSave();if(sequence.dirty)throw Error('Lưu timeline trước khi chạy AI.');
  const project=sequence.id,id=clip.id,revision=sequence.doc.revision;sequence.busy=true;seqControls();
  try{
    const result=await seqJob('editor_'+kind,{project_id:project,clip_id:id,revision});
    if(sequence.id!==project)throw Error('Dự án đã đổi; kết quả nằm trong Lịch sử.');
    sequence.busy=false;
    if(kind==='face'){
      if(sequence.doc.revision!==result.revision)throw Error('Timeline đã đổi; chạy lại căn mặt để tránh dùng mốc cũ.');
      if(!confirm(`Tìm mặt ở ${result.proposal.detected_samples}/${result.proposal.total_samples} mẫu. Thay keyframe hiện tại và bố cục bằng căn mặt? Mẫu không thấy mặt giữ tâm trước. Kiểm tra kỹ đoạn đổi cảnh/nhiều người.`))return;
      const {detected_samples,total_samples,...layout}=result.proposal;
      seqChange(()=>{const row=sequence.doc.tracks.flatMap(t=>t.clips).find(c=>c.id===id);if(!row)throw Error('Clip không còn.');Object.assign(row,layout);});seqChoose(id);
    }else{
      if(new Set([...sequence.doc.assets,...result.media_items.map(i=>i.id)]).size>200)throw Error('Thư viện đầy; file kết quả vẫn trong Lịch sử.');
      for(const item of result.media_items)sequence.media.set(item.id,item);
      seqChange(()=>{for(const item of result.media_items)if(!sequence.doc.assets.includes(item.id))sequence.doc.assets.push(item.id);});
    }
    toast(result.message);
  }finally{sequence.busy=false;seqControls();if(sequence.dirty)seqScheduleSave();}
}
function seqSelectedIds(){
  const all=new Set(sequence.doc?.tracks.flatMap(t=>t.clips.map(c=>c.id))||[]);
  if(!sequence.selection?.has(sequence.selected))sequence.selection=new Set(all.has(sequence.selected)?[sequence.selected]:[]);
  return [...sequence.selection].filter(id=>all.has(id));
}
function seqChoose(id,extend=false,retain=false){
  const ids=new Set(seqSelectedIds());
  if(extend){if(ids.has(id))ids.delete(id);else ids.add(id);}else if(!retain||!ids.has(id)){ids.clear();ids.add(id);}
  sequence.selection=ids;sequence.selected=ids.has(id)?id:([...ids].at(-1)||"");seqMarkSelection();seqProperties();seqMonitor();
}
function seqMarkSelection(){
  const ids=new Set(seqSelectedIds());$("seq-timeline")?.querySelectorAll(".seq-clip").forEach(b=>{b.classList.toggle("selected",ids.has(b.dataset.clip));b.setAttribute("aria-pressed",String(ids.has(b.dataset.clip)));});
  if($("seq-selected-count"))$("seq-selected-count").textContent=ids.size+" clip được chọn";
}
function setupSequenceUI(){
  const root=$("page-edit");
  // Static markup only. User names/content always use textContent.
  root.innerHTML=`<div class="seq-toolbar"><select id="seq-project" aria-label="Chọn dự án"></select><button id="seq-new">＋ Dự án</button><button id="seq-open">Mở</button><button id="seq-import-main">Nhập video lồng tiếng</button><button id="seq-save">Lưu</button><span id="seq-status">Chọn hoặc tạo dự án để bắt đầu</span><span class="spacer"></span><button id="seq-undo" title="Ctrl+Z">↶ Hoàn tác</button><button id="seq-redo" title="Ctrl+Shift+Z">↷ Làm lại</button><button id="seq-preview">Xem chính xác</button><button id="seq-export" class="primary">Xuất MP4</button></div>
  <div class="seq-main"><aside class="seq-panel seq-library-panel"><div class="seq-library-heading"><h3>Thư viện media</h3><label id="seq-add-media" class="button file-button" role="button" tabindex="0" aria-label="Chọn file media" title="Chọn một hoặc nhiều file">＋<input id="seq-files" type="file" multiple accept=".mp4,.mov,.mkv,.avi,.webm,.png,.jpg,.jpeg,.webp,.wav,.mp3,.m4a,.ogg,.flac" hidden></label></div><div id="seq-library"></div></aside>
  <div class="seq-monitor"><div id="seq-stage"></div><div class="seq-transport"><button id="seq-play">▶</button><input id="seq-seek" type="range" min="0" max="1000" value="0" step="10" aria-label="Tua timeline"><output id="seq-time">0.00 / 0.00s</output></div><div id="seq-output"></div><p class="seq-warning" id="seq-preview-note">Xem nhanh: bố cục cơ bản. Nút Xem chính xác render cùng timeline và kích thước với bản xuất.</p></div>
  <aside class="seq-panel seq-properties"><h3>Thuộc tính clip</h3><div id="seq-properties"></div><hr><label class="field">Canvas<select id="seq-ratio"><option value="1280x720">16:9 · 1280×720</option><option value="720x1280">9:16 · 720×1280</option><option value="1080x1080">1:1 · 1080×1080</option><option value="1080x1920">9:16 · 1080×1920</option><option value="1920x1080">16:9 · 1920×1080</option><option value="2560x1440">2K · 2560×1440</option><option value="1440x2560">2K dọc · 1440×2560</option><option value="3840x2160">4K · 3840×2160</option><option value="2160x3840">4K dọc · 2160×3840</option></select></label><label class="field">FPS<select id="seq-fps"><option>25</option><option>30</option><option>60</option></select></label><button id="seq-draft" class="wide">Tải bản nháp JSON</button></aside></div>
  <div class="seq-toolbar"><button id="seq-video-track">＋ Track video/ảnh</button><button id="seq-audio-track">＋ Track audio</button><button id="seq-split">Chia tại con trỏ</button><button id="seq-merge">Ghép đoạn liền</button><button id="seq-copy">Nhân đôi</button><button id="seq-delete">Xóa clip</button><label><input id="seq-ripple" type="checkbox"> Xóa dồn track</label><label><input id="seq-snap" type="checkbox" checked> Bắt dính</label><span class="spacer"></span><label>Zoom <input id="seq-zoom" type="range" min="8" max="100" value="24" style="width:100px"></label></div>
  <div class="seq-timeline" id="seq-timeline"><div class="empty">Chưa có timeline</div></div>`;
  const creativeButton=seqButton('✦ Kho sáng tạo',seqCreativeOpen);creativeButton.id='seq-creative';$('seq-library').before(creativeButton);
  seqSetupStudioTools();
  const repair=seqButton('Căn clip vượt nguồn…',seqRepairSourceBounds);repair.id='seq-source-repair';repair.hidden=true;$('seq-save').after(repair);
  api('creative/catalog').then(value=>{seqCreativeCatalog=value;seqMonitor();}).catch(()=>{});
  on("seq-open","click",()=>seqOpen($("seq-project").value));
  on("seq-new","click",async()=>{
    const name=prompt("Tên dự án biên tập:","Video mới");if(!name?.trim())return;
    const parent=prompt("Thư mục lưu dự án (để trống dùng mặc định):",state.settings.project_root||"");if(parent===null)return;
    const project=await api("projects",{name,parent,kind:'edit'});await poll();$("seq-project").value=project.id;await seqOpen(project.id);
  });
  on("seq-import-main","click",async()=>{
    seqRequire();const p=await api("projects/"+sequence.id);if(!p.video)throw Error("Dự án chưa có video lồng tiếng.");
    if(!confirm("Chỉ nhập video nguồn. Các hiệu ứng, phụ đề và audio lồng tiếng không tự sao chép. Tiếp tục?"))return;
    sequence.busy=true;seqControls();try{await seqImport(p.video);}finally{sequence.busy=false;seqControls();}seqAddClip(p.video);
  });
  on("seq-files","change",async e=>{
    seqRequire();sequence.busy=true;seqControls();
    try{for(const file of e.target.files){$("seq-status").textContent="Đang nhập: "+file.name;const asset=await upload(file);await seqImport(asset.id);}}
    finally{sequence.busy=false;e.target.value="";seqControls();if(sequence.dirty)seqScheduleSave();}
  });
  on("seq-save","click",()=>seqSave());
  on("seq-add-media","keydown",e=>{if(e.target===$("seq-add-media")&&["Enter"," "].includes(e.key)){e.preventDefault();$("seq-files").click();}});
  on("seq-undo","click",()=>seqHistory(false));on("seq-redo","click",()=>seqHistory(true));
  on("seq-video-track","click",()=>seqAddTrack("video"));on("seq-audio-track","click",()=>seqAddTrack("audio"));
  on("seq-split","click",()=>seqEditSelected((track,clip)=>{const parts=seqSplit(clip,sequence.time,seqId(),sequence.media.get(clip.asset)?.kind==="image");track.clips.splice(track.clips.indexOf(clip),1,...parts);}));
  on("seq-delete","click",()=>seqChange(()=>{sequence.doc=seqGroupEdit(sequence.doc,seqSelectedIds(),null,$("seq-ripple").checked);sequence.selection=new Set();sequence.selected="";}));
  on("seq-merge","click",()=>seqEditSelected((track,clip)=>{const rows=[...track.clips].sort((a,b)=>a.start_ms-b.start_ms),right=rows[rows.indexOf(clip)+1],merged=seqMerge(clip,right);track.clips.splice(track.clips.indexOf(right),1);Object.assign(clip,merged);}));
  on("seq-copy","click",()=>seqEditSelected((track,clip)=>{
    const clone={...clip,id:seqId(),start_ms:clip.start_ms+clip.duration_ms};if(seqOverlap(track,clone,"")||clone.start_ms+clone.duration_ms>3_600_000)throw Error("Không còn chỗ ngay sau clip. Di chuyển clip khác trước.");track.clips.push(clone);sequence.selected=clone.id;
  }));
  on("seq-play","click",()=>sequence.playing?seqPause():seqPlay());
  on("seq-seek","input",e=>{seqPause();sequence.time=Number(e.target.value);seqMonitor();});
  on("seq-zoom","input",e=>{sequence.zoom=Number(e.target.value);seqTimeline();});
  on("seq-ratio","change",e=>seqChange(()=>{[sequence.doc.width,sequence.doc.height]=e.target.value.split("x").map(Number);}));
  on("seq-fps","change",e=>seqChange(()=>{sequence.doc.fps=Number(e.target.value);}));
  on("seq-preview","click",()=>seqRender(true));on("seq-export","click",()=>seqRender(false));
  const qualityLabel=element('label','actions','Xuất: '),quality=element('select');quality.id='seq-export-quality';quality.setAttribute('aria-label','Chất lượng video đầu ra');
  for(const [value,title] of [['canvas','Canvas hiện tại'],['720','720p'],['1080','1080p'],['1440','2K · 1440p'],['2160','4K · 2160p']]){const option=element('option','',title);option.value=value;quality.append(option);}qualityLabel.append(quality);$('seq-export').before(qualityLabel);
  quality.onchange=()=>{try{if(quality.value==='canvas')return;seqChange(()=>Object.assign(sequence.doc,seqOutputSize(sequence.doc.width,sequence.doc.height,quality.value)));}catch(e){toast(e.message,true);quality.value='canvas';}};
  const folder=seqButton("📂 Mở thư mục lưu",()=>openOutputFolder("edit"));folder.id="seq-open-folder";$("seq-time").after(folder);
  const count=element("small","","0 clip được chọn");count.id="seq-selected-count";count.title="Ctrl/Shift + bấm chọn nhiều · Ctrl+A chọn tất cả · Esc bỏ chọn";$("seq-delete").after(count);
  $("seq-delete").after(seqButton("Dịch nhóm…",()=>{const value=prompt("Dịch tất cả clip đang chọn (giây; số âm để lùi):","1");if(value===null)return;if(!value.trim())throw Error("Nhập số giây.");seqChange(()=>{sequence.doc=seqGroupEdit(sequence.doc,seqSelectedIds(),Number(value)*1000);});}));
  const presets=element("details","seq-property-group"),summary=element("summary","","Preset bố cục"),select=element("select");select.id="seq-layout-preset";select.setAttribute("aria-label","Preset bố cục");presets.append(summary,select);
  const reload=async()=>{const rows=await api("layout-presets");sequence.layoutPresets=rows;select.replaceChildren();for(const p of rows){const option=element("option","",p.name+" · "+p.kind);option.value=p.id;select.append(option);}};
  presets.append(seqButton("Lưu bố cục clip",async()=>{const {track,clip}=seqSelection();if(!clip||track.kind==="audio")throw Error("Chọn một lớp video, chữ hoặc vùng mờ.");const name=prompt("Tên preset bố cục:",clip.label);if(name===null)return;
    const keys=track.kind==="blur"?["x","y","region_w","region_h","blur"]:["x","y","scale","rotation","opacity",...(track.kind==="text"?["font","font_size","color","box","box_color","box_opacity"]:["fit","blend","flip_h","flip_v","color_filter","filter_strength"])],layout={};for(const key of keys)if(clip[key]!==undefined)layout[key]=clip[key];
    const saved=await api("layout-presets",{name,kind:track.kind,layout});await reload();select.value=saved.id;toast("Đã lưu bố cục; không lưu nội dung, file hay thời gian.");
  }),seqButton("Áp dụng cho nhóm chọn",()=>{const preset=sequence.layoutPresets?.find(p=>p.id===select.value);if(!preset)throw Error("Chọn preset đã lưu.");seqChange(()=>{const ids=new Set(seqSelectedIds()),rows=sequence.doc.tracks.flatMap(t=>t.clips.filter(c=>ids.has(c.id)).map(c=>({track:t,clip:c})));if(!rows.length)throw Error("Chọn clip trước.");if(rows.some(r=>r.track.kind!==preset.kind||r.track.locked))throw Error("Chọn các clip cùng loại với preset và không thuộc track bị khóa.");for(const r of rows)Object.assign(r.clip,preset.layout);});}));
  $("seq-draft").before(presets);presets.addEventListener("toggle",()=>{if(presets.open)reload().catch(e=>toast(e.message,true));});
  const multi=element('details','seq-property-group'),multiSelect=element('select');multiSelect.id='seq-track-preset';multiSelect.setAttribute('aria-label','Preset nhiều track');multi.append(element('summary','','Preset nhiều track'),multiSelect);let trackPresets=[];
  const refreshMulti=async()=>{trackPresets=await api('track-presets');multiSelect.replaceChildren();for(const p of trackPresets){const o=element('option','',p.name+' · '+p.timeline.tracks.length+' track');o.value=p.id;multiSelect.append(o);}};
  multi.addEventListener('toggle',()=>{if(multi.open)refreshMulti().catch(e=>toast(e.message,true));});
  multi.append(seqButton('Lưu toàn bộ track',async()=>{seqRequire();if(sequence.busy||sequence.blocked)throw Error('Chờ tác vụ hoặc giải quyết xung đột.');const name=prompt('Tên preset nhiều track (gồm media, chữ và hiệu ứng):');if(name===null)return;await api('track-presets',{name,timeline:sequence.doc});await refreshMulti();toast('Đã lưu preset nhiều track; media tham chiếu trên máy này.');}),seqButton('Thêm tại con trỏ',async()=>{seqRequire();if(sequence.busy||sequence.blocked)throw Error('Chờ tác vụ hoặc giải quyết xung đột.');const preset=trackPresets.find(p=>p.id===multiSelect.value);if(!preset)throw Error('Chọn preset trước.');const project=sequence.id,generation=sequence.generation;const next=seqApplyTrackPreset(sequence.doc,preset,sequence.time,seqId);
    for(const key of next.assets)if(!sequence.media.has(key))sequence.media.set(key,await api('projects/'+project+'/editor-media/'+key));
    if(project!==sequence.id||generation!==sequence.generation)throw Error('Timeline đã đổi trong lúc nạp preset; thử lại.');seqChange(()=>sequence.doc=next);
  }),seqButton('Xóa preset',async()=>{if(!multiSelect.value||!confirm('Xóa preset này? Không xóa media hoặc timeline đã áp dụng.'))return;await api('track-presets/'+multiSelect.value+'/delete',{});await refreshMulti();}));$("seq-draft").before(multi);
  let wheelAt=0,wheelClip="";
  $("seq-stage").addEventListener("wheel",e=>{
    const {track,clip}=seqSelection();if(!clip||track.kind==="audio"||track.kind==="blur"||track.locked||sequence.busy||sequence.blocked||sequence.rendered||sequence.time<clip.start_ms||sequence.time>=clip.start_ms+clip.duration_ms)return;
    if(track.kind==='video'&&clip.keyframes?.length>=64&&!clip.keyframes.some(p=>p.ms===Math.round(sequence.time-clip.start_ms))){toast('Tối đa 64 mốc; chọn mốc có sẵn hoặc xóa bớt.',true);return;}
    e.preventDefault();seqPause();const now=performance.now();if(wheelClip!==clip.id||now-wheelAt>300){sequence.undo.push(seqCopy(sequence.doc));sequence.redo=[];}wheelAt=now;wheelClip=clip.id;
    const layout=seqMotionValues(clip,sequence.time-clip.start_ms),change=e.shiftKey?{rotation:((layout.rotation+(e.deltaY<0?-5:5)+540)%360)-180}:{scale:Math.max(.05,Math.min(4,layout.scale*Math.exp(-Math.max(-150,Math.min(150,e.deltaY))*.002)))};
    if(track.kind==='video')seqSetPosition(clip,sequence.time,change);else Object.assign(clip,change);
    seqModified();
  },{passive:false});
  const live=seqButton("↩ Xem realtime",()=>{sequence.rendered=null;seqClearMonitor();seqMonitor();});live.id="seq-live";$("seq-preview").before(live);
  $("seq-audio-track").after(seqButton("＋ Chữ",()=>seqAddVisual("text")),seqButton("＋ Vùng mờ",()=>seqAddVisual("blur")),seqButton("Nhập phụ đề dự án",()=>seqImportCaptions()),seqButton('Chỉnh phụ đề hàng loạt',seqBatchTextDialog));
  const draw=seqButton("Vẽ vùng mờ",()=>{seqRequire();if(sequence.busy||sequence.blocked)return;seqPause();sequence.objectPick=false;if(sequence.rendered){sequence.rendered=null;seqClearMonitor();seqMonitor();}sequence.drawMask=!sequence.drawMask;$("seq-stage").classList.toggle("seq-drawing",sequence.drawMask);draw.setAttribute("aria-pressed",String(sequence.drawMask));});draw.id="seq-drawmask";draw.setAttribute("aria-pressed","false");$("seq-audio-track").after(draw);
  $("seq-stage").addEventListener("pointerdown",e=>{
    if(!sequence.drawMask||sequence.busy||sequence.blocked||e.button!==0)return;e.preventDefault();e.stopImmediatePropagation();const stage=$("seq-stage"),rect=stage.getBoundingClientRect();stage.setPointerCapture(e.pointerId);
    const point=evt=>({x:Math.max(0,Math.min(100,(evt.clientX-rect.left)/rect.width*100)),y:Math.max(0,Math.min(100,(evt.clientY-rect.top)/rect.height*100))}),start=point(e),box=element("div","seq-draw-box");let last=start;stage.append(box);
    const move=evt=>{last=point(evt);Object.assign(box.style,{left:Math.min(start.x,last.x)+"%",top:Math.min(start.y,last.y)+"%",width:Math.abs(last.x-start.x)+"%",height:Math.abs(last.y-start.y)+"%"});};
    const end=evt=>{stage.removeEventListener("pointermove",move);stage.removeEventListener("pointerup",end);stage.removeEventListener("pointercancel",end);box.remove();sequence.drawMask=false;stage.classList.remove("seq-drawing");draw.setAttribute("aria-pressed","false");
      const objectPick=sequence.objectPick;sequence.objectPick=false;if(evt.type==="pointercancel")return;last=point(evt);const w=Math.abs(last.x-start.x),h=Math.abs(last.y-start.y);if(w<1||h<1){toast("Kéo vùng rộng/cao ít nhất 1% canvas.",true);return;}const region={x:(start.x+last.x)/2,y:(start.y+last.y)/2,region_w:w,region_h:h};if(objectPick){seqObjectRegion(region).catch(error=>toast(error.message,true));return;}try{seqAddVisual("blur",region);}catch(error){toast(error.message,true);}
    };
    stage.addEventListener("pointermove",move);stage.addEventListener("pointerup",end);stage.addEventListener("pointercancel",end);
  },true);
  const proxy=seqButton("Chuẩn bị video xem realtime",async()=>{const {clip}=seqSelection();if(!clip)throw Error("Chọn clip cần chuẩn bị.");sequence.proxyFailures.delete(sequence.id+":"+clip.asset);await seqEnsureProxy(sequence.media.get(clip.asset));});$("seq-draft").before(proxy);
  let timelineHeight=Number(localStorage.getItem("rv-seq-timeline-height"))||190;
  const height=()=>{$("seq-timeline").style.height=Math.max(100,Math.min(timelineHeight,Math.max(100,root.clientHeight-250)))+"px";};
  const divider=element("div","seq-divider");divider.tabIndex=0;divider.setAttribute("role","separator");divider.setAttribute("aria-label","Điều chỉnh chiều cao timeline");divider.setAttribute("aria-orientation","horizontal");divider.title="Kéo để thay đổi chiều cao timeline · phím ↑/↓";
  $("seq-video-track").closest(".seq-toolbar").before(divider);
  divider.onpointerdown=e=>{if(e.button!==0)return;e.preventDefault();divider.setPointerCapture(e.pointerId);const initial=$("seq-timeline").clientHeight,y=e.clientY;
    const move=evt=>{timelineHeight=Math.max(100,Math.min(350,initial+y-evt.clientY));height();seqMonitor();};
    const end=()=>{divider.removeEventListener("pointermove",move);divider.removeEventListener("pointerup",end);divider.removeEventListener("pointercancel",end);localStorage.setItem("rv-seq-timeline-height",timelineHeight);};
    divider.addEventListener("pointermove",move);divider.addEventListener("pointerup",end);divider.addEventListener("pointercancel",end);
  };
  divider.onkeydown=e=>{if(!["ArrowUp","ArrowDown"].includes(e.key))return;e.preventDefault();timelineHeight=Math.max(100,Math.min(350,timelineHeight+(e.key==="ArrowUp"?20:-20)));height();localStorage.setItem("rv-seq-timeline-height",timelineHeight);};
  new ResizeObserver(height).observe(root);
  on("seq-draft","click",()=>{
    seqRequire();const draft=sequence.blocked?localStorage.getItem("rv-editor-"+sequence.id):JSON.stringify(sequence.doc,null,2);const url=URL.createObjectURL(new Blob([draft],{type:"application/json"}));const a=element("a");a.href=url;a.download="editor-draft.json";a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);
  });
  const resolve=seqButton("Dùng bản đã lưu trên đĩa",async()=>{
    if(!sequence.blocked)return;if(!confirm("Giữ bản nháp xung đột trong kho phục hồi trình duyệt và mở bản trên đĩa? Nên tải JSON trước."))return;
    const key="rv-editor-"+sequence.id,raw=localStorage.getItem(key),archive="rv-editor-conflict-"+sequence.id+"-"+Date.now();
    if(raw){localStorage.setItem(archive,raw);localStorage.setItem("rv-editor-conflict-last-"+sequence.id,archive);localStorage.removeItem(key);}
    const wasDirty=sequence.dirty;sequence.dirty=false;sequence.blocked=false;
    try{await seqOpen(sequence.id);}catch(e){if(raw)localStorage.setItem(key,raw);sequence.dirty=wasDirty;sequence.blocked=true;throw e;}
  });resolve.id="seq-resolve";resolve.className="wide";$("seq-draft").after(resolve);
  const oldDraft=seqButton("Tải bản nháp xung đột đã giữ",()=>{
    seqRequire();const key=localStorage.getItem("rv-editor-conflict-last-"+sequence.id),raw=key&&localStorage.getItem(key);if(!raw)throw Error("Không có bản nháp xung đột đã lưu.");
    const url=URL.createObjectURL(new Blob([raw],{type:"application/json"})),a=element("a");a.href=url;a.download="editor-conflict-draft.json";a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);
  });oldDraft.id="seq-conflict-download";oldDraft.className="wide";resolve.after(oldDraft);
  window.addEventListener("keydown",e=>{
    if(ui.tab!=="edit"||/^(INPUT|TEXTAREA|SELECT)$/.test(e.target.tagName)||document.querySelector("dialog[open]"))return;
    if((e.ctrlKey||e.metaKey)&&e.key.toLowerCase()==="z"){e.preventDefault();seqHistory(e.shiftKey);}
    else if((e.ctrlKey||e.metaKey)&&e.key.toLowerCase()==="a"){e.preventDefault();sequence.selection=new Set(sequence.doc?.tracks.flatMap(t=>t.clips.map(c=>c.id))||[]);sequence.selected=[...sequence.selection][0]||"";seqMarkSelection();seqProperties();seqMonitor();}
    else if(e.key==="Escape"){sequence.selection=new Set();sequence.selected="";seqMarkSelection();seqProperties();seqMonitor();}
    else if(e.key==="Delete"){e.preventDefault();$("seq-delete").click();}
    else if(e.key===" "){e.preventDefault();$("seq-play").click();}
  });
  window.addEventListener("beforeunload",e=>{if(sequence.dirty){seqDraft();e.preventDefault();e.returnValue="";}});
  document.querySelectorAll("[data-tab]").forEach(b=>b.addEventListener("click",()=>{if(b.dataset.tab!=="edit"){seqPause();sequence.drawMask=false;sequence.objectPick=false;$("seq-stage").classList.remove("seq-drawing");draw.setAttribute("aria-pressed","false");}}));
  seqControls();
  let scrollFrame=0;$("seq-timeline").addEventListener("scroll",()=>{const root=$("seq-timeline");if(sequence.timelineDrag||scrollFrame||sequence.viewportLeft===root.scrollLeft&&sequence.viewportTop===root.scrollTop)return;scrollFrame=requestAnimationFrame(()=>{scrollFrame=0;if(!sequence.timelineDrag)seqTimeline();});});
  new ResizeObserver(()=>seqMonitor()).observe($("seq-stage").parentElement);
}
function seqRefreshProjects(){
  if(!$("seq-project"))return;const projects=state.projects.filter(p=>!p.kind||['edit','hybrid'].includes(p.kind));const signature=JSON.stringify(projects.map(p=>[p.id,p.name]));if(signature===sequence.projectsSignature)return;
  sequence.projectsSignature=signature;const select=$("seq-project"),selected=select.value;select.replaceChildren();const placeholder=element("option","","Chọn dự án…");placeholder.value="";select.append(placeholder);
  for(const p of projects){const option=element("option","",p.name);option.value=p.id;select.append(option);}select.value=sequence.id||selected;
}
function seqRequire(){if(!sequence.doc)throw Error("Chọn dự án và bấm Mở, hoặc tạo dự án mới.");}
function seqSelection(){for(const track of sequence.doc?.tracks||[]){const clip=track.clips.find(c=>c.id===sequence.selected);if(clip)return {track,clip};}return {track:sequence.doc?.tracks.find(t=>t.id===sequence.selected)};}
function seqDraft(){if(sequence.id&&sequence.doc)try{localStorage.setItem("rv-editor-"+sequence.id,JSON.stringify({base:sequence.doc.revision,doc:sequence.doc,dirty:sequence.dirty,at:Date.now()}));}catch{toast("Không lưu được bản nháp trình duyệt. Bấm Lưu hoặc tải JSON.",true);}}
async function seqOpen(id){
  if(sequence.busy)throw Error("Chờ tác vụ editor hoàn tất.");if(!id)throw Error("Chọn dự án.");
  if(sequence.dirty){await seqSave();if(sequence.dirty)throw Error("Lưu hoặc tải bản nháp trước khi đổi dự án.");}
  const data=await api("projects/"+id+"/timeline");seqPause();clearTimeout(sequence.timer);seqClearMonitor();
  Object.assign(sequence,{id,doc:data.timeline,media:new Map(data.media.map(m=>[m.id,m])),undo:[],redo:[],selected:"",selection:new Set(),outputFiles:null,time:0,dirty:false,blocked:false,rendered:null,drawMask:false});
  $("seq-stage").classList.remove("seq-drawing");$("seq-drawmask").setAttribute("aria-pressed","false");
  let draft;try{draft=JSON.parse(localStorage.getItem("rv-editor-"+id)||"null");}catch{toast("Bản nháp không đọc được. Dự án đã lưu vẫn được giữ.",true);}
  if(draft?.dirty){
    if(draft.base===data.timeline.revision&&confirm("Có bản nháp chưa lưu của dự án này. Khôi phục?")){
      for(const key of new Set([...draft.doc.assets,...draft.doc.tracks.flatMap(t=>t.clips.map(c=>c.asset).filter(Boolean))]))if(!sequence.media.has(key))sequence.media.set(key,await api("projects/"+id+"/editor-media/"+key));
      sequence.doc=draft.doc;sequence.dirty=true;seqScheduleSave();
    }
    else if(draft.base!==data.timeline.revision){sequence.blocked=true;toast("Có bản nháp cũ khác revision. Bấm Tải bản nháp JSON để giữ bản cũ. Không tự ghi đè dự án.",true);}
  }
  $("seq-output").replaceChildren();$("seq-status").textContent="Đã mở · revision "+sequence.doc.revision;seqRefreshProjects();$("seq-project").value=id;seqRefresh();
}
function seqChange(fn){
  seqRequire();if(sequence.blocked)throw Error("Giữ bản nháp khác revision. Tải JSON trước khi tiếp tục.");if(sequence.busy)throw Error("Chờ tác vụ hoàn tất.");seqPause();const before=seqCopy(sequence.doc),selection={selected:sequence.selected,selection:new Set(sequence.selection),time:sequence.time};
  try{fn();if(sequence.doc.tracks.length>SEQ_MAX_TRACKS)throw Error('Tối đa 64 track.');if(sequence.doc.tracks.flatMap(t=>t.clips).length>500||sequence.doc.tracks.filter(t=>["video","audio"].includes(t.kind)).flatMap(t=>t.clips).length>100)throw Error("Tối đa 500 clip, trong đó 100 clip media.");}catch(e){sequence.doc=before;Object.assign(sequence,selection);seqRefresh();throw e;}
  if(JSON.stringify(before)===JSON.stringify(sequence.doc))return;
  sequence.undo.push(before);if(sequence.undo.length>50)sequence.undo.shift();sequence.redo=[];seqModified();
}
function seqModified(){sequence.dirty=true;sequence.generation++;if(sequence.rendered){sequence.rendered=null;seqClearMonitor();}$("seq-output").replaceChildren();seqDraft();seqScheduleSave();seqRefresh();}
function seqHistory(redo){
  if(!sequence.doc||sequence.busy||sequence.blocked)return;const from=redo?sequence.redo:sequence.undo,to=redo?sequence.undo:sequence.redo;if(!from.length)return;
  seqPause();const revision=sequence.doc.revision;to.push(seqCopy(sequence.doc));sequence.doc=from.pop();sequence.doc.revision=revision;seqModified();
}
function seqScheduleSave(){clearTimeout(sequence.timer);sequence.timer=setTimeout(()=>seqSave().catch(e=>{toast(e.message,true);}),1200);}
async function seqSave(){
  seqRequire();if(sequence.blocked)throw Error("Dừng tự lưu để bảo vệ bản nháp khác revision. Mở lại dự án sau khi xử lý bản nháp.");
  if(sequence.busy)return;if(sequence.saving){await sequence.saving;return sequence.dirty?seqSave():undefined;}if(!sequence.dirty)return;
  const generation=sequence.generation,id=sequence.id,value=seqCopy(sequence.doc);$("seq-status").textContent="Đang lưu…";
  sequence.saving=api("projects/"+id+"/timeline",value);
  try{const saved=await sequence.saving;sequence.doc.revision=saved.revision;sequence.dirty=sequence.generation!==generation;seqDraft();if($('seq-source-repair'))$('seq-source-repair').hidden=true;$("seq-status").textContent=sequence.dirty?"Có thay đổi mới…":"Đã tự lưu · revision "+saved.revision;}
  catch(e){if(/đang xử lý/.test(e.message)){seqScheduleSave();return;}if(/phiên khác|ghi đè/.test(e.message))sequence.blocked=true;$("seq-status").textContent="Chưa lưu · bản nháp giữ trên máy";if(/Clip vượt quá thời lượng nguồn/.test(e.message)&&$('seq-source-repair')){$('seq-source-repair').hidden=false;toast('Bản nháp giữ nguyên. Bấm Căn clip vượt nguồn cạnh Lưu để duyệt sửa độ dài.',true);}throw e;}
  finally{sequence.saving=null;seqControls();}
  if(sequence.dirty)seqScheduleSave();
}
async function seqJob(kind,payload){
  const project=payload.project_id||sequence.id,job=await api("jobs",{kind,payload:{...payload,project_id:project,ui_tab:"edit"}});
  while(true){await new Promise(resolve=>setTimeout(resolve,700));const row=await api("jobs/"+job.id);if(sequence.id===project)$("seq-status").textContent=Math.round(row.progress)+"% · "+row.message;
    if(row.status==="complete")return row.result;if(!["queued","running"].includes(row.status))throw Error(row.message);
  }
}
async function seqImport(id){
  if(!sequence.doc.assets.includes(id)&&sequence.doc.assets.length>=200)throw Error("Thư viện tối đa 200 media.");
  const result=await seqJob("editor_media",{asset:id});sequence.media.set(id,result.media);
  // Import loop owns busy state; commit media without enabling unrelated edits.
  if(!sequence.doc.assets.includes(id)){sequence.undo.push(seqCopy(sequence.doc));sequence.doc.assets.push(id);sequence.redo=[];seqModified();}
}
function seqAddTrack(kind){seqChange(()=>{if(sequence.doc.tracks.length>=SEQ_MAX_TRACKS)throw Error("Tối đa 64 track.");const id=seqId();sequence.doc.tracks.push({id,name:(kind==="audio"?"Audio ":"Video ")+(sequence.doc.tracks.length+1),kind,locked:false,hidden:false,muted:false,clips:[]});sequence.selected=id;});}
function seqAddVisual(kind,region={}){
  const text=kind==="text"?"Tiêu đề của bạn":"";
  seqChange(()=>{if(sequence.doc.tracks.length>=SEQ_MAX_TRACKS||sequence.doc.tracks.flatMap(t=>t.clips).length>=500)throw Error("Đạt giới hạn track/clip.");
    const clip={id:seqId(),asset:"",label:kind==="blur"?"Vùng mờ":text.slice(0,80),text,start_ms:Math.round(sequence.time),in_ms:0,duration_ms:Math.min(5000,3_600_000-Math.round(sequence.time)),volume:1,...seqTransformDefaults,region_w:30,region_h:15,blur:12,font:"Arial",font_size:36,color:"#ffffff",box:false,...region};
    if(clip.duration_ms<100)throw Error("Không còn thời gian để thêm lớp.");sequence.doc.tracks.push({id:seqId(),name:kind==="blur"?"Vùng mờ":"Chữ",kind,locked:false,hidden:false,muted:false,clips:[clip]});sequence.selected=clip.id;
  });
}
function seqLiveField(input,track,clip,key,valid){
  let before=null;
  const value=()=>input.type==="checkbox"?input.checked:['number','range'].includes(input.type)?Number(input.value):input.value;
  input.oninput=()=>{const next=value();if(track.locked||sequence.busy||sequence.blocked||!valid(next))return;
    if(track.kind==="video"&&Object.keys(seqTransformDefaults).includes(key)&&clip.keyframes?.length>=64&&!clip.keyframes.some(p=>p.ms===Math.max(0,Math.min(clip.duration_ms,Math.round(sequence.time-clip.start_ms))))){toast("Tối đa 64 mốc; chọn mốc có sẵn hoặc xóa bớt.",true);return;}
    if(!before){before=seqCopy(sequence.doc);sequence.undo.push(before);sequence.redo=[];}seqPause();if(track.kind==="video"&&Object.keys(seqTransformDefaults).includes(key))seqSetPosition(clip,sequence.time,{[key]:next});else clip[key]=next;if(key==="text"){clip.label=next.slice(0,80);clip.word_cues=[];}
    sequence.time=Math.max(clip.start_ms,Math.min(sequence.time,clip.start_ms+clip.duration_ms-1));
    if(sequence.rendered){sequence.rendered=null;seqClearMonitor();}sequence.dirty=true;sequence.generation++;$("seq-output").replaceChildren();seqDraft();seqScheduleSave();seqControls();seqMonitor();
  };
  input.onchange=()=>{try{const next=value();if(!valid(next))throw Error("Giá trị ngoài phạm vi.");if(before){before=null;seqRefresh();}else seqEditSelected((t,c)=>{if(t.kind==="video"&&Object.keys(seqTransformDefaults).includes(key))seqSetPosition(c,sequence.time,{[key]:next});else c[key]=next;});}catch(e){before=null;seqProperties();toast(e.message,true);}};
}
async function seqImportCaptions(){
  seqRequire();const id=sequence.id,project=await api("projects/"+id);if(!project.cues?.length)throw Error("Nhập SRT hoặc nhận dạng trong tab Lồng tiếng trước, rồi chọn cùng dự án tại đây.");
  if(!confirm("Sao chép lời đọc tiếng Việt (nếu có), hoặc bản dịch/nguyên văn và timeline sang track chữ. Không sửa cue lồng tiếng. Tiếp tục?"))return;
  if(sequence.id!==id)throw Error("Dự án đã đổi; nhập lại.");
  seqChange(()=>{const rows=project.cues.map(c=>({id:seqId(),asset:"",label:(c.text||c.source_text||"").slice(0,80),text:c.text||c.source_text||"",start_ms:c.start_ms,in_ms:0,duration_ms:c.end_ms-c.start_ms,volume:1,x:50,y:88,font:"Arial",font_size:36,color:"#ffffff",box:true}));
    if(rows.some(c=>!c.text.trim()||c.duration_ms<100||c.start_ms<0||c.start_ms+c.duration_ms>3_600_000))throw Error("Phụ đề có cue trống/ngắn hơn 100ms hoặc vượt 60 phút. Kiểm tra trước khi nhập.");
    if(sequence.doc.tracks.flatMap(t=>t.clips).length+rows.length>500)throw Error("Tối đa 500 clip gồm cả phụ đề.");
    const tracks=[];for(const c of rows){let t=tracks.find(t=>!seqOverlap(t,c,""));if(!t){t={id:seqId(),name:"Phụ đề "+(tracks.length+1),kind:"text",locked:false,hidden:false,muted:false,clips:[]};tracks.push(t);}t.clips.push(c);}
    if(sequence.doc.tracks.length+tracks.length>SEQ_MAX_TRACKS)throw Error("Quá nhiều cue chồng nhau; tối đa 64 track.");sequence.doc.tracks.push(...tracks);sequence.selected=rows[0].id;sequence.time=rows[0].start_ms;
  });
}
function seqAddClip(id){
  seqChange(()=>{
    const asset=sequence.media.get(id);let {track}=seqSelection();const kind=track?.kind==="audio"&&asset.has_audio?"audio":asset.kind==="audio"?"audio":"video";
    if(!track||track.kind!==kind){track=sequence.doc.tracks.find(t=>t.kind===kind&&!t.locked);if(!track){if(sequence.doc.tracks.length>=SEQ_MAX_TRACKS)throw Error("Tối đa 64 track.");track={id:seqId(),name:kind==="audio"?"Audio":"Video",kind,locked:false,hidden:false,muted:false,clips:[]};sequence.doc.tracks.push(track);}}
    if(track.locked)throw Error("Track đang khóa.");if(sequence.doc.tracks.flatMap(t=>t.clips).length>=500||sequence.doc.tracks.filter(t=>["video","audio"].includes(t.kind)).flatMap(t=>t.clips).length>=100)throw Error("Tối đa 100 clip media, tổng cộng 500 clip.");
    const clip={id:seqId(),asset:id,label:asset.name,start_ms:Math.round(sequence.time),in_ms:0,duration_ms:asset.kind==="image"?5000:Math.min(asset.duration_ms,3_600_000),volume:1};
    if(seqOverlap(track,clip,""))clip.start_ms=Math.max(0,...track.clips.map(c=>c.start_ms+c.duration_ms));
    if(clip.start_ms+clip.duration_ms>3_600_000)throw Error("Timeline tối đa 60 phút.");track.clips.push(clip);sequence.selected=clip.id;sequence.time=clip.start_ms;
  });
}
function seqEditSelected(fn){seqChange(()=>{const {track,clip}=seqSelection();if(!clip)throw Error("Chọn một clip trên timeline.");if(track.locked)throw Error("Mở khóa track trước khi sửa.");const old=clip.text;fn(track,clip);if(old!==clip.text&&clip.word_cues?.length&&clip.text.split(/\s+/u).filter(Boolean).join(' ')!==clip.word_cues.map(w=>w.word).join(' '))clip.word_cues=[];});}
function seqRefresh(){seqLibrary();seqTimeline();seqProperties();seqMonitor();seqControls();}
function seqControls(){
  const disabled=!sequence.doc||sequence.busy||sequence.blocked;
  for(const id of ["seq-save","seq-files","seq-import-main","seq-video-track","seq-audio-track","seq-drawmask","seq-split","seq-merge","seq-copy","seq-delete","seq-preview","seq-export","seq-export-quality","seq-ratio","seq-fps"]){if($(id))$(id).disabled=disabled;}
  $("seq-open").disabled=sequence.busy;$("seq-new").disabled=sequence.busy;$("seq-undo").disabled=disabled||!sequence.undo.length;$("seq-redo").disabled=disabled||!sequence.redo.length;
  $("seq-resolve").hidden=!sequence.blocked;$("seq-conflict-download").hidden=!sequence.id||!localStorage.getItem("rv-editor-conflict-last-"+sequence.id);
  if(sequence.dirty&&!sequence.busy&&!sequence.saving)$("seq-status").textContent=sequence.blocked?"Xung đột revision · giữ bản nháp":"Chưa lưu · bản nháp trên máy";
}
function seqLibrary(){
  const list=$("seq-library");list.replaceChildren();for(const asset of sequence.media.values()){
    const button=seqButton("",()=>seqAddClip(asset.id));button.className="seq-media";button.disabled=sequence.busy;button.title="Thêm "+asset.name;
    if(asset.thumbnail){const img=element("img");img.src=asset.thumbnail;img.alt="";button.append(img);}button.append(element("span","",asset.name+" · "+(asset.kind==="image"?"Ảnh":(asset.duration_ms/1000).toFixed(1)+"s")));list.append(button);
  }
}
function seqProperties(){
  const root=$("seq-properties"),panel=root.parentElement,identity=sequence.id+":"+sequence.selected;
  const same=panel.dataset.selection===identity,top=same?panel.scrollTop:0;
  const controls=[...root.querySelectorAll('input,select,textarea,button')],focus=same?controls.indexOf(document.activeElement):-1;
  const nested=[...root.querySelectorAll('.seq-keyframes')].map(n=>n.scrollTop);
  seqBuildProperties();panel.dataset.selection=identity;
  if(focus>=0)root.querySelectorAll('input,select,textarea,button')[focus]?.focus({preventScroll:true});
  root.querySelectorAll('.seq-keyframes').forEach((n,i)=>n.scrollTop=nested[i]||0);
  panel.scrollTop=top;
}
function seqBuildProperties(){
  const root=$("seq-properties");root.replaceChildren();if(!sequence.doc)return;
  $("seq-ratio").value=sequence.doc.width+"x"+sequence.doc.height;$("seq-fps").value=sequence.doc.fps;
  const quality=$('seq-export-quality'),short=String(Math.min(sequence.doc.width,sequence.doc.height));if(quality){quality.value=['720','1080','1440','2160'].includes(short)?short:'canvas';quality.title=`Đầu ra ${sequence.doc.width}×${sequence.doc.height}; thay đổi canvas, giữ tỷ lệ.`;}
  const {track,clip}=seqSelection();if(!clip){root.append(element("p","hint","Chọn clip để chỉnh. Video trên track cao hơn trong thứ tự dựng che video phía dưới; track mới được đặt trên cùng."));return;}
  const clipName=element("strong","seq-clip-name",clip.label);clipName.title=clip.label;root.append(clipName);
  if(clip.asset&&clip.volume>1)root.append(element("p","hint","Xem nhanh phát âm lượng tối đa 1; bản xuất giữ mức bạn đặt."));
  for(const [key,label,factor,step] of [["start_ms","Bắt đầu timeline (s)",1000,.01],["in_ms","Điểm đầu nguồn (s)",1000,.01],["duration_ms","Thời lượng (s)",1000,.01],["volume","Âm lượng (0–2)",1,.05]]){
    if(!clip.asset&&["in_ms","volume"].includes(key))continue;
    const field=element("label","field",label),input=element("input");input.type="number";input.step=step;input.min=key==="duration_ms"?.1:0;input.max=key==="volume"?2:3600;input.value=clip[key]/factor;input.disabled=track.locked||sequence.busy;
    input.onchange=()=>{try{seqEditSelected((t,c)=>{const next={...c,[key]:key==="volume"?Number(input.value):Math.round(Number(input.value)*factor)},asset=sequence.media.get(c.asset);
      if(!Number.isFinite(next[key])||next.start_ms<0||next.in_ms<0||next.duration_ms<100||next.volume<0||next.volume>2||next.start_ms+next.duration_ms>3_600_000||asset?.kind==="image"&&next.in_ms!==0||asset&&asset.kind!=="image"&&seqSourceMs(next,next.duration_ms)>asset.duration_ms+1||seqOverlap(t,next,c.id))throw Error("Thông số không hợp lệ, vượt nguồn hoặc chồng clip cùng track.");if(key==="duration_ms")Object.assign(next,seqAnimationRange(c,0,next.duration_ms));Object.assign(c,next);
    });}catch(e){toast(e.message,true);seqProperties();}};field.append(input);root.append(field);
  }
  if(clip.asset&&sequence.media.get(clip.asset)?.kind!=="image"){
    const field=element("label","field","Tốc độ clip · giữ cao độ (0,25–4×)"),input=element("input");input.id="seq-speed";Object.assign(input,{type:"number",min:.25,max:4,step:.05,value:clip.speed??1,disabled:track.locked||sequence.busy});
    input.onchange=()=>{try{seqEditSelected((t,c)=>{const next=seqRetime(c,Number(input.value)),asset=sequence.media.get(c.asset);if(seqOverlap(t,next,c.id)||seqSourceMs(next,next.duration_ms)>asset.duration_ms+2)throw Error("Tốc độ làm clip chồng đoạn khác hoặc vượt nguồn; chuyển track/dời clip trước.");Object.assign(c,next);});}catch(e){seqProperties();toast(e.message,true);}};field.append(input);root.append(field);
    const curve=element('select');curve.id='seq-speed-curve';for(const [value,title] of [['ramp','Curve · chậm → nhanh'],['down','Curve · nhanh → chậm'],['pulse','Curve · nhanh–chậm–nhanh']]){const option=element('option','',title);option.value=value;curve.append(option);}root.append(curve);
    root.append(seqButton('Áp dụng curve mượt',()=>seqEditSelected((t,c)=>{const points=seqSmoothCurve(c,curve.value),next={...c,speed_curve:points},asset=sequence.media.get(c.asset);if(asset?.duration_ms&&seqSourceMs(next,c.duration_ms)>asset.duration_ms+1)throw Error('Curve vượt thời lượng nguồn.');c.speed_curve=points;})));
    root.append(seqButton('◆ Thêm mốc tốc độ tại con trỏ',()=>seqEditSelected((t,c)=>{const ms=Math.round(sequence.time-c.start_ms);if(ms<0||ms>c.duration_ms)throw Error('Tua vào clip trước.');const points=c.speed_curve?.length?seqCopy(c.speed_curve):[{ms:0,speed:c.speed??1},{ms:c.duration_ms,speed:c.speed??1}];if(points.some(p=>p.ms===ms))return;if(points.length>=16)throw Error('Tối đa 16 mốc tốc độ.');points.push({ms,speed:seqSpeedAt(c,ms)});c.speed_curve=points.sort((a,b)=>a.ms-b.ms);}))); 
    for(const point of clip.speed_curve||[]){const row=element('div','actions'),time=element('input'),rate=element('input');Object.assign(time,{type:'number',min:0,max:clip.duration_ms/1000,step:.01,value:point.ms/1000,disabled:track.locked||sequence.busy||point.ms===0||point.ms===clip.duration_ms});Object.assign(rate,{type:'number',min:.25,max:4,step:.05,value:point.speed,disabled:track.locked||sequence.busy});time.setAttribute('aria-label','Mốc tốc độ (s)');rate.setAttribute('aria-label','Tốc độ tại mốc');
      const commit=()=>{try{seqEditSelected((t,c)=>{const points=c.speed_curve.map(p=>p.ms===point.ms?{ms:Math.round(Number(time.value)*1000),speed:Number(rate.value)}:{...p}).sort((a,b)=>a.ms-b.ms);if(points.some(p=>!Number.isFinite(p.ms)||!Number.isFinite(p.speed)||p.ms<0||p.ms>c.duration_ms||p.speed<.25||p.speed>4)||new Set(points.map(p=>p.ms)).size!==points.length)throw Error('Mốc tốc độ không hợp lệ/trùng.');if(seqSourceMs({...c,speed_curve:points},c.duration_ms)>sequence.media.get(c.asset).duration_ms+1)throw Error('Curve đọc vượt nguồn; giảm tốc độ/trim điểm đầu.');c.speed_curve=points;});}catch(e){toast(e.message,true);seqProperties();}};time.onchange=rate.onchange=commit;row.append(time,element('span','','s →'),rate,element('span','','×'));root.append(row);}
    if(clip.speed_curve?.length)root.append(seqButton('Bỏ curve · giữ lượng nguồn',()=>seqEditSelected((t,c)=>{c.speed=Math.max(.25,Math.min(4,(seqSourceMs(c,c.duration_ms)-c.in_ms)/c.duration_ms));c.speed_curve=[];})));
    root.append(element('small','seq-warning','Curve mượt giữ độ dài clip, không dời track khác. Video dùng ánh xạ thời gian chính xác; audio thay tempo từng 20ms, có sai số DSP nhỏ. Tối đa 16 mốc, 0,25–4×.'));
    root.append(seqButton('Áp dụng curve theo đoạn',()=>seqEditSelected((t,c)=>{const rates={ramp:[.5,.75,1,1.5,2],down:[2,1.5,1,.75,.5],pulse:[2,1,.5,1,2]}[curve.value],rows=seqSpeedCurve(c,rates,seqId),oldEnd=c.start_ms+c.duration_ms,newEnd=rows.at(-1).start_ms+rows.at(-1).duration_ms,delta=newEnd-oldEnd;
      if(sequence.doc.tracks.flatMap(t=>t.clips).length+rows.length-1>500||sequence.doc.tracks.filter(t=>['video','audio'].includes(t.kind)).flatMap(t=>t.clips).length+rows.length-1>100)throw Error('Curve vượt giới hạn clip.');
      if(t.clips.some(k=>k.id!==c.id&&k.start_ms>=oldEnd&&k.start_ms+k.duration_ms+delta>3_600_000))throw Error('Curve vượt 60 phút.');
      for(const k of t.clips)if(k.id!==c.id&&k.start_ms>=oldEnd)k.start_ms+=delta;t.clips.splice(t.clips.indexOf(c),1,...rows);
    })));
    root.append(element('small','seq-warning','Chế độ theo đoạn: chia thành 5 clip tốc độ cố định, dời clip sau trên cùng track. Dùng Curve mượt phía trên nếu muốn nội suy liên tục. Có thể Hoàn tác.'));
  }
  const field=element("label","field","Chuyển sang track"),select=element("select");for(const t of sequence.doc.tracks.filter(t=>t.kind===track.kind)){const o=element("option","",t.name);o.value=t.id;select.append(o);}select.value=track.id;select.disabled=track.locked||sequence.busy;
  select.onchange=()=>{try{seqEditSelected((t,c)=>{const target=sequence.doc.tracks.find(r=>r.id===select.value);if(target.locked||seqOverlap(target,c,""))throw Error("Track đích khóa hoặc có clip chồng nhau.");t.clips.splice(t.clips.indexOf(c),1);target.clips.push(c);});}catch(e){toast(e.message,true);seqProperties();}};field.append(select);root.append(field);
  if(track.kind!=="audio"){
    root.append(element("strong","","Bố cục · thay đổi hiện ngay"));
    for(const [key,label,min,max,step] of [["x","Tâm ngang (%)",-100,200,1],["y","Tâm dọc (%)",-100,200,1],["scale","Phóng to/thu nhỏ",.05,4,.05],["rotation","Xoay (độ)",-180,180,1],["opacity","Độ hiện (0–1)",0,1,.05]]){
      if(track.kind==="blur"&&!Object.keys(seqTransformDefaults).includes(key))continue;
      const field=element("label","field",label),input=element("input");input.type="number";Object.assign(input,{min,max,step,value:Math.round((track.kind==="video"&&Object.keys(seqTransformDefaults).includes(key)?seqMotionValues(clip,sequence.time-clip.start_ms)[key]:seqTransform(clip)[key])*1000)/1000,disabled:track.locked||sequence.busy});if(track.kind==="video"&&Object.keys(seqTransformDefaults).includes(key))input.dataset.motion=key;
      seqLiveField(input,track,clip,key,value=>Number.isFinite(value)&&value>=min&&value<=max&&(track.kind!=="blur"||value>=0&&value<=100));field.append(input);root.append(field);
    }
    root.append(seqButton("Đặt lại bố cục",()=>seqEditSelected((t,c)=>{Object.assign(c,seqTransformDefaults);c.keyframes=[];})));
    for(const [text,delta] of [["Đưa lớp lên",1],["Đưa lớp xuống",-1]])root.append(seqButton(text,()=>seqChange(()=>{if(track.locked)throw Error("Track đang khóa.");const i=sequence.doc.tracks.indexOf(track),j=i+delta;if(j<0||j>=sequence.doc.tracks.length)return;[sequence.doc.tracks[i],sequence.doc.tracks[j]]=[sequence.doc.tracks[j],sequence.doc.tracks[i]];})));
  }
  if(track.kind==="video"){
    root.append(element("strong","","Lật hình · cả clip / theo đoạn"));
    for(const [key,title] of [['flip_h','Lật trái ↔ phải'],['flip_v','Lật trên ↔ dưới']]){
      const field=element('label','field',title),input=element('input');input.type='checkbox';input.id='seq-'+key;input.checked=!!clip[key];input.disabled=track.locked||sequence.busy;seqLiveField(input,track,clip,key,value=>typeof value==='boolean');field.append(input);root.append(field);
    }
    const range=[];for(const [title,value] of [['Từ timeline (s)',clip.start_ms/1000],['Đến timeline (s)',(clip.start_ms+clip.duration_ms)/1000]]){const field=element('label','field',title),input=element('input');Object.assign(input,{type:'number',min:clip.start_ms/1000,max:(clip.start_ms+clip.duration_ms)/1000,step:.01,value,disabled:track.locked||sequence.busy});field.append(input);root.append(field);range.push(input);}
    const flipAxis=element('select');flipAxis.id='seq-flip-axis';flipAxis.setAttribute('aria-label','Hướng lật đoạn');for(const [value,title] of [['flip_h','Trái ↔ phải'],['flip_v','Trên ↔ dưới']]){const option=element('option','',title);option.value=value;flipAxis.append(option);}flipAxis.disabled=track.locked||sequence.busy;root.append(flipAxis);
    const flipButton=seqButton('Lật đoạn đã chọn',()=>seqEditSelected((t,c)=>{const result=seqFlipRange(c,Number(range[0].value)*1000,Number(range[1].value)*1000,flipAxis.value,[seqId(),seqId()],sequence.media.get(c.asset)?.kind==='image');t.clips.splice(t.clips.indexOf(c),1,...result.clips);sequence.selected=result.selected;sequence.selection=new Set([result.selected]);sequence.time=Math.round(Number(range[0].value)*1000);}));flipButton.id='seq-flip-range';flipButton.disabled=track.locked||sequence.busy;root.append(flipButton);
    root.append(element('small','seq-warning','Chỉ tách và lật đoạn này; không đổi timeline hay file gốc.'));
    root.append(element("strong","","Keyframe · bố cục"));
    const easingField=element("label","field","Kiểu chuyển động"),easing=element("select");easing.id="seq-motion-easing";for(const [value,title] of [["linear","Đều"],["smooth","Mềm đầu/cuối"],["hold","Giữ rồi đổi vị trí"]]){const option=element("option","",title);option.value=value;easing.append(option);}easing.value=clip.motion_easing||"linear";easing.disabled=track.locked||sequence.busy;easing.onchange=()=>{try{seqEditSelected((t,c)=>c.motion_easing=easing.value);}catch(e){toast(e.message,true);}};easingField.append(easing);root.append(easingField);
    root.append(seqButton("◆ Lưu bố cục tại con trỏ",()=>seqEditSelected((t,c)=>{if(sequence.time<c.start_ms||sequence.time>c.start_ms+c.duration_ms)throw Error("Tua vào khoảng của clip trước.");seqRecordPosition(c,sequence.time-c.start_ms,seqMotionValues(c,sequence.time-c.start_ms));})));
    const list=element("div","seq-keyframes");
    for(const p of clip.keyframes||[]){const row=element("div","actions");row.append(seqButton("◆ "+(p.ms/1000).toFixed(2)+"s · "+p.x.toFixed(1)+", "+p.y.toFixed(1),()=>{seqPause();sequence.time=clip.start_ms+p.ms;seqProperties();seqMonitor();}),seqButton("×",()=>seqEditSelected((t,c)=>{const layout=seqMotionValues(c,p.ms);c.keyframes=c.keyframes.filter(k=>k.ms!==p.ms);if(!c.keyframes.length)Object.assign(c,layout);})));list.append(row);}const help=element("small","seq-warning","Kéo/zoom/xoay/sửa độ hiện để ghi mốc.");help.title="Sau khi có mốc: tua rồi chỉnh bố cục để thêm/cập nhật mốc. Phát để xem chuyển động.";root.append(list,help);
    root.append(element("strong","","Nền / lớp phủ / hòa trộn"));
    for(const [key,title,options] of [["fit","Lấp khung",[["contain","Giữ toàn hình"],["cover","Lấp đầy / cắt viền"]]],["blend","Hòa trộn",[["normal","Bình thường / lớp phủ"],["screen","Screen · bỏ nền đen"],["multiply","Multiply · bỏ nền trắng"],["addition","Cộng sáng"]]]]){
      const field=element("label","field",title),select=element("select");for(const [value,label] of options){const o=element("option","",label);o.value=value;select.append(o);}select.value=clip[key]||(key==="fit"?"contain":"normal");select.disabled=track.locked||sequence.busy;
      select.onchange=()=>{try{seqEditSelected((t,c)=>{c[key]=select.value;});}catch(e){toast(e.message,true);}};field.append(select);root.append(field);
    }
    root.append(seqButton("Đặt làm nền dưới cùng",()=>seqChange(()=>{if(track.locked)throw Error("Track đang khóa.");sequence.doc.tracks.splice(sequence.doc.tracks.indexOf(track),1);sequence.doc.tracks.unshift(track);clip.x=clip.y=50;clip.scale=1;clip.rotation=0;clip.opacity=1;clip.fit="cover";clip.blend="normal";clip.keyframes=[];})));
    root.append(element("small","seq-warning","Nền là track dưới cùng; ảnh/video khác là lớp phủ. Tắt tiếng track hiệu ứng nếu chỉ cần hình."));
  }
  if(track.kind!=="blur"){
    if(track.kind==='video'){
      root.append(element('strong','','Bộ lọc màu'));
      root.append(seqButton('✦ Chọn từ kho trực quan',seqCreativeOpen));
      const field=element('label','field','Cường độ bộ lọc'),input=element('input');Object.assign(input,{type:'range',min:0,max:1,step:.05,value:clip.filter_strength??1,disabled:track.locked||sequence.busy});seqLiveField(input,track,clip,'filter_strength',v=>Number.isFinite(v)&&v>=0&&v<=1);field.append(input);root.append(field,seqButton('Bỏ bộ lọc',()=>seqEditSelected((t,c)=>{c.color_filter='none';})));
    }
    if(track.kind==='video'&&clip.asset){
      root.append(element('strong','','AI · hình ảnh'));
      root.append(seqButton('✧ Căn mặt / tracking theo mẫu',()=>seqVisualAI('face')),seqButton('✧ Tách nền hình / video',()=>seqVisualAI('background')));
      root.append(element('small','seq-warning','CPU riêng · INSTALL_VISION.bat. Căn mặt tối đa 60s; tách nền video 15s nguồn, 720px/12fps. Hình trong suốt thêm vào thư viện, không sửa nguồn.'));
    }
    if(clip.asset&&sequence.media.get(clip.asset)?.has_audio){
      root.append(element('strong','','AI · âm thanh'));
      root.append(seqButton('✧ Tách giọng / nhạc toàn file',async()=>{
        if(!confirm('Demucs tách toàn file nguồn trên CPU, không chỉ khoảng clip. Có thể mất nhiều phút; lần đầu cần tải model. Kết quả thêm vào thư viện, không tự thay tiếng gốc. Tiếp tục?'))return;
        const project=sequence.id,asset=clip.asset;sequence.busy=true;seqControls();
        try{const result=await seqJob('editor_separate',{project_id:project,asset});
          if(sequence.id!==project){toast('Tách xong. Mở kết quả trong Lịch sử; dự án đang mở không thay đổi.');return;}
          if(new Set([...sequence.doc.assets,...result.media_items.map(i=>i.id)]).size>200)throw Error('Thư viện đã đầy; kết quả vẫn lưu trong thư mục editor.');
          for(const item of result.media_items)sequence.media.set(item.id,item);
          sequence.busy=false;
          seqChange(()=>{for(const item of result.media_items)if(!sequence.doc.assets.includes(item.id))sequence.doc.assets.push(item.id);});toast(result.message);
        }finally{sequence.busy=false;seqControls();if(sequence.dirty)seqScheduleSave();}
      }));
      root.append(element('small','seq-warning','Kết quả vocals/no_vocals nằm ở thư viện: chọn track audio rồi bấm file để thêm. Tắt tiếng track gốc nếu dùng nhạc tách.'));
    }
    root.append(element("strong","","Hiệu ứng vào / ra"));
    for(const [key,title] of [["fade_in_ms","Mờ / âm lượng vào (s)"],["fade_out_ms","Mờ / âm lượng ra (s)"]]){const field=element("label","field",title),input=element("input");Object.assign(input,{type:"number",min:0,max:Math.min(10,clip.duration_ms/1000),step:.05,value:(clip[key]||0)/1000,disabled:track.locked||sequence.busy});input.onchange=()=>{try{seqEditSelected((t,c)=>{const value=Math.round(Number(input.value)*1000),other=key==="fade_in_ms"?c.fade_out_ms:c.fade_in_ms;if(!Number.isFinite(value)||value<0||value>10000||value+(other||0)>c.duration_ms)throw Error("Tổng vào/ra phải nằm trong thời lượng clip, tối đa 10s mỗi phía.");c[key]=value;});}catch(e){seqProperties();toast(e.message,true);}};field.append(input);root.append(field);}
    if(track.kind==="video")root.append(seqButton("Mờ nối clip sau qua nền",()=>seqEditSelected((t,c)=>{const next=[...t.clips].sort((a,b)=>a.start_ms-b.start_ms).find(k=>k.start_ms===c.start_ms+c.duration_ms);if(!next)throw Error("Cần clip kế tiếp liền nhau trên cùng track.");const value=Math.min(500,c.duration_ms-(c.fade_in_ms||0),next.duration_ms-(next.fade_out_ms||0));if(value<1)throw Error("Không còn khoảng cho hiệu ứng.");c.fade_out_ms=value;next.fade_in_ms=value;})));
    if(track.kind==='video'){
      const kind=element('select');kind.id='seq-transition-kind';for(const [value,title] of [['crossfade','Crossfade · chồng hai hình'],['wipeleft','Wipe · từ trái'],['wiperight','Wipe · từ phải']]){const option=element('option','',title);option.value=value;kind.append(option);}root.append(kind);
      const seconds=element('input');Object.assign(seconds,{type:'number',min:.1,max:10,step:.1,value:.5});seconds.id='seq-transition-seconds';seconds.setAttribute('aria-label','Thời gian chuyển cảnh (s)');root.append(seconds);
      root.append(seqButton('Nối từ clip trước · chồng thật',()=>{if(!confirm('Đưa clip này lên track kế trên, bắt đầu sớm hơn để chồng clip trước. Bố cục clip này đổi thành lấp đầy canvas và bỏ keyframe; các clip khác giữ nguyên. Tiếp tục?'))return;seqChange(()=>{sequence.doc=seqTransition(sequence.doc,clip.id,kind.value,Math.round(Number(seconds.value)*1000),seqId);});}));
      if((clip.transition_in||'none')!=='none')root.append(seqButton('Bỏ chuyển cảnh hình',()=>seqEditSelected((t,c)=>{c.transition_in='none';c.transition_ms=0;})));
    }
    root.append(element("small","seq-warning","Chuyển cảnh thật chồng clip trên track riêng; âm nguồn crossfade. Bỏ chuyển cảnh không dời lại clip hay bỏ fade của clip trước; dùng Hoàn tác để khôi phục toàn bộ."));
  }
  if(track.kind==="text"){
    if(clip.word_cues?.length)root.append(element('small','hint',`${clip.word_cues.length} từ đã căn audio. Sửa nội dung sẽ bỏ mốc và trở về nhịp ước lượng; nhận dạng lại để căn chữ mới.`));
    root.append(element("strong","","Chữ / phụ đề"));
    const field=element("label","field","Nội dung"),input=element("textarea");input.value=clip.text;input.disabled=track.locked||sequence.busy;seqLiveField(input,track,clip,"text",value=>typeof value==="string"&&value.trim().length>0&&value.length<=3000);field.append(input);root.append(field);
    for(const [key,label,type,values] of [["font","Phông chữ","select",["Arial","Segoe UI","Times New Roman","Be Vietnam Pro"]],["color","Màu chữ","color"],["font_size","Cỡ chữ (pixel canvas)","number"],["box","Nền hộp chữ","checkbox"],['box_color','Màu nền hộp','color'],['box_opacity','Độ hiện nền (0–1)','number']]){
      const field=element("label","field",label),input=element(type==="select"?"select":"input");if(values)for(const value of values){const o=element("option","",value);o.value=value;input.append(o);}else input.type=type;
      input.dataset.textStyle=key;input.disabled=track.locked||sequence.busy;input.value=clip[key]??({font_size:36,color:'#ffffff',box_color:'#000000',box_opacity:.6}[key]??'Arial');input.checked=!!clip[key];input.min=key==='box_opacity'?0:10;input.max=key==='box_opacity'?1:160;input.step=key==='box_opacity'?.05:1;
      seqLiveField(input,track,clip,key,value=>key==='box_opacity'?Number.isFinite(value)&&value>=0&&value<=1:key!=="font_size"||Number.isInteger(value)&&value>=10&&value<=160);field.append(input);root.append(field);
    }
  }
  if(track.kind==="blur")root.append(element("strong","","Vùng mờ"));
  if(track.kind==="blur")for(const [key,label,min,max] of [["region_w","Rộng (%)",1,100],["region_h","Cao (%)",1,100],["blur","Độ mờ",1,40]]){
    const field=element("label","field",label),input=element("input");Object.assign(input,{type:"number",min,max,value:Math.round((clip[key]??(key==="blur"?12:key==="region_w"?30:15))*1000)/1000,disabled:track.locked||sequence.busy});seqLiveField(input,track,clip,key,value=>Number.isFinite(value)&&value>=min&&value<=max&&(key!=="blur"||Number.isInteger(value)));field.append(input);root.append(field);
  }
  seqGroupProperties(root);
}
function seqGroupProperties(root){
  let group=null;const children=[...root.children];
  const section=(key,title)=>{const details=element("details","seq-property-group"),summary=element("summary","",title);details.append(summary);details.open=localStorage.getItem("rv-seq-group-"+key)!=="closed";details.ontoggle=()=>localStorage.setItem("rv-seq-group-"+key,details.open?"open":"closed");root.append(details);return details;};
  for(const child of children){
    if(child.tagName==="STRONG"&&child!==children[0]){group=section(child.textContent,child.textContent);child.remove();}
    else if(child.classList.contains("field")&&!group){group=section("time","Thời gian & audio");group.append(child);}
    else if(group)group.append(child);
  }
}
function seqTimeline(){
  const root=$("seq-timeline"),scrollLeft=root.scrollLeft,scrollTop=root.scrollTop;root.replaceChildren();if(!sequence.doc)return;
  const width=Math.max(600,(seqLength(sequence.doc)/1000+5)*sequence.zoom),ruler=element("div","seq-ruler");ruler.style.width=(width+155)+"px";
  const visibleLeft=Math.max(0,scrollLeft-335),visibleRight=scrollLeft+Math.max(600,root.clientWidth)+180;
  const interval=Math.max(1,Math.ceil(80/sequence.zoom));for(let s=Math.max(0,Math.floor(visibleLeft/sequence.zoom/interval)*interval);s<Math.min(width,visibleRight)/sequence.zoom;s+=interval){const tick=element("span","",s+"s");tick.style.left=155+s*sequence.zoom+"px";ruler.append(tick);}
  ruler.onclick=e=>{seqPause();sequence.time=Math.min(seqLength(sequence.doc),Math.max(0,(e.clientX-ruler.getBoundingClientRect().left-155)/sequence.zoom*1000));seqMonitor();};root.append(ruler);
  // Highest video layer appears first visually; renderer iterates bottom-to-top.
  for(const track of [...sequence.doc.tracks].reverse()){
    const lane=element("div","seq-lane "+track.kind),label=element("div","seq-track-label"),body=element("div","seq-lane-body");body.style.width=width+"px";
    const name=element("strong","",track.name);name.title="Bấm chọn track; bấm đúp đổi tên";name.onclick=()=>{sequence.selected=track.id;seqProperties();seqMonitor();};name.ondblclick=()=>{const value=prompt("Tên track:",track.name);if(value?.trim())seqChange(()=>{track.name=value.trim().slice(0,80);});};label.append(name);
    for(const [key,off,on] of [["locked","Khóa","🔒"],["hidden","Ẩn","Hiện"],["muted","Tắt tiếng","🔇"]]){
      if(key==="muted"&&["text","blur"].includes(track.kind))continue;
      if(key==="hidden"&&track.kind==="audio")continue;const button=seqButton(track[key]?on:off,()=>seqChange(()=>{track[key]=!track[key];}));button.disabled=sequence.busy;label.append(button);
    }
    for(const clip of track.clips){
      const clipLeft=clip.start_ms/1000*sequence.zoom,clipWidth=Math.max(4,clip.duration_ms/1000*sequence.zoom);
      if(clipLeft+clipWidth<visibleLeft||clipLeft>visibleRight)continue;
      const bar=element("div","seq-clip"+(seqSelectedIds().includes(clip.id)?" selected":""));bar.dataset.clip=clip.id;bar.tabIndex=0;bar.setAttribute("role","button");bar.setAttribute("aria-label",clip.label);bar.style.left=clip.start_ms/1000*sequence.zoom+"px";bar.style.width=Math.max(4,clip.duration_ms/1000*sequence.zoom)+"px";
      for(const p of clip.keyframes||[]){const mark=element("i","seq-keyframe-mark");mark.style.left=Math.min(99,p.ms/clip.duration_ms*100)+"%";mark.title="Keyframe "+(p.ms/1000).toFixed(2)+"s";bar.append(mark);}
      const asset=sequence.media.get(clip.asset),image=track.kind==="audio"?(clip.speed_curve?.length?null:asset?.waveform):asset?.thumbnail;
      if(track.kind==="video"&&asset?.thumbnails?.length){
        for(let px=Math.max(0,Math.floor((visibleLeft-clipLeft)/64)*64);px<Math.min(clipWidth,visibleRight-clipLeft);px+=64){const img=element("img");img.src=seqThumbnail(asset,clip,(px+32)/sequence.zoom*1000);img.alt="";img.loading="lazy";img.style.left=px+"px";img.style.width="64px";img.style.objectFit="cover";bar.append(img);}
      }else if(image){const img=element("img");img.src=image;img.alt="";if(track.kind==="audio"&&asset?.duration_ms){const span=clip.duration_ms*(clip.speed??1);img.style.width=asset.duration_ms/span*100+"%";img.style.left=-clip.in_ms/span*100+"%";}bar.append(img);}bar.append(element("span","",clip.label+((clip.speed??1)!==1?" · "+clip.speed+"×":"")));
      for(const edge of ["start","end"]){const handle=element("i","seq-handle "+edge);handle.dataset.edge=edge;bar.append(handle);}
      let pointerHandled=false;
      bar.onclick=e=>{if(pointerHandled){pointerHandled=false;return;}seqPause();seqChoose(clip.id,e.ctrlKey||e.metaKey||e.shiftKey);sequence.time=clip.start_ms;seqMonitor();};
      bar.onkeydown=e=>{if(e.key==="Enter")bar.click();};
      bar.onpointerdown=e=>{
        if(sequence.busy||sequence.blocked||e.button!==0)return;seqPause();e.preventDefault();pointerHandled=true;seqChoose(clip.id,e.ctrlKey||e.metaKey||e.shiftKey,true);sequence.time=clip.start_ms;seqMonitor();
        if(track.locked||e.ctrlKey||e.metaKey||e.shiftKey)return;
        bar.setPointerCapture(e.pointerId);
        sequence.timelineDrag=true;
        const before=seqCopy(sequence.doc),original={...clip},x=e.clientX,edge=e.target.dataset.edge,ids=seqSelectedIds();let moved=false;
        const move=evt=>{const dx=evt.clientX-x;if(Math.abs(dx)<3&&!moved)return;moved=true;let next;try{next=seqTrim(original,dx/sequence.zoom*1000,edge,asset?.duration_ms||0,!asset||asset.kind==="image");}catch(e){$("seq-status").textContent=e.message;return;}
          if(!edge&&$("seq-snap").checked){const points=[0,...before.tracks.flatMap(t=>t.clips.filter(c=>!ids.includes(c.id)).flatMap(c=>[c.start_ms,c.start_ms+c.duration_ms]))];next.start_ms=seqSnap(next.start_ms,next.duration_ms,points,8/sequence.zoom*1000);}
          if(!edge){try{const updated=seqGroupEdit(before,ids,next.start_ms-original.start_ms);for(const t of sequence.doc.tracks)for(const c of t.clips){c.start_ms=updated.tracks.find(u=>u.id===t.id).clips.find(u=>u.id===c.id).start_ms;const b=root.querySelector('[data-clip="'+c.id+'"]');if(b)b.style.left=c.start_ms/1000*sequence.zoom+"px";}sequence.time=clip.start_ms;seqMonitor();}catch(e){$("seq-status").textContent=e.message;}return;}
          if(!seqOverlap(track,next,clip.id)&&next.start_ms+next.duration_ms<=3_600_000){Object.assign(clip,next);bar.style.left=clip.start_ms/1000*sequence.zoom+"px";bar.style.width=Math.max(4,clip.duration_ms/1000*sequence.zoom)+"px";sequence.time=clip.start_ms;seqMonitor();}
        };
        const end=evt=>{sequence.timelineDrag=false;bar.removeEventListener("pointermove",move);bar.removeEventListener("pointerup",end);bar.removeEventListener("pointercancel",end);if(evt.type==="pointercancel"){before.revision=sequence.doc.revision;sequence.doc=before;}else if(moved){sequence.undo.push(before);sequence.redo=[];seqModified();}seqRefresh();};
        bar.addEventListener("pointermove",move);bar.addEventListener("pointerup",end);bar.addEventListener("pointercancel",end);
      };body.append(bar);
    }lane.append(label,body);root.append(lane);
  }
  const head=element("div","seq-playhead");head.id="seq-playhead";root.append(head);root.scrollLeft=scrollLeft;root.scrollTop=scrollTop;sequence.viewportLeft=root.scrollLeft;sequence.viewportTop=root.scrollTop;seqMarkSelection();seqMonitor();
}
function seqClearMonitor(){for(const node of sequence.nodes.values()){if(node.pause){node.pause();node.removeAttribute("src");node.load();}node.remove();}sequence.nodes.clear();$("seq-selection")?.remove();}
function seqPause(){sequence.playing=false;sequence.playToken++;for(const n of sequence.nodes.values())if(n.pause)n.pause();if($("seq-play"))$("seq-play").textContent="▶";}
function seqPlay(){
  seqRequire();if(!seqLength(sequence.doc))return;if(sequence.time>=seqLength(sequence.doc))sequence.time=0;sequence.playing=true;sequence.clock=performance.now();$("seq-play").textContent="Ⅱ";seqMonitor();
  const token=++sequence.playToken;const tick=now=>{if(!sequence.playing||token!==sequence.playToken)return;const ready=seqMonitor();if(ready)sequence.time=Math.min(seqLength(sequence.doc),sequence.time+Math.max(0,Math.min(100,now-sequence.clock)));sequence.clock=now;if(sequence.time>=seqLength(sequence.doc))seqPause();else requestAnimationFrame(tick);};requestAnimationFrame(tick);
}
async function seqEnsureProxy(item){
  if(!item||item.kind==="image"||item.preview_url)return;
  const project=sequence.id,key=project+":"+item.id;if(sequence.proxyFailures.has(key))return;
  if(sequence.proxies.has(key))return sequence.proxies.get(key);
  const task=(async()=>{
    try{const result=await seqJob("editor_proxy",{asset:item.id,project_id:project});if(sequence.id!==project)return;
      sequence.media.set(item.id,{...item,...result.media});for(const [id,node] of sequence.nodes)if(node.dataset.asset===item.id){node.pause();node.removeAttribute("src");node.load();node.remove();sequence.nodes.delete(id);}seqMonitor();if(sequence.dirty)seqScheduleSave();
    }catch(e){sequence.proxyFailures.add(key);if(sequence.id===project){seqPause();$("seq-preview-note").textContent="Không chuẩn bị được media: "+e.message;toast(e.message,true);}}
    finally{sequence.proxies.delete(key);}
  })();sequence.proxies.set(key,task);return task;
}
function seqMonitor(){
  if(!sequence.doc)return;const stage=$("seq-stage"),length=seqLength(sequence.doc);$("seq-time").textContent=(sequence.time/1000).toFixed(2)+" / "+(length/1000).toFixed(2)+"s";$("seq-seek").max=Math.max(1,length);$("seq-seek").value=sequence.time;
  const monitor=stage.parentElement,ratio=sequence.doc.width/sequence.doc.height,availableHeight=Math.max(50,monitor.clientHeight-65),canvasWidth=Math.min(monitor.clientWidth,availableHeight*ratio);
  stage.style.width=canvasWidth+"px";stage.style.height=canvasWidth/ratio+"px";stage.style.flex="0 0 auto";
  const head=$("seq-playhead");if(head)head.style.left=155+sequence.time/1000*sequence.zoom+"px";
  if(sequence.rendered){
    let node=sequence.nodes.get("render");if(!node){seqClearMonitor();node=element("video");node.src=sequence.rendered.url;node.preload="auto";stage.append(node);sequence.nodes.set("render",node);}
    $("seq-selection")?.remove();seqSyncNode(node,sequence.time/1000,1,false);return node.readyState>=2&&!node.seeking;
  }
  const active=new Set();let z=0,ready=true;
  for(const track of sequence.doc.tracks){for(const clip of track.clips){
    if(sequence.time<clip.start_ms||sequence.time>=clip.start_ms+clip.duration_ms||track.kind!=="audio"&&track.hidden||track.kind==="audio"&&track.muted)continue;
    if(["text","blur"].includes(track.kind)){
      active.add(clip.id);let node=sequence.nodes.get(clip.id);if(!node){node=element("div","seq-visual "+track.kind);stage.append(node);sequence.nodes.set(clip.id,node);seqBindCanvas(node,track,clip);}
      node.hidden=false;node.style.zIndex=String(z++);node.classList.toggle("chosen",clip.id===sequence.selected);const t=seqAnimatedTransform(clip,sequence.time);
      if(track.kind==="text"){seqTextPreview(node,clip,sequence.time-clip.start_ms);const pop=clip.text_animation==='pop'?.75+.25*Math.min(1,(sequence.time-clip.start_ms)/180):1;Object.assign(node.style,{left:t.x+"%",top:t.y+"%",transform:`translate(-50%,-50%) rotate(${t.rotation}deg) scale(${t.scale*pop})`,fontFamily:clip.font||"Arial",fontSize:(clip.font_size||36)*canvasWidth/sequence.doc.width+"px",color:clip.color||"#ffffff",opacity:t.opacity,background:clip.box?(clip.box_color||'#000000')+Math.round((clip.box_opacity??.6)*255).toString(16).padStart(2,'0'):"transparent"});}
      else{const w=clip.region_w??30,h=clip.region_h??15,x=Math.max(w/2,Math.min(100-w/2,t.x)),y=Math.max(h/2,Math.min(100-h/2,t.y));Object.assign(node.style,{left:x+"%",top:y+"%",width:w+"%",height:h+"%",transform:"translate(-50%,-50%)",backdropFilter:`blur(${(clip.blur||12)*canvasWidth/sequence.doc.width}px)`});}
      continue;
    }
    const item=sequence.media.get(clip.asset);if(!item)continue;active.add(clip.id);let node=sequence.nodes.get(clip.id);
    if(!node){node=element(item.kind==="image"?"img":track.kind==="audio"?"audio":"video");node.dataset.asset=item.id;node.preload="auto";node.playsInline=true;
      node.onloadedmetadata=node.onloadeddata=()=>{if(sequence.nodes.get(clip.id)===node)seqMonitor();};
      node.onerror=()=>{if(sequence.nodes.get(clip.id)!==node)return;if(!item.preview_url)seqEnsureProxy(item);else{seqPause();$("seq-preview-note").textContent="Không phát được bản xem. Thử nút Chuẩn bị video xem realtime hoặc kiểm tra file nguồn.";}};
      stage.append(node);sequence.nodes.set(clip.id,node);node.src=item.preview_url||item.url;
      if(track.kind==="video")seqBindCanvas(node,track,clip);
      if(item.kind!=="image"&&!item.preview_url&&(item.url.match(/\.(mkv|avi)(?:\?|$)/i)||node.tagName==="VIDEO"&&!node.canPlayType("video/mp4")&&item.url.match(/\.(mp4|mov)(?:\?|$)/i)))seqEnsureProxy(item);
    }
    node.style.zIndex=String(z++);node.hidden=false;
    const transition=seqTransitionProgress(clip,sequence.time-clip.start_ms);
    if(track.kind==="video"){const t=seqAnimatedTransform(clip,sequence.time);Object.assign(node.style,{left:t.x+"%",top:t.y+"%",right:"auto",bottom:"auto",width:t.scale*100+"%",height:t.scale*100+"%",transform:`translate(-50%,-50%) rotate(${t.rotation}deg) scale(${clip.flip_h?-1:1},${clip.flip_v?-1:1})`,opacity:t.opacity*(clip.transition_in==='crossfade'?transition:1),clipPath:seqWipeMask(clip,transition),objectFit:clip.fit||"contain",mixBlendMode:clip.blend==="addition"?"plus-lighter":clip.blend==="normal"||!clip.blend?"normal":clip.blend});}
    if(track.kind==='video')node.style.filter=seqColorStyle(clip);
    if(node.tagName!=="IMG"){seqSyncNode(node,seqSourceMs(clip,sequence.time-clip.start_ms)/1000,Math.min(1,clip.volume)*seqEnvelope({...clip,fade_out_ms:Math.max(clip.fade_out_ms||0,clip.audio_fade_out_ms||0)},sequence.time-clip.start_ms)*transition,track.muted,false,seqSpeedAt(clip,sequence.time-clip.start_ms));if(node.readyState<2||node.seeking||node.error)ready=false;}else if(!node.complete||!node.naturalWidth)ready=false;
  }}
  const existing=new Set(sequence.doc.tracks.flatMap(t=>t.clips.map(c=>c.id)));
  for(const filter of [...($('seq-filter-defs')?.children||[])])if(!existing.has(filter.id.replace('seq-color-','')))filter.remove();
  for(const [id,node] of sequence.nodes)if(!active.has(id)){node.hidden=true;if(node.pause)node.pause();if(!existing.has(id)){node.remove();if(node.load){node.removeAttribute("src");node.load();}sequence.nodes.delete(id);}}
  // Keep a small nearby cache, not one decoder for every visited clip of a long project.
  const distances=new Map(sequence.doc.tracks.flatMap(t=>t.clips.map(c=>[c.id,Math.min(Math.abs(sequence.time-c.start_ms),Math.abs(sequence.time-c.start_ms-c.duration_ms))])));
  const idle=[...sequence.nodes.keys()].filter(id=>!active.has(id)).sort((a,b)=>(distances.get(a)||0)-(distances.get(b)||0));
  for(const id of idle.slice(8)){const node=sequence.nodes.get(id);node.remove();if(node.load){node.removeAttribute("src");node.load();}sequence.nodes.delete(id);}
  if(sequence.playing)for(const id of active){const n=sequence.nodes.get(id);if(!n?.pause)continue;if(ready)seqSyncNode(n,n.currentTime,n.volume,n.muted);else n.pause();}
  seqDrawSelection();
  const selected=seqSelection().clip;if(selected)for(const field of $("seq-properties").querySelectorAll('[data-motion]'))if(document.activeElement!==field)field.value=Math.round(seqMotionValues(selected,sequence.time-selected.start_ms)[field.dataset.motion]*1000)/1000;
  $("seq-preview-note").textContent=sequence.proxies.size?"Đang tạo bản xem tương thích một lần cho video nguồn. Bố cục vẫn sửa được; không render toàn timeline.":ready?"Realtime · kéo chữ/video/vùng mờ trên hình để đặt vị trí. Font và mức mờ có thể chênh nhẹ so với bản xuất; Xem chính xác để đối chiếu.":"Đang nạp khung hình/âm thanh · con trỏ chờ media sẵn sàng.";
  return ready;
}
function seqDrawSelection(){
  const stage=$("seq-stage"),{track,clip}=seqSelection(),node=clip&&sequence.nodes.get(clip.id);let box=$("seq-selection");
  if(!clip||!node||node.hidden||track.kind==="audio"||track.locked||sequence.playing||sequence.rendered){if(box)box.hidden=true;return;}
  if(!box){box=element("div","seq-selection");box.id="seq-selection";for(const corner of ["nw","ne","sw","se","rotate"]){const grip=element("button","seq-grip "+corner);grip.type="button";grip.dataset.mode=corner;grip.setAttribute("aria-label",corner==="rotate"?"Xoay lớp trực tiếp":"Đổi kích thước lớp "+corner);grip.title=corner==="rotate"?"Kéo để xoay · giữ Shift bắt góc 15°":"Kéo để zoom · con lăn zoom · Shift + con lăn xoay";grip.onpointerdown=e=>seqResizeCanvas(e,grip,corner);box.append(grip);}stage.append(box);}
  const t=seqAnimatedTransform(clip,sequence.time),sw=stage.clientWidth,sh=stage.clientHeight;let w,h;
  if(track.kind==="video"){const item=sequence.media.get(clip.asset),sourceW=node.videoWidth||node.naturalWidth||item.width,sourceH=node.videoHeight||node.naturalHeight||item.height,fit=Math.min(sw/Math.max(1,sourceW),sh/Math.max(1,sourceH));w=clip.fit==="cover"?sw*t.scale:sourceW*fit*t.scale;h=clip.fit==="cover"?sh*t.scale:sourceH*fit*t.scale;}
  else if(track.kind==="text"){w=node.offsetWidth*t.scale;h=node.offsetHeight*t.scale;}
  else {w=sw*(clip.region_w??30)/100;h=sh*(clip.region_h??15)/100;}
  box.hidden=false;box.classList.toggle("blur",track.kind==="blur");box.dataset.clip=clip.id;
  Object.assign(box.style,{left:node.style.left,top:node.style.top,width:w+"px",height:h+"px",transform:`translate(-50%,-50%) rotate(${track.kind==="blur"?0:t.rotation}deg)`});
  box.querySelector(".rotate").hidden=track.kind==="blur";
}
function seqResizeCanvas(e,grip,mode){
  const {track,clip}=seqSelection();if(!clip||track.locked||sequence.busy||sequence.blocked||e.button!==0)return;
  e.preventDefault();e.stopPropagation();seqPause();grip.setPointerCapture(e.pointerId);
  const before=seqCopy(sequence.doc),initial=seqMotionValues(clip,sequence.time-clip.start_ms),box=$("seq-selection").getBoundingClientRect(),stage=$("seq-stage").getBoundingClientRect(),center={x:box.left+box.width/2,y:box.top+box.height/2},start={x:e.clientX,y:e.clientY};let moved=false;
  const move=evt=>{if(Math.abs(evt.clientX-start.x)+Math.abs(evt.clientY-start.y)<2&&!moved)return;moved=true;
    if(track.kind==="blur"){clip.region_w=Math.max(1,Math.min(100,2*Math.abs(evt.clientX-center.x)/stage.width*100));clip.region_h=Math.max(1,Math.min(100,2*Math.abs(evt.clientY-center.y)/stage.height*100));}
    else if(track.kind==="video"){try{seqSetPosition(clip,sequence.time,seqPointerTransform(initial,mode,start,{x:evt.clientX,y:evt.clientY},center,evt.shiftKey));}catch(e){toast(e.message,true);}}else Object.assign(clip,seqPointerTransform(initial,mode,start,{x:evt.clientX,y:evt.clientY},center,evt.shiftKey));
    seqMonitor();
  };
  const end=evt=>{grip.removeEventListener("pointermove",move);grip.removeEventListener("pointerup",end);grip.removeEventListener("pointercancel",end);
    if(evt.type==="pointercancel"){before.revision=sequence.doc.revision;sequence.doc=before;seqRefresh();}
    else if(moved){sequence.undo.push(before);sequence.redo=[];seqModified();}
  };
  grip.addEventListener("pointermove",move);grip.addEventListener("pointerup",end);grip.addEventListener("pointercancel",end);
}
function seqBindCanvas(node,track,clip){
  node.onpointerdown=e=>{
    const selected=sequence.doc.tracks.flatMap(t=>t.clips).find(c=>c.id===clip.id),owner=sequence.doc.tracks.find(t=>t.clips.includes(selected));
    if(!selected||!owner||owner.locked||sequence.busy||sequence.blocked||e.button!==0)return;
    e.preventDefault();seqPause();sequence.selected=selected.id;$("seq-timeline").querySelectorAll(".seq-clip").forEach(b=>b.classList.toggle("selected",b.dataset.clip===selected.id));seqProperties();node.setPointerCapture(e.pointerId);
    const before=seqCopy(sequence.doc),rect=$("seq-stage").getBoundingClientRect(),initial=seqAnimatedTransform(selected,sequence.time),x=e.clientX,y=e.clientY;let moved=false;
    const move=evt=>{if(Math.abs(evt.clientX-x)+Math.abs(evt.clientY-y)<3&&!moved)return;moved=true;const min=owner.kind==="blur"?0:-100,max=owner.kind==="blur"?100:200,position={x:Math.max(min,Math.min(max,initial.x+(evt.clientX-x)/rect.width*100)),y:Math.max(min,Math.min(max,initial.y+(evt.clientY-y)/rect.height*100))};try{seqSetPosition(selected,sequence.time,position);}catch(e){toast(e.message,true);}seqMonitor();};
    const end=evt=>{node.removeEventListener("pointermove",move);node.removeEventListener("pointerup",end);node.removeEventListener("pointercancel",end);if(evt.type==="pointercancel"){before.revision=sequence.doc.revision;sequence.doc=before;seqRefresh();}else if(moved){sequence.undo.push(before);sequence.redo=[];seqModified();}else seqMonitor();};
    node.addEventListener("pointermove",move);node.addEventListener("pointerup",end);node.addEventListener("pointercancel",end);
  };
}
function seqSyncNode(node,seconds,volume,muted,allowPlay=true,speed=node.playbackRate||1){
  node.playbackRate=speed;node.preservesPitch=true;
  node.volume=volume;node.muted=muted;if(node.readyState>=1&&!node.seeking&&Math.abs(node.currentTime-seconds)>(sequence.playing?.18:.015))node.currentTime=seconds;
  if(sequence.playing&&allowPlay&&node.paused&&node.readyState>=2&&!node.seeking)node.play().catch(e=>{if(e.name==="NotAllowedError"){seqPause();toast("Bấm Phát để cho phép phát audio/video.",true);}});else if(!sequence.playing&&!node.paused)node.pause();
}
async function seqRender(preview){
  seqRequire();await seqSave();if(sequence.dirty)throw Error("Timeline chưa lưu xong.");sequence.busy=true;seqPause();seqControls();
  try{const result=await seqJob(preview?"editor_preview":"editor_export",{revision:sequence.doc.revision});sequence.outputFiles=result.files;const file=result.files[0];$("seq-output").replaceChildren(downloadLink(file));
    if(preview){sequence.rendered=file;sequence.time=0;seqClearMonitor();seqMonitor();$("seq-preview-note").textContent="Bản render chính xác của revision "+result.revision+" · dùng cùng canvas, FPS và graph dựng với bản xuất.";}
    else toast("Đã xuất MP4. Bấm liên kết dưới video để tải.");
  }finally{sequence.busy=false;seqControls();}
}

function seqWordTiming(text,duration){const tokens=text.match(/\S+/gu)||[],length=w=>Array.from(w).length,total=tokens.reduce((n,w)=>n+length(w),0);let at=0;return tokens.map(word=>{const end=at+length(word)*duration/Math.max(1,total),row={word,start:Math.round(at),end:Math.round(end)};at=end;return row;});}
function seqTextPreview(node,clip,ms){
  if(!['karaoke','typewriter'].includes(clip.text_animation)){if(node.dataset.textStamp||node.textContent!==clip.text)node.textContent=clip.text;delete node.dataset.textStamp;return;}
  const words=clip.word_cues?.length?clip.word_cues:seqWordTiming(clip.text,clip.duration_ms),current=words.reduce((n,w,i)=>ms>=w.start?i:n,-1);
  const stamp=[clip.text,clip.text_animation,clip.color,current].join('|');if(node.dataset.textStamp===stamp)return;node.dataset.textStamp=stamp;node.replaceChildren();
  for(const [i,w] of words.entries()){if(clip.text_animation==='typewriter'&&i>current)break;const span=element('span','',w.word+(i<words.length-1?' ':''));if(clip.text_animation==='karaoke')span.style.color=i<=current?(clip.color||'#ffffff'):'#ffff00';node.append(span);}
}
function seqStyleProposal(doc,style,ids){
  const styles={clean:{font:'Be Vietnam Pro',font_size:38,color:'#ffffff',box:true,text_animation:'pop',y:85},manga:{font:'Arial',font_size:48,color:'#ffe347',box:true,text_animation:'pop',y:80},retro:{font:'Times New Roman',font_size:40,color:'#fff3d6',box:false,text_animation:'typewriter',y:82},karaoke:{font:'Be Vietnam Pro',font_size:40,color:'#ffffff',box:true,text_animation:'karaoke',y:84}};
  if(!styles[style])throw Error('Phong cách không hợp lệ.');const result=seqCopy(doc),selected=new Set(ids);let count=0;
  for(const t of result.tracks)for(const c of t.clips)if(t.kind==='text'&&!t.locked&&(!selected.size||selected.has(c.id))){if(c.text.split(/\s+/u).length>200)throw Error('Chia câu dài hơn 200 từ trước.');Object.assign(c,styles[style]);count++;}
  if(!count)throw Error('Chọn clip chữ hoặc bỏ chọn để áp dụng mọi track chữ chưa khóa.');return result;
}
// Pure operation: never edits cue text/timing, other track kinds or locked tracks.
function seqBatchText(doc,scope,ids,trackId,patch){
  if(!['all','track','selected'].includes(scope))throw Error('Phạm vi phụ đề không hợp lệ.');
  const rules={x:v=>Number.isFinite(v)&&v>=0&&v<=100,y:v=>Number.isFinite(v)&&v>=0&&v<=100,
    font_size:v=>Number.isInteger(v)&&v>=10&&v<=160,font:v=>['Arial','Segoe UI','Times New Roman','Be Vietnam Pro'].includes(v),
    color:v=>typeof v==='string'&&/^#[a-fA-F0-9]{6}$/.test(v),box_color:v=>typeof v==='string'&&/^#[a-fA-F0-9]{6}$/.test(v),box_opacity:v=>Number.isFinite(v)&&v>=0&&v<=1,box:v=>typeof v==='boolean',text_animation:v=>['none','pop','typewriter','karaoke'].includes(v)};
  if(!patch||!Object.keys(patch).length||Object.entries(patch).some(([k,v])=>!rules[k]||!rules[k](v)))throw Error('Chọn thuộc tính và nhập giá trị hợp lệ.');
  const selected=new Set(ids),result=seqCopy(doc);let changed=0,skipped=0,eligible=0;
  for(const track of result.tracks)for(const clip of track.clips){
    if(track.kind!=='text'||scope==='track'&&track.id!==trackId||scope==='selected'&&!selected.has(clip.id))continue;
    if(track.locked){skipped++;continue;}eligible++;
    if(patch.text_animation&&patch.text_animation!=='none'&&clip.text.trim().split(/\s+/u).length>200)throw Error('Chữ động tối đa 200 từ mỗi clip; chia câu trước.');
    if(Object.entries(patch).some(([k,v])=>clip[k]!==v)){Object.assign(clip,patch);changed++;}
  }
  if(!eligible)throw Error('Không có clip chữ chưa khóa trong phạm vi đã chọn.');
  return {doc:result,changed,skipped};
}
function seqBatchTextDialog(){
  seqRequire();if(sequence.busy||sequence.blocked)throw Error('Chờ tác vụ hoặc giải quyết xung đột.');
  const project=sequence.id,generation=sequence.generation,ids=seqSelectedIds(),current=seqSelection(),trackId=current.track?.id;
  const first=current.track?.kind==='text'&&current.clip?current.clip:sequence.doc.tracks.find(t=>t.kind==='text'&&!t.locked)?.clips[0];
  const d=seqToolDialog('Chỉnh phụ đề hàng loạt');d.id='seq-studio-dialog';
  const scope=element('select');scope.id='seq-text-scope';
  for(const [v,label] of [['all','Toàn bộ chữ / phụ đề'],['track','Track chữ hiện tại'],['selected','Các cue đã chọn']]){const opt=element('option','',label);opt.value=v;scope.append(opt);}
  const scopeLabel=element('label','field','Phạm vi áp dụng');scopeLabel.append(scope);d.append(scopeLabel);
  const count=element('p','hint');count.id='seq-text-target-count';d.append(count,element('p','hint','Chỉ áp dụng thuộc tính được tích. Giữ nguyên lời, thời gian và mốc karaoke; bỏ qua track khóa. Bấm Áp dụng để xem ngay; có Hoàn tác.'));
  const defaults={x:50,y:88,font_size:36,font:'Arial',color:'#ffffff',box:true,box_color:'#000000',box_opacity:.6,text_animation:'none'},fields=[];
  for(const [key,title,type,choices] of [['x','Vị trí ngang (%)','number'],['y','Vị trí dọc (%)','number'],['font_size','Cỡ chữ (pixel canvas)','number'],['font','Phông chữ','select',['Arial','Segoe UI','Times New Roman','Be Vietnam Pro']],['color','Màu chữ','color'],['box','Nền hộp chữ','checkbox'],['box_color','Màu nền hộp','color'],['box_opacity','Độ hiện nền (0–1)','number'],['text_animation','Kiểu chạy','select',[['none','Không chạy'],['pop','Hiện nổi'],['typewriter','Máy chữ'],['karaoke','Karaoke · theo từ']]]]){
    const row=element('div','actions seq-batch-field'),use=element('input'),label=element('label','check',title);use.type='checkbox';use.checked=['x','y','font_size'].includes(key);use.dataset.batchUse=key;label.prepend(use);row.append(label);
    const input=element(type==='select'?'select':'input');input.dataset.batchField=key;input.setAttribute('aria-label',title);
    if(type==='select')for(const item of choices){const [v,n]=Array.isArray(item)?item:[item,item];const o=element('option','',n);o.value=v;input.append(o);}else input.type=type;
    const value=first?.[key]??defaults[key];input.value=value;input.checked=!!value;
    if(type==='number'){input.min=key==='font_size'?10:0;input.max=key==='font_size'?160:key==='box_opacity'?1:100;input.step=key==='font_size'?1:key==='box_opacity'?.05:.1;}
    input.disabled=!use.checked;use.onchange=()=>input.disabled=!use.checked;row.append(input);d.append(row);fields.push({key,use,input,type});
  }
  const targets=()=>{let n=0,locked=0;for(const t of sequence.doc.tracks)for(const c of t.clips)if(t.kind==='text'&&(scope.value==='all'||scope.value==='track'&&t.id===trackId||scope.value==='selected'&&ids.includes(c.id))){if(t.locked)locked++;else n++;}count.textContent=`${n} cue sẽ áp dụng · ${locked} cue khóa bỏ qua`;apply.disabled=!n;};
  const apply=seqButton('Áp dụng · có Hoàn tác',()=>{
    if(project!==sequence.id||generation!==sequence.generation)throw Error('Timeline đã đổi; mở lại bảng chỉnh phụ đề.');
    const patch={};for(const {key,use,input,type} of fields)if(use.checked)patch[key]=type==='number'?Number(input.value):type==='checkbox'?input.checked:input.value;
    const result=seqBatchText(sequence.doc,scope.value,ids,trackId,patch);if(result.changed)seqChange(()=>sequence.doc=result.doc);d.close();
    toast(`${result.changed} cue đã cập nhật · ${result.skipped} cue khóa bỏ qua`);
  });apply.id='seq-text-batch-apply';d.append(apply);scope.onchange=targets;targets();
}
function seqCutProposal(doc,id,points,newId){
  const result=seqCopy(doc),track=result.tracks.find(t=>t.clips.some(c=>c.id===id)),original=track?.clips.find(c=>c.id===id);
  if(!original||track.locked||original.transition_in&&original.transition_in!=='none')throw Error('Clip đã đổi/khóa hoặc có chuyển cảnh.');
  const boundaries=[...new Set(points)].sort((a,b)=>a-b);if(boundaries.length>64||boundaries.some(x=>!Number.isInteger(x)||x<100||x>original.duration_ms-100))throw Error('Mốc cắt cần trong clip, tối đa 64.');
  let parts=[original];for(const offset of boundaries){const last=parts.pop();parts.push(...seqSplit(last,original.start_ms+offset,newId()));}
  track.clips.splice(track.clips.indexOf(original),1,...parts);if(result.tracks.filter(t=>['video','audio'].includes(t.kind)).flatMap(t=>t.clips).length>100)throw Error('Cắt vượt 100 clip media.');return result;
}
function seqToolDialog(title){let d=$('seq-studio-dialog');if(!d){d=element('dialog');d.id='seq-studio-dialog';document.body.append(d);}d.replaceChildren();const head=element('div','actions');head.append(element('strong','',title),seqButton('Đóng ✕',()=>d.close()));d.append(head);d.onkeydown=e=>{if(e.key==='Escape')d.close();};if(!d.open)d.show();return d;}
function seqWordProposal(doc,result,words,newId,target='auto'){
  if(!words.length||words.length>2000)throw Error('Cần 1–2000 từ, chia clip nếu dài hơn.');let previous=0;
  for(const w of words){if(!Number.isInteger(w.start)||!Number.isInteger(w.end)||w.start<previous||w.start>=w.end||w.end>result.duration_ms||!w.word||w.word.length>300||/\s/u.test(w.word))throw Error('Mỗi dòng cần bắt đầu/kết thúc tăng dần trong clip và một từ không trống.');previous=w.end;}
  const copy=seqCopy(doc);
  const clips=[];for(let i=0;i<words.length;i+=8){const group=words.slice(i,i+8),a=group[0].start,b=group.at(-1).end,duration=Math.max(100,b-a);if(i+8<words.length&&a+duration>words[i+8].start||a+duration>result.duration_ms)throw Error('Nhóm từ ngắn hơn 100ms/chồng nhóm kế; sửa mốc trước.');const text=group.map(w=>w.word).join(' ');clips.push({id:newId(),asset:'',label:text.slice(0,80),start_ms:result.start_ms+a,in_ms:0,duration_ms:duration,text,text_animation:'karaoke',word_cues:group.map(w=>({...w,start:w.start-a,end:w.end-a})),font:'Be Vietnam Pro',font_size:40,color:'#ffffff',box:true,...seqTransformDefaults,y:84});}
  const eligible=t=>t.kind==='text'&&!t.locked&&!t.hidden&&clips.every(c=>!seqOverlap(t,c,''));
  let track;
  if(target==='auto'){const rows=copy.tracks.filter(eligible);track=rows.find(t=>(t.name||'').startsWith('Karaoke'))||rows.find(t=>!t.clips.length)||rows[0];}
  else if(target!=='new'){track=copy.tracks.find(t=>t.id===target);if(!track||!eligible(track))throw Error('Track chữ đã chọn bị khóa/ẩn hoặc có clip chồng mốc karaoke. Chọn Tự động, track khác hoặc tạo mới; không ghi đè chữ cũ.');}
  if(!track){if(copy.tracks.length>=SEQ_MAX_TRACKS)throw Error('Đã đủ 64 track và không có track chữ phù hợp. Chọn track chữ có khoảng trống hoặc bỏ track không cần; chia video ngắn hơn không giảm số track.');track={id:newId(),name:'Karaoke · mốc audio đã duyệt',kind:'text',locked:false,hidden:false,muted:false,clips:[]};copy.tracks.push(track);}
  track.clips.push(...clips);track.clips.sort((a,b)=>a.start_ms-b.start_ms);if(copy.tracks.flatMap(t=>t.clips).length>500)throw Error('Quá 500 clip.');return copy;
}
async function seqRecognizeWords(language,allowDownload){
  const result=await seqStudioJob('words',{language,allow_download:allowDownload}),project=sequence.id,generation=sequence.generation,d=seqToolDialog('Duyệt mốc từ từ audio');
  const reference=element('textarea');reference.rows=2;reference.placeholder='Dán lời dịch khớp audio lồng tiếng của clip này';reference.setAttribute('aria-label','Lời dịch tham chiếu');
  const alignedNote=element('p','hint');d.append(reference,seqButton('Đối chiếu / căn lời dịch theo audio',async()=>{if(project!==sequence.id||generation!==sequence.generation)throw Error('Timeline đã đổi; nhận dạng lại.');if(!reference.value.trim())throw Error('Dán lời dịch của audio lồng tiếng, không phải bản dịch của audio gốc ngoại ngữ.');const aligned=await api('align-reference',{reference:reference.value,words:result.words});alignedNote.textContent=`Khớp ${(aligned.coverage*100).toFixed(0)}% · ${aligned.can_apply?'đủ mốc để duyệt':'chưa có mốc cho: '+aligned.unmatched.map(w=>w.word).join(', ')}. Không bịa mốc từ thiếu; không phải forced alignment.`;if(aligned.can_apply){$('seq-word-review').value=aligned.words.map(w=>`${(w.start/1000).toFixed(3)}\t${(w.end/1000).toFixed(3)}\t${w.word}`).join('\n');}else toast('Chưa khớp toàn bộ lời. Kiểm tra audio/ngôn ngữ hoặc sửa mốc thủ công; mốc đang duyệt giữ nguyên.',true);}),alignedNote);
  d.append(element('p','hint',`${result.words.length} từ · ${result.language}. Whisper nhận dạng lời gốc, không tự căn lời dịch. Mỗi dòng: giây bắt đầu / giây kết thúc / một từ; cách bằng TAB hoặc dấu cách. Mốc tương đối trong clip. Sửa trước khi thêm; phụ đề cũ giữ nguyên.`));
  const destination=element('select');destination.id='seq-word-target';destination.setAttribute('aria-label','Track nhận karaoke');
  for(const [value,name] of [['auto','Tự động · dùng track chữ có khoảng trống'],['new','Tạo track karaoke mới'],...sequence.doc.tracks.filter(t=>t.kind==='text'&&!t.locked&&!t.hidden).map(t=>[t.id,t.name])]){const o=element('option','',name);o.value=value;destination.append(o);}d.append(element('small','hint',`${sequence.doc.tracks.length}/${SEQ_MAX_TRACKS} track. Tự động dùng lại track chữ không chồng clip; nếu cần mới tạo thêm. Không sửa chữ cũ.`),destination);
  const input=element('textarea');input.id='seq-word-review';input.rows=12;input.value=result.words.map(w=>`${(w.start/1000).toFixed(3)}\t${(w.end/1000).toFixed(3)}\t${w.word}`).join('\n');d.append(input,seqButton('Thêm karaoke · có Hoàn tác',()=>{if(project!==sequence.id||generation!==sequence.generation)throw Error('Timeline đã đổi; nhận dạng lại.');const words=input.value.trim().split(/\r?\n/u).map(line=>{const fields=line.trim().split(/\s+/u);if(fields.length!==3)throw Error('Mỗi dòng cần đúng hai mốc và một từ.');return {start:Math.round(Number(fields[0])*1000),end:Math.round(Number(fields[1])*1000),word:fields[2]};});seqChange(()=>sequence.doc=seqWordProposal(sequence.doc,result,words,seqId,destination.value));d.close();}));
}
async function seqStudioJob(mode,extra={}){
  seqRequire();if(sequence.busy||sequence.blocked)throw Error('Chờ tác vụ/giải quyết bản nháp trước.');await seqSave();if(sequence.dirty)throw Error('Timeline chưa lưu.');const project=sequence.id,generation=sequence.generation;
  sequence.busy=true;seqPause();seqControls();try{const result=await seqJob('editor_tools',{mode,revision:sequence.doc.revision,clip_id:seqSelection().clip?.id,at_ms:Math.round(sequence.time),...extra});if(project!==sequence.id||generation!==sequence.generation)throw Error('Dự án đã thay đổi; kết quả giữ trong Lịch sử.');return result;}finally{sequence.busy=false;seqControls();}
}
function seqToolMediaClip(item,name,duration,start,newId){
  const length=Math.min(Math.round(duration),3_600_000-Math.round(start),item.kind==='image'?3_600_000:Math.floor(item.duration_ms));
  if(!Number.isFinite(length)||length<100||!Number.isFinite(start)||start<0)throw Error('Media tạo ra không đủ 100ms hoặc vượt timeline.');
  return {id:newId(),asset:item.id,label:name,start_ms:Math.round(start),in_ms:0,duration_ms:length,speed:1,volume:0,...seqTransformDefaults};
}
function seqFitClipToSource(clip,item){
  if(item.kind==='image'||seqSourceMs(clip,clip.duration_ms)<=item.duration_ms)return seqCopy(clip);
  let lo=0,hi=clip.duration_ms;while(lo<hi){const mid=Math.ceil((lo+hi)/2);if(seqSourceMs(clip,mid)<=item.duration_ms)lo=mid;else hi=mid-1;}
  if(lo<100)throw Error(`Clip ${clip.label}: nguồn còn dưới 100ms. Chỉnh điểm đầu nguồn hoặc bỏ clip này; không tự xóa.`);
  return {...seqCopy(clip),...seqAnimationRange(clip,0,lo),duration_ms:lo,audio_fade_out_ms:Math.min(clip.audio_fade_out_ms||0,lo-Math.min(clip.fade_in_ms||0,lo)),transition_ms:(clip.transition_in||'none')==='none'?0:Math.min(clip.transition_ms,lo)};
}
async function seqRepairSourceBounds(){
  seqRequire();if(sequence.busy||sequence.blocked)throw Error('Chờ tác vụ hoặc xử lý bản nháp khác revision trước.');
  const project=sequence.id,generation=sequence.generation,doc=seqCopy(sequence.doc),rows=[];sequence.busy=true;seqPause();seqControls();
  try{
    const keys=[...new Set(doc.tracks.filter(t=>['video','audio'].includes(t.kind)).flatMap(t=>t.clips.map(c=>c.asset)))];
    for(const key of keys){const item=await api('projects/'+project+'/editor-media/'+key);sequence.media.set(key,item);}
    if(sequence.id!==project||sequence.generation!==generation)throw Error('Timeline đã đổi; kiểm tra lại.');
    for(const t of doc.tracks)if(['video','audio'].includes(t.kind))for(let i=0;i<t.clips.length;i++){const c=t.clips[i],item=sequence.media.get(c.asset);if(item.kind==='image'||seqSourceMs(c,c.duration_ms)<=item.duration_ms+40)continue;if(t.locked)throw Error(`Mở khóa track ${t.name} rồi kiểm tra lại.`);const next=seqFitClipToSource(c,item);rows.push({label:c.label,before:c.duration_ms,after:next.duration_ms});t.clips[i]=next;}
  }finally{sequence.busy=false;seqControls();}
  if(!rows.length){toast('Không có clip vượt nguồn. Bản nháp giữ nguyên.');return;}
  const dialog=seqToolDialog('Duyệt căn độ dài theo file nguồn');dialog.append(element('p','hint','Chỉ rút phần cuối clip bị vượt nguồn; không đổi điểm bắt đầu hay đẩy clip khác. Nguồn giữ nguyên; keyframe/curve/fade được cắt theo đoạn mới. Có Hoàn tác.'),element('pre','',rows.map(r=>`${r.label}: ${(r.before/1000).toFixed(3)}s → ${(r.after/1000).toFixed(3)}s`).join('\n')),seqButton('Áp dụng & lưu · có Hoàn tác',async()=>{if(sequence.id!==project||sequence.generation!==generation)throw Error('Timeline đã đổi; kiểm tra lại.');doc.revision=sequence.doc.revision;seqChange(()=>sequence.doc=doc);dialog.close();await seqSave();}));
}
function seqAddToolMedia(item,name,duration=2000,start=sequence.time){
  const clip=seqToolMediaClip(item,name,duration,start,seqId);sequence.media.set(item.id,item);seqChange(()=>{if(sequence.doc.tracks.length>=SEQ_MAX_TRACKS)throw Error('Tối đa 64 track.');if(!sequence.doc.assets.includes(item.id))sequence.doc.assets.push(item.id);sequence.doc.tracks.push({id:seqId(),name,kind:'video',locked:false,hidden:false,muted:true,clips:[clip]});sequence.selected=clip.id;});if(clip.duration_ms<duration)toast('Đã căn lớp mới theo độ dài file thực tế; không kéo dài vượt nguồn.');
}
async function seqAnalyze(){
  const result=await seqStudioJob('analyze'),project=sequence.id,generation=sequence.generation,d=seqToolDialog('Duyệt nhịp / cảnh trước khi cắt');d.append(element('p','hint',`${result.beats.length} điểm nhấn audio · ${result.scenes.length} cảnh. Mốc là giây tương đối trong clip; xóa dòng không muốn. Không phải beat tracker AI.`));
  const input=element('textarea');input.rows=8;input.value=result.points.map(ms=>(ms/1000).toFixed(3)).join('\n');d.append(input,seqButton('Áp dụng điểm cắt · có Hoàn tác',()=>{if(project!==sequence.id||generation!==sequence.generation)throw Error('Timeline đã đổi; phân tích lại.');const points=input.value.trim()?input.value.trim().split(/\s+/u).map(x=>Math.round(Number(x)*1000)):[];seqChange(()=>sequence.doc=seqCutProposal(sequence.doc,result.clip_id,points,seqId));d.close();}));
}
async function seqObjectRegion(region){
  const {clip}=seqSelection();if(!clip?.asset)throw Error('Chọn video nguồn trước.');await seqSave();const project=sequence.id,generation=sequence.generation;sequence.busy=true;seqControls();let result;
  try{result=await seqJob('editor_object',{clip_id:clip.id,revision:sequence.doc.revision,at_ms:Math.round(sequence.time),region,reidentify:$('seq-object-reidentify')?.checked===true});}finally{sequence.busy=false;seqControls();}
  if(project!==sequence.id||generation!==sequence.generation)throw Error('Timeline đã đổi; dò lại.');
  const d=seqToolDialog('Duyệt lớp bám vật thể'),select=element('select');const o=element('option','','Vùng mờ bám vật thể');o.value='';select.append(o);for(const item of sequence.media.values())if(item.kind==='image'){const option=element('option','',item.name);option.value=item.id;select.append(option);}d.append(element('p','hint',`${result.method||'local-template'} · ${(result.duration_ms/1000).toFixed(1)}s · ${result.segments?.length||1} đoạn hiện lớp. Đoạn mất dấu của tái tìm không tạo lớp. ${result.stopped?'Đã dừng ở '+(result.stopped.ms/1000).toFixed(2)+'s; chọn lại vùng ở đoạn sau.':''} Không nhận diện danh tính; cần duyệt, không bảo đảm che thông tin nhạy cảm.`),select,seqButton('Thêm lớp bám · Hoàn tác',()=>{if(project!==sequence.id||generation!==sequence.generation)throw Error('Timeline đã đổi.');const next=seqTrackedProposal(sequence.doc,result,select.value,seqId);seqChange(()=>{sequence.doc=next;sequence.selected=next.tracks.at(-1).clips[0].id;});d.close();}));
  const samples=element('details');samples.append(element('summary','','Duyệt độ tin cậy / che khuất'));for(const row of result.review_rows||[])samples.append(element('p','hint',`${(row.ms/1000).toFixed(2)}s · ${{held:'Giữ vị trí cũ',lost:'Mất dấu · không hiện lớp',confirming:'Đang xác nhận · không hiện lớp',reacquired:'Tái bám được',tracked:'Bám được'}[row.state]||row.state} · độ khớp ${Number(row.confidence||0).toFixed(2)}`));d.append(samples);
}
function seqSetupStudioTools(){
  const panel=element('details','seq-property-group');panel.id='seq-studio-tools';panel.append(element('summary','','✦ Phòng sáng tạo'));
  seqSetupAdvanced(panel);
  seqSetupReframe(panel);
  const wordLanguage=element('select');wordLanguage.setAttribute('aria-label','Ngôn ngữ nhận dạng từ');for(const [v,n] of [['','Tự nhận ngôn ngữ'],['vi','Tiếng Việt'],['en','Tiếng Anh'],['zh','Tiếng Trung'],['ja','Tiếng Nhật'],['ko','Tiếng Hàn'],['fr','Tiếng Pháp'],['de','Tiếng Đức'],['es','Tiếng Tây Ban Nha'],['ru','Tiếng Nga'],['th','Tiếng Thái']]){const o=element('option','',n);o.value=v;wordLanguage.append(o);}const downloadLabel=element('label','actions','Cho phép tải model Whisper còn thiếu (Internet)'),download=element('input');download.type='checkbox';download.checked=false;downloadLabel.prepend(download);panel.append(element('small','hint','Căn karaoke từ audio của clip đã chọn · tối đa 5 phút, tốc độ cố định. Model theo Cài đặt; chạy CPU riêng, có thể dừng trong Lịch sử. Chưa phải căn lời dịch.'),wordLanguage,downloadLabel,seqButton('Nhận dạng & duyệt từng từ…',()=>seqRecognizeWords(wordLanguage.value,download.checked)));
  const encoder=element('select');encoder.setAttribute('aria-label','Encoder xuất MP4');for(const [v,n] of [['libx264','CPU · x264 (mặc định)'],['h264_nvenc','NVIDIA · NVENC (thử nghiệm)'],['h264_qsv','Intel · QSV (thử nghiệm)'],['h264_amf','AMD · AMF (thử nghiệm)']]){const o=element('option','',n);o.value=v;encoder.append(o);}encoder.onchange=()=>seqChange(()=>sequence.doc.encoder=encoder.value);panel.addEventListener('toggle',()=>{if(panel.open&&sequence.doc)encoder.value=sequence.doc.encoder||'libx264';});panel.append(encoder,element('small','hint','GPU chỉ encode MP4, cần driver/phần cứng/FFmpeg hỗ trợ. Filter/AI vẫn CPU. Nếu báo lỗi chọn CPU; không tự fallback. Dùng dự án thử ≤30s để đo.'));
  const threads=element('label','field','Luồng encoder CPU (1 nhẹ / 2 cân bằng / 4–8 nhanh hơn nếu máy đủ khỏe)'),threadInput=element('input');Object.assign(threadInput,{type:'number',min:1,max:8,value:2});threads.append(threadInput);threadInput.onchange=()=>{const n=Number(threadInput.value);if(!Number.isInteger(n)||n<1||n>8){toast('Chọn 1–8 luồng encoder.',true);return;}seqChange(()=>sequence.doc.render_threads=n);};panel.addEventListener('toggle',()=>{if(panel.open&&sequence.doc)threadInput.value=sequence.doc.render_threads??2;});panel.append(threads);
  const style=element('select');style.setAttribute('aria-label','Phong cách chữ');for(const [v,name] of [['clean','Clean · nổi nhẹ'],['manga','Manga · vàng nổi'],['retro','Retro · máy chữ'],['karaoke','Karaoke · theo từ']]){const o=element('option','',name);o.value=v;style.append(o);}panel.append(element('small','hint','Chọn chữ để áp phong cách; bỏ chọn áp mọi chữ chưa khóa. Clip có mốc audio dùng mốc đã duyệt; chưa có mốc thì ước lượng theo độ dài từ.'),style,seqButton('Duyệt & áp phong cách chữ',()=>{seqRequire();const next=seqStyleProposal(sequence.doc,style.value,seqSelectedIds());if(confirm('Áp phong cách chữ? Nội dung và timeline giữ nguyên; có Hoàn tác.'))seqChange(()=>sequence.doc=next);}),seqButton('Phân tích nhịp / cảnh…',seqAnalyze),seqButton('Chọn vùng bám trên video',()=>{seqRequire();const {track,clip}=seqSelection();if(track?.kind!=='video'||!clip?.asset)throw Error('Chọn video nguồn, con trỏ trong đoạn còn lại ≤12s.');seqPause();sequence.rendered=null;seqClearMonitor();seqMonitor();sequence.objectPick=true;sequence.drawMask=true;$('seq-stage').classList.add('seq-drawing');toast('Kéo vùng có chi tiết trên video; sau dò chọn vùng mờ hoặc ảnh/sticker.');}),seqButton('Comic Freeze tại con trỏ',async()=>{const at=sequence.time,r=await seqStudioJob('comic');if(confirm('Thêm ảnh truyện tranh 2s đè lên video tại con trỏ? Audio không dừng; có Hoàn tác.'))seqAddToolMedia(r.media,'Comic Freeze',2000,at);}),seqButton('Sân khấu sóng âm podcast',async()=>{const {clip}=seqSelection(),at=clip?.start_ms,duration=clip?.duration_ms;const r=await seqStudioJob('stage');if(confirm('Thêm lớp sóng âm im tiếng đúng đoạn clip? Audio gốc giữ nguyên.'))seqAddToolMedia(r.media,'Sân khấu podcast',duration,at);}));
  const ratios=element('div','actions');for(const ratio of ['16:9','9:16','1:1']){const label=element('label','',ratio),input=element('input');input.type='checkbox';input.checked=true;input.value=ratio;label.prepend(input);ratios.append(label);}panel.append(element('small','hint','Xuất đa tỷ lệ giữ bố cục %. Chọn Canvas / Căn khung thông minh để duyệt từng tỷ lệ trước. 2K/4K tăng số pixel, không tự phục hồi chi tiết nguồn.'),ratios,seqButton('Xuất các tỷ lệ đã chọn',async()=>{if(!confirm('Render các bản đã chọn, có thể mất nhiều thời gian. Tiếp tục?'))return;const r=await seqStudioJob('multi',{ratios:[...ratios.querySelectorAll('input:checked')].map(x=>x.value),quality:Number($('seq-multi-quality').value)});sequence.outputFiles=r.files;$('seq-output').replaceChildren(...r.files.map(downloadLink));}),seqButton('Xuất gói dự án .rvp',async()=>{const r=await seqStudioJob('bundle');sequence.outputFiles=r.files;$('seq-output').replaceChildren(...r.files.map(downloadLink));}),seqButton('Đo render CPU · dự án ≤30s',async()=>{const r=await seqStudioJob('benchmark');const d=seqToolDialog('Kết quả đo render');d.append(element('pre','',JSON.stringify(r.report,null,2)),...r.files.map(downloadLink));}));
  const input=element('input');input.type='file';input.accept='.rvp';input.hidden=true;panel.append(input,seqButton('Nhập gói .rvp → dự án mới',()=>input.click()));input.onchange=async()=>{try{if(!input.files[0])return;if(!confirm('Nhập media từ gói do bạn tin cậy vào dự án mới? Không ghi đè dự án hiện tại.'))return;const asset=await upload(input.files[0]),result=await seqStudioJob('import',{asset:asset.id});await poll();await seqOpen(result.project_id);}catch(e){toast(e.message,true);}finally{input.value='';}};
  $('seq-draft').before(panel);
  const open=seqButton('✦ Công cụ dựng',()=>{panel.open=true;panel.scrollIntoView({block:'nearest'});});open.id='seq-open-studio';$('seq-library').before(open);
  // Move existing controls into compact groups; preserve handlers and values.
  const children=[...panel.children];let section=null;
  const begin=(title,node)=>{section=element('details','seq-tool-section');section.append(element('summary','',title));panel.insertBefore(section,node);};
  for(const node of children){
    if(node===wordLanguage.previousElementSibling)begin('Nhận dạng từ / Karaoke',node);
    if(node===encoder)begin('Encoder / hiệu năng xuất',node);
    if(node===style.previousElementSibling)begin('Chữ / AI hình / sáng tạo',node);
    if(node===ratios.previousElementSibling)begin('Xuất nhiều tỷ lệ / gói dự án',node);
    if(section)section.append(node);
  }
  const quality=element('select');quality.setAttribute('aria-label','Chất lượng xuất nhiều tỷ lệ');quality.id='seq-multi-quality';
  for(const [value,title] of [['720','720p · nhẹ'],['1080','1080p · Full HD'],['1440','1440p · 2K'],['2160','2160p · 4K']]){const option=element('option','',title);option.value=value;quality.append(option);}quality.value='1080';ratios.before(quality);
}
