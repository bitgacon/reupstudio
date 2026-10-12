// Saved credentials are never returned to the browser. Switching is explicit.
function setupLLMUI(){
 if($('llm-profile-box'))return;
 const box=element('details','card');box.id='llm-profile-box';box.append(element('summary','','Nhiều LLM / nhiều key · chọn cấu hình'));
 const field=(label,id,type='text')=>{const l=element('label','field',label),i=element(type==='select'?'select':'input');i.id=id;if(type!=='select')i.type=type;l.append(i);box.append(l);return i;};
 const profiles=field('Cấu hình đã lưu','llm-profile','select'),name=field('Tên riêng của key / cấu hình','llm-name'),preset=field('Nhà cung cấp','llm-provider','select');
 const batch=field('Số cue mỗi yêu cầu (1–20)','llm-batch','number'),pause=field('Nghỉ giữa yêu cầu (giây)','llm-pause','number');batch.min=1;batch.max=20;batch.value=10;pause.min=0;pause.max=60;pause.step=.5;pause.value=2;
 box.append(element('p','hint','Dùng các ô Base URL / model / key bên dưới để lưu cấu hình. Key trống giữ key của profile đang sửa; profile mới có thể dùng key hiện tại nếu cùng endpoint. Không tự đảo key khi quota 429; nhiều key cùng project Gemini vẫn chung hạn mức. Chọn Dùng cấu hình để áp dụng, sau đó Dịch / Tiếp tục.'));
 let data={profiles:[],presets:[]};
 const refresh=async()=>{data=await api('llm-profiles');const keep=profiles.value;profiles.replaceChildren(new Option('＋ Cấu hình mới',''));data.profiles.forEach(r=>profiles.append(new Option(r.name+' · '+r.model+(r.has_key?' · có key':''),r.id)));profiles.value=data.profiles.some(r=>r.id===keep)?keep:'';preset.replaceChildren();data.presets.forEach(r=>preset.append(new Option(r.name,r.id)));};
 profiles.onchange=()=>{const r=data.profiles.find(r=>r.id===profiles.value);if(!r){name.value='';return;}name.value=r.name;preset.value=r.provider;batch.value=r.batch_size;pause.value=r.pause_seconds;$('setting-url').value=r.url;$('setting-model').value=r.model;$('setting-key').value='';$('setting-key').placeholder=r.has_key?'Đã lưu key của cấu hình này; để trống để giữ':'Nhập key';};
 preset.onchange=()=>{const r=data.presets.find(r=>r.id===preset.value);if(!r)return;$('setting-url').value=r.url;$('setting-model').value=r.model;$('setting-key').value='';$('setting-key').placeholder='Nhập key đúng nhà cung cấp';};
 const actions=element('div','actions');box.append(actions);
 const button=(text,fn)=>{const b=makeButton(text,fn);b.type='button';actions.append(b);return b;};
 button('＋ Mới',()=>{profiles.value='';name.value='';$('setting-key').value='';name.focus();});
 button('Lưu cấu hình',async()=>{const body={id:profiles.value,name:name.value,provider:preset.value,url:$('setting-url').value,model:$('setting-model').value,batch_size:Number(batch.value),pause_seconds:Number(pause.value),use_current_key:!profiles.value&&!$('setting-key').value};if($('setting-key').value)body.key=$('setting-key').value;const old=profiles.value;await api('llm-profiles/save',body);await refresh();profiles.value=old||data.profiles.at(-1)?.id||'';$('setting-key').value='';toast('Đã lưu cấu hình trên máy, chưa đổi API đang dùng.');});
 button('Dùng cấu hình',async()=>{if(!profiles.value)throw Error('Chọn cấu hình đã lưu.');await api('llm-profiles/activate',{id:profiles.value});await poll();const s=state.settings;$('setting-url').value=s.translation_url;$('setting-model').value=s.translation_model;$('setting-key').value='';if(state.project){const p=$('edit-translation_provider');p.value='api';p.dispatchEvent(new Event('input'));}toast('Đã chọn API. Dịch / Tiếp tục giữ các cue đã xong; không tự luân chuyển key.');});
 button('Xóa cấu hình',async()=>{if(!profiles.value)throw Error('Chọn cấu hình trước.');if(!confirm('Xóa cấu hình lưu này? Cài đặt API hiện đang dùng vẫn giữ nguyên.'))return;await api('llm-profiles/delete',{id:profiles.value});profiles.value='';await refresh();name.value='';});
 $('setting-url').parentElement.before(box);
 $('settings-open').addEventListener('click',()=>refresh().catch(e=>toast(e.message,true)));
 refresh().catch(e=>toast(e.message,true));
 $('translate-all').before(makeButton('Kiểm tra phụ đề sau dịch',showSubtitleQC));
}

async function showSubtitleQC(){
 if(!state.project)throw Error('Mở dự án trước.');await saveProject();const result=await api('projects/'+state.project.id+'/subtitle-qc');
 let dialog=$('subtitle-qc-dialog');if(!dialog){dialog=element('dialog','large-dialog');dialog.id='subtitle-qc-dialog';document.body.append(dialog);}dialog.replaceChildren();dialog.append(element('h2','','Kiểm tra phụ đề / lời đọc'),makeButton('Đóng ×',()=>dialog.close()),element('p','hint','Ước tính theo luật đọc, không phải forced alignment hoặc thời lượng TTS chính xác. Không tự sửa nội dung/timeline.'));
 dialog.append(element('p','',`${result.cues} cue · ${result.issues.length} cảnh báo`));
 for(const issue of result.issues){const row=element('div','history-row');row.append(element('span','',`#${issue.cue}: ${issue.message}`),makeButton('Đến câu',()=>{dialog.close();$('cue-filter').value='all';renderCues();const input=[...$('cue-list').querySelectorAll('.cue-select')].find(i=>Number(i.dataset.id)===issue.cue);if(input){input.checked=true;input.closest('.cue-card').scrollIntoView({block:'center'});}const cue=state.project.cues.find(c=>c.id===issue.cue);if(cue)seek(cue);}));dialog.append(row);}
 dialog.showModal();
}
