"use strict";
function refreshOutputFolders(){
  for(const input of document.querySelectorAll('[data-output-setting]')){
    if(document.activeElement!==input&&!input.dataset.dirty) input.value=state.settings[input.dataset.outputSetting]||"";
    input.placeholder=state.settings.output_root||"Mặc định: outputs theo chức năng";
  }
}
document.addEventListener('DOMContentLoaded',()=>{
  const reveal=seqButton('📂 Mở thư mục lưu',()=>openOutputFolder(ui.tab));reveal.id='player-open-folder';
  document.getElementById('player-downloads').after(reveal);
  const add=(parent,key,title)=>{
    const row=document.createElement('div');row.className='output-folder-row';
    const label=document.createElement('label');label.textContent=title;
    const input=document.createElement('input');input.dataset.outputSetting=key;input.setAttribute('aria-label',title);
    input.oninput=()=>input.dataset.dirty='1';
    const browse=document.createElement('button');browse.type='button';browse.textContent='Chọn…';
    const save=document.createElement('button');save.type='button';save.textContent='Lưu';
    browse.onclick=async()=>{try{const result=await api('folder',{});if(result.path){input.value=result.path;input.dataset.dirty='1';}}catch(e){toast(e.message+' — Có thể nhập đường dẫn trực tiếp.',true);}};
    save.onclick=async()=>{try{state.settings=await api('settings',{[key]:input.value.trim()});delete input.dataset.dirty;refreshOutputFolders();toast('Đã lưu thư mục. Chỉ áp dụng cho kết quả mới; không di chuyển file cũ.');}catch(e){toast(e.message,true);}};
    row.append(label,input,browse,save);
    parent.append(row);
  };
  const folders=document.createElement('details');folders.className='storage-settings';
  const summary=document.createElement('summary');summary.textContent='Thư mục lưu trữ · mặc định và theo chức năng';folders.append(summary);
  document.getElementById('settings-form').querySelector('.card-heading').after(folders);
  add(folders,'output_root','Đầu ra mặc định');
  for(const [tab,title] of [['tts','Văn bản → Giọng nói'],['clone','Mẫu voice clone'],['dub','Lồng tiếng video'],['edit','Biên tập video'],['podcast','Hội thoại / Podcast'],['documents','Đọc tài liệu'],['downloads','Tải video / audio'],['removal','Xóa logo/phụ đề']])add(folders,tab+'_output',title);
  for(const p of document.querySelectorAll('#settings-form p'))if(p.textContent.includes('Giao diện mới, không phải CIT Voice Studio'))p.remove();
  const box=document.createElement('section');box.className='distribution-card';box.innerHTML='<h3>Bản quyền</h3><p id="license-info" role="status">Đang kiểm tra…</p><div class="license-entry"><input id="license-key" type="password" autocomplete="off" aria-label="Key bản quyền" placeholder="Nhập key được cấp"><button type="button" id="license-activate" class="primary">Kích hoạt</button></div><h3>Cập nhật ứng dụng</h3><p class="hint">Luôn kiểm tra khi mở app. Tự tải bản mới đã xác minh; chờ tác vụ xong và lưu dự án trước khi cài.</p><p id="update-info" role="status"></p><button type="button" id="update-check">Kiểm tra ngay</button><button type="button" id="update-download" hidden>Tải lại bộ cài</button><button type="button" id="update-install" hidden>Cài bản mới & mở lại app</button><div id="update-files"></div>';
  document.getElementById('settings-form').append(box);
  const license=async()=>{try{const value=await api('license');document.getElementById('license-info').textContent=value.message+' Mã máy: '+value.machine.slice(0,16);const button=document.getElementById('license-refresh');if(button)button.hidden=!value.configured;}catch(e){toast(e.message,true);}};
  const renew=document.createElement('button');renew.type='button';renew.id='license-refresh';renew.textContent='Gia hạn phiên ngay';document.getElementById('license-activate').after(renew);
  renew.onclick=async()=>{renew.disabled=true;try{await api('license/refresh',{});await license();toast('Đã gia hạn phiên bản quyền.');}catch(e){toast(e.message,true);}finally{renew.disabled=false;}};
  let downloading=false,ready=false;
  const busy=()=>state.jobs.some(j=>['running','queued'].includes(j.status));
  const install=async()=>{if(busy()||sequence.busy)return;try{if(state.dirty)await saveProject();if(sequence.dirty)await seqSave();if(sequence.dirty||sequence.blocked)throw Error('Lưu hoặc xử lý bản nháp editor trước khi cài cập nhật.');const result=await api('update/install',{});document.getElementById('update-info').textContent=result.message;ready=false;}catch(e){document.getElementById('update-info').textContent=e.message;}};
  const download=async()=>{if(downloading||busy())return;downloading=true;try{document.getElementById('update-info').textContent='Đang tải bản mới và kiểm tra SHA256…';const result=await api('update',{});document.getElementById('update-info').textContent=result.message;filesPanel([result.file],document.getElementById('update-files'));ready=true;document.getElementById('update-install').hidden=false;await install();}catch(e){document.getElementById('update-info').textContent=e.message;}finally{downloading=false;}};
  const update=async()=>{try{const result=await api('update');document.getElementById('update-info').textContent=result.message;document.getElementById('update-download').hidden=!result.available;if(result.available&&!ready)await download();}catch(e){document.getElementById('update-info').textContent=e.message;}};
  document.getElementById('settings-open').addEventListener('click',license);
  document.getElementById('license-activate').onclick=async()=>{try{await api('license',{key:document.getElementById('license-key').value});document.getElementById('license-key').value='';await license();}catch(e){document.getElementById('license-info').textContent=e.message;}};
  document.getElementById('update-check').onclick=update;
  document.getElementById('update-download').onclick=download;
  document.getElementById('update-install').onclick=install;
  setTimeout(update,4000);setInterval(update,15*60*1000);
  setInterval(()=>{if(ready&&!busy()&&!document.querySelector('dialog[open]'))install();},30000);
  const style=document.createElement('style');style.textContent='.output-folder-row{display:flex;align-items:center;gap:6px;margin:6px 0;padding:7px 10px;border:1px solid var(--border,#dce5ec);border-radius:10px}.output-folder-row input{flex:1;min-width:80px}.output-folder-row button{white-space:nowrap}.output-folder-row label{font-size:12px}';document.head.append(style);
});

async function openOutputFolder(tab){
  if(tab==='removal'){const jobs=state.jobs.filter(j=>j.ui_tab==='removal'&&j.status==='complete'&&j.result?.files?.length);const result=await api('open-output-folder',{tab:'removal',artifact:jobs[0]?.result.files[0].url||''});toast('Đã mở: '+result.path);return;}
  const project=tab==='edit'?sequence.id:tab==='dub'?state.project?.id:'';
  const jobs=state.jobs.filter(j=>j.status==='complete'&&j.ui_tab===tab&&(!project||j.project_id===project)&&j.result?.files?.length);
  const files=tab==='edit'?(sequence.outputFiles||jobs[0]?.result.files):tab==='dub'?(state.project?.exports?.length?state.project.exports:jobs[0]?.result.files):(ui.results[tab]?.files||jobs[0]?.result.files);
  const result=await api('open-output-folder',{tab,project_id:project||'',artifact:files?.[0]?.url||''});
  toast('Đã mở: '+result.path);
}
