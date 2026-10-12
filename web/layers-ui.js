"use strict";
const visualNames={visual_background:"Nền ảnh / video",overlay_layer:"Lớp phủ",blend_layer:"Hòa trộn"};
function timedActive(row,ms){return ms>=(row.start_ms||0)&&(row.end_ms==null||ms<row.end_ms);}
function timelineDuration(){const p=state.project;return Math.max(p?.video_info?.duration_ms||0,Number.isFinite($("video-preview").duration)?$("video-preview").duration*1000:0,...(p?.cues||[]).map(c=>c.end_ms))||10000;}
function trimInterval(start,end,delta,edge,duration){
  const minimum=Math.min(100,duration);
  if(edge==="start")start=Math.max(0,Math.min(end-minimum,start+delta));
  else if(edge==="end")end=Math.min(duration,Math.max(start+minimum,end+delta));
  else{const shift=Math.max(-start,Math.min(duration-end,delta));start+=shift;end+=shift;}
  return {start_ms:Math.round(start),end_ms:Math.round(end)};
}
function setupVisualLayers(){
  for(const [key,name] of Object.entries(visualNames)){
    const grid=detailPanel(name),field=element("label","field full","Chọn ảnh hoặc video (không lấy âm thanh)"),file=element("input");file.type="file";file.accept=".png,.jpg,.jpeg,.webp,.mp4,.mov,.mkv,.avi,.webm";field.append(file);grid.append(field);
    file.onchange=()=>Promise.resolve().then(async()=>{if(!state.project||!file.files[0])return;const asset=await upload(file.files[0]);state.project.edit[key].asset=asset.id;state.project.edit_assets??={};state.project.edit_assets[key]=asset;dirty();updateStage();renderTimeline();}).catch(e=>toast(e.message,true));
    grid.append(makeButton("Bỏ "+name,()=>{state.project.edit[key].asset="";dirty();updateStage();renderTimeline();}));
    const fields=[["x","Ngang (%)",0,100,1],["y","Dọc (%)",0,100,1],["width","Rộng (% khung)",1,200,1],["opacity","Độ hiện (0–1)",0,1,.05],["start_ms","Bắt đầu (giây)",0,86400,.1],["end_ms","Kết thúc (trống = hết video)",0,86400,.1]];
    for(const [prop,label,min,max,step] of fields){const box=element("label","field",label),input=element("input");input.type="number";Object.assign(input,{min,max,step});input.dataset.layer=key;input.dataset.prop=prop;input.onchange=()=>{const row=state.project.edit[key],value=input.value===""?null:Number(input.value)*(prop.endsWith("_ms")?1000:1);if(prop==="end_ms"&&value!=null&&value<=(row.start_ms||0)){toast("Kết thúc phải sau bắt đầu.");updateVisualLayers();return;}if(prop==="start_ms"&&row.end_ms!=null&&value>=row.end_ms){toast("Bắt đầu phải trước kết thúc.");updateVisualLayers();return;}row[prop]=value??(prop==="end_ms"?null:0);dirty();updateStage();renderTimeline();};box.append(input);grid.append(box);}
    if(key==="blend_layer"){const field=element("label","field","Kiểu hòa trộn"),select=element("select");for(const mode of ["normal","screen","multiply"]){const o=element("option","",{normal:"Bình thường",screen:"Screen · làm sáng",multiply:"Multiply · làm tối"}[mode]);o.value=mode;select.append(o);}select.dataset.layer=key;select.dataset.prop="mode";select.onchange=()=>{state.project.edit[key].mode=select.value;dirty();updateStage();};field.append(select);grid.append(field);}
    grid.append(element("p","hint full","Kéo hai đầu track dưới timeline để chọn thời gian. Video lớp được lặp; âm thanh của lớp không được ghép vào bản xuất."));
  }
  const video=$("video-preview");for(const event of ["timeupdate","seeked","play","pause","loadedmetadata"])video.addEventListener(event,()=>{syncTimedPreview();if(event==="loadedmetadata")renderTimeline();});
}
function updateVisualLayers(){
  if(!state.project||!$("video-source-layer"))return;
  const c=state.project.edit;
  for(const [key,name] of Object.entries(visualNames)){
    c[key]??={asset:"",x:50,y:50,width:100,opacity:key==="blend_layer"?.5:1,mode:key==="blend_layer"?"screen":"normal",start_ms:0,end_ms:null};
    const row=c[key],asset=state.project.edit_assets?.[key],wrap=document.querySelector(".video-wrap");
    for(const field of document.querySelectorAll(`[data-layer="${key}"]`)){if(document.activeElement!==field)field.value=field.dataset.prop==="mode"?row.mode:row[field.dataset.prop]==null?"":row[field.dataset.prop]/(field.dataset.prop.endsWith("_ms")?1000:1);}
    let node=$("visual-"+key);const isImage=asset&&/\.(png|jpe?g|webp)(?:$|\?)/i.test(asset.url||asset.name||"");
    if(node&&((node.tagName==="IMG")!==Boolean(isImage))){node.remove();node=null;}
    if(!node&&row.asset&&asset){node=element(isImage?"img":"video","visual-layer");node.id="visual-"+key;node.setAttribute("aria-label",name);if(!isImage){node.muted=true;node.loop=true;node.playsInline=true;node.preload="auto";}
      if(key==="visual_background")wrap.prepend(node);else wrap.append(node);
    }
    if(!node)continue;if(!row.asset||!asset){node.remove();continue;}
    if(node.getAttribute("src")!==asset.url)node.src=asset.url;
    Object.assign(node.style,{width:row.width+"%",left:`${(100-row.width)*row.x/100}%`,top:`${row.y}%`,transform:`translateY(-${row.y}%)`,opacity:row.opacity,mixBlendMode:key==="blend_layer"?row.mode:"normal",zIndex:key==="visual_background"?"0":"2"});
  }
  syncTimedPreview();
}
function syncTimedPreview(){
  if(!state.project)return;const main=$("video-preview"),ms=main.currentTime*1000,c=state.project.edit;
  $("old-sub-mask")?.classList.toggle("hidden",c.original_subtitles==="keep"||!timedActive({start_ms:c.mask_start_ms,end_ms:c.mask_end_ms},ms));
  (c.blur_regions||[]).forEach((row,i)=>{const node=document.querySelector(`.custom-blur-mask[data-mask-index="${i}"]`);if(node)node.classList.toggle("hidden",!timedActive(row,ms));});
  for(const key of Object.keys(visualNames)){const node=$("visual-"+key),row=c[key];if(!node||!row)continue;const active=timedActive(row,ms);node.classList.toggle("hidden",!active);if(node.tagName==="VIDEO"){if(Number.isFinite(node.duration)&&node.duration>0){const desired=Math.max(0,main.currentTime-(row.start_ms||0)/1000)%node.duration;if(Math.abs(node.currentTime-desired)>.15)node.currentTime=desired;}if(active&&!main.paused)node.play().catch(()=>{});else node.pause();}}
}
function renderLayerTracks(target,zoom){
  const p=state.project;if(!p)return;const duration=timelineDuration(),rows=[];
  if(p.edit.original_subtitles!=="keep"){const c=p.edit,row={get start_ms(){return c.mask_start_ms||0;},set start_ms(value){c.mask_start_ms=value;},get end_ms(){return c.mask_end_ms;},set end_ms(value){c.mask_end_ms=value;}};rows.push({row,label:"Vùng phụ đề gốc",index:-1});}
  (p.edit.blur_regions||[]).forEach((row,i)=>rows.push({row,label:`Vùng mờ ${i+1}`,index:i}));
  for(const [key,label] of Object.entries(visualNames))if(p.edit[key]?.asset)rows.push({row:p.edit[key],label,key});
  target.style.height=48+rows.length*29+"px";
  rows.forEach(({row,label,index,key},i)=>{
    const lane=element("div","layer-lane"),bar=element("button","layer-clip",label);lane.style.top=48+i*29+"px";lane.style.width="100%";
    const position=()=>{const end=Math.min(duration,row.end_ms??duration);bar.style.left=(row.start_ms||0)/1000*zoom+"px";bar.style.width=Math.max(8,(end-(row.start_ms||0))/1000*zoom)+"px";bar.title=`${label}: ${((row.start_ms||0)/1000).toFixed(2)} → ${(end/1000).toFixed(2)} giây`;};position();
    bar.setAttribute("aria-label",label+" · kéo để đổi thời gian");
    for(const edge of ["start","end"]){const handle=element("span","clip-handle "+edge);handle.dataset.edge=edge;bar.append(handle);}
    bar.onclick=()=>{if(index!=null){ui.maskIndex=index;refreshMaskList();updateStage();}$("video-preview").currentTime=(row.start_ms||0)/1000;};
    bar.onpointerdown=e=>{if(state.jobs.some(j=>j.project_id===p.id&&["queued","running"].includes(j.status)))return;e.preventDefault();bar.setPointerCapture(e.pointerId);const x=e.clientX,start=row.start_ms||0,end=Math.min(duration,row.end_ms??duration),edge=e.target.dataset.edge,restore={start_ms:row.start_ms,end_ms:row.end_ms};
      let moved=false;
      const move=evt=>{if(Math.abs(evt.clientX-x)<2&&!moved)return;moved=true;Object.assign(row,trimInterval(start,end,(evt.clientX-x)/zoom*1000,edge,duration));position();syncTimedPreview();};
      const finish=evt=>{if(evt.type==="pointercancel")Object.assign(row,restore);else if(moved)dirty();bar.removeEventListener("pointermove",move);bar.removeEventListener("pointerup",finish);bar.removeEventListener("pointercancel",finish);if(moved){updateVisualLayers();renderTimeline();}};bar.addEventListener("pointermove",move);bar.addEventListener("pointerup",finish);bar.addEventListener("pointercancel",finish);
    };
    lane.append(bar);target.append(lane);
  });
  syncTimedPreview();
}
