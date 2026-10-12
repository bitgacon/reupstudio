"use strict";
document.addEventListener('DOMContentLoaded',()=>{
  const panel=element('details','storage-settings');panel.id='advanced-ai-settings';panel.append(element('summary','','AI nâng cao · runtime/model riêng'));
  panel.append(element('p','hint','Không tải khi mở app/chạy tác vụ. CTC và MuseTalk cài tại Thư viện hoặc nối runtime riêng. MMS mặc định chỉ phi thương mại; MuseTalk cần NVIDIA và thư mục không dấu/khoảng trắng.'));
  for(const [key,label] of [['alignment_python','Python CTC'],['alignment_model','Thư mục model CTC'],['alignment_language','Ngôn ngữ ISO 639-3 (vie / eng / zho)'],['avatar_home','Thư mục MuseTalk (không dấu/khoảng trắng)'],['avatar_python','Python riêng MuseTalk'],['reid_model','Model ReID ONNX local (tùy chọn, NCHW 256×128)']]){
    const field=element('label','field',label),input=element('input');input.id='ai-'+key;field.append(input);panel.append(field);
  }
  const roman=element('label','check'),check=element('input');check.type='checkbox';check.id='ai-alignment_romanize';roman.append(check,document.createTextNode('Romanize cho model MMS'));panel.append(roman);
  panel.append(seqButton('Lưu kết nối AI',async()=>{const value={};for(const k of ['alignment_python','alignment_model','alignment_language','avatar_home','avatar_python','reid_model'])value[k]=$('ai-'+k).value.trim();value.alignment_romanize=check.checked;await api('advanced-ai',value);toast('Đã lưu. Runtime/model được kiểm tra khi chạy, không tải ngầm.');}));
  $('settings-form').append(panel);panel.addEventListener('toggle',async()=>{if(!panel.open)return;try{const c=await api('advanced-ai');for(const k of ['alignment_python','alignment_model','alignment_language','avatar_home','avatar_python','reid_model'])$('ai-'+k).value=c[k];check.checked=c.alignment_romanize;}catch(e){toast(e.message,true);}});
});
function seqAISettings(){ $('settings-open').click();settingsChoose('ai');$('advanced-ai-settings').open=true; }
function seqTrackedProposal(doc,result,asset,newId){
  const copy=seqCopy(doc);if(copy.tracks.length>=SEQ_MAX_TRACKS)throw Error('Tối đa 64 track.');
  const segments=result.segments?.length?result.segments:[{start:0,end:result.duration_ms,keyframes:result.keyframes}];
  const clips=segments.map(s=>{const keys=s.keyframes.map(k=>({...k}));if(!keys.length||s.end-s.start<100)throw Error('Đoạn tracking không hợp lệ.');
    const c={id:newId(),asset,label:asset?'Sticker tái bám':'Vùng mờ tái bám',start_ms:result.start_ms+s.start,in_ms:0,duration_ms:s.end-s.start,volume:0,...seqTransformDefaults,x:keys[0].x,y:keys[0].y,region_w:result.region_w,region_h:result.region_h,blur:12,keyframes:keys,motion_easing:'linear'};if(asset)c.scale=.2;return c;});
  if(copy.tracks.flatMap(t=>t.clips).length+clips.length>500)throw Error('Quá 500 clip.');
  copy.tracks.push({id:newId(),name:clips[0].label,kind:asset?'video':'blur',locked:false,hidden:false,muted:true,clips});return copy;
}
function seqSetupAdvanced(panel){
  const details=element('details','seq-property-group');details.append(element('summary','','AI nâng cao / phối nhiều lớp'));
  details.append(seqButton('Forced alignment · lời khớp audio',seqForcedAlignment),seqButton('Avatar · MuseTalk',seqAvatarDialog),seqButton('Phối nhiều lớp tự động',seqComposeDialog),seqButton('Đạo diễn AI · phối bằng prompt',seqDirectorDialog),seqButton('Cài / nối runtime AI',seqAISettings));
  const label=element('label','check'),input=element('input');input.type='checkbox';input.id='seq-object-reidentify';label.append(input,document.createTextNode('Tracking tái tìm mẫu toàn khung · thử nghiệm'));details.append(label,element('small','hint','Tái tìm theo ngoại hình OpenCV, không phải nhận diện danh tính. Có che khuất/đổi cảnh: chỉ hiện lại sau 2 mẫu chắc chắn; đoạn mất dấu không tạo lớp.'));
  panel.append(details);
}
async function seqForcedAlignment(){
  seqRequire();const {clip}=seqSelection();if(!clip?.asset)throw Error('Chọn clip audio/video cần căn. Lời dịch phải tương ứng audio lồng tiếng, không phải audio gốc ngoại ngữ.');
  const d=seqToolDialog('Forced alignment CTC'),input=element('textarea');input.rows=4;input.placeholder='Nhập lời được nói trong audio clip đang chọn (tối đa 30s)';const project=sequence.id,generation=sequence.generation;
  d.append(element('p','hint','Căn bằng emission CTC + Viterbi, không dùng mốc Whisper để đoán từ thiếu. Chỉ chạy model đã cài; kết quả vẫn cần nghe/duyệt.'),input,seqButton('Căn lời → duyệt',async()=>{
    if(sequence.id!==project||sequence.generation!==generation)throw Error('Timeline đã đổi; mở lại công cụ.');
    const result=await seqStudioJob('alignment',{reference:input.value.trim()});seqReviewForced(result);
  }),seqButton('Cài / nối CTC',seqAISettings));
}
function seqReviewForced(result){
  const project=sequence.id,generation=sequence.generation,d=seqToolDialog('Duyệt căn lời CTC'),input=element('textarea');input.rows=12;
  input.value=result.words.map(w=>`${(w.start/1000).toFixed(3)}\t${(w.end/1000).toFixed(3)}\t${w.word}`).join('\n');
  const weak=result.words.filter(w=>w.confidence<.5);d.append(element('p','hint',`${result.words.length} từ; ${weak.length} từ độ tin cậy dưới 0.50: ${weak.map(w=>w.word).join(', ')}. Mỗi dòng: giây bắt đầu, kết thúc, một từ. Sửa và nghe clip trước khi áp dụng.`),input,seqButton('Thêm karaoke · Hoàn tác',()=>{
    if(project!==sequence.id||generation!==sequence.generation)throw Error('Timeline đã đổi; căn lại.');
    const words=input.value.trim().split(/\r?\n/u).map(line=>{const a=line.trim().split(/\s+/u);if(a.length!==3)throw Error('Mỗi dòng cần hai mốc và một từ.');return {start:Math.round(Number(a[0])*1000),end:Math.round(Number(a[1])*1000),word:a[2]};});
    seqChange(()=>sequence.doc=seqWordProposal(sequence.doc,result,words,seqId));d.close();
  }));
}
function seqAssetChoice(kind,empty='Không thêm'){
  const select=element('select');const none=element('option','',empty);none.value='';select.append(none);
  for(const item of sequence.media.values())if(kind(item)){const o=element('option','',item.name);o.value=item.id;select.append(o);}return select;
}
function seqAvatarDialog(){
  seqRequire();const d=seqToolDialog('Avatar AI · MuseTalk v1.5'),portrait=seqAssetChoice(i=>i.kind==='image','Chọn ảnh chân dung');
  const consent=element('label','check'),check=element('input');check.type='checkbox';consent.append(check,document.createTextNode('Tôi có quyền dùng hình và giọng này để tạo avatar.'));
  const project=sequence.id,generation=sequence.generation;d.append(element('p','hint','Chọn clip audio/video tối đa 30s trên timeline để điều khiển môi. Cần MuseTalk đã cài, model và GPU CUDA. Kết quả là media riêng, không thay clip gốc.'),portrait,consent,seqButton('Tạo avatar → duyệt',async()=>{
    if(project!==sequence.id||generation!==sequence.generation)throw Error('Timeline đã đổi.');
    const r=await seqStudioJob('avatar',{portrait:portrait.value,portrait_consent:check.checked});sequence.media.set(r.media.id,r.media);
    const dialog=seqToolDialog('Duyệt avatar AI'),video=element('video');video.controls=true;video.src=r.media.preview_url||r.media.url;video.style.maxWidth='100%';dialog.append(video,seqButton('Thêm track avatar · Hoàn tác',()=>{if(project!==sequence.id||generation!==sequence.generation)throw Error('Timeline đã đổi; media giữ trong lịch sử.');seqAddToolMedia(r.media,'Avatar AI',r.duration_ms,r.start_ms);dialog.close();}));
  }),seqButton('Nối MuseTalk',seqAISettings));
}
function seqComposeDialog(){
  seqRequire();const d=seqToolDialog('Phối nhiều lớp · đề xuất local'),project=sequence.id,generation=sequence.generation;
  const style=element('select');for(const [v,n] of [['story','Kể chuyện'],['news','Bản tin'],['podcast','Podcast']]){const o=element('option','',n);o.value=v;style.append(o);}
  const background=seqAssetChoice(i=>['image','video'].includes(i.kind)),overlay=seqAssetChoice(i=>['image','video'].includes(i.kind)),music=seqAssetChoice(i=>i.has_audio),title=element('input'),duration=element('input');title.placeholder='Tiêu đề (tùy chọn)';Object.assign(duration,{type:'number',min:.1,max:60,value:5,step:.1});
  for(const [name,node] of [['Phong cách',style],['Nền dưới video gốc',background],['Lớp phủ góc trên',overlay],['Nhạc nền (15%)',music],['Tiêu đề',title],['Thời lượng (giây)',duration]]){const label=element('label','field',name);label.append(node);d.append(label);}
  d.append(element('p','hint','Dùng media đã nhập, bắt đầu tại con trỏ. Nền ở dưới, overlay/chữ ở trên. Rút lớp theo độ dài nguồn, không kéo dài file. Đây là bộ bố cục theo quy tắc, chưa phải AI tự chọn nội dung.'),seqButton('Tạo đề xuất → duyệt',async()=>{
    if(project!==sequence.id||generation!==sequence.generation)throw Error('Timeline đã đổi.');
    const r=await seqStudioJob('compose',{options:{style:style.value,start_ms:Math.round(sequence.time),duration_ms:Math.round(Number(duration.value)*1000),background:background.value,overlay:overlay.value,music:music.value,title:title.value}});
    const dialog=seqToolDialog('Duyệt các lớp sẽ thêm');dialog.append(element('pre','',r.added.map(x=>`${x.name}: ${(x.duration_ms/1000).toFixed(2)}s`).join('\n')),seqButton('Áp dụng · Hoàn tác',()=>{if(project!==sequence.id||generation!==sequence.generation)throw Error('Timeline đã đổi; tạo lại.');seqChange(()=>sequence.doc=r.timeline);dialog.close();}));
  }));
}

function seqDirectorDialog(){
  seqRequire();if(sequence.busy)throw Error('Chờ tác vụ hiện tại.');
  const project=sequence.id,generation=sequence.generation,start=Math.round(sequence.time),d=seqToolDialog('Đạo diễn AI · phối bằng prompt');
  const prompt=element('textarea');prompt.id='seq-director-prompt';prompt.rows=4;prompt.maxLength=5000;prompt.placeholder='Mô tả bố cục, thứ tự xuất hiện, tiêu đề và nhạc bạn muốn…';
  const duration=element('input');duration.id='seq-director-duration';Object.assign(duration,{type:'number',min:.1,max:60,step:.1,value:5});
  const media=element('div','card compact');media.id='seq-director-assets';
  for(const item of sequence.media.values())if(sequence.doc.assets.includes(item.id)){
    const label=element('label','check'),check=element('input'),name=element('span','',item.name);name.dataset.i18nSkip='';check.type='checkbox';check.value=item.id;label.append(check,name);media.append(label);
  }
  const consent=element('label','check'),allow=element('input');allow.id='seq-director-consent';allow.type='checkbox';
  consent.append(allow,document.createTextNode('Cho phép gửi prompt, tên và thông tin media đã chọn tới API LLM. Không gửi video/audio hay nội dung dự án khác.'));
  for(const [name,node] of [['Yêu cầu dựng',prompt],['Khoảng đề xuất (giây)',duration],['Media cho phép AI sử dụng',media]]){const field=element('label','field',name);field.append(node);d.append(field);}
  const generate=seqButton('Gửi prompt → duyệt lớp',async()=>{
      if(project!==sequence.id||generation!==sequence.generation)throw Error('Timeline đã đổi; mở lại công cụ.');
      if(!allow.checked)throw Error('Cần cho phép gửi prompt và thông tin media đã chọn tới API LLM.');
      const assets=[...media.querySelectorAll('input:checked')].map(i=>i.value);
      const r=await seqStudioJob('director',{prompt:prompt.value,start_ms:start,duration_ms:Math.round(Number(duration.value)*1000),assets,allow_external:true});
      if(project!==sequence.id||generation!==sequence.generation)throw Error('Timeline đã đổi; tạo đề xuất AI lại.');
      seqDirectorReview(r,project,generation);
    });generate.id='seq-director-generate';
  d.append(element('p','hint','Dùng model API đang chọn trong Cài đặt → Dịch & API. Có thể phát sinh phí. Chỉ thêm lớp mới; giữ nguyên clip cũ. Luôn duyệt trước khi áp dụng.'),consent,generate);
}

function seqDirectorReview(result,project,generation){
  const d=seqToolDialog('Duyệt đề xuất đạo diễn AI'),summary=element('p','',result.summary);summary.dataset.i18nSkip='';d.append(summary);
  const list=element('pre','');list.textContent=result.added.map(x=>`${x.name} · ${(x.start_ms/1000).toFixed(2)}–${((x.start_ms+x.duration_ms)/1000).toFixed(2)}s · X/Y ${x.x}/${x.y} · scale ${x.scale} · opacity ${x.opacity} · volume ${x.volume}\n${x.text||sequence.media.get(x.asset)?.name||''}`).join('\n\n');d.append(list);
  const apply=seqButton('Áp dụng · Hoàn tác',()=>{
    if(project!==sequence.id||generation!==sequence.generation||sequence.doc.revision!==result.revision)throw Error('Timeline đã đổi; tạo đề xuất AI lại.');
    seqChange(()=>sequence.doc=result.timeline);d.close();
  });apply.id='seq-director-apply';d.append(apply);
}
