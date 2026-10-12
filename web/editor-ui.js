"use strict";
const ui={tab:"tts",results:{},defaults:{},presets:[],characters:[],selection:[0,0],folderPicker:false,previewRequests:new Set(),maskDraw:false,maskIndex:-1};
const tabTitles={tts:"Văn bản → Giọng nói",clone:"Voice Clone",dub:"Lồng tiếng video",edit:"Biên tập video",podcast:"Hội thoại / Podcast",documents:"Đọc tài liệu"};
tabTitles.downloads='Tải video / audio';
function updateBuildStatus(serverBuild){
  const loadedBuild=document.querySelector('meta[name="reup-web-build"]').content;
  $("app-version").title=`Giao diện: ${loadedBuild} · Máy chủ: ${serverBuild||"cũ"}`;
  $("ui-update-notice").classList.toggle("hidden",!serverBuild||serverBuild===loadedBuild);
}
function switchPlayerTab(name){
  if(ui.tab!==name){$("player").pause();$("video-preview").pause();dubPreviewActive=false;$("video-preview").muted=false;}
  ui.tab=name;const result=ui.results[name];
  if(result){showAudio(result.files,result.title,false,name);}else{$("player").removeAttribute("src");$("player").load();$("player-title").textContent=tabTitles[name];$("player-detail").textContent="Kết quả riêng của mục này sẽ xuất hiện ở đây.";$("player-downloads").replaceChildren();}
  document.body.dataset.tab=name;
}
function estimateDuration(){
  const text=$("tts-text").value;const pause=[...text.matchAll(/\[nghỉ\s+(\d+(?:\.\d+)?)s\]|\[(\d+(?:\.\d+)?)\]/gi)].reduce((v,m)=>v+Number(m[1]||m[2]),0);
  const words=text.replace(/\[[^\]]*\]/g,"").trim().split(/\s+/).filter(Boolean).length;
  const seconds=words/4.5/Number($("tts-rate").value);
  $("audio-estimate").textContent=words||pause?`Ước tính audio: ${Math.max(1,Math.round(seconds*.8+pause))}–${Math.max(1,Math.ceil(seconds*1.25+pause))} giây`:"Ước tính audio: 0 giây";
  if(typeof scheduleReadingEstimate==="function")scheduleReadingEstimate();
}
function assignCharacter(name){
  const area=$("podcast-text"),[start,end]=ui.selection;
  if(start===end){toast("Bôi đen phần lời thoại trong kịch bản, rồi bấm tên nhân vật.");return;}
  const selected=area.value.slice(start,end).replace(/^\s*\[[^\]\n]+\]\s*:\s*/gm,"").trim();
  const before=area.value.slice(0,start),after=area.value.slice(end);
  const replacement=(before&&!before.endsWith("\n")?"\n":"")+`[${name}]: ${selected}`+(after&&!after.startsWith("\n")?"\n":"");
  area.setRangeText(replacement,start,end,"select");ui.selection=[area.selectionStart,area.selectionEnd];
  localStorage.setItem("rv-podcast",area.value);renderSpeakers();area.focus();
}
function configField(parent,key,label,type="number",options=null,min=0,max=100,step=1){
  const field=element("label","field",label);let input;
  if(options){input=element("select");for(const [value,text] of Object.entries(options)){const opt=element("option","",text);opt.value=value;input.append(opt);}}
  else{input=element("input");input.type=type;if(type==="number"){input.min=min;input.max=max;input.step=step;}}
  input.id="edit-"+key;input.dataset.edit=key;input.oninput=()=>{if(!state.project)return;state.project.edit[key]=type==="checkbox"?input.checked:type==="number"?Number(input.value):input.value;dirty();updateStage();renderTimeline();};
  field.append(input);parent.append(field);return input;
}
function detailPanel(title){const panel=element("details","edit-panel card compact");panel.append(element("summary","",title));const grid=element("div","edit-fields");panel.append(grid);$("edit-panels").append(panel);return grid;}
function setupEditorUI(){
  setupDownloads();
  setupRemoval();
  setupSequenceUI();
  setupReadingUI();
  const chosenVoice=element("div","selected-voice-name","Đang chọn: Chưa chọn giọng");chosenVoice.id="selected-voice-name";chosenVoice.setAttribute("aria-live","polite");$("voice-list").before(chosenVoice);
  taskNames.preview="Tạo bản xem tương thích";taskNames.separate="Tách giọng AI";
  try{ui.characters=JSON.parse(localStorage.getItem("rv-characters")||"[]");}catch{}
  const estimate=element("span","","Ước tính audio: 0 giây");estimate.id="audio-estimate";document.querySelector(".editor-bottom").lastElementChild.replaceWith(estimate);
  const dock=element("div","context-dock");dock.id="context-dock";
  const actions=element("div","context-actions");dock.append(actions,$("job-panel"),document.querySelector(".playerbar"));document.body.append(dock);
  new ResizeObserver(()=>document.documentElement.style.setProperty("--dock-height",dock.clientHeight+"px")).observe(dock);
  for(const [tab,ids] of Object.entries({tts:["tts-generate"],clone:["clone-save","clone-test"],podcast:["podcast-generate"],documents:["document-to-tts"],dub:[]})){
    const bar=element("div","tab-actions");bar.dataset.context=tab;for(const id of ids){$(id).classList.remove("wide");bar.append($(id));}actions.append(bar);
  }
  const add=makeButton("＋ Thêm nhân vật",()=>{const name=prompt("Tên nhân vật mới (không dùng dấu [ ] hoặc dấu hai chấm)");if(name===null)return;const clean=name.trim();if(!clean||clean.length>60||/[\[\]:\r\n]/.test(clean))throw Error("Tên nhân vật cần 1–60 ký tự, không có [ ] : hoặc xuống dòng.");ui.characters=[...new Set([...ui.characters,clean])];localStorage.setItem("rv-characters",JSON.stringify(ui.characters));renderSpeakers();});
  $("parse-speakers").before(add);$("speaker-list").before(element("p","hint","Bôi đen lời thoại bên trái → bấm tên nhân vật để gán. Có thể thêm nhiều nhân vật."));
  for(const evt of ["select","keyup","mouseup"])on("podcast-text",evt,()=>{ui.selection=[$("podcast-text").selectionStart,$("podcast-text").selectionEnd];});
  const side=document.querySelector(".dub-sidebar");const panels=element("div");panels.id="edit-panels";side.append(panels);
  const chained=element("label","check"),check=element("input");check.type="checkbox";check.id="asr-translate";chained.append(check,document.createTextNode(" Dịch ngay sau Whisper theo cấu hình mục 2"));$("asr-start").before(chained);
  $("asr-start").nextElementSibling.textContent="Whisper lưu timeline trước khi dịch. Nếu dịch lỗi, không cần nhận dạng lại. Model chọn trong Cài đặt.";
  const consent=$("allow-translation");consent.parentElement.replaceChildren(consent,document.createTextNode(" Cho phép gửi văn bản phụ đề tới dịch vụ dịch qua Internet"));
  $("translate-all").nextElementSibling.textContent="Google không cần API key; vẫn cần mạng và có thể giới hạn truy cập. Lưu sau từng câu; bấm tiếp tục bỏ qua câu đã dịch. API ở ⚙ là tùy chọn. SRT đã Việt: bỏ qua Dịch.";
  $("project-list-view").querySelector(".notice").textContent="Video và tổng hợp giọng xử lý trên máy. Google / API chỉ nhận văn bản khi bạn cho phép. Chỉ sử dụng video và giọng bạn có quyền khai thác.";
  const translation=configField($("translate-all").parentElement,"target_language","Ngôn ngữ đích của phụ đề","text",{vi:"Tiếng Việt",en:"English",zh:"中文",ja:"日本語",ko:"한국어",fr:"Français",de:"Deutsch",th:"ไทย"});
  $("translate-all").before(translation.parentElement);$("translate-all").textContent="Dịch / Tiếp tục phụ đề";
  const provider=configField($("translate-all").parentElement,"translation_provider","Bộ dịch","text",{google_v1:"Google V1 · giống Subtitle Edit · không key",google:"Google Web · giống subviet · không key",api:"Gemini / API · dùng key ở ⚙"});
  $("translate-all").before(provider.parentElement);
  const source=configField($("translate-all").parentElement,"source_language","Ngôn ngữ nguyên văn để dịch","text",{auto:"Tự nhận diện",zh:"Tiếng Trung",en:"English",vi:"Tiếng Việt",ja:"日本語",ko:"한국어",fr:"Français",de:"Deutsch",th:"ไทย"});
  $("translate-all").before(source.parentElement);
  translation.addEventListener("change",()=>renderCues());
  $("translate-all").parentElement.append(element("p","hint","Audio chỉ đọc ô Lời đọc tiếng Việt bằng VieNeu. Bản dịch ngoại ngữ được lưu riêng để xuất phụ đề."));
  $("translate-all").after(makeButton("Dịch riêng lời đọc sang tiếng Việt",async()=>{if(!$("allow-translation").checked)throw Error("Cho phép gửi văn bản tới dịch vụ dịch trước.");await saveProject();await startTask("translate",{project_id:state.project.id,allow_external:true,for_speech:true});},"wide quiet"));
  $("cue-regenerate").before(makeButton("Dịch lại câu đã chọn",()=>{const ids=selectedCueIds();if(!ids.length)throw Error("Chọn ít nhất một câu.");return translate(ids);}));
  const canvasControls=element("div","edit-fields canvas-controls");document.querySelector(".video-wrap").before(canvasControls);
  configField(canvasControls,"output_ratio","Tỷ lệ khung đầu ra","text",{source:"Theo video gốc", "9:16":"9:16 · dọc", "16:9":"16:9 · ngang", "1:1":"1:1 · vuông", "4:5":"4:5", "4:3":"4:3",custom:"Tự nhập kích thước"});
  configField(canvasControls,"video_fit","Đặt video vào khung","text",{contain:"Giữ đủ hình · có viền",cover:"Phủ kín · cắt phần thừa"});
  configField(canvasControls,"output_short_side","Cạnh ngắn đầu ra","number",{720:"720 px",1080:"1080 px",1440:"2K · 1440 px",2160:"4K · 2160 px"});
  configField(canvasControls,"canvas_color","Màu nền khung","color");
  configField(canvasControls,"output_width","Rộng (px chẵn)","number",null,64,3840,2);configField(canvasControls,"output_height","Cao (px chẵn)","number",null,64,3840,2);
  const dimensions=element("p","hint full");dimensions.id="canvas-dimensions";canvasControls.append(dimensions);
  let grid=detailPanel("Khung hình · zoom / xoay");
  configField(grid,"zoom","Zoom video","number",null,.25,3,.05);configField(grid,"rotation","Xoay (độ)","number",null,-180,180,1);
  configField(grid,"video_x","Vị trí ngang (%)");configField(grid,"video_y","Vị trí dọc (%)");
  grid=detailPanel("Phụ đề mới · vị trí & kiểu chữ");
  configField(grid,"subtitle_font","Phông chữ","text",{"Arial":"Arial","Segoe UI":"Segoe UI","Times New Roman":"Times New Roman","Be Vietnam Pro":"Be Vietnam Pro"});
  configField(grid,"subtitle_size","Cỡ chữ (px video)","number",null,10,160);
  configField(grid,"subtitle_style","Kiểu chạy","text",{outline:"Viền chữ",box:"Hộp nền",fade:"Hiện / mờ dần",karaoke:"Karaoke ước lượng theo cue"});
  configField(grid,"subtitle_color","Màu chữ","color");configField(grid,"subtitle_x","Vị trí ngang (%)");configField(grid,"subtitle_y","Vị trí dọc (%)");
  configField(grid,'subtitle_box_color','Màu nền hộp','color');configField(grid,'subtitle_box_opacity','Độ hiện nền (0–1)','number',null,0,1,.05);
  grid.append(element("p","hint full","Karaoke chia đều thời gian cho các từ, không phải căn từ tự động. Chọn Xuất video + phụ đề dính hình để áp dụng."));
  grid=detailPanel("Xử lý phụ đề gốc trên hình");
  configField(grid,"original_subtitles","Cách xử lý","text",{keep:"Giữ nguyên",cover:"Che bằng vùng đen",blur:"Làm mờ vùng chữ"});
  configField(grid,"mask_blur","Độ mờ (px video gốc)","number",null,1,40);
  grid.append(makeButton("＋ Vẽ thêm vùng mờ",()=>setMaskDraw(true)),element("p","hint full","Các thông số bên dưới chỉ dành cho vùng phụ đề gốc. Vùng vẽ tay độc lập: thêm tối đa 20 vùng bằng nút dưới video; chọn từng vùng để kéo, đổi cỡ hoặc xóa. Esc hủy thao tác."));
  for(const [key,label,max] of [["mask_x","Trái (%)",99],["mask_y","Trên (%)",99],["mask_w","Rộng (%)",100],["mask_h","Cao (%)",100]])configField(grid,key,label,"number",null,key.endsWith("w")||key.endsWith("h")?1:0,max,.01);
  grid.append(element("p","hint full","Chỉ xử lý chữ đã dính trong hình. Không khôi phục được nội dung bị chữ che; video gốc luôn giữ nguyên."));
  grid=detailPanel("Logo & tiêu đề · kéo để đặt vị trí");
  addAssetControl(grid,"logo","Chọn logo PNG / JPG", ".png,.jpg,.jpeg,.webp");
  configField(grid,"logo_size","Rộng logo (%)","number",null,2,70);configField(grid,"logo_x","Logo ngang (%)");configField(grid,"logo_y","Logo dọc (%)");
  configField(grid,"title","Tiêu đề","text");configField(grid,"title_size","Cỡ tiêu đề","number",null,10,160);configField(grid,"title_color","Màu tiêu đề","color");configField(grid,"title_x","Tiêu đề ngang (%)");configField(grid,"title_y","Tiêu đề dọc (%)");
  configField(grid,'title_box','Nền hộp tiêu đề','checkbox');configField(grid,'title_box_color','Màu nền tiêu đề','color');configField(grid,'title_box_opacity','Độ hiện nền (0–1)','number',null,0,1,.05);
  grid=detailPanel("Âm thanh · nhạc nền & tách giọng AI");
  configField(grid,"original_audio","Âm thanh gốc","text",{mute:"Tắt tiếng gốc",original:"Giữ cả giọng và nhạc",instrumental:"Chỉ nhạc đã tách AI",vocals:"Chỉ giọng đã tách AI"});
  configField(grid,"original_volume","Âm lượng gốc (0–2)","number",null,0,2,.05);configField(grid,"voice_volume","Lời Việt (0–2)","number",null,0,2,.05);
  addAssetControl(grid,"background","Thêm audio nền", ".wav,.mp3,.m4a,.flac,.ogg");configField(grid,"background_volume","Âm lượng nền (0–2)","number",null,0,2,.05);
  configField(grid,"ducking","Tự hạ nhạc khi có lời đọc","checkbox");configField(grid,"denoise","Lọc nhiễu lời Việt","checkbox");configField(grid,"normalize","Chuẩn hóa mục tiêu −14 LUFS","checkbox");
  grid.append(makeButton("✧ Tách giọng AI trên CPU",async()=>{await saveProject();if(!state.project.video)throw Error("Chọn video trước.");if(!confirm("Tách giọng / nhạc bằng Demucs trên CPU; lần đầu tải model qua Internet và có thể mất nhiều phút. Tiếp tục?"))return;await startTask("separate",{project_id:state.project.id});}),element("p","hint full","Demucs tạo vocals + no_vocals; có thể còn lẫn tiếng. Audio nền lặp tới hết video. Nghe bản xuất để đánh giá hiệu ứng audio."));
  grid=detailPanel("Cấu hình dùng lại & nơi lưu");
  const presets=element("select");presets.id="preset-list";grid.append(presets,makeButton("Áp dụng",()=>{const preset=ui.presets.find(p=>p.id===presets.value);if(!preset)return;if(!confirm("Áp dụng cấu hình lên dự án này? Không thay timeline/lời thoại."))return;state.project.edit={...preset.edit};dirty();loadEditControls();}));
  grid.append(makeButton("Lưu thành cấu hình mới",async()=>{const name=prompt("Tên cấu hình dùng lại","Cấu hình của tôi");if(!name)return;await api("presets",{name,edit:state.project.edit});await poll();loadEditControls();toast("Đã lưu cấu hình. Có thể chọn khi tạo dự án mới.");}));
  const location=element("p","hint full");location.id="project-location";grid.append(location);
  const wrap=document.querySelector(".video-wrap");$("video-preview").controls=false;
  const well=element("div","preview-well");wrap.before(well);well.append(wrap);
  const sourceLayer=element("div","source-layer");sourceLayer.id="video-source-layer";wrap.prepend(sourceLayer);sourceLayer.append($("video-preview"));
  for(const id of ["old-sub-mask","title-preview","logo-preview"]){const el=element(id==="logo-preview"?"img":"div");el.id=id;wrap.append(el);}
  sourceLayer.append($("old-sub-mask"));$("logo-preview").addEventListener("load",updateStage);
  const mask=$("old-sub-mask");mask.classList.add("source-mask");mask.dataset.maskIndex="-1";mask.setAttribute("aria-label","Vùng phụ đề gốc: kéo để di chuyển, kéo góc để đổi kích thước");
  for(const corner of ["nw","ne","sw","se"]){const handle=element("span","mask-handle "+corner);handle.dataset.corner=corner;mask.append(handle);}
  $("logo-preview").alt="Logo";$("caption-preview").classList.add("movable");$("title-preview").classList.add("movable");$("logo-preview").classList.add("movable");
  const transport=element("div","video-transport");transport.append(makeButton("▶ / Ⅱ",()=>{const v=$("video-preview");if(v.paused)v.play().catch(()=>toast("Video chưa phát được. Bấm Tạo bản xem WebM bên dưới.",true));else v.pause();}));
  const scrub=element("input");scrub.type="range";scrub.id="video-scrub";scrub.min=0;scrub.max=100;scrub.value=0;scrub.step=.05;scrub.setAttribute("aria-label","Tua video");scrub.oninput=()=>{$("video-preview").currentTime=Number(scrub.value);};transport.append(scrub);const clock=element("span","hint","0:00");clock.id="video-clock";transport.append(clock,makeButton("⛶",()=>{document.querySelector(".video-card").classList.toggle("expanded");updateStage();}));well.after(transport);
  transport.after(makeButton("↻ Tạo bản xem WebM nếu video không phát",async()=>{await saveProject();await startTask("preview",{project_id:state.project.id});},"quiet wide"));
  $("video-preview").addEventListener("loadedmetadata",updateStage);$("video-preview").addEventListener("error",()=>{if(state.project?.video)autoCompatiblePreview();});
  $("video-preview").addEventListener("timeupdate",()=>{const v=$("video-preview");scrub.max=Number.isFinite(v.duration)?v.duration:100;scrub.value=v.currentTime;clock.textContent=`${v.currentTime.toFixed(1)} / ${Number.isFinite(v.duration)?v.duration.toFixed(1):"…"}s`;const cue=state.project?.cues.find(c=>c.start_ms<=v.currentTime*1000&&c.end_ms>v.currentTime*1000);$("caption-preview").textContent=cue?(state.project.edit?.target_language!=="vi"?(cue.translation||cue.text):cue.text):"";});
  for(const [id,prefix] of [["caption-preview","subtitle"],["title-preview","title"],["logo-preview","logo"]])enableDrag(id,prefix);
  const videoCard=document.querySelector(".video-card"),settingsScroll=element("div","dub-settings-scroll");settingsScroll.id="dub-settings-scroll";settingsScroll.setAttribute("aria-label","Tùy chỉnh video, cuộn riêng");settingsScroll.tabIndex=0;
  const canvasCard=element("article","card compact");canvasCard.append(element("h3","","Khung đầu ra"),canvasControls);settingsScroll.append(canvasCard);
  const sourceSettings=element("details","card compact video-source-settings");sourceSettings.append(element("summary","","Video nguồn & bản xem"));
  for(const child of [...videoCard.children])if(child!==well&&child!==transport)sourceSettings.append(child);
  settingsScroll.append(sourceSettings);
  for(const child of [...side.children])if(child!==videoCard)settingsScroll.append(child);
  side.append(settingsScroll);
  setupVisualLayers();
  for(const card of [...settingsScroll.querySelectorAll("article.card")]){const heading=card.querySelector("h3");if(!heading)continue;const details=element("details",card.className),summary=element("summary","",heading.textContent);heading.remove();details.append(summary,...card.childNodes);card.replaceWith(details);}
  videoCard.prepend(element("div","preview-pinned-label","Xem trực tiếp · cố định khi cuộn thông số"));
  settingsScroll.prepend(element("div","settings-scroll-label","Thông số video · cuộn trong khung này ↓"));
  const direct=element("div","direct-tools");
  const draw=makeButton("▧ Vẽ vùng mờ",()=>setMaskDraw(!ui.maskDraw));draw.id="mask-draw";draw.setAttribute("aria-pressed","false");
  direct.append(draw,makeButton("Xóa vùng đang chọn",()=>{if(!state.project)return;const c=state.project.edit;if(ui.maskIndex<0){c.original_subtitles="keep";$("edit-original_subtitles").value="keep";}else{c.blur_regions.splice(ui.maskIndex,1);ui.maskIndex=Math.min(ui.maskIndex,c.blur_regions.length-1);}setMaskDraw(false);refreshMaskList();dirty();updateStage();renderTimeline();}));
  const selection=element("div","mask-selection"),selector=element("select");selector.id="mask-select";selector.setAttribute("aria-label","Vùng mờ đang chọn");selector.onchange=()=>{ui.maskIndex=Number(selector.value);refreshMaskList();updateStage();};
  const strength=element("input");strength.id="mask-strength";strength.type="number";strength.min=1;strength.max=40;strength.setAttribute("aria-label","Độ mờ vùng đang chọn");strength.onchange=()=>{applyMask({mask_blur:Math.max(1,Math.min(40,Math.round(Number(strength.value)||12)))});dirty();};
  selection.append(selector,element("span","hint","Độ mờ"),strength);direct.append(selection);
  const hint=element("span","hint","Kéo hình / tiêu đề để đặt vị trí");hint.id="stage-hint";direct.append(hint);videoCard.append(direct);
  enableMaskEditing(wrap);enableVideoDrag(wrap);new ResizeObserver(updateStage).observe(side);new ResizeObserver(updateStage).observe(well);window.addEventListener("resize",updateStage);
  $("export-volume").closest("label").classList.add("hidden");$("export-normalize").closest("label").classList.add("hidden");$("export-dialog").querySelector(".notice").textContent="Xuất dùng cấu hình hình ảnh/âm thanh trong dự án. Xem trước trên giao diện chỉ minh họa bố cục; phông chữ/hiệu ứng chính xác xem ở video xuất.";
  const qualityField=element('label','field','Chất lượng video đầu ra'),quality=element('select');quality.id='dub-export-quality';
  for(const [value,title] of [['canvas','Giữ canvas đã cấu hình'],['720','720p'],['1080','1080p'],['1440','2K · 1440p'],['2160','4K · 2160p']]){const option=element('option','',title);option.value=value;quality.append(option);}qualityField.append(quality);$('export-mode').closest('label').after(qualityField);
  const size=element('small','hint');size.id='dub-export-size';qualityField.after(size);
  quality.onchange=()=>{try{if(!state.project)return;const current=projectGeometry(),next=seqOutputSize(current.w,current.h,quality.value);if(quality.value!=='canvas'){Object.assign(state.project.edit,{output_ratio:'custom',output_width:next.width,output_height:next.height});dirty();loadEditControls();}size.textContent=`Đầu ra ${next.width}×${next.height}. Chọn chất lượng sẽ đổi canvas, giữ tỷ lệ. Nâng kích thước không thêm chi tiết.`;}catch(e){toast(e.message,true);quality.value='canvas';}};
  const dialog=element("dialog");dialog.id="project-create-dialog";dialog.innerHTML='<div class="card-heading"><h2>Tạo dự án lồng tiếng</h2><button id="create-close" class="icon">×</button></div><label class="field">Tên dự án<input id="create-name" maxlength="100" value="Lồng tiếng mới"></label><label class="field">Thư mục lưu (trống = data/projects)<input id="create-folder" placeholder="D:\\DuAnVideo"></label><button id="create-browse">Chọn thư mục…</button><label class="check"><input id="create-default" type="checkbox"> Dùng thư mục này cho dự án mới sau này</label><label class="field">Cấu hình dùng lại<select id="create-preset"></select></label><p class="hint">Tạo một thư mục con riêng; không ghi đè file có sẵn. Video, logo, nhạc, cue và bản xuất được lưu trong đó.</p><button id="create-submit" class="primary wide">Tạo dự án</button>';
  document.body.append(dialog);on("create-close","click",()=>dialog.close());on("create-browse","click",async()=>{const result=await api("folder",{});if(result.path)$("create-folder").value=result.path;});
  on("create-submit","click",async()=>{const parent=$("create-folder").value.trim();const edit=ui.presets.find(p=>p.id===$("create-preset").value)?.edit;const p=await api("projects",{name:$("create-name").value,parent,edit});if($("create-default").checked){try{await api("settings",{project_root:parent});}catch(error){toast("Đã tạo dự án; chưa lưu thư mục mặc định: "+error.message,true);}}dialog.close();await loadProject(p.id);await poll();});
  for(const p of $("settings-dialog").querySelectorAll("p")){if(p.textContent.includes("Reup Voice Studio 0.1.0"))p.textContent=p.textContent.replace("0.1.0",document.querySelector('meta[name="reup-version"]').content);}
}
function addAssetControl(grid,key,label,accept){
  const field=element("label","field full",label),input=element("input");input.type="file";input.accept=accept;input.id="asset-"+key;field.append(input);grid.append(field);
  input.onchange=()=>Promise.resolve().then(async()=>{const asset=await upload(input.files[0]);state.project.edit[key]=asset.id;state.project.edit_assets??={};state.project.edit_assets[key]=asset;dirty();updateStage();}).catch(e=>toast(e.message,true));
  grid.append(makeButton("Bỏ "+(key==="logo"?"logo":"audio nền"),()=>{state.project.edit[key]="";dirty();updateStage();}));
}
function loadEditControls(){
  if(!state.project)return;state.project.edit={...ui.defaults,...state.project.edit};
  setMaskDraw(false);
  state.project.edit.blur_regions=(state.project.edit.blur_regions||[]).map(r=>({...r}));ui.maskIndex=-1;refreshMaskList();
  for(const input of document.querySelectorAll("[data-edit]")){const value=state.project.edit[input.dataset.edit];if(input.type==="checkbox")input.checked=Boolean(value);else input.value=value??"";}
  $("project-location").textContent="Lưu tại: "+(state.project.folder||"data/projects");fillPresets($("preset-list"));updateStage();
}
function fillPresets(select){const old=select.value;select.replaceChildren();const opt=element("option","","Mặc định / không áp dụng");opt.value="";select.append(opt);for(const p of ui.presets){const o=element("option","",p.name);o.value=p.id;select.append(o);}select.value=old;}
function openProjectDialog(){$("create-folder").value=state.settings.project_root||"";$("create-browse").disabled=!ui.folderPicker;fillPresets($("create-preset"));$("project-create-dialog").showModal();}
async function autoCompatiblePreview(){
  const p=state.project;if(!p?.video||p.preview)return;const key=p.id+":"+p.video;
  if(ui.previewRequests.has(key)||state.jobs.some(j=>j.project_id===p.id&&["queued","running"].includes(j.status))){toast("Codec chưa phát được. Bấm Tạo bản xem WebM khi tác vụ hiện tại xong.");return;}
  ui.previewRequests.add(key);
  try{await saveProject();await startTask("preview",{project_id:p.id});toast("Đang tạo bản xem WebM cho codec chưa được hỗ trợ; video gốc giữ nguyên.");}catch(error){toast("Chưa tạo được bản xem: "+error.message,true);}
}
function canvasGeometry(width,height,c){
  const even=n=>Math.max(2,Math.floor(n/2+.5)*2);let w=even(width),h=even(height);
  if(c.output_ratio==="custom"){w=Number(c.output_width)||1080;h=Number(c.output_height)||1920;}
  else if(c.output_ratio&&c.output_ratio!=="source"){const [a,b]=c.output_ratio.split(":").map(Number),unit=Number(c.output_short_side||720)/Math.min(a,b);w=even(a*unit);h=even(b*unit);}
  const fit=(c.video_fit==="cover"?Math.max:Math.min)(w/width,h/height),sw=even(width*fit*Number(c.zoom||1)),sh=even(height*fit*Number(c.zoom||1)),angle=Number(c.rotation||0)*Math.PI/180;
  const rw=sw*Math.abs(Math.cos(angle))+sh*Math.abs(Math.sin(angle)),rh=sw*Math.abs(Math.sin(angle))+sh*Math.abs(Math.cos(angle));
  return {w,h,sw,sh,rw,rh,left:(w-sw)/2+(w-rw)*(Number(c.video_x??50)/100-.5),top:(h-sh)/2+(h-rh)*(Number(c.video_y??50)/100-.5)};
}
function projectGeometry(){const v=$("video-preview");return canvasGeometry(state.project.video_info?.width||v.videoWidth||1280,state.project.video_info?.height||v.videoHeight||720,state.project.edit||{});}
function updateStage(){
  updateVisualLayers();
  if(!state.project)return;const c=state.project.edit||{},wrap=document.querySelector(".video-wrap"),well=wrap.parentElement,g=projectGeometry();
  const limit=document.querySelector(".video-card").classList.contains("expanded")?Math.max(180,window.innerHeight-330):Math.max(50,Math.min(300,document.querySelector(".dub-sidebar").clientHeight*.44-40));
  if(!well.clientWidth)return;
  const scale=Math.min(well.clientWidth/g.w,limit/g.h);
  Object.assign(wrap.style,{aspectRatio:`${g.w}/${g.h}`,width:g.w*scale+"px",height:g.h*scale+"px",background:c.canvas_color||"#000000"});
  Object.assign($("video-source-layer").style,{width:g.sw*scale+"px",height:g.sh*scale+"px",left:g.left*scale+"px",top:g.top*scale+"px",transform:`rotate(${c.rotation||0}deg)`});
  $("canvas-dimensions").textContent=`Đầu ra ${g.w} × ${g.h} px · kéo hình để đổi vị trí; zoom / xoay ở mục Khung hình.`;
  for(const key of ["output_width","output_height"])$("edit-"+key).parentElement.classList.toggle("hidden",c.output_ratio!=="custom");
  $("edit-output_short_side").parentElement.classList.toggle("hidden",["source","custom"].includes(c.output_ratio));
  for(const [id,key] of [["caption-preview","subtitle"],["title-preview","title"]]){const el=$(id);el.style.left=c[key+"_x"]+"%";el.style.top=c[key+"_y"]+"%";el.style.fontSize=Number(c[key+"_size"])*scale+"px";el.style.color=c[key+"_color"];el.style.fontFamily=c.subtitle_font;const box=key==='subtitle'?c.subtitle_style==='box':c.title_box;el.style.background=box?(c[key+'_box_color']||'#000000')+Math.round((c[key+'_box_opacity']??.6)*255).toString(16).padStart(2,'0'):'transparent';}
  $("title-preview").textContent=c.title||"";const logo=$("logo-preview");logo.classList.toggle("hidden",!c.logo);if(c.logo&&state.project.edit_assets?.logo&&logo.getAttribute("src")!==state.project.edit_assets.logo.url)logo.src=state.project.edit_assets.logo.url;logo.style.width=c.logo_size+"%";logo.style.left=`${(100-c.logo_size)*c.logo_x/100}%`;logo.style.top=`${Math.max(0,wrap.clientHeight-logo.clientHeight)*c.logo_y/100}px`;
  const paint=(mask,r,mode,index)=>{mask.classList.toggle("hidden",mode==="keep");mask.classList.toggle("active-mask",ui.maskIndex===index);mask.style.left=r.mask_x+"%";mask.style.top=r.mask_y+"%";mask.style.width=Math.min(r.mask_w,100-r.mask_x)+"%";mask.style.height=Math.min(r.mask_h,100-r.mask_y)+"%";mask.style.background=mode==="cover"?"black":"transparent";mask.style.backdropFilter=mode==="blur"?`blur(${Math.max(.5,Number(r.mask_blur||12)*g.sw/(state.project.video_info?.width||$("video-preview").videoWidth||1280)*scale)}px)`:"none";};
  paint($("old-sub-mask"),c,c.original_subtitles,-1);
  for(const node of $("video-source-layer").querySelectorAll(".custom-blur-mask"))node.remove();
  (c.blur_regions||[]).forEach((r,index)=>{const mask=element("div","source-mask custom-blur-mask");mask.dataset.maskIndex=index;mask.setAttribute("aria-label",`Vùng mờ ${index+1}`);for(const corner of ["nw","ne","sw","se"]){const handle=element("span","mask-handle "+corner);handle.dataset.corner=corner;mask.append(handle);}const label=element("span","mask-number",String(index+1));mask.append(label);paint(mask,r,"blur",index);$("video-source-layer").append(mask);});
  syncTimedPreview();
}
function enableVideoDrag(wrap){wrap.addEventListener("pointerdown",e=>{
  if(ui.maskDraw||e.target.closest(".movable,.source-mask")||!state.project?.video||state.jobs.some(j=>j.project_id===state.project.id&&["running","queued"].includes(j.status)))return;
  e.preventDefault();wrap.setPointerCapture(e.pointerId);const g=projectGeometry(),scale=wrap.clientWidth/g.w,x=e.clientX,y=e.clientY,oldX=state.project.edit.video_x,oldY=state.project.edit.video_y;
  const move=evt=>{for(const [key,delta,space,old] of [["video_x",evt.clientX-x,g.w-g.rw,oldX],["video_y",evt.clientY-y,g.h-g.rh,oldY]]){if(Math.abs(space)<1)continue;const value=Math.max(0,Math.min(100,old+delta/scale/space*100));state.project.edit[key]=Math.round(value);$("edit-"+key).value=state.project.edit[key];}dirty();updateStage();};
  const end=()=>{wrap.removeEventListener("pointermove",move);wrap.removeEventListener("pointerup",end);wrap.removeEventListener("pointercancel",end);};wrap.addEventListener("pointermove",move);wrap.addEventListener("pointerup",end);wrap.addEventListener("pointercancel",end);
});}
function setMaskDraw(enabled){
  ui.maskDraw=enabled;
  document.querySelector(".video-wrap")?.classList.toggle("drawing-mask",enabled);
  if($("mask-draw")){$("mask-draw").textContent=enabled?"✓ Hủy vẽ vùng mới":"＋ Vẽ thêm vùng mờ";$("mask-draw").setAttribute("aria-pressed",String(enabled));}
  if($("stage-hint"))$("stage-hint").textContent=enabled?"Kéo trên hình để vẽ vùng · Esc để hủy":"Kéo vùng mờ để di chuyển · kéo góc để đổi cỡ";
}
function sourcePoint(x,y,g,rotation){
  // Inverse of the source layer's center rotation; coordinates in output pixels.
  const angle=Number(rotation||0)*Math.PI/180,dx=x-(g.left+g.sw/2),dy=y-(g.top+g.sh/2);
  return {x:(dx*Math.cos(angle)+dy*Math.sin(angle)+g.sw/2)/g.sw*100,y:(-dx*Math.sin(angle)+dy*Math.cos(angle)+g.sh/2)/g.sh*100};
}
function maskBounds(a,b){
  const clamp=n=>Math.max(0,Math.min(100,n)),left=Math.min(99,clamp(Math.min(a.x,b.x))),top=Math.min(99,clamp(Math.min(a.y,b.y)));
  return {mask_x:left,mask_y:top,mask_w:Math.min(100-left,Math.max(1,clamp(Math.max(a.x,b.x))-left)),mask_h:Math.min(100-top,Math.max(1,clamp(Math.max(a.y,b.y))-top))};
}
function refreshMaskList(){
  if(!state.project||!$("mask-select"))return;const c=state.project.edit,select=$("mask-select");select.replaceChildren();
  for(const [value,label] of [[-1,"Phụ đề gốc (riêng)"],...(c.blur_regions||[]).map((r,i)=>[i,`Vùng mờ ${i+1}`])]){const option=element("option","",label);option.value=value;select.append(option);}select.value=ui.maskIndex;
  $("mask-strength").value=(ui.maskIndex<0?c:c.blur_regions[ui.maskIndex])?.mask_blur||12;
}
function applyMask(value){const c=state.project.edit,target=ui.maskIndex<0?c:c.blur_regions[ui.maskIndex];if(!target)return;for(const [key,n] of Object.entries(value)){target[key]=typeof n==="number"?Math.round(n*100)/100:n;if(ui.maskIndex<0&&$("edit-"+key))$("edit-"+key).value=target[key];}updateStage();}
function enableMaskEditing(wrap){
  wrap.addEventListener("pointerdown",e=>{
    const maskTarget=e.target.closest(".source-mask");
    if((!ui.maskDraw&&!maskTarget)||!state.project?.video||state.jobs.some(j=>j.project_id===state.project.id&&["running","queued"].includes(j.status)))return;
    const g=projectGeometry(),rect=wrap.getBoundingClientRect(),scale=rect.width/g.w,c=state.project.edit;
    const point=evt=>sourcePoint((evt.clientX-rect.left)/scale,(evt.clientY-rect.top)/scale,g,c.rotation),start=point(e);
    if(ui.maskDraw&&(start.x<0||start.x>100||start.y<0||start.y>100)){toast("Chọn trên hình video, không phải phần viền ngoài.");return;}
    const drawing=ui.maskDraw,previousIndex=ui.maskIndex;c.blur_regions??=[];
    if(drawing&&c.blur_regions.length>=20){toast("Tối đa 20 vùng vẽ tay. Xóa vùng không cần trước khi thêm.");setMaskDraw(false);return;}
    e.preventDefault();e.stopImmediatePropagation();wrap.setPointerCapture(e.pointerId);
    if(drawing){ui.maskIndex=c.blur_regions.length;c.blur_regions.push({...maskBounds(start,start),mask_blur:12});}else ui.maskIndex=Number(maskTarget.dataset.maskIndex);
    const target=ui.maskIndex<0?c:c.blur_regions[ui.maskIndex],corner=e.target.dataset.corner,restore={mask_x:target.mask_x,mask_y:target.mask_y,mask_w:target.mask_w,mask_h:target.mask_h},old={...restore,mask_w:Math.min(target.mask_w,100-target.mask_x),mask_h:Math.min(target.mask_h,100-target.mask_y)};
    refreshMaskList();updateStage();renderTimeline();
    const wasDirty=state.dirty;let moved=false;
    const move=evt=>{const p=point(evt);moved=true;
      if(drawing)applyMask(maskBounds(start,p));
      else if(corner){const anchor={x:old.mask_x+(corner.includes("w")?old.mask_w:0),y:old.mask_y+(corner.includes("n")?old.mask_h:0)};applyMask(maskBounds(anchor,p));}
      else applyMask({mask_x:Math.max(0,Math.min(100-old.mask_w,old.mask_x+p.x-start.x)),mask_y:Math.max(0,Math.min(100-old.mask_h,old.mask_y+p.y-start.y))});
    };
    const finish=evt=>{if(evt?.type==="keydown"&&evt.key!=="Escape")return;const cancel=evt?.type==="pointercancel"||evt?.type==="keydown"||!moved;if(cancel){if(drawing){c.blur_regions.splice(ui.maskIndex,1);ui.maskIndex=previousIndex;}else applyMask(restore);state.dirty=wasDirty;$("save-status").textContent=wasDirty?"Có thay đổi chưa lưu":"Đã lưu";}else if(moved)dirty();refreshMaskList();updateStage();renderTimeline();
      wrap.removeEventListener("pointermove",move);wrap.removeEventListener("pointerup",finish);wrap.removeEventListener("pointercancel",finish);document.removeEventListener("keydown",finish);if(wrap.hasPointerCapture(e.pointerId))wrap.releasePointerCapture(e.pointerId);if(drawing)setMaskDraw(false);
    };
    wrap.addEventListener("pointermove",move);wrap.addEventListener("pointerup",finish);wrap.addEventListener("pointercancel",finish);document.addEventListener("keydown",finish);
  });
  document.addEventListener("keydown",e=>{if(e.key==="Escape")setMaskDraw(false);});
}
function enableDrag(id,prefix){const el=$(id);el.addEventListener("pointerdown",e=>{if(!state.project||state.jobs.some(j=>j.project_id===state.project.id&&["running","queued"].includes(j.status)))return;e.preventDefault();el.setPointerCapture(e.pointerId);const move=evt=>{const rect=el.parentElement.getBoundingClientRect();const x=prefix==="logo"?(evt.clientX-rect.left-el.clientWidth/2)/Math.max(1,rect.width-el.clientWidth):(evt.clientX-rect.left)/rect.width;const y=prefix==="logo"?(evt.clientY-rect.top-el.clientHeight/2)/Math.max(1,rect.height-el.clientHeight):(evt.clientY-rect.top)/rect.height;for(const [key,value] of [[prefix+"_x",x],[prefix+"_y",y]]){state.project.edit[key]=Math.round(Math.max(0,Math.min(100,value*100)));$("edit-"+key).value=state.project.edit[key];}dirty();updateStage();};el.addEventListener("pointermove",move);el.addEventListener("pointerup",()=>el.removeEventListener("pointermove",move),{once:true});});}
