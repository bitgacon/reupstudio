"use strict";
const $ = id => document.getElementById(id);
const state = {csrf:"", voices:[], jobs:[], projects:[], settings:{}, selectedVoice:"", voiceFilter:"all",
  project:null, dirty:false, cloneAsset:null, speakers:{}, jobsSeen:new Map(), intents:new Map(), playerFiles:[], polling:false};
const statusNames = {queued:"Đang chờ",running:"Đang tạo",complete:"Hoàn thành",review:"Cần xem lại",error:"Lỗi",pending:"Chưa tạo",cancelled:"Đã dừng",interrupted:"Bị gián đoạn"};
const taskNames = {voices:"Nạp thư viện giọng",tts:"Văn bản → Giọng nói",clone:"Clone giọng",document:"Đọc tài liệu",podcast:"Hội thoại / Podcast",import_srt:"Nhập SRT",asr:"Nhận dạng video",translate:"Dịch / Rút gọn",dub:"Tạo lời lồng tiếng",export:"Xuất kết quả",editor_media:"Nhập media editor",editor_preview:"Render xem trước",editor_export:"Xuất timeline"};
taskNames.tts_voices='Danh sách giọng ElevenLabs';
taskNames.project_transfer='Chuyển dự án';
Object.assign(taskNames,{download:'Tải & render media',download_scan:'Lấy link kênh/playlist'});
taskNames.editor_separate='AI · tách giọng/nhạc editor';
const samples = {intro:"Xin chào! Đây là Reup Voice Studio. Một không gian nhỏ để bạn biến ý tưởng thành những giọng nói đầy cảm xúc.",story:"Buổi sáng hôm ấy, nắng vừa ghé qua ô cửa. Cô mở cuốn sổ cũ, và một câu chuyện tưởng đã ngủ quên bỗng bắt đầu…",explain:"Mỗi câu chuyện đều có một giọng kể riêng. Với công cụ xử lý trên máy, bạn có thể nghe thử, chỉnh lời đọc và tạo lại từng phần trước khi xuất bản."};
const podcastSample = "[Host]: Xin chào các bạn! Hôm nay chúng ta cùng trò chuyện về cách kể một câu chuyện thật hay.\n[Khách mời]: Rất vui được tham gia. Theo tôi, một câu chuyện hay bắt đầu từ sự chân thành.\n[Host]: Vậy điều gì giúp người nghe muốn ở lại?\n[Khách mời]: Một giọng kể tự nhiên, khoảng nghỉ hợp lý, và một điều đáng để nhớ.";
function element(tag, className, text) {const el=document.createElement(tag); if(className) el.className=className; if(text!==undefined) el.textContent=text; return el;}
function toast(text,error=false) {const el=$("toast");el.textContent=text;el.classList.remove("hidden");el.classList.toggle("error",error);clearTimeout(toast.timer);toast.timer=setTimeout(()=>el.classList.add("hidden"),error?11000:6000);}
function on(id,event,handler) {$(id).addEventListener(event,e=>{try{Promise.resolve(handler(e)).catch(err=>toast(err.message,true));}catch(err){toast(err.message,true);}});}
async function api(path,body) {
  const response=await fetch("/api/"+path,{method:body===undefined?"GET":"POST",headers:body===undefined?{}:{"Content-Type":"application/json","X-Reup-Token":state.csrf},body:body===undefined?undefined:JSON.stringify(body)});
  const data=await response.json(); if(!response.ok) throw Error(typeof data.detail==="string"?data.detail:JSON.stringify(data.detail||data));return data;
}
function upload(file,label) {
  if(!file) return Promise.reject(Error("Chưa chọn file."));
  return new Promise((resolve,reject)=>{const xhr=new XMLHttpRequest();xhr.open("POST","/api/upload");xhr.setRequestHeader("X-Reup-Token",state.csrf);
    xhr.upload.onprogress=e=>{if(label&&e.lengthComputable)$(label).textContent=`Đang nhập ${file.name} · ${Math.round(e.loaded/e.total*100)}%`;};
    xhr.onload=()=>{let data;try{data=JSON.parse(xhr.responseText);}catch{reject(Error("Không đọc được phản hồi tải file."));return;}if(xhr.status>=400)reject(Error(data.detail||"Không nhập được file."));else{if(label)$(label).textContent=file.name;resolve(data);}};
    xhr.onerror=()=>reject(Error("Mất kết nối khi nhập file.")); const form=new FormData();form.append("file",file);xhr.send(form);
  });
}
function changeTab(name) {if(name!=='removal'&&$('vsr-video'))$('vsr-video').pause();switchPlayerTab(name);document.querySelectorAll(".page").forEach(p=>p.classList.toggle("active",p.id==="page-"+name));document.querySelectorAll("[data-tab]").forEach(b=>b.classList.toggle("active",b.dataset.tab===name));document.querySelectorAll(".tab-actions").forEach(p=>p.classList.toggle("hidden",p.dataset.context!==name));localStorage.setItem("rv-tab",name);renderJobs();}
function voiceOptions(select, selected, common=false) {select.replaceChildren(); if(common){const opt=element("option","","Giọng chung");opt.value="";select.append(opt);}else if(!state.voices.length){const opt=element("option","","Bấm Nạp giọng ở mục TTS");opt.value="";select.append(opt);}for(const row of state.voices){const opt=element("option","",row.name+(row.custom?" · Clone":""));opt.value=row.id;opt.dataset.i18nSkip='';select.append(opt);}if([...select.options].some(o=>o.value===selected))select.value=selected;}
function gender(row) {const value=(row.gender||"").toLowerCase();return value==="female"||value==="nữ"?"female":value==="male"||value==="nam"?"male":"custom";}
function selectVoice(id){
  state.selectedVoice=id;localStorage.setItem("rv-voice",id);
  for(const row of $("voice-list").querySelectorAll(".voice-row")){const selected=row.dataset.voiceId===id;row.classList.toggle("selected",selected);row.setAttribute("aria-checked",String(selected));}
  $("selected-voice-name").textContent="Đang chọn: "+(state.voices.find(v=>v.id===id)?.name||"Chưa chọn giọng");
}
function renderVoices() {
  $("voice-count").textContent=state.voices.length; if(!state.selectedVoice||!state.voices.some(v=>v.id===state.selectedVoice)) state.selectedVoice=state.voices[0]?.id||"";
  const query=$("voice-search").value.toLocaleLowerCase("vi"); const rows=state.voices.filter(v=>(state.voiceFilter==="all"||(state.voiceFilter==="custom"?v.custom:gender(v)===state.voiceFilter))&&`${v.name} ${v.description}`.toLocaleLowerCase("vi").includes(query));
  const list=$("voice-list"),scroll=list.scrollTop;list.replaceChildren();if(!rows.length) list.append(element("div","empty",state.voices.length?"Không có giọng phù hợp bộ lọc.":"Bấm Nạp giọng để khởi động VieNeu."));
  for(const voice of rows) {const row=element("div","voice-row"+(state.selectedVoice===voice.id?" selected":""));row.tabIndex=0;row.setAttribute("role","radio");row.setAttribute("aria-checked",state.selectedVoice===voice.id);row.setAttribute("aria-label",voice.name);
    row.append(element("span","avatar "+(voice.custom?"custom":gender(voice)),voice.custom?"✧":gender(voice)==="female"?"♀":"♂"));const label=element("div","voice-label");label.append(element("strong","",voice.name),element("small","",voice.description||(voice.custom?"Giọng clone của bạn":"Giọng VieNeu · 48 kHz")));row.append(label);
    const preview=element("button","voice-preview","▶");preview.title="Nghe thử "+voice.name;preview.setAttribute("aria-label",preview.title);preview.onclick=e=>{e.stopPropagation();startTask("tts",{text:"Xin chào! Đây là giọng đọc của tôi. Chúc bạn một ngày tốt lành.",voice:voice.id,rate:1},{play:true,title:"Nghe thử · "+voice.name}).catch(err=>toast(err.message,true));};row.append(preview);
    row.dataset.voiceId=voice.id;
    const choose=()=>selectVoice(voice.id);row.onclick=choose;row.onkeydown=e=>{if(e.target===row&&(e.key==="Enter"||e.key===" ")){e.preventDefault();choose();}};list.append(row);
  }
  selectVoice(state.selectedVoice);list.scrollTop=scroll;
}
function refreshSelects() {document.querySelectorAll(".voice-select").forEach(sel=>voiceOptions(sel,sel.id==="dub-voice"?(state.project?.voice||state.selectedVoice):(sel.value||state.selectedVoice)));renderSpeakers();}
function textCount() {const text=$("tts-text").value;$("text-count").textContent=`${text.length.toLocaleString("vi")} ký tự · ${text.trim()?text.trim().split(/\s+/).length:0} từ`;estimateDuration();localStorage.setItem("rv-tts",text);}
function downloadLink(file) {const a=element("a","download","↓ "+file.type.toUpperCase());a.href=file.url;a.download=file.name;a.title=file.name;return a;}
function filesPanel(files,target) {target.replaceChildren();for(const file of files||[])target.append(downloadLink(file));}
function showAudio(files,title="Audio đã tạo",autoplay=true,tab=ui.tab) {
  const chosen=(files||[]).find(f=>f.type==="mp3")||(files||[]).find(f=>f.type==="wav");if(!chosen)return;
  ui.results[tab]={files,title};if(tab!==ui.tab)return;
  state.playerFiles=files||[];const audio=state.playerFiles.find(f=>f.type==="mp3")||state.playerFiles.find(f=>f.type==="wav");if(!audio)return;
  $("player").src=audio.url;$("player-title").textContent=title;$("player-detail").textContent="Nghe lại trước khi sử dụng · file đã lưu trên máy";filesPanel(files,$("player-downloads"));
  if(autoplay)$("player").play().catch(()=>toast("Audio đã sẵn sàng. Bấm ▶ ở thanh phát để nghe."));
}
async function startTask(kind,payload={},intent={}) {
  payload.ui_tab=payload.project_id?"dub":ui.tab;intent.tab=payload.ui_tab;
  const job=await api("jobs",{kind,payload});state.intents.set(job.id,intent);state.jobsSeen.set(job.id,"queued");toast("Đã thêm: "+taskNames[kind]);await poll();return job;
}
async function taskFinished(summary) {
  const intent=state.intents.get(summary.id)||{};state.intents.delete(summary.id);
  if(summary.status==="error"){if(summary.project_id&&state.project?.id===summary.project_id&&!state.dirty)await loadProject(summary.project_id,false);toast(summary.message,true);return;}
  const job=await api("jobs/"+summary.id);const result=job.result||{};
  if(job.kind==='download_scan'&&result.entries){$('download-urls').value=result.entries.map(r=>r.url).join('\n');changeTab('downloads');}
  if(job.kind==='download')await refreshDownloads();
  if(['subtitle_remove','vsr_check','subtitle_prepare'].includes(job.kind))await refreshRemoval();
  if(job.kind==='removal_preview'&&job.result){removalApplyPreview(job.result.asset,job.result.preview);if(removalUI.outputAsset===job.result.asset)removalApplyOutputPreview(job.result.preview);}
  if(job.kind==='removal_effect_preview'&&job.result)removalShowEffect(job.result);
  if(job.kind==='library_install'){await refreshLibraries();await refreshRemoval(true);await refreshTTSProviders();}
  if(job.kind==='tts_voices')await refreshTTSProviders();
  if(job.kind==="document"&&result.text){$("document-text").value=result.text;localStorage.setItem("rv-document",result.text.slice(0,100000));$("document-warnings").textContent=(result.warnings||[]).join("\n");$("document-warnings").classList.toggle("hidden",!result.warnings?.length);}
  if(job.kind==="clone"&&result.voice){state.selectedVoice=result.voice.name;await poll();renderVoices();$("clone-voice").value=result.voice.name;}
  if(result.files){showAudio(result.files,intent.title||taskNames[job.kind],Boolean(intent.play),job.ui_tab||intent.tab||"tts");if(job.kind==="export")filesPanel(result.files,$("export-results"));}
  if(job.project_id&&state.project?.id===job.project_id){await loadProject(job.project_id,false);}
  if(job.kind==='project_transfer'&&job.status==='complete'&&result.project_id){await poll();changeTab(result.tab);if(result.tab==='edit')await seqOpen(result.project_id);else await loadProject(result.project_id);}
  if(job.status==="complete")toast(job.message);else if(job.status==="cancelled")toast("Đã dừng. Các cue hoàn thành vẫn được giữ.");
}
async function poll(initial=false) {
  if(state.polling)return;state.polling=true;
  try {const data=await api("state");state.csrf=data.csrf;state.settings=data.settings;state.projects=data.projects;state.jobs=data.jobs;state.job_load_issues=data.job_load_issues||[];
    updateBuildStatus(data.web_build);
    const voicesChanged=JSON.stringify(state.voices)!==JSON.stringify(data.voices);state.voices=data.voices;
    $("engine-status").classList.toggle("ready",data.engine.running);$("engine-status").replaceChildren(element("i"),document.createTextNode(data.engine.running?" Engine đã mở":" Chưa nạp model"));
    refreshOutputFolders();
    await refreshDownloads();
    await refreshRemoval();
    renderLibraryProgress();
    if(ui.tab==='removal')await refreshRemovalPreview();
    seqRefreshProjects();
    if(voicesChanged||initial){renderVoices();refreshSelects();}
    ui.defaults=data.editor_defaults;ui.presets=data.presets||[];ui.folderPicker=data.folder_picker;renderProjects();renderJobs();if($("history-dialog").open)renderHistory();
    if(initial){for(const tab of Object.keys(tabTitles)){const saved=state.jobs.find(j=>(j.ui_tab||"tts")===tab&&j.status==="complete"&&["tts","podcast","export"].includes(j.kind)&&j.result?.files?.some(f=>["wav","mp3"].includes(f.type)));if(saved)ui.results[tab]={files:saved.result.files,title:taskNames[saved.kind]};}if(ui.results[ui.tab])showAudio(ui.results[ui.tab].files,ui.results[ui.tab].title,false);}
    for(const job of state.jobs){const previous=state.jobsSeen.get(job.id);state.jobsSeen.set(job.id,job.status);if(!initial&&previous&&["queued","running"].includes(previous)&&!["queued","running"].includes(job.status))setTimeout(()=>taskFinished(job).catch(e=>toast(e.message,true)),0);}
  } finally {state.polling=false;}
}
function renderJobs() {
  const context=state.jobs.filter(j=>(j.ui_tab||"tts")===ui.tab);const running=context.find(j=>j.status==="running")||context.find(j=>j.status==="queued");$("job-panel").classList.toggle("hidden",!running);$("history-count").textContent=state.jobs.length;
  if(running){$("job-title").textContent=`${Math.round(running.progress)}% · ${taskNames[running.kind]||running.kind}`;$("job-message").textContent=running.message;$("job-progress").value=running.progress;$("job-cancel").onclick=()=>api("jobs/"+running.id+"/cancel",{}).then(()=>toast("Sẽ dừng sau bước hiện tại.")).catch(e=>toast(e.message,true));}
  const busy=state.jobs.some(j=>j.project_id===state.project?.id&&["running","queued"].includes(j.status));
  if(state.project){$("project-editor").querySelectorAll("input:not(#timeline-zoom),textarea,select,button:not(#project-back):not(#dub-preview)").forEach(el=>el.disabled=busy);$("save-status").textContent=busy?"Đang xử lý…":state.dirty?"Có thay đổi chưa lưu":"Đã lưu";}
}
function renderHistory() {
  const list=$("history-list");list.replaceChildren();if(!state.jobs.length)list.append(element("div","empty","Chưa có tác vụ."));
  if(state.job_load_issues?.length)list.append(element('p','hint','Một số bản ghi lịch sử bị lỗi; file gốc được giữ để khôi phục.'));
  for(const job of state.jobs){const row=element("article","history-row");const head=element("div");head.append(element("strong","",taskNames[job.kind]||job.kind),element("span","badge "+job.status,statusNames[job.status]||job.status),element("small","",new Date(job.created*1000).toLocaleString("vi-VN")));row.append(head,element("p","",job.message));
    const downloads=element("div","downloads");for(const file of job.result?.files||[])downloads.append(downloadLink(file));
    if(job.retryable){const retry=makeButton('↻ Chạy lại',async()=>{
      retry.disabled=true;try{const info=await api('jobs/'+job.id+'/retry-info');
        const message=info.network?'Chạy lại tác vụ này? Có thể gửi dữ liệu lên Internet và phát sinh phí/quota.':'Chạy lại tác vụ này? Tạo job mới, giữ kết quả cũ.';
        const projectNote=info.uses_current_project?' Dùng dữ liệu dự án hiện tại; giữ phần cue đã tạo còn hợp lệ.':'';
        if(!confirm(uiLabel(message)+uiLabel(projectNote)))return;
        await api('jobs/'+job.id+'/retry',{confirmed:true,network_confirmed:info.network});await poll();renderHistory();toast('Đã tạo lượt chạy lại.');
      }finally{retry.disabled=false;}
    });retry.dataset.retryJob=job.id;downloads.prepend(retry);}
    if(job.result?.files?.some(f=>["wav","mp3"].includes(f.type))){const play=element("button","quiet","▶ Nghe");play.onclick=()=>{changeTab(job.ui_tab||"tts");showAudio(job.result.files,taskNames[job.kind]);$("history-dialog").close();};downloads.prepend(play);}
    if(job.kind==="document"&&job.status==="complete"){const open=element("button","quiet","Mở văn bản");open.onclick=()=>api("jobs/"+job.id).then(r=>{$("document-text").value=r.result.text;changeTab("documents");$("history-dialog").close();}).catch(e=>toast(e.message,true));downloads.append(open);}
    const del=makeButton('× Xóa lịch sử',async()=>{if(!confirm('Xóa mục lịch sử này? File kết quả vẫn được giữ.'))return;await api('history/clear',{ids:[job.id]});await poll();renderHistory();});del.disabled=['queued','running'].includes(job.status);downloads.append(del);
    row.append(downloads);list.append(row);
  }
}
function renderSpeakers() {
  const names=[...$("podcast-text").value.matchAll(/^\s*\[([^\]\n]{1,60})\]\s*:/gm)].map(m=>m[1].trim());const unique=[...new Set([...ui.characters,...names])];const list=$("speaker-list");list.replaceChildren();
  for(const [i,name] of unique.entries()){const card=element('div','podcast-speaker-card');card.dataset.speaker=name;const row=element("div","speaker-row");const assign=makeButton(name,()=>assignCharacter(name));assign.title="Gán phần văn bản đang bôi đen cho "+name;row.append(element("span","avatar "+(i%2?"female":""),name.slice(0,1).toUpperCase()),assign);const cfg=podcastSpeech(name),external=cfg&&cfg.provider!=='vieneu';const sel=element("select");sel.setAttribute("aria-label","Giọng "+name);voiceOptions(sel,cfg?.voice||state.speakers[name]||state.voices[i%Math.max(1,state.voices.length)]?.id);if(!external)state.speakers[name]=sel.value;sel.hidden=!!external;sel.onchange=()=>{state.speakers[name]=sel.value;localStorage.setItem("rv-speakers",JSON.stringify(state.speakers));if(cfg){cfg.voice=sel.value;savePodcastSpeech();}card.querySelector('.podcast-speaker-summary').textContent=podcastSpeechSummary(name);};row.append(sel,makeButton('Giọng / ngôn ngữ',()=>podcastEditSpeech(name)),makeButton('▶',()=>podcastPreviewSpeech(name)));row.lastChild.title='Nghe thử lượt thoại đầu của '+name;card.append(row,element('small','podcast-speaker-summary',podcastSpeechSummary(name)));list.append(card);}
  if(!unique.length)list.append(element("div","empty","Nhập [Tên nhân vật]: lời thoại để gán giọng."));
}
function dirty() {state.dirty=true;$("save-status").textContent="Có thay đổi chưa lưu";}
function editPayload() {const p=state.project;return {revision:p.revision,name:$("project-name").value,voice:$("dub-voice").value||p.voice,video:p.video,edit:p.edit,tts:p.tts||null,translation_consent:!!p.translation_consent,cues:p.cues.map(c=>({id:c.id,start_ms:c.start_ms,end_ms:c.end_ms,source_text:c.source_text,text:c.text,translation:c.translation||"",voice:c.voice||"",rate:c.rate||1,tts:c.tts||null}))};}
async function saveProject() {if(!state.project)throw Error("Chọn dự án trước.");if(!state.dirty)return;state.project=await api("projects/"+state.project.id,editPayload());state.dirty=false;$("save-status").textContent="Đã lưu";renderIssues();renderTimeline();}
async function loadProject(id,switchView=true) {state.project=await api("projects/"+id);state.dirty=false;$("project-name").value=state.project.name;voiceOptions($("dub-voice"),state.project.voice||state.selectedVoice);if(!state.project.voice&&$("dub-voice").value){state.project.voice=$("dub-voice").value;dirty();}
  $("allow-translation").checked=state.project.translation_consent===true;
  if(switchView){$("project-list-view").classList.add("hidden");$("project-editor").classList.remove("hidden");changeTab("dub");}
  const v=state.project.video_asset;const url=state.project.preview?.url||v?.url;$("video-empty").classList.toggle("hidden",!!v);$("video-name").textContent=v?.name||"";if(v&&$("video-preview").getAttribute("src")!==url)$("video-preview").src=url;if(!v){$("video-preview").removeAttribute("src");$("video-preview").load();}loadEditControls();
  renderCues();renderTimeline();renderIssues();filesPanel(state.project.exports,$("export-results"));renderJobs();
}
function renderProjects(){const grid=$('project-grid');grid.replaceChildren();const projects=state.projects.filter(p=>!p.kind||['dub','hybrid'].includes(p.kind));if(!projects.length){grid.append(element('div','empty','Tạo dự án đầu tiên để nhập video hoặc SRT.'));return;}for(const p of projects){const card=element('article','project-card'),button=element('button','project-open');button.append(element('strong','',p.name),element('span','meta',`${p.cues} câu · ${p.complete} đã tạo`));button.onclick=()=>loadProject(p.id).catch(e=>toast(e.message,true));const remove=makeButton('Xóa',()=>removeProject(p.id),'project-delete');remove.title='Xóa khỏi danh sách · có xác nhận và có thể khôi phục';remove.setAttribute('aria-label','Xóa dự án '+p.name);card.append(button,remove);grid.append(card);}}

async function removeProject(id){
  if(!id)throw Error('Chọn dự án trước.');
  if(sequence.busy||sequence.saving)throw Error('Chờ tác vụ / lưu Biên tập hoàn tất.');
  if(!confirm('Xóa dự án khỏi danh sách? Thư mục, video nguồn và kết quả vẫn giữ để khôi phục. Các sửa chưa lưu sẽ bị bỏ.'))return;
  if(sequence.id===id)clearTimeout(sequence.timer);
  await api('projects/'+id+'/delete',{});
  if(state.project?.id===id){state.project=null;state.dirty=false;$('video-preview').pause();$('project-editor').classList.add('hidden');$('project-list-view').classList.remove('hidden');}
  if(sequence.id===id){seqPause();clearTimeout(sequence.timer);seqClearMonitor();sequence.id='';sequence.doc=null;sequence.dirty=false;sequence.undo=[];sequence.redo=[];sequence.selected='';sequence.media=new Map();sequence.generation++;localStorage.removeItem('rv-editor-'+id);seqRefresh();}
  await poll();toast('Đã xóa khỏi danh sách. Có thể khôi phục dự án; file vẫn giữ.');
}
async function restoreProjects(){
  const rows=await api('deleted-projects');let dialog=$('deleted-project-dialog');if(!dialog){dialog=element('dialog','large-dialog');dialog.id='deleted-project-dialog';document.body.append(dialog);}dialog.replaceChildren();dialog.append(makeButton('Đóng ×',()=>dialog.close()));
  if(!rows.length)dialog.append(element('p','','Không có dự án đã xóa.'));
  for(const row of rows){const item=element('div','history-row');item.append(element('strong','',row.name),makeButton('Khôi phục',async()=>{await api('projects/'+row.id+'/restore',{});await poll();dialog.close();}));dialog.append(item);}dialog.showModal();
}
function setupCleanupUI(){
  setupLLMUI();
  if($('history-dialog').dataset.cleanup)return;$('history-dialog').dataset.cleanup='1';
  const clear=makeButton('Xóa lịch sử đã kết thúc',async()=>{if(!confirm('Xóa lịch sử đã kết thúc? Tác vụ đang chạy và mọi file kết quả vẫn giữ.'))return;await api('history/clear',{});await poll();renderHistory();});$('history-dialog').querySelector('.card-heading').append(clear);
  $('seq-open').after(makeButton('Xóa dự án',()=>removeProject($('seq-project').value)),makeButton('Khôi phục dự án',restoreProjects));
  $('project-save').after(makeButton('Xóa dự án',()=>removeProject(state.project?.id)));
  $('project-save').after(makeButton('→ Biên tập',async()=>{
    if(!state.project)throw Error('Chọn dự án trước.');await saveProject();
    if(!confirm('Tạo bản sao sang Biên tập? Khi audio đã tạo đúng phiên bản, giữ lời đọc và hiệu ứng trong video. Nếu chưa có audio, chỉ chuyển video nguồn, phụ đề và tiêu đề. Bản gốc giữ nguyên.'))return;
    await startTask('project_transfer',{project_id:state.project.id,target:'edit',revision:state.project.revision,confirmed:true});
  }));
  $('seq-save').after(makeButton('→ Lồng tiếng',async()=>{
    seqRequire();await seqSave();if(sequence.dirty)throw Error('Lưu timeline trước khi chuyển.');
    if(!confirm('Render toàn bộ timeline thành video rồi tạo bản sao sang Lồng tiếng? Chữ và hiệu ứng sẽ nằm trong video. Nhập SRT / nhận dạng lại để tạo lời đọc. Bản gốc giữ nguyên.'))return;
    await startTask('project_transfer',{project_id:sequence.id,target:'dub',revision:sequence.doc.revision,confirmed:true});
  }));
  $('project-grid').before(makeButton('Khôi phục dự án đã xóa',restoreProjects));
  const gemini=makeButton('Dùng Gemini · Google AI Studio',()=>{
    $('setting-url').value='https://generativelanguage.googleapis.com/v1beta/openai';$('setting-model').value='gemini-3.8-flash';
    if(state.project){const provider=document.querySelector('[data-edit="translation_provider"]');if(provider){provider.value='api';provider.dispatchEvent(new Event('input'));}}
    toast('Giữ/nhập key rồi Lưu cài đặt. Trong dự án chọn Bộ dịch Gemini / API và cho phép gửi văn bản.');
  });
  gemini.type='button';
  $('setting-url').parentElement.before(gemini,element('p','hint','Key Google AI Studio dùng Gemini API, không dùng URL trang aistudio.google.com. Tên model API viết dạng gemini-3.8-flash. Dự án phải chọn Bộ dịch Gemini / API; Google không-key không dùng key này.'));
}
function selectedCueIds(){return [...$("cue-list").querySelectorAll(".cue-select:checked")].map(x=>Number(x.dataset.id));}
function makeButton(text,fn,cls="quiet") {const b=element("button",cls,text);b.onclick=()=>Promise.resolve().then(fn).catch(e=>toast(e.message,true));return b;}
function compactCueText(input){input.rows=1;input.style.height="auto";input.style.height=Math.min(90,Math.max(32,input.scrollHeight))+"px";}
function cueEstimate(cue){const e=cue.estimate;return e&&e.text===cue.text&&e.rate===Number(cue.rate||1)&&e.start_ms===cue.start_ms&&e.end_ms===cue.end_ms?e:null;}
function scheduleCueEstimate(card,cue){
  clearTimeout(card.estimateTimer);const snapshot={id:cue.id,text:cue.text,rate:Number(cue.rate||1),start_ms:cue.start_ms,end_ms:cue.end_ms};
  card.estimateTimer=setTimeout(async()=>{try{const estimate=await api('cue-estimate',snapshot);if(!card.isConnected||Object.keys(snapshot).some(k=>snapshot[k]!==cue[k]&&!(k==='rate'&&snapshot[k]===Number(cue.rate||1))))return;cue.estimate=estimate;updateCueSpeed(card,cue);}catch(error){if(card.isConnected){const badge=card.querySelector('.cue-speed');badge.textContent='Không ước tính được · kiểm tra chữ/ngắt nghỉ';badge.title=error.message;}}},350);
}
function updateCueSpeed(card,cue){
  let badge=card.querySelector('.cue-speed');if(!badge){badge=element('div','cue-speed');const head=card.querySelector('.cue-head');head.insertBefore(badge,head.querySelector('.badge'));}
  const ready=!!cue.audio&&['complete','review'].includes(cue.status);
  const estimate=cueEstimate(cue),speed=ready?Number(cue.generated_rate??cue.rate??1)*Number(cue.speed_factor??1):estimate?.speed;
  const severity=speed!=null?(speed<=1.3?'normal':speed<=1.5?'caution':speed<=1.8?'fast':'very-fast'):'unknown';
  badge.className='cue-speed '+severity;
  badge.style.setProperty('--speed-warning',String(Math.max(0,Math.min(1,((speed??1)-1.3)/.2))));
  const slot=(cue.end_ms-cue.start_ms)/1000;
  badge.textContent=ready?`Tốc độ thực tế ${speed.toFixed(2)}×, khung ${slot.toFixed(2)}s`:(estimate?.speed!=null?`Ước tính ${estimate.speed.toFixed(2)}×, khung ${slot.toFixed(2)}s${cue.audio?' · audio cũ':''}`:(slot<=0?'Khung cue không hợp lệ':cue.audio?'Audio cũ · đang ước tính':'Chưa có audio · đang ước tính'));
  badge.title=ready?`Đặt ${Number(cue.generated_rate??cue.rate??1).toFixed(2)}× × căn ${Number(cue.speed_factor??1).toFixed(2)}×${cue.voiced_ms!=null?' · lời trước căn '+(cue.voiced_ms/1000).toFixed(2)+'s':''}. Nghe audio đã căn, không cần render video.`:'Tạo lại audio để cập nhật tốc độ thực tế.';
  if(!ready&&estimate)badge.title=`Ước tính lời ${estimate.min_seconds.toFixed(2)}–${estimate.max_seconds.toFixed(2)}s, đã tính từ điển/ngắt nghỉ. Không phải đo audio thật; nên rút gọn nếu nhanh. ${cue.audio?'Audio cũ chưa cập nhật.':''}`;
  const listen=card.querySelector('.cue-listen');if(listen)listen.disabled=!ready;
}
function cueMatchesFilter(cue,filter,edit={}){
  if(filter==='all')return true;
  if(filter==='review')return ['review','error'].includes(cue.status);
  if(filter==='fast'){const ready=!!cue.audio&&['complete','review'].includes(cue.status);return (ready?Number(cue.generated_rate??cue.rate??1)*Number(cue.speed_factor??1):cueEstimate(cue)?.speed??Number(cue.rate??1))>1.3;}
  if(filter==='untranslated'){
    const target=edit.target_language||'vi';
    if(target!=='vi')return !(cue.translation||'').trim()||cue.translation_language!==target;
    if(!(cue.text||'').trim())return true;
    if(edit.source_language==='vi')return false;
    return cue.translation_state?.text?.status!=='complete'&&(cue.text||'').trim()===(cue.source_text||'').trim();
  }
  return !['review','complete'].includes(cue.status);
}
function renderCues() {
  if(!state.project)return;const list=$("cue-list");const selected=new Set(selectedCueIds());list.replaceChildren();$("cue-count").textContent=state.project.cues.length;
  const filter=$("cue-filter").value;const rows=state.project.cues.filter(c=>cueMatchesFilter(c,filter,state.project.edit));
  if(!rows.length)list.append(element("div","empty",state.project.cues.length?"Không có câu trong bộ lọc này.":"Nhập SRT hoặc nhận dạng video để bắt đầu."));
  for(const cue of rows){const card=element("div","cue-card");card.id="cue-"+cue.id;const head=element("div","cue-head");const box=element("input","cue-select");box.type="checkbox";box.dataset.id=cue.id;box.checked=selected.has(cue.id);box.setAttribute("aria-label","Chọn câu "+cue.id);head.append(box,element("strong","","#"+cue.id));
    for(const [index,key] of ["start_ms","end_ms"].entries()){if(index)head.append(element("span","","→"));const input=element("input");input.type="number";input.min=0;input.step=.001;input.value=(cue[key]/1000).toFixed(3);input.title=(index?"Kết thúc":"Bắt đầu")+" (giây)";input.setAttribute("aria-label",input.title+" câu "+cue.id);input.onchange=()=>{if(!Number.isFinite(Number(input.value)))return;cue[key]=Math.round(Number(input.value)*1000);cue.status="pending";dirty();renderTimeline();};head.append(input);}
    head.append(element("span","badge "+cue.status,statusNames[cue.status]||"Chưa tạo"));card.append(head);
    const original=element("details");original.append(element("summary","","Nguyên văn"),element("div","",cue.source_text));card.append(original);
    const text=element("textarea");text.value=cue.text;text.rows=1;text.setAttribute("aria-label","Lời đọc câu "+cue.id);text.oninput=()=>{cue.text=text.value;cue.status="pending";dirty();compactCueText(text);updateCueSpeed(card,cue);};card.append(text);
    card.append(element("small","","Lời đọc · "+(ttsCatalog?.languages[(cue.tts||state.project.tts)?.language||'vi']||'Tiếng Việt')));
    for(const checkpoint of Object.values(cue.translation_state||{})){if(checkpoint.status==="error")card.append(element("div","cue-note",`Dịch ${checkpoint.target}: ${checkpoint.error}`));}
    if(cue.translation_language&&cue.translation_language!==state.project.edit?.target_language&&state.project.edit?.target_language!=="vi")card.append(element("div","cue-note",`Bản dịch cũ là ${cue.translation_language}; cần dịch lại theo ngôn ngữ đích mới trước khi xuất.`));
    if(state.project.edit?.target_language!=="vi"||cue.translation){const translated=element("textarea");translated.rows=2;translated.value=cue.translation||"";translated.placeholder="Bản dịch phụ đề ngoại ngữ — không dùng để đọc";translated.setAttribute("aria-label","Bản dịch câu "+cue.id);translated.oninput=()=>{cue.translation=translated.value;dirty();};card.append(translated);}
    const controls=element("div","cue-actions");const voice=element("select");voiceOptions(voice,cue.voice||"",true);voice.setAttribute("aria-label","Giọng câu "+cue.id);voice.onchange=()=>{cue.voice=voice.value;cue.status="pending";dirty();};const rate=element("input");rate.type="number";rate.min=.5;rate.max=2;rate.step=.05;rate.value=cue.rate||1;rate.title="Tốc độ đọc cue";rate.setAttribute("aria-label","Tốc độ câu "+cue.id);rate.onchange=()=>{cue.rate=Number(rate.value);cue.status="pending";dirty();};controls.append(voice,rate,element("span","muted","×"));
    controls.append(ttsCueButton(cue));if((cue.tts||state.project.tts)?.provider&&((cue.tts||state.project.tts).provider!=='vieneu'||(cue.tts||state.project.tts).voice)){voice.disabled=true;voice.title='Giọng được chọn trong Giọng / diễn xuất';}
    controls.append(makeButton("Tua",()=>seek(cue)),makeButton("Dịch lại",()=>translate([cue.id])),makeButton("Rút gọn",()=>translate([cue.id],true)),makeButton("Tạo lại",async()=>{await saveProject();await startTask("dub",{project_id:state.project.id,selected:[cue.id],force:true});}));
    if(cue.audio)controls.append(makeButton("▶ Nghe tốc độ xuất",()=>showAudio([{url:cue.audio_url||`/files/projects/${state.project.id}/cues/${cue.audio}`,name:`cue-${cue.id}.wav`,type:"wav"}],"Câu "+cue.id),'quiet cue-listen'));
    controls.append(makeButton("×",()=>{if(confirm("Xóa câu này khỏi dự án? Chưa lưu cho đến khi bấm Lưu.")){state.project.cues=state.project.cues.filter(c=>c.id!==cue.id);dirty();renderCues();renderTimeline();}}));card.append(controls);
    if(cue.error)card.append(element("div","cue-note",cue.error));list.append(card);updateCueSpeed(card,cue);
    card.addEventListener('change',()=>{updateCueSpeed(card,cue);scheduleCueEstimate(card,cue);});card.addEventListener('input',()=>{updateCueSpeed(card,cue);scheduleCueEstimate(card,cue);});
    if(!cueEstimate(cue))scheduleCueEstimate(card,cue);
    requestAnimationFrame(()=>card.querySelectorAll('textarea').forEach(compactCueText));
  }
}
function renderIssues() {const target=$("cue-issues");target.replaceChildren();const issues=state.project?.issues||[];if(!issues.length)target.append(element("p","","Không có lỗi timeline được phát hiện."));for(const issue of issues.slice(0,30))target.append(element("p","",`${issue.cue?"Câu "+issue.cue:"Khối "+issue.block}: ${issue.message}`));if(issues.length>30)target.append(element("p","",`… và ${issues.length-30} mục khác.`));}
function seek(cue) {$("video-preview").currentTime=cue.start_ms/1000;if(dubPreviewActive)$("player").currentTime=cue.start_ms/1000;document.querySelectorAll(".cue-card").forEach(c=>c.classList.remove("selected"));$("cue-"+cue.id)?.classList.add("selected");$("cue-"+cue.id)?.scrollIntoView({behavior:"smooth",block:"nearest"});}
function renderTimeline() {const target=$("timeline");target.replaceChildren();const cues=state.project?.cues||[];const zoom=Number($("timeline-zoom").value);const end=timelineDuration()/1000;target.style.width=Math.max(600,end*zoom)+"px";for(let t=0;t<=end;t+=10){const tick=element("span","timeline-time",`${Math.floor(t/60)}:${String(t%60).padStart(2,"0")}`);tick.style.left=t*zoom+"px";target.append(tick);}for(const cue of cues){const box=element("button","timeline-cue "+cue.status,`#${cue.id} ${cue.text}`);box.style.left=cue.start_ms/1000*zoom+"px";box.style.width=Math.max(8,(cue.end_ms-cue.start_ms)/1000*zoom)+"px";box.title=`${(cue.start_ms/1000).toFixed(3)} → ${(cue.end_ms/1000).toFixed(3)} · ${cue.text}`;box.onclick=()=>seek(cue);target.append(box);}renderLayerTracks(target,zoom);}
async function translate(selected=null,shorten=false) {if(shorten&&state.project.edit.translation_provider!=="api")throw Error("Google chỉ dịch, không rút gọn. Hãy sửa lời đọc thủ công hoặc chọn API trong Bộ dịch.");if(!$("allow-translation").checked)throw Error("Cần cho phép gửi văn bản phụ đề tới dịch vụ dịch qua Internet.");await saveProject();await startTask("translate",{project_id:state.project.id,selected,force:selected!==null,shorten,allow_external:true});}
function bindDrop(id,input,handler){on(input,"change",e=>handler(e.target.files[0]));const drop=$(id);drop.addEventListener("dragover",e=>{e.preventDefault();drop.classList.add("drag");});drop.addEventListener("dragleave",()=>drop.classList.remove("drag"));drop.addEventListener("drop",e=>{e.preventDefault();drop.classList.remove("drag");Promise.resolve(handler(e.dataTransfer.files[0])).catch(err=>toast(err.message,true));});}
async function cloneFile(file){state.cloneAsset=await upload(file,"clone-source");$("clone-audio").src=state.cloneAsset.url;$("clone-audio").classList.remove("hidden");}
let recorder=null,recordStream=null,recordTimer=null;
let dubPreviewActive=false;
document.querySelectorAll("[data-tab]").forEach(b=>b.onclick=()=>changeTab(b.dataset.tab));
document.querySelectorAll(".dialog-close").forEach(b=>b.onclick=()=>b.closest("dialog").close());
document.querySelectorAll("[data-tag]").forEach(b=>b.onclick=()=>{const t=$("tts-text"),start=t.selectionStart,end=t.selectionEnd;t.setRangeText(b.dataset.tag,start,end,"end");t.focus();textCount();});
document.querySelectorAll("[data-sample]").forEach(b=>b.onclick=()=>{if($("tts-text").value&&!confirm("Thay nội dung hiện tại bằng mẫu?"))return;$("tts-text").value=samples[b.dataset.sample];textCount();});
document.querySelectorAll("[data-filter]").forEach(b=>b.onclick=()=>{state.voiceFilter=b.dataset.filter;document.querySelectorAll("[data-filter]").forEach(x=>x.classList.toggle("active",x===b));renderVoices();});
on("tts-text","input",textCount);on("voice-search","input",renderVoices);
on("paste-text","click",async()=>{try{$("tts-text").value=await navigator.clipboard.readText();textCount();}catch{toast("Đặt con trỏ vào ô văn bản và nhấn Ctrl+V.");}});
on("copy-text","click",async()=>{await navigator.clipboard.writeText($("tts-text").value);toast("Đã chép văn bản.");});
on("clear-text","click",()=>{if(confirm("Xóa nội dung đang soạn?")){$("tts-text").value="";textCount();}});
on("tts-rate","input",()=>{$("tts-rate-label").textContent=Number($("tts-rate").value).toFixed(2)+"×";estimateDuration();});
on("reload-voices","click",()=>{const provider=ttsMain?.value().provider||ttsSaved().provider;if(provider==='vieneu')return startTask('voices');if(provider==='elevenlabs')return startTask('tts_voices',{provider});return refreshTTSProviders().then(()=>toast('Danh sách giọng được tạo khi cài runtime trong Thư viện tùy chọn.'));});
on("tts-generate","click",()=>{const payload=ttsGeneratePayload();return startTask('tts',payload,{play:true,title:'TTS · '+payload.tts.provider});});
bindDrop("clone-drop","clone-file",cloneFile);
on("clone-save","click",()=>{if(!state.cloneAsset)throw Error("Chọn mẫu audio trước.");if(!$("clone-consent").checked)throw Error("Xác nhận bạn có quyền sử dụng mẫu giọng.");return startTask("clone",{asset_id:state.cloneAsset.id,name:$("clone-name").value,denoise:$("clone-denoise").checked,consent:true});});
on("clone-test","click",()=>startTask("tts",{text:$("clone-text").value,voice:$("clone-voice").value},{play:true,title:"Nghe thử · "+$("clone-voice").value}));
on("record","click",async()=>{if(recorder&&recorder.state==="recording"){recorder.stop();return;}if(!navigator.mediaDevices?.getUserMedia)throw Error("Không có micro trên giao diện này. Dùng file thu sẵn hoặc mở bản trình duyệt.");recordStream=await navigator.mediaDevices.getUserMedia({audio:true});try{recorder=new MediaRecorder(recordStream);const chunks=[];recorder.ondataavailable=e=>{if(e.data.size)chunks.push(e.data);};recorder.onstop=async()=>{clearTimeout(recordTimer);recordStream.getTracks().forEach(t=>t.stop());$("record").textContent="● Thu từ micro";try{await cloneFile(new File(chunks,"micro.webm",{type:recorder.mimeType}));}catch(err){toast(err.message,true);}};recorder.start();$("record").textContent="■ Dừng thu (tối đa 8s)";recordTimer=setTimeout(()=>{if(recorder.state==="recording")recorder.stop();},8000);}catch(err){recordStream.getTracks().forEach(t=>t.stop());throw err;}});
on("podcast-text","input",()=>{localStorage.setItem("rv-podcast",$("podcast-text").value);clearTimeout(renderSpeakers.timer);renderSpeakers.timer=setTimeout(renderSpeakers,500);});
on("podcast-sample","click",()=>{if($("podcast-text").value&&!confirm("Thay kịch bản bằng mẫu?"))return;$("podcast-text").value=podcastSample;renderSpeakers();});on("parse-speakers","click",renderSpeakers);
on("podcast-pause","input",()=>$("pause-label").textContent=Number($("podcast-pause").value).toFixed(2)+"s");on("podcast-rate","input",()=>$("podcast-rate-label").textContent=Number($("podcast-rate").value).toFixed(2)+"×");
on("podcast-generate","click",()=>{renderSpeakers();return startTask('podcast',podcastGeneratePayload(),{play:true,title:'Hội thoại / Podcast'});});
bindDrop("document-drop","document-file",async file=>{const asset=await upload(file,"document-source");await startTask("document",{asset_id:asset.id});});
on("document-clean","click",()=>{$("document-text").value=$("document-text").value.replace(/[\t ]+/g," ").replace(/\n{3,}/g,"\n\n").trim();});
on("document-to-tts","click",()=>{const text=$("document-text").value.trim();if(!text)throw Error("Chưa có nội dung văn bản.");if(text.length>100000)throw Error("Tài liệu trên 100.000 ký tự. Hãy chọn/cắt một phần để đọc mỗi lần.");if($("tts-text").value&&!confirm("Thay nội dung ở TTS bằng văn bản tài liệu?"))return;$("tts-text").value=text;textCount();changeTab("tts");});
on("project-new","click",()=>openProjectDialog());
on("project-back","click",async()=>{await saveProject();$("video-preview").pause();dubPreviewActive=false;$("project-list-view").classList.remove("hidden");$("project-editor").classList.add("hidden");await poll();});
on("project-name","input",dirty);on("dub-voice","change",()=>{state.project.voice=$("dub-voice").value;state.project.cues.forEach(c=>c.status="pending");dirty();});
on("project-save","click",async()=>{await saveProject();renderCues();toast("Đã lưu thay đổi.");});
on("video-file","change",async e=>{await saveProject();const uploaded=await upload(e.target.files[0],"video-name");state.project.video=uploaded.id;dirty();await saveProject();await loadProject(state.project.id);});
on("video-remove","click",async()=>{state.project.video="";dirty();await saveProject();await loadProject(state.project.id);});
on("srt-file","change",async e=>{if(state.project.cues.length&&!confirm("Nhập SRT mới sẽ thay danh sách câu. Bản trước được lưu snapshot. Tiếp tục?"))return;await saveProject();const asset=await upload(e.target.files[0]);await startTask("import_srt",{project_id:state.project.id,asset_id:asset.id});});
on("asr-start","click",async()=>{if(!state.project.video)throw Error("Chọn video trước.");const translateAfter=$("asr-translate").checked;if(translateAfter&&!$("allow-translation").checked)throw Error("Bật cho phép gửi văn bản tới dịch vụ dịch ở mục 2 trước.");if(state.project.cues.length&&!confirm("Nhận dạng sẽ thay danh sách câu hiện tại; bản cũ được giữ snapshot. Tiếp tục?"))return;await saveProject();await startTask("asr",{project_id:state.project.id,language:$("asr-language").value,allow_download:$("allow-download").checked,translate_after:translateAfter,allow_external:$("allow-translation").checked});});
on("translate-all","click",()=>translate());
on("validate-cues","click",async()=>{await saveProject();await loadProject(state.project.id,false);toast(state.project.issues.length?`Có ${state.project.issues.length} mục cần xem ở khung Kiểm tra.`:"SRT không có lỗi timeline được phát hiện.");});
on("dub-generate","click",async()=>{await saveProject();await startTask("dub",{project_id:state.project.id});});
on("cue-regenerate","click",async()=>{const selected=selectedCueIds();if(!selected.length)throw Error("Tích chọn các câu cần tạo lại.");await saveProject();await startTask("dub",{project_id:state.project.id,selected,force:true});});
on("cue-add","click",()=>{const cues=state.project.cues;const start=Math.max(0,...cues.map(c=>c.end_ms));cues.push({id:Math.max(0,...cues.map(c=>c.id))+1,start_ms:start,end_ms:start+2000,text:"",source_text:"",voice:"",rate:1,status:"pending"});dirty();renderCues();renderTimeline();$("cue-list").scrollTop=$("cue-list").scrollHeight;});
on("cue-filter","change",renderCues);on("timeline-zoom","input",renderTimeline);
$("cue-filter").title="Tốc độ >1,3×: dùng tốc độ thực tế nếu audio còn hợp lệ, nếu chưa tạo thì dùng ước tính đã tính luật đọc. Chưa dịch: chưa có bản dịch đúng ngôn ngữ hoặc lời còn giống nguyên văn chưa xác nhận.";
on("allow-translation","change",()=>{if(state.project){state.project.translation_consent=$("allow-translation").checked;dirty();}});
on("export-open","click",async()=>{await saveProject();$('dub-export-quality').value='canvas';const g=projectGeometry();$('dub-export-size').textContent=`Đầu ra hiện tại ${g.w}×${g.h}. Chất lượng chỉ áp dụng khi xuất video.`;$("export-dialog").showModal();});
on("export-start","click",async()=>{await saveProject();await startTask("export",{project_id:state.project.id,mode:$("export-mode").value},{play:false});$("export-dialog").close();});
on("dub-preview","click",()=>{const files=state.project.exports||[];if(!files.some(f=>f.type==="wav"||f.type==="mp3"))throw Error("Xuất audio trước để xem với bản lồng tiếng.");if(!state.project.video)throw Error("Chưa có video.");showAudio(files,"Xem trước lồng tiếng",false);const video=$("video-preview");video.muted=true;$("player").currentTime=video.currentTime;dubPreviewActive=true;video.play();$("player").play();});
on("video-preview","timeupdate",()=>{const video=$("video-preview");const ms=video.currentTime*1000;const cue=state.project?.cues.find(c=>c.start_ms<=ms&&c.end_ms>ms);$("caption-preview").textContent=cue?.text||"";if(dubPreviewActive&&Math.abs($("player").currentTime-video.currentTime)>.25)$("player").currentTime=video.currentTime;});
on("video-preview","pause",()=>{if(dubPreviewActive)$("player").pause();});on("video-preview","play",()=>{if(dubPreviewActive)$("player").play().catch(()=>{});});
on("stop-play","click",()=>{$("player").pause();$("player").currentTime=0;$("video-preview").pause();dubPreviewActive=false;$("video-preview").muted=false;});
on("history-open","click",()=>{renderHistory();$("history-dialog").showModal();});
on("theme","click",()=>{const theme=document.documentElement.dataset.theme==="dark"?"light":"dark";document.documentElement.dataset.theme=theme;localStorage.setItem("rv-theme",theme);});
on("settings-open","click",()=>{const s=state.settings;$("setting-precision").value=s.precision;$("setting-whisper").value=s.whisper_model;$("setting-home").value=s.vieneu_home;$("setting-url").value=s.translation_url;$("setting-model").value=s.translation_model;$("setting-key").value="";$("setting-key").placeholder=s.has_translation_key?"Đã có khóa; để trống để giữ nguyên":"Chưa có khóa";$("setting-clear-key").checked=false;$("settings-dialog").showModal();});
on("settings-form","submit",async e=>{e.preventDefault();const value={precision:$("setting-precision").value,whisper_model:$("setting-whisper").value,vieneu_home:$("setting-home").value.trim(),translation_url:$("setting-url").value.trim(),translation_model:$("setting-model").value.trim()};if($("setting-key").value||$("setting-clear-key").checked)value.translation_key=$("setting-clear-key").checked?"":$("setting-key").value;state.settings=await api("settings",value);$("setting-key").value="";$("setting-clear-key").checked=false;$("settings-save-info").textContent="Đã lưu cài đặt";toast("Đã lưu cài đặt");await poll();});
window.addEventListener("beforeunload",e=>{if(state.dirty){e.preventDefault();e.returnValue="";}if(recordStream)recordStream.getTracks().forEach(t=>t.stop());});
async function init(){setupEditorUI();document.documentElement.dataset.theme=localStorage.getItem("rv-theme")||"light";state.selectedVoice=localStorage.getItem("rv-voice")||"";try{state.speakers=JSON.parse(localStorage.getItem("rv-speakers")||"{}");}catch{}$("tts-text").value=localStorage.getItem("rv-tts")??$("tts-text").value;$("podcast-text").value=localStorage.getItem("rv-podcast")||podcastSample;$("document-text").value=localStorage.getItem("rv-document")||"";textCount();const tab=localStorage.getItem("rv-tab");changeTab(["tts","clone","dub","edit","podcast","documents","downloads","removal"].includes(tab)?tab:"tts");await poll(true);setInterval(()=>poll().catch(e=>{console.warn(e.message);}),2500);if(ttsSaved().provider==='vieneu'&&!state.voices.length&&!state.jobs.some(j=>["queued","running"].includes(j.status))&&!new URLSearchParams(location.search).has("smoke")){const providers=await api("tts-providers");if(providers.catalog.some(p=>p.id==='vieneu'&&p.installed))await startTask("voices");}}
init().then(()=>{setupCleanupUI();console.info("REUP_UI_READY="+document.querySelector('meta[name="reup-version"]').content+"; pinned="+Boolean($("dub-settings-scroll"))+"; mask="+Boolean($("mask-draw")));}).catch(err=>toast("Không kết nối được ứng dụng: "+err.message,true));
