"use strict";
Object.assign(UI_TEXT,{
 'Sao lưu / Khôi phục':['Backup / Restore','备份 / 恢复'],
 'Sao lưu dự án đã chọn':['Back up selected projects','备份所选项目'],
 'Kèm cài đặt':['Include settings','包含设置'],
 'Kèm API key (gói không mã hóa)':['Include API keys (archive is not encrypted)','包含 API 密钥（备份未加密）'],
 'Không kèm model, thư viện, giọng clone, lịch sử job hoặc file render cũ. Tối đa 2 GB mỗi gói.':['Excludes models, libraries, cloned voices, job history and old renders. Up to 2 GB per archive.','不包含模型、组件、克隆声音、任务历史或旧渲染。每份备份最多 2 GB。'],
 '＋ Chọn bản sao lưu':['＋ Select backup','＋ 选择备份'],
 'Thêm thành dự án mới':['Add as new projects','添加为新项目'],
 'Khôi phục cài đặt':['Restore settings','恢复设置'],
 'Khôi phục API key trong gói':['Restore API keys from archive','恢复备份中的 API 密钥'],
 'Khôi phục đã chọn':['Restore selection','恢复所选内容'],
 'Đang xử lý bản sao lưu…':['Processing backup…','正在处理备份…'],
 'Tải bản sao lưu':['Download backup','下载备份'],
 'Không có dự án. Vẫn có thể sao lưu cài đặt.':['No projects. Settings can still be backed up.','没有项目，仍可备份设置。'],
 'Gói không mã hóa. API key có thể bị đọc nếu chia sẻ file. Tiếp tục?':['Archive is not encrypted. Sharing it exposes API keys. Continue?','备份未加密，分享文件会暴露 API 密钥。继续？'],
 'Khôi phục thành dự án mới; không ghi đè dự án hiện có. Cài đặt chỉ thay khi đã tích chọn. Tiếp tục?':['Restore as new projects, without overwriting existing ones. Settings change only if selected. Continue?','恢复为新项目，不覆盖现有项目。仅在勾选时更改设置。继续？'],
 'Đã khôi phục. Tải lại giao diện để dùng dữ liệu mới.':['Restored. Reload the interface to use restored data.','恢复完成。重新加载界面以使用新数据。'],
 'Tải lại giao diện':['Reload interface','重新加载界面'],
 'Đã kiểm tra checksum toàn bộ gói.':['All archive checksums verified.','已验证备份内所有文件的校验值。'],
 'Gói có API key; không chia sẻ file.':['Archive contains API keys; do not share it.','备份包含 API 密钥，请勿分享。'],
 'Cài đặt đường dẫn máy cũ không được khôi phục. Quyền gửi phụ đề qua Internet cần xác nhận lại.':['Old machine paths are not restored. Subtitle network consent must be confirmed again.','不恢复旧机器路径。字幕联网授权需要重新确认。'],
 'Lưu thay đổi đang sửa trước khi sao lưu/khôi phục.':['Save pending edits before backup/restore.','备份或恢复前请保存正在编辑的更改。'],
 'Chọn tất cả':['Select all','全选'],'Bỏ chọn tất cả':['Deselect all','取消全选']
});
document.addEventListener('DOMContentLoaded',()=>{
 const box=element('section','card');box.id='backup-settings';
 box.innerHTML='<h3>Sao lưu / Khôi phục</h3><p class="hint">Không kèm model, thư viện, giọng clone, lịch sử job hoặc file render cũ. Tối đa 2 GB mỗi gói.</p><p class="hint">Lưu thay đổi đang sửa trước khi sao lưu/khôi phục.</p><div class="actions"><button type="button" id="backup-select-all">Chọn tất cả</button><button type="button" id="backup-select-none">Bỏ chọn tất cả</button></div><div id="backup-projects" style="max-height:180px;overflow:auto"></div><label class="check"><input id="backup-settings-check" type="checkbox" checked> Kèm cài đặt</label><label class="check"><input id="backup-keys-check" type="checkbox"> Kèm API key (gói không mã hóa)</label><button type="button" id="backup-create">Sao lưu dự án đã chọn</button><div id="backup-download"></div><hr><label class="button file-button">＋ Chọn bản sao lưu<input id="backup-file" type="file" accept=".rvbackup" hidden></label><div id="backup-inspection"></div><label class="check"><input id="backup-restore-projects" type="checkbox" checked> Thêm thành dự án mới</label><label class="check"><input id="backup-restore-settings" type="checkbox"> Khôi phục cài đặt</label><label class="check"><input id="backup-restore-keys" type="checkbox"> Khôi phục API key trong gói</label><p class="hint">Cài đặt đường dẫn máy cũ không được khôi phục. Quyền gửi phụ đề qua Internet cần xác nhận lại.</p><button type="button" id="backup-restore" disabled>Khôi phục đã chọn</button><p id="backup-status" role="status"></p>';
 $('settings-storage').append(box);
 let asset='',inspection=null,busy=false;
 const render=()=>{
  const list=$('backup-projects');list.replaceChildren();
  for(const p of state.projects){const label=element('label','check'),check=element('input');check.type='checkbox';check.value=p.id;check.checked=true;const name=element('span','',p.name);name.dataset.i18nSkip='';label.append(check,name);list.append(label);}
  if(!state.projects.length)list.append(element('p','hint','Không có dự án. Vẫn có thể sao lưu cài đặt.'));
 };
 $('settings-open').addEventListener('click',render);
 for(const [id,checked] of [['backup-select-all',true],['backup-select-none',false]])$(id).onclick=()=>{for(const input of $('backup-projects').querySelectorAll('input'))input.checked=checked;};
 const run=async action=>{
  if(busy)return;busy=true;
  for(const button of box.querySelectorAll('button,input'))button.disabled=true;
  $('backup-status').textContent=uiText('Đang xử lý bản sao lưu…');
  try{if(state.dirty||sequence.dirty)throw Error(uiText('Lưu thay đổi đang sửa trước khi sao lưu/khôi phục.'));await action();}
  catch(e){$('backup-status').textContent=e.message;toast(e.message,true);}
  finally{busy=false;for(const button of box.querySelectorAll('button,input'))button.disabled=false;$('backup-restore').disabled=!asset;}
 };
 $('backup-create').onclick=()=>{
  const keys=$('backup-keys-check').checked,ids=[...$('backup-projects').querySelectorAll('input:checked')].map(e=>e.value),settings=$('backup-settings-check').checked;
  if(keys&&!confirm(uiText('Gói không mã hóa. API key có thể bị đọc nếu chia sẻ file. Tiếp tục?')))return;
  return run(async()=>{const result=await api('backups/create',{project_ids:ids,include_settings:settings,include_keys:keys});const link=element('a','button',uiText('Tải bản sao lưu'));link.href=result.url;link.download=result.name;$('backup-download').replaceChildren(link);$('backup-status').textContent=result.name;});
 };
 $('backup-file').onchange=()=>{const file=$('backup-file').files[0];if(!file)return;asset='';inspection=null;$('backup-inspection').replaceChildren();return run(async()=>{const uploaded=await upload(file);const result=await api('backups/inspect',{asset_id:uploaded.id});asset=uploaded.id;inspection=result;
  const detail=$('backup-inspection');for(const p of result.projects){const row=element('p','',p.name+' · '+p.cues);row.dataset.i18nSkip='';detail.append(row);}
  detail.append(element('p','hint','Đã kiểm tra checksum toàn bộ gói.'));if(result.include_keys)detail.append(element('p','notice','Gói có API key; không chia sẻ file.'));
  $('backup-restore-settings').checked=false;$('backup-restore-keys').checked=false;$('backup-status').textContent=file.name;
 });};
 $('backup-restore').onclick=()=>{
  if(!asset||!inspection)return;
  const projects=$('backup-restore-projects').checked,settings=$('backup-restore-settings').checked,keys=$('backup-restore-keys').checked;
  if(!confirm(uiText('Khôi phục thành dự án mới; không ghi đè dự án hiện có. Cài đặt chỉ thay khi đã tích chọn. Tiếp tục?')))return;
  if(keys&&inspection.include_keys&&!confirm(uiText('Gói không mã hóa. API key có thể bị đọc nếu chia sẻ file. Tiếp tục?')))return;
  return run(async()=>{await api('backups/restore',{asset_id:asset,projects,settings,keys,confirmed:true});asset='';inspection=null;await poll();if(settings)settingsApplyUI(await api('ui-preferences'));$('backup-status').textContent='Đã khôi phục. Tải lại giao diện để dùng dữ liệu mới.';const reload=element('button','','Tải lại giao diện');reload.type='button';reload.onclick=()=>location.reload();$('backup-inspection').replaceChildren(reload);render();});
 };
});
