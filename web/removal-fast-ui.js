"use strict";
const removalLightModes=['fast-delogo','telea','navier-stokes','smooth','blur','mosaic','solid','crop','logo'];
const removalBatch={sources:[],scope:'shared',shared:[],overrides:{}};
const removalLocalFiles=new Map();
function removalImportFiles(files){
 const supported=files.filter(f=>/\.(mp4|mov|mkv|avi|webm|png|jpe?g|webp)$/i.test(f.name));
 if(removalBatch.sources.length+supported.length>1000){toast('Danh sách tối đa 1000 file; xử lý tối đa 20 file mỗi lượt.',true);return;}
 for(const file of supported){const asset='local-'+crypto.randomUUID(),url=URL.createObjectURL(file);removalLocalFiles.set(asset,file);removalBatch.sources.push({asset,url,name:file.webkitRelativePath||file.name,checked:false});}
 removalBatchList();if(supported.length){const row=removalBatch.sources[removalBatch.sources.length-supported.length];removalUseSource(row.asset,row.url,row.name);}
 if(!supported.length)toast('Chọn ảnh PNG/JPG/WebP hoặc video MP4/MOV/MKV/AVI/WebM.',true);
}
async function removalEnsureUploaded(id){
 const file=removalLocalFiles.get(id);if(!file)return id;
 const row=removalBatch.sources.find(r=>r.asset===id);if(!row)throw Error('File đã bị bỏ khỏi danh sách.');
 if(!row.uploadPromise)row.uploadPromise=upload(file).catch(e=>{delete row.uploadPromise;throw e;});
 const result=await row.uploadPromise;if(row.asset!==id)return row.asset;
 row.asset=result.id;row.url=result.url||('/files/uploads/'+result.id+'/'+result.file);
 if(removalBatch.overrides[id]){removalBatch.overrides[result.id]=removalBatch.overrides[id];delete removalBatch.overrides[id];}
 if(removalUI.asset===id){removalUI.asset=result.id;if($('vsr-source-image')?.hidden===false)$('vsr-source-image').src=row.url;removalPersist();}
 removalLocalFiles.delete(id);removalBatchRemember();return result.id;
}
function removalEffectPayload(){return {asset:removalUI.asset,regions:removalUI.regions.map(r=>({...r})),mode:$('vsr-mode').value,margin:Number($('vsr-margin').value),radius:Number($('vsr-radius').value),keep_audio:$('vsr-keep-audio').checked,logo_asset:removalBatch.logo||'',seconds:Number($('vsr-snapshot-time').value||0)};}
function removalEffectSignature(){return JSON.stringify(removalEffectPayload());}
function removalShowEffect(result){
 if(result.asset!==removalUI.asset||result.signature!==removalEffectSignature())return;
 const img=$('vsr-effect-result');img.src=result.picture.url;img.hidden=false;$('vsr-video').pause();$('vsr-regions').hidden=true;
 $('vsr-effect-status').textContent='Kết quả tại mốc đã chọn · ảnh thật, không phải video chuyển động';
}
function removalShowOriginal(){if($('vsr-effect-result'))$('vsr-effect-result').hidden=true;$('vsr-regions').hidden=false;}
function removalBatchRemember(){
 if(removalUI.asset){const regions=removalUI.regions.map(r=>({...r}));if(removalBatch.scope==='shared')removalBatch.shared=regions;else removalBatch.overrides[removalUI.asset]=regions;}
 const current=removalBatch.sources.find(r=>r.asset===removalUI.asset);if(current)current.subtitle=removalUI.subtitle;
 localStorage.setItem('rv-vsr-batch',JSON.stringify({...removalBatch,sources:removalBatch.sources.filter(r=>!removalLocalFiles.has(r.asset)).map(({uploadPromise,...r})=>r)}));
}
function removalBatchList(){
 const list=$('vsr-batch-list');list.replaceChildren();
 for(const id of ['vsr-select-all','vsr-deselect-all'])if($(id))$(id).disabled=!removalBatch.sources.length;
 for(const row of removalBatch.sources){const line=element('div','actions'),check=element('input');check.type='checkbox';check.checked=row.checked!==false;check.onchange=()=>{row.checked=check.checked;removalBatchRemember();};
  const button=element('button','',row.name);button.dataset.i18nSkip='';button.onclick=()=>removalUseSource(row.asset,row.url,row.name,row.subtitle||'');
  const del=element('button','','×');del.title='Xóa khỏi danh sách';del.onclick=()=>{removalBatch.sources=removalBatch.sources.filter(r=>r!==row);removalBatchRemember();removalBatchList();};line.append(check,button,del);list.append(line);
 }
}
function setupFastRemoval(){
 taskNames.removal_effect_preview='Xem kết quả xóa nhẹ';
 taskNames.subtitle_remove='Xóa phụ đề / logo';$('page-removal').querySelector('h1').textContent='Xóa phụ đề / logo';
 const select=$('vsr-mode');for(const [value,title] of [['crop','Cắt khung · giữ vùng đã vẽ'],['logo','Chèn logo mới'],['solid','Tô đen'],['mosaic','Mosaic · ô vuông'],['blur','Che mờ'],['smooth','Telea + làm mịn · không phải AI'],['navier-stokes','Navier–Stokes · tái tạo nhẹ'],['telea','Telea · tái tạo nhẹ'],['fast-delogo','Nhanh · FFmpeg delogo']]){const option=element('option','',title);option.value=value;select.prepend(option);}
 select.querySelector('option[value="opencv"]')?.remove();
 const source=$('vsr-source');source.accept='.mp4,.mov,.mkv,.avi,.webm,.png,.jpg,.jpeg,.webp';source.parentElement.firstChild.textContent='＋ Ảnh / video';
 const folder=element('label','button file-button','＋ Thư mục'),folderInput=element('input');folderInput.type='file';folderInput.multiple=true;folderInput.setAttribute('webkitdirectory','');folderInput.hidden=true;folderInput.onchange=()=>{removalImportFiles([...folderInput.files]);folderInput.value='';};folder.append(folderInput);source.parentElement.after(folder);
 const sourceImage=element('img');sourceImage.id='vsr-source-image';sourceImage.hidden=true;sourceImage.alt='Ảnh nguồn';sourceImage.style.cssText='width:100%;height:320px;object-fit:contain';sourceImage.onload=removalOverlayLayout;$('vsr-video').after(sourceImage);
 const controls=element('div','vsr-light-controls');controls.innerHTML='<div class="actions"><label class="field">Nới vùng (px)<input id="vsr-margin" type="number" min="0" max="64" step="1" value="3"></label><label class="field">Bán kính tái tạo<input id="vsr-radius" type="number" min="1" max="32" step="1" value="6"></label></div><label class="check"><input id="vsr-keep-audio" type="checkbox" checked> Giữ âm thanh gốc</label><label class="check"><input id="vsr-skip-existing" type="checkbox" checked> Bỏ qua kết quả cùng nguồn và cấu hình</label><p class="hint">FFmpeg chạy ngay, không cần VSR. Telea / Navier–Stokes cần OpenCV nhẹ; không tải model AI. Bán kính dùng cho tái tạo/che mờ; nới vùng tính theo pixel nguồn.</p>';
 select.closest('label').after(controls);
 controls.append(element('p','hint','Telea / Navier–Stokes là nội suy nền lân cận: có thể nhòe, không khôi phục chi tiết bị che và rất chậm với video CPU. Thử Xem kết quả tại mốc trước; dùng VSR AI khi cần tái tạo nền phức tạp.'));
 const logo=element('label','button file-button','＋ Ảnh logo');const file=element('input');file.type='file';file.accept='.png,.jpg,.jpeg,.webp';file.hidden=true;file.onchange=async()=>{try{if(!file.files[0])return;removalBatch.logo=(await upload(file.files[0])).id;select.value='logo';removalPersist();toast('Đã chọn logo.');}catch(e){toast(e.message,true);}finally{file.value='';}};logo.append(file);controls.append(logo,element('p','hint','Cắt khung: một vùng GIỮ LẠI, không phải vùng xóa. Logo giữ tỷ lệ ảnh, nằm trong vùng đã vẽ. Nới vùng không áp dụng cho cắt / logo.'));
 const install=element('button','','Cài OpenCV nhẹ');install.onclick=()=>{$('settings-open').click();settingsChoose('libraries');};controls.append(install);
 const reset=seqButton('Xóa tất cả vùng',()=>{removalUI.regions=[];removalRenderRegions();});$('vsr-sub-band').after(reset);
 const picture=element('img');picture.id='vsr-effect-result';picture.hidden=true;picture.alt='Kết quả xóa nhẹ';$('vsr-regions').before(picture);
 const actions=element('div','actions');actions.append(seqButton('Xem gốc',removalShowOriginal),seqButton('Xem kết quả tại mốc',async()=>{
  await removalEnsureUploaded(removalUI.asset);const payload=removalEffectPayload();if(!payload.asset||!payload.regions.length)throw Error('Chọn ảnh/video và vẽ vùng trước.');
  if(!removalLightModes.includes(payload.mode))throw Error('Xem nhanh tại mốc chỉ hỗ trợ chế độ xóa nhẹ; AI VSR cần xử lý đoạn thử.');
  await startTask('removal_effect_preview',{...payload,signature:JSON.stringify(payload)});
 }));const status=element('p','hint');status.id='vsr-effect-status';$('vsr-source-name').before(actions,status);
 const batch=element('details','card');batch.innerHTML='<summary>Video hàng loạt · tối đa 20 tác vụ</summary><label class="field">Vùng này áp cho<select id="vsr-batch-scope"><option value="shared">Tất cả video · co giãn theo tỷ lệ</option><option value="individual">Riêng từng video</option><option value="mixed">Dùng chung, video có vùng riêng ghi đè</option></select></label><div class="actions"><button type="button" id="vsr-select-all">Chọn tất cả</button><button type="button" id="vsr-deselect-all">Bỏ chọn tất cả</button></div><div id="vsr-batch-list"></div><button id="vsr-batch-start" class="primary wide">Xử lý video đã tích</button><p class="hint">Chọn nhiều video bằng nút + Video. Các tác vụ chạy tuần tự; nguồn giữ nguyên. Mỗi video có SRT riêng nếu dùng Whisper.</p>';$('vsr-region-list').after(batch);
 const selectAll=checked=>{for(const row of removalBatch.sources)row.checked=checked;removalBatchRemember();removalBatchList();};
 $('vsr-select-all').onclick=()=>selectAll(true);$('vsr-deselect-all').onclick=()=>selectAll(false);
 try{const saved=JSON.parse(localStorage.getItem('rv-vsr')||'{}');select.value=saved.mode==='opencv'?'telea':saved.mode||'fast-delogo';if(!select.value)select.value='fast-delogo';for(const key of ['margin','radius'])if(saved[key]!==undefined)$('vsr-'+key).value=saved[key];$('vsr-keep-audio').checked=saved.keepAudio!==false;$('vsr-skip-existing').checked=saved.skipExisting!==false;const b=JSON.parse(localStorage.getItem('rv-vsr-batch')||'{}');if(Array.isArray(b.sources))removalBatch.sources=b.sources.slice(0,1000);removalBatch.logo=b.logo||'';removalBatch.overrides=b.overrides||{};removalBatch.shared=b.shared||[];removalBatch.scope=['shared','individual','mixed'].includes(b.scope)?b.scope:'shared';}catch{}
 const persist=removalPersist;removalPersist=function(){persist();if($('vsr-margin')){removalShowOriginal();const saved=JSON.parse(localStorage.getItem('rv-vsr')||'{}');Object.assign(saved,{margin:Number($('vsr-margin').value),radius:Number($('vsr-radius').value),keepAudio:$('vsr-keep-audio').checked,skipExisting:$('vsr-skip-existing').checked});if(removalLocalFiles.has(saved.asset)){delete saved.asset;delete saved.url;}else if(saved.url?.startsWith('blob:')){const row=removalBatch.sources.find(r=>r.asset===saved.asset);saved.url=row?.url||'';}localStorage.setItem('rv-vsr',JSON.stringify(saved));removalBatchRemember();}};
 const original=removalUseSource;removalUseSource=function(asset,url,name,subtitle=''){
  removalBatchRemember();if(!removalBatch.sources.some(r=>r.asset===asset))removalBatch.sources.push({asset,url,name,subtitle,checked:true});
  const regions=(removalBatch.scope==='shared'?removalBatch.shared:removalBatch.overrides[asset]||(removalBatch.scope==='mixed'?removalBatch.shared:[])).map(r=>({...r}));
  original(asset,url,name,subtitle);removalShowOriginal();removalUI.regions=regions;removalRenderRegions();removalBatchList();
 };
 $('vsr-batch-scope').value=removalBatch.scope;
 if(removalUI.asset&&!removalBatch.sources.some(r=>r.asset===removalUI.asset))removalBatch.sources.push({asset:removalUI.asset,url:$('vsr-video').getAttribute('src'),name:removalUI.sourceName,subtitle:removalUI.subtitle,checked:true});
 if(!removalBatch.shared.length)removalBatch.shared=removalUI.regions.map(r=>({...r}));removalBatchList();
 if(removalUI.asset&&/\.(png|jpe?g|webp)$/i.test(removalUI.sourceName)){const row=removalBatch.sources.find(r=>r.asset===removalUI.asset);if(row){const regions=removalUI.regions;removalUseSource(row.asset,row.url,row.name,row.subtitle||'');removalUI.regions=regions;removalRenderRegions();}}
 on('vsr-batch-scope','change',()=>{removalBatchRemember();removalBatch.scope=$('vsr-batch-scope').value;removalUI.regions=(removalBatch.overrides[removalUI.asset]||removalBatch.shared).map(r=>({...r}));removalRenderRegions();});
 for(const id of ['vsr-margin','vsr-radius','vsr-keep-audio','vsr-skip-existing'])on(id,'change',()=>{removalShowOriginal();removalPersist();});
 on('vsr-mode','change',()=>{removalShowOriginal();removalPersist();});on('vsr-draw','click',removalShowOriginal);
 on('vsr-snapshot-time','change',removalShowOriginal);
 $('vsr-video').addEventListener('playing',removalShowOriginal);
 const payloadFor=row=>({...removalEffectPayload(),asset:row.asset,regions:(removalBatch.scope==='shared'?removalBatch.shared:removalBatch.overrides[row.asset]||(removalBatch.scope==='mixed'?removalBatch.shared:[])).map(r=>({...r})),subtitle_mode:/\.(png|jpe?g|webp)$/i.test(row.name||removalUI.sourceName)?'none':$('vsr-sub-mode').value,subtitle_asset:row.asset===removalUI.asset?removalUI.subtitle:row.subtitle||'',language:$('vsr-language').value,allow_download:$('vsr-whisper-download').checked,device:$('vsr-device').value,skip_existing:$('vsr-skip-existing').checked});
 $('vsr-start').onclick=()=>Promise.resolve().then(async()=>{removalBatchRemember();await removalEnsureUploaded(removalUI.asset);const p=payloadFor({asset:removalUI.asset,subtitle:removalUI.subtitle});if(!p.asset||!p.regions.length)throw Error('Chọn ảnh/video và vẽ vùng trước.');return startTask('subtitle_remove',p);}).catch(e=>toast(e.message,true));
 $('vsr-batch-start').onclick=async()=>{try{removalBatchRemember();const rows=removalBatch.sources.filter(r=>r.checked!==false),busy=state.jobs.filter(j=>['queued','running'].includes(j.status)).length;if(!rows.length||rows.length+busy>20)throw Error('Chọn ảnh/video; hàng đợi tối đa 20 tác vụ.');const payloads=rows.map(payloadFor);if(payloads.some(p=>!p.regions.length||p.subtitle_mode==='import'&&!p.subtitle_asset))throw Error('Mỗi file cần vùng xóa và SRT nếu chọn nhập SRT.');if(!confirm('Đưa '+rows.length+' file vào hàng đợi xóa?'))return;let count=0;for(let i=0;i<rows.length;i++){payloads[i].asset=await removalEnsureUploaded(rows[i].asset);await startTask('subtitle_remove',payloads[i]);count++;}toast('Đã đưa '+count+' file vào hàng đợi.');}catch(e){toast(e.message,true);}};
 batch.querySelector('summary').textContent='Ảnh / video hàng loạt · tối đa 20 tác vụ';$('vsr-batch-start').textContent='Xử lý file đã tích';batch.querySelector('.hint').textContent='Thêm file hoặc cả thư mục (kể cả thư mục con), bấm tên để xem, tích file cần xử lý. File mới chỉ tải vào dữ liệu khi xử lý/xem kết quả; chưa tải thì cần chọn lại sau khi mở app. Ảnh xuất PNG riêng; nguồn giữ nguyên.';
 // Keep runtime configuration in Settings, while retaining existing handlers/IDs.
 const runtime=$('vsr-home').closest('details');runtime.id='vsr-runtime-settings';runtime.open=false;$('settings-libraries').append(runtime);
 runtime.append($('vsr-device').closest('label'));
 controls.querySelector('button')?.remove();
 tabTitles.removal='Xóa logo/phụ đề';taskNames.subtitle_remove='Xóa phụ đề/logo';
 document.querySelector('.tabs [data-tab="removal"]').textContent='▧ Xóa logo/phụ đề';$('page-removal').querySelector('h1').textContent='Xóa logo/phụ đề';$('vsr-start').textContent='▶ Xóa phụ đề/logo';$('download-send-vsr').textContent='→ Xóa logo/phụ đề';
 $('vsr-results').closest('article').querySelector('h3').textContent='Kết quả';$('vsr-saved-subtitles').closest('article').querySelector('h3').textContent='SRT đã lưu';
 const help=element('details','card');help.append(element('summary','','Hướng dẫn'));
 for(const note of [...$('page-removal').querySelectorAll('p.hint:not([id])')]){if(note.textContent.length>80)help.append(note);}
 $('page-removal').querySelector('.vsr-controls').append(help);
 $('vsr-sub-mode').closest('details').querySelector('summary').textContent='1. Phụ đề gốc (tùy chọn)';select.closest('details').querySelector('summary').textContent='2. Xóa vùng đã chọn';
}
