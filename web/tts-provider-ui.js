// No model download or cloud text request is triggered by selecting a provider.
let ttsCatalog=null,ttsMain=null;
let podcastTTS=null;
function podcastSpeechMap(){
 if(podcastTTS===null){podcastTTS=Object.create(null);try{const saved=JSON.parse(localStorage.getItem('rv-podcast-tts')||'{}');if(saved&&typeof saved==='object'&&!Array.isArray(saved))for(const [name,opt] of Object.entries(saved))if(opt&&typeof opt==='object'&&!Array.isArray(opt)&&typeof opt.provider==='string')podcastTTS[name]=opt;}catch{}}
 return podcastTTS;
}
function podcastSpeech(name){return Object.hasOwn(podcastSpeechMap(),name)?podcastSpeechMap()[name]:null;}
function savePodcastSpeech(){localStorage.setItem('rv-podcast-tts',JSON.stringify(podcastSpeechMap()));}
function podcastSpeechSummary(name){const opt=podcastSpeech(name);if(!opt)return 'VieNeu · tiếng Việt';return `${ttsCatalog?.catalog.find(r=>r.id===opt.provider)?.name||opt.provider} · ${ttsCatalog?.languages[opt.language]||opt.language}${opt.voice?' · '+opt.voice:''}${opt.emotion&&opt.emotion!=='neutral'?' · '+(ttsCatalog?.emotions[opt.emotion]||opt.emotion):''}`;}
function podcastActiveNames(){return [...new Set([...$('podcast-text').value.matchAll(/^\s*\[([^\]\n]{1,60})\]\s*:/gm)].map(m=>m[1].trim()))];}
function podcastGeneratePayload(){
 const speaker_tts=Object.create(null),speakers=Object.create(null);
 for(const name of podcastActiveNames()){
  const opt=podcastSpeech(name);if(opt){speaker_tts[name]={...opt};if(opt.provider==='elevenlabs'&&!opt.cloud_consent)throw Error('Nhân vật '+name+': cần cho phép gửi lời đọc tới ElevenLabs.');if(opt.provider!=='vieneu'&&!opt.voice)throw Error('Nhân vật '+name+': chưa chọn giọng TTS.');}
  speakers[name]=opt?.voice||(opt&&opt.provider!=='vieneu'?'':state.speakers[name]||'');
  if(!speakers[name])throw Error('Chưa gán giọng cho '+name+'.');
 }
 return {text:$('podcast-text').value,speakers,speaker_tts,rate:Number($('podcast-rate').value),pause:Number($('podcast-pause').value)};
}
async function podcastEditSpeech(name){
 await refreshTTSProviders();let dialog=$('podcast-tts-dialog');if(!dialog){dialog=element('dialog','large-dialog');dialog.id='podcast-tts-dialog';document.body.append(dialog);}dialog.replaceChildren();dialog.append(element('h2','','Giọng / ngôn ngữ · '+name),makeButton('Đóng ×',()=>dialog.close()));
 const fields=element('div','tts-provider-fields');dialog.append(fields);const form=ttsForm(fields,podcastSpeech(name)||{provider:'vieneu',language:'vi',voice:state.speakers[name]||''});
 dialog.append(element('p','hint','Mỗi nhân vật có thể dùng bộ TTS/ngôn ngữ riêng. Văn bản không tự dịch. Qwen3 trên CPU có thể rất chậm; Kokoro phù hợp cho bản nháp tiếng Anh. Chọn bộ không tự tải model.'));
 const apply=opt=>{if(opt)podcastSpeechMap()[name]=opt;else delete podcastSpeechMap()[name];savePodcastSpeech();const y=$('speaker-list').scrollTop;renderSpeakers();$('speaker-list').scrollTop=y;dialog.close();};
 dialog.append(makeButton('Lưu giọng nhân vật',()=>apply(form.value()),'primary'),makeButton('Dùng giọng VieNeu cũ',()=>apply(null)));dialog.showModal();
}
function podcastPreviewSpeech(name){
 const lines=$('podcast-text').value.split('\n');let text='';for(const line of lines){const match=line.match(/^\s*\[([^\]\n]{1,60})\]\s*:\s*(.*)$/);if(match?.[1].trim()===name){text=match[2].trim();break;}}
 if(!text)throw Error('Chưa có lời thoại trên dòng [Tên]: của nhân vật '+name+'.');
 const opt=podcastSpeech(name)||{provider:'vieneu',language:'vi',voice:state.speakers[name]||''};const voice=opt.voice||(opt.provider==='vieneu'?state.speakers[name]:'');if(!voice)throw Error('Chưa chọn giọng cho '+name+'.');if(opt.provider==='elevenlabs'&&!opt.cloud_consent)throw Error('Cần cho phép gửi lời đọc tới ElevenLabs cho '+name+'.');
 return startTask('tts',{text:text.slice(0,120),voice,tts:opt,rate:Number($('podcast-rate').value)},{play:true,title:'Nghe thử · '+name});
}
function ttsSaved(){try{return JSON.parse(localStorage.getItem('rv-tts-options')||'null')||{provider:'vieneu',language:'vi'};}catch{return {provider:'vieneu',language:'vi'};}}
async function refreshTTSProviders(){ttsCatalog=await api('tts-providers');if(ttsMain)ttsMain.refresh();return ttsCatalog;}
function ttsForm(parent,initial={},changed=()=>{}){
 const controls={},labels={};
 const field=(name,title,tag='select')=>{const label=element('label','field',title),input=element(tag);input.dataset.tts=name;label.append(input);parent.append(label);controls[name]=input;labels[name]=label;return input;};
 const provider=field('provider','Bộ tạo giọng'),language=field('language','Ngôn ngữ'),voice=field('voice','Giọng đọc'),emotion=field('emotion','Diễn xuất');
 const intensity=field('intensity','Mức biểu cảm (0–1)','input');intensity.type='range';intensity.min=0;intensity.max=1;intensity.step=.1;intensity.value=initial.intensity??.5;
 const instruction=field('instruction','Mô tả cách đọc · Qwen3','textarea');instruction.rows=2;instruction.maxLength=500;instruction.value=initial.instruction||'';
 const model=field('model','Model ElevenLabs');model.append(new Option('Eleven v3 · thẻ cảm xúc','eleven_v3'),new Option('Multilingual v2 · bình thường','eleven_multilingual_v2'));model.value=initial.model||'eleven_v3';
 const consent=field('cloud_consent','Cho phép gửi lời đọc tới ElevenLabs (có thể tính credit)','input');consent.type='checkbox';consent.checked=!!initial.cloud_consent;labels.cloud_consent.classList.add('check');
 const note=element('p','hint');parent.append(note);
 let desired={provider:'vieneu',language:'vi',voice:'',emotion:'neutral',...initial};
 const row=()=>ttsCatalog?.catalog.find(r=>r.id===provider.value);
 function languages(){const r=row();if(!r)return;const keep=language.value||desired.language;language.replaceChildren(...r.languages.map(id=>new Option(ttsCatalog.languages[id]||id,id)));language.value=r.languages.includes(keep)?keep:r.languages[0];voices();}
 function voices(){const r=row();if(!r)return;const keep=voice.value||desired.voice;let rows=r.id==='vieneu'?state.voices.map(v=>({id:v.id,name:v.name,language:'vi'})):r.voices;rows=rows.filter(v=>!v.language||v.language===language.value);voice.replaceChildren(new Option(r.id==='vieneu'?'Giọng VieNeu đang chọn':'Chọn giọng…',''),...rows.map(v=>new Option(v.name,v.id)));if(rows.some(v=>v.id===keep))voice.value=keep;else if(r.id!=='vieneu')voice.value=rows[0]?.id||'';}
 function capabilities(){const r=row();if(!r)return;const keep=emotion.value||desired.emotion;const allowed=r.id==='elevenlabs'&&model.value==='eleven_multilingual_v2'?['neutral']:r.emotions;emotion.replaceChildren(...allowed.map(id=>new Option(ttsCatalog.emotions[id],id)));emotion.value=allowed.includes(keep)?keep:'neutral';emotion.disabled=allowed.length===1;labels.intensity.hidden=!['chatterbox','qwen'].includes(r.id);labels.instruction.hidden=!r.instruction;labels.model.hidden=!r.cloud;labels.cloud_consent.hidden=!r.cloud;
  note.textContent=r.cloud?'API chính thức; không phải thư viện miễn phí vô hạn. Bấm Nạp giọng để lấy danh sách sau khi lưu key.':r.id==='vieneu'&&r.installed?'Giữ nguyên giọng tiếng Việt hiện có.':r.installed?'Đã cài runtime local; chạy offline. Cần nghe kiểm tra chất lượng từng ngôn ngữ.':'Chưa cài. Vào ⚙ → Thư viện tùy chọn để tải/cài khi cần. Không tự tải khi chọn.';
 }
 function value(){const r=row();if(!r)throw Error('Danh sách bộ TTS chưa sẵn sàng.');return {provider:r.id,language:language.value,voice:voice.value,emotion:emotion.value,intensity:Number(intensity.value),instruction:r.instruction?instruction.value.trim():'',cloud_consent:r.cloud&&consent.checked,model:r.cloud?model.value:'',reference_asset:initial.reference_asset||'',reference_consent:!!initial.reference_consent};}
 function notify(){changed(value());}
 function refresh(){if(!ttsCatalog)return;const keep=provider.value||desired.provider;provider.replaceChildren(...ttsCatalog.catalog.map(r=>new Option(r.name,r.id)));provider.value=ttsCatalog.catalog.some(r=>r.id===keep)?keep:'vieneu';languages();capabilities();}
 provider.onchange=()=>{desired={provider:provider.value};language.replaceChildren();voice.replaceChildren();emotion.replaceChildren();consent.checked=false;instruction.value='';languages();capabilities();notify();};
 language.onchange=()=>{voices();notify();};model.onchange=()=>{capabilities();notify();};[voice,emotion,intensity,instruction,consent].forEach(input=>input.onchange=notify);
 refresh();return {value,refresh,controls};
}
function ttsGeneratePayload(){const tts=ttsMain?.value()||ttsSaved();const voice=tts.voice||(tts.provider==='vieneu'?state.selectedVoice:'');if(!voice)throw Error('Chọn giọng trước; giọng local xuất hiện sau khi cài thư viện.');if(tts.provider==='elevenlabs'&&!tts.cloud_consent)throw Error('Cần cho phép gửi văn bản tới ElevenLabs.');return {text:$('tts-text').value,voice,rate:Number($('tts-rate').value),tts};}
function ttsCueButton(cue){const opt=cue.tts||state.project.tts;return makeButton(opt?`Giọng · ${opt.provider}${opt.emotion!=='neutral'?' · '+opt.emotion:''}`:'Giọng / diễn xuất',()=>ttsEdit(cue));}
async function ttsEdit(cue=null){
 if(!state.project)throw Error('Mở dự án trước.');await refreshTTSProviders();
 let dialog=$('tts-cue-dialog');if(!dialog){dialog=element('dialog','large-dialog');dialog.id='tts-cue-dialog';document.body.append(dialog);}dialog.replaceChildren();dialog.append(element('h2','',cue?'Giọng / diễn xuất · câu '+cue.id:'Giọng mặc định của dự án'),makeButton('Đóng ×',()=>dialog.close()));
 const box=element('div','tts-provider-fields');dialog.append(box);const form=ttsForm(box,cue?.tts||state.project.tts||{});
 dialog.append(element('p','hint','Chỉ đổi cách tạo audio, không thay chữ phụ đề. Đổi bộ/giọng/diễn xuất sẽ yêu cầu tạo lại cue. Chất lượng biểu cảm phụ thuộc model.'));
 const apply=opt=>{if(cue){cue.tts=opt;cue.status='pending';}else{state.project.tts=opt;state.project.cues.filter(c=>!c.tts).forEach(c=>c.status='pending');}dirty();const y=$('cue-list').scrollTop;renderCues();$('cue-list').scrollTop=y;dialog.close();};
 dialog.append(makeButton('Áp dụng · chưa lưu',()=>apply(form.value()),'primary'),makeButton(cue?'Dùng giọng mặc định dự án':'Trở về VieNeu',()=>apply(null)));dialog.showModal();
}
async function setupTTSProviders(){
 await refreshTTSProviders();const box=element('details','tts-provider-box');box.open=true;box.append(element('summary','','Bộ TTS · ngôn ngữ & diễn xuất'));const fields=element('div','tts-provider-fields');box.append(fields);$('voice-list').before(box);
 const apply=value=>{localStorage.setItem('rv-tts-options',JSON.stringify(value));const local=value.provider==='vieneu';$('voice-list').hidden=!local;document.querySelector('.voice-controls').hidden=!local;if($('selected-voice-name'))$('selected-voice-name').hidden=!local;document.querySelectorAll('#page-tts [data-tag]').forEach(b=>b.hidden=!local&&b.dataset.tag!=='[nghỉ 1s]');document.querySelector('#page-tts .local-badge').textContent=local||value.provider!=='elevenlabs'?'● TTS chạy trên máy':'☁ ElevenLabs · gửi văn bản khi bạn cho phép';};
 ttsMain=ttsForm(fields,ttsSaved(),apply);apply(ttsMain.value());
 box.append(makeButton('▶ Nghe thử đoạn đầu',()=>{const payload=ttsGeneratePayload();payload.text=payload.text.slice(0,120);if(!payload.text.trim())throw Error('Nhập một câu trước.');return startTask('tts',payload,{play:true,title:'Nghe thử · '+payload.tts.provider});}));
 $('dub-voice').parentElement.after(makeButton('Giọng đa ngôn ngữ / diễn xuất dự án',()=>ttsEdit()));
 const settings=element('details','card');settings.id='tts-provider-settings';settings.append(element('summary','','TTS đa ngôn ngữ · API & thiết bị'));
 const label=element('label','field','API key ElevenLabs (không dùng key Gemini)'),key=element('input');key.type='password';key.autocomplete='off';key.placeholder=ttsCatalog.has_elevenlabs_key?'Đã lưu key; để trống để giữ':'Chưa có key';label.append(key);settings.append(label);
 const clearLabel=element('label','check',' Xóa key ElevenLabs đang lưu'),clear=element('input');clear.type='checkbox';clearLabel.prepend(clear);settings.append(clearLabel);
 const device=element('select');device.append(new Option('CPU · chậm với model lớn','cpu'),new Option('NVIDIA CUDA · cần GPU/driver phù hợp','cuda'));device.value=ttsCatalog.device;const deviceLabel=element('label','field','Thiết bị Chatterbox / Qwen3 (chọn trước khi cài)');deviceLabel.append(device);settings.append(deviceLabel);
 settings.append(element('p','hint','Kokoro dùng CPU. Đổi CPU/CUDA có thể cần cài lại runtime; không tự tải. ElevenLabs free có hạn mức và điều kiện riêng, không bảo đảm quyền thương mại. CapCut chưa có API TTS công khai được tích hợp; có thể nhập audio xuất từ CapCut vào editor.'));
 settings.append(makeButton('Lưu cấu hình TTS',async()=>{ttsCatalog=await api('tts-providers/config',{elevenlabs_key:key.value.trim(),clear_key:clear.checked,device:device.value});key.value='';clear.checked=false;key.placeholder=ttsCatalog.has_elevenlabs_key?'Đã lưu key; để trống để giữ':'Chưa có key';ttsMain.refresh();toast('Đã lưu cấu hình TTS, chưa tải model hoặc gửi lời đọc.');}));
 settings.querySelectorAll('button').forEach(b=>b.type='button');$('settings-form').append(settings);renderSpeakers();
 $('settings-open').addEventListener('click',()=>refreshTTSProviders().catch(e=>toast(e.message,true)));
}
document.addEventListener('DOMContentLoaded',()=>setupTTSProviders().catch(e=>toast(e.message,true)));
