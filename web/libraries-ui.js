"use strict";
let librarySignature='';
document.addEventListener('DOMContentLoaded',()=>{
  const panel=element('details','storage-settings');panel.id='optional-libraries';
  panel.innerHTML='<summary>Thư viện tùy chọn · tải theo nhu cầu</summary><p class="hint">Cài riêng, không đưa mọi model vào setup. Đổi nơi cài chỉ áp dụng lần tải mới; không chuyển/xóa bộ cũ. VSR tải bộ portable đầy đủ 1.1.1, không phải Source code 1.4.0.</p><div class="output-folder-row"><input id="libraries-root" aria-label="Thư mục cài thư viện"><button type="button" id="libraries-browse">Chọn…</button><button type="button" id="libraries-save">Lưu</button></div><div id="library-catalog"></div><p id="library-status" role="status"></p><button type="button" id="library-cancel" hidden>Dừng tải/cài</button>';
  $('settings-form').append(panel);
  $('libraries-root').oninput=()=>$('libraries-root').dataset.dirty='1';
  on('libraries-browse','click',async()=>{const r=await api('folder',{});if(r.path){$('libraries-root').value=r.path;$('libraries-root').dataset.dirty='1';}});
  on('libraries-save','click',async()=>{await api('libraries/config',{root:$('libraries-root').value.trim()});delete $('libraries-root').dataset.dirty;toast('Đã lưu nơi cài thư viện.');await refreshLibraries();});
  on('settings-open','click',()=>refreshLibraries().catch(e=>toast(e.message,true)));
});
async function refreshLibraries(){
  if(!$('library-catalog'))return;
  const result=await api('libraries');if(document.activeElement!==$('libraries-root')&&!$('libraries-root').dataset.dirty)$('libraries-root').value=result.root;
  taskNames.library_install='Tải / cài thư viện tùy chọn';
  const sig=JSON.stringify(result.catalog);if(sig!==librarySignature){librarySignature=sig;const list=$('library-catalog');list.replaceChildren();for(const row of result.catalog){const card=element('article','library-card'),meta=element('div','library-meta'),actions=element('div','library-actions');card.dataset.installed=String(row.installed);meta.append(element('strong','',row.title),element('span','library-badge',row.installed?(row.managed?'Đã cài':'Đã kết nối ngoài'):'Chưa cài'),element('p','hint',row.description));if(row.path)meta.append(element('p','library-path',row.path));const button=element('button','',row.installed?'Kiểm tra / tải lại':'Cài thư viện');button.type='button';button.dataset.libraryInstall=row.id;button.onclick=async()=>{try{if(!confirm(row.title+'\n'+row.description+'\nTải qua Internet và cài vào: '+result.root+'?'))return;await startTask('library_install',{library:row.id});await refreshLibraries();}catch(e){toast(e.message,true);}};actions.append(button);if(row.installed){const remove=element('button','library-remove','Gỡ bỏ');remove.type='button';remove.dataset.libraryRemove=row.id;remove.onclick=()=>removeLibraryDialog(row);actions.append(remove);}card.append(meta,actions);list.append(card);}}
  renderLibraryProgress();
  const whisper=result.catalog.find(r=>r.id==='whisper');
  if(whisper?.installed){const meta=document.querySelector('[data-library-install="whisper"]').closest('.library-card').querySelector('.library-meta');let hint=$('whisper-model-installed');if(!hint){hint=element('p','hint');hint.id='whisper-model-installed';meta.append(hint);}hint.textContent=whisper.model===state.settings.whisper_model?'Đang dùng · '+whisper.model:'Model đã cài: '+(whisper.model||'?')+' · đang chọn: '+state.settings.whisper_model+' (cài model này nếu chưa có)';}
  for(const button of $('library-catalog').querySelectorAll('[data-library-install]')){
    if(button.dataset.libraryInstall==='avatar'){
      button.onclick=async()=>{try{
        if(!confirm('Cài/kiểm tra avatar MuseTalk v1.5? Cần NVIDIA, 25 GB trống và thư mục không dấu/khoảng trắng. Sẽ tải runtime/model nhiều GB. Tôi đã đọc giấy phép các thành phần upstream và có quyền sử dụng phù hợp.'))return;
        await startTask('library_install',{library:'avatar',accept_avatar_models:true});await refreshLibraries();
      }catch(e){toast(e.message,true);}};
    }
    const row=result.catalog.find(r=>r.id==='alignment');
    if(row&&button.dataset.libraryInstall==='alignment'){
      button.textContent='Cài CTC + model phi thương mại';
      button.onclick=async()=>{try{if(!confirm('Model MMS dùng CC-BY-NC-4.0: chỉ dùng phi thương mại. Tải vài GB và cài runtime riêng? Với thương mại hãy kết nối model được cấp quyền riêng.'))return;await startTask('library_install',{library:'alignment',accept_noncommercial:true});await refreshLibraries();}catch(e){toast(e.message,true);}};
    }
  }
}
function removeLibraryDialog(row){
 let d=$('library-remove-dialog');if(!d){d=element('dialog');d.id='library-remove-dialog';document.body.append(d);}d.replaceChildren();
 d.append(element('h2','','Gỡ bỏ · '+row.title),element('p','hint',row.managed?'Có thể ngắt kết nối để giữ file, hoặc chọn xóa runtime/model để giải phóng dung lượng. Không xóa dự án/kết quả.':'Đây là bộ kết nối ngoài. Chỉ ngắt kết nối; app không xóa thư mục này.'),element('p','library-path',row.path));
 const label=element('label','check'),erase=element('input');erase.type='checkbox';erase.disabled=!row.managed;label.append(erase,document.createTextNode('Xóa cả runtime/model đã cài · không thể hoàn tác'));d.append(label);
 const remove=makeButton('Gỡ bỏ',async()=>{remove.disabled=true;try{const r=await api('libraries/remove',{library:row.id,delete_files:erase.checked});librarySignature='';await refreshLibraries();await refreshTTSProviders();await poll();toast(r.message);d.close();}finally{remove.disabled=false;}},'primary');remove.type='button';const close=makeButton('Hủy',()=>d.close());close.type='button';d.append(remove,close);d.showModal();
}
function renderLibraryProgress(){
  if(!$('library-status'))return;const job=state.jobs.find(j=>j.kind==='library_install'),busy=job&&['queued','running'].includes(job.status);
  const label=busy?Math.round(job.progress)+'% · '+job.message:job?.status==='error'?'Lần cài trước bị lỗi. Bộ đã nhận diện bên trên vẫn có thể dùng; bấm Kiểm tra để xác minh.':job?.message||'';
  $('library-status').textContent=label;
  let details=$('library-error-detail');if(!details){details=element('details');details.id='library-error-detail';details.append(element('summary','','Chi tiết lỗi lần cài trước'),element('pre'));$('library-status').after(details);}
  details.hidden=job?.status!=='error';details.querySelector('pre').textContent=job?.status==='error'?job.message:'';
  $('library-cancel').hidden=!busy;$('library-cancel').onclick=()=>api('jobs/'+job.id+'/cancel',{});
}
function removalEnhance(){
  const device=element('label','field','Thiết bị · portable 1.1.1');device.innerHTML+=' <select id="vsr-device"><option value="cpu">CPU · ổn định, chậm hơn</option><option value="auto">DirectML / tự chọn của VSR · thử nghiệm</option></select>';$('vsr-mode').closest('label').before(device);
  $('vsr-device').value=removalUI.device||'cpu';
  on('vsr-device','change',()=>{removalUI.device=$('vsr-device').value;removalPersist();});
  const img=element('img');img.id='vsr-poster';img.hidden=true;img.alt='Khung hình gốc để vẽ vùng xóa';$('vsr-video').after(img);
  const actions=$('vsr-home').closest('details').querySelector('.actions');
  const detect=element('button','','Chọn bộ đã giải nén');detect.onclick=async()=>{try{const r=await api('folder',{});const home=r.path||$('vsr-home').value;if(!home)throw Error('Nhập thư mục bộ VSR.');const status=await api('subtitle-removal/detect',{home});$('vsr-home').value=status.home;$('vsr-python').value=status.python;$('vsr-status').textContent=status.message;}catch(e){toast(e.message,true);}};
  const libraries=element('button','','Tải / cài thư viện');libraries.onclick=()=>{$('settings-open').click();settingsChoose('libraries');$('optional-libraries').open=true;};actions.prepend(detect,libraries);
  const settings=element('button','','⚙ Thư mục lưu');settings.onclick=()=>{$('settings-open').click();settingsChoose('storage');const details=$('settings-storage').querySelector('details');details.open=true;document.querySelector('[data-output-setting="removal_output"]').scrollIntoView({block:'center'});};$('vsr-open-folder').before(settings);
  const preview=element('button','','↻ Tạo bản xem WebM');preview.id='vsr-proxy';preview.onclick=()=>removalRequestPreview(false);$('vsr-draw').after(preview);
  const snapshot=element('div','actions');snapshot.innerHTML='<label>Mốc xem (giây) <input id="vsr-snapshot-time" type="number" min="0" step=".1" value="0" style="width:80px"></label><button id="vsr-snapshot">Xem khung hình</button>';$('vsr-source-name').after(snapshot);on('vsr-snapshot','click',()=>removalRequestPreview(true));
  taskNames.removal_preview='Tạo bản xem VSR';
  // WebM conversion is explicitly requested, never automatic for every import.
  $('vsr-video').addEventListener('error',()=>{removalRequestPreview(true).catch(e=>toast(e.message,true));});
  $('vsr-video').addEventListener('loadeddata',()=>{$('vsr-poster').hidden=true;});
  const runtimePanel=$('vsr-home').closest('details');runtimePanel.open=false;
  runtimePanel.querySelector('summary').textContent='VSR · kết nối tự động / tùy chỉnh nâng cao';
}
function removalPosterOnly(){return !!$('vsr-video').canPlayType('video/mp4');}
async function removalRequestPreview(posterOnly=true){
  if(typeof removalEnsureUploaded==='function')await removalEnsureUploaded(removalUI.asset);
  if(!removalUI.asset)throw Error('Chọn video trước.');
  if(posterOnly&&removalUI.preview?.proxy_url){$('vsr-video').currentTime=Number($('vsr-snapshot-time')?.value||0);$('vsr-poster').hidden=true;}
  if(state.jobs.some(j=>j.kind==='removal_preview'&&['running','queued'].includes(j.status)))return;
  await startTask('removal_preview',{asset:removalUI.asset,poster_only:posterOnly,seconds:Number($('vsr-snapshot-time')?.value||0)});
}
function removalApplyPreview(asset,preview){
  if(asset!==removalUI.asset||!preview?.poster_url)return;
  removalUI.preview=preview;const img=$('vsr-poster'),v=$('vsr-video');
  if(img.src!==new URL(preview.poster_url,location.href).href)img.src=preview.poster_url;
  const changed=removalUI.appliedPoster!==preview.poster_url;
  removalUI.appliedPoster=preview.poster_url;
  if(changed)img.hidden=v.readyState>=2;
  if(preview.proxy_url){if(v.getAttribute('src')!==preview.proxy_url){const time=v.currentTime||0,playing=!v.paused;v.src=preview.proxy_url;v.addEventListener('loadedmetadata',()=>{v.currentTime=Math.min(time,v.duration||time);if(playing)v.play().catch(()=>{});},{once:true});}}
  removalOverlayLayout();
}
async function refreshRemovalPreview(){if(removalUI.asset&&!removalUI.asset.startsWith('local-')&&$('vsr-source-image')?.hidden!==false&&$('vsr-poster')){const asset=removalUI.asset,p=await api('subtitle-removal/preview/'+asset);removalApplyPreview(asset,p);}if($('vsr-output-dialog')?.open&&removalUI.outputAsset){const p=await api('subtitle-removal/preview/'+removalUI.outputAsset);removalApplyOutputPreview(p);}}
function removalApplyOutputPreview(preview){const video=$('vsr-output-video');if(!preview.proxy_url||!$('vsr-output-dialog').open)return;if(video.getAttribute('src')!==preview.proxy_url){video.src=preview.proxy_url;video.play().catch(()=>{});}$('vsr-output-status').textContent='Bản xem WebM · file MP4 tải về giữ nguyên.';}
async function removalViewOutput(row){
  $('vsr-video').pause();const video=$('vsr-output-video');removalUI.outputAsset=row.asset;
  video.pause();video.removeAttribute('src');video.load();$('vsr-output-dialog').showModal();
  $('vsr-output-status').textContent='Đang chuẩn bị bản xem tương thích…';
  try{const cached=await api('subtitle-removal/preview/'+row.asset);if(removalUI.outputAsset!==row.asset||!$('vsr-output-dialog').open)return;if(cached.proxy_url){removalApplyOutputPreview(cached);return;}
    if(video.canPlayType('video/mp4')){video.src=row.video.url;video.play().catch(()=>{});$('vsr-output-status').textContent='Bản video đã xử lý.';}
    else await startTask('removal_preview',{asset:row.asset,poster_only:false,seconds:0});
  }catch(e){$('vsr-output-status').textContent=e.message;toast(e.message,true);}
}
