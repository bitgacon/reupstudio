"use strict";
function seqReframeProposal(doc,result,ids){
  if(doc.revision!==result.revision)throw Error('Timeline đã đổi; dò lại để không dùng bố cục cũ.');
  if(!Number.isInteger(result.width)||!Number.isInteger(result.height)||result.width<128||result.height<128||result.width>3840||result.height>3840)throw Error('Kích thước đề xuất không hợp lệ.');
  const selected=new Set(ids);if(!selected.size)throw Error('Tích chọn ít nhất một clip đã dò được mặt.');
  const next=seqCopy(doc),known=new Set();
  for(const row of result.proposals){if(!selected.has(row.clip_id))continue;
    const t=next.tracks.find(t=>t.clips.some(c=>c.id===row.clip_id)),c=t?.clips.find(c=>c.id===row.clip_id);
    if(!c||t.kind!=='video'||t.locked||t.hidden)throw Error('Clip mất/khóa/ẩn; chưa áp dụng.');
    if(known.has(c.id))throw Error('Trùng clip trong đề xuất.');known.add(c.id);
    const layout=row.layout;
    for(const key of ['x','y','scale','rotation','opacity','fit','motion_easing','keyframes']){
      if(layout[key]===undefined)throw Error('Thiếu dữ liệu bố cục.');c[key]=seqCopy(layout[key]);
    }
    if(!Array.isArray(c.keyframes)||c.keyframes.length<2||c.keyframes.length>64||c.keyframes[0].ms!==0||c.keyframes.at(-1).ms!==c.duration_ms)throw Error('Mốc căn mặt không khớp thời lượng clip.');
  }
  if(known.size!==selected.size)throw Error('Clip không có đề xuất hợp lệ.');
  next.width=result.width;next.height=result.height;return next;
}
async function seqReframe(ratio){
  seqRequire();const ids=seqSelectedIds();if(!ids.length)throw Error('Chọn clip nguồn trước; Ctrl+click để chọn nhiều clip.');
  if(!confirm('Dò mặt cho clip đã chọn rồi duyệt khung '+ratio+'? CPU riêng; mỗi clip ≤60s, tối đa 12 clip/4 phút mỗi lượt. Bố cục cũ chỉ thay khi bạn áp dụng.'))return;
  const project=sequence.id,result=await seqStudioJob('reframe',{ratio,clip_ids:ids});
  if(project!==sequence.id||result.revision!==sequence.doc.revision)throw Error('Timeline đã đổi; kết quả nằm trong Lịch sử.');
  const d=seqToolDialog('Duyệt căn khung thông minh · '+ratio),choices=[];
  d.dataset.mode='reframe';d.append(element('p','hint','Thay canvas và bố cục các clip được tích; thời gian, audio và nguồn giữ nguyên. Chữ/logo/vùng mờ giữ tọa độ %. Có Hoàn tác. Nhiều người/đổi cảnh có thể chọn nhầm mặt; xem đầu/giữa/cuối trước khi xuất.'));
  for(const row of result.proposals){const label=element('label','reframe-choice'),input=element('input');input.type='checkbox';input.checked=true;input.value=row.clip_id;label.append(input,element('span','',`${row.label||'Clip'} · thấy mặt ${row.layout.detected_samples}/${row.layout.total_samples} mẫu${row.replaces_motion?' · thay chuyển động/zoom/xoay hiện có':''}`));d.append(label);choices.push(input);}
  for(const row of result.skipped)d.append(element('p','hint','Giữ nguyên: '+(row.label||'Clip')+' · '+row.reason));
  if(!choices.length){d.append(element('p','notice','Không có clip đủ điều kiện; canvas/timeline chưa thay đổi.'));return;}
  const before=seqCopy(sequence.doc),oldTime=sequence.time;let previewed=false,kept=false;
  sequence.busy=true;clearTimeout(sequence.timer);seqControls();
  const restore=()=>{if(previewed&&!kept&&project===sequence.id){seqPause();sequence.doc=seqCopy(before);sequence.time=oldTime;sequence.rendered=null;seqClearMonitor();seqRefresh();previewed=false;}};
  d.addEventListener('close',()=>{restore();sequence.busy=false;seqControls();if(sequence.dirty)seqScheduleSave();},{once:true});
  d.append(seqButton('Xem thử realtime · chưa lưu',()=>{if(project!==sequence.id||sequence.doc.revision!==result.revision)throw Error('Timeline đã đổi.');seqPause();sequence.doc=seqReframeProposal(before,result,choices.filter(i=>i.checked).map(i=>i.value));previewed=true;sequence.rendered=null;seqClearMonitor();seqRefresh();toast('Đang xem bố cục đề xuất. Bấm Áp dụng để giữ hoặc Đóng để trở lại.');}),seqButton('Áp dụng · có Hoàn tác',()=>{if(project!==sequence.id||sequence.doc.revision!==result.revision)throw Error('Timeline đã đổi.');const next=seqReframeProposal(before,result,choices.filter(i=>i.checked).map(i=>i.value));restore();sequence.busy=false;seqChange(()=>sequence.doc=next);kept=true;d.close();toast('Đã áp dụng khung '+ratio+'. Xem lại chữ/logo/vùng mờ trước khi xuất.');}));
}
function seqSetupReframe(panel){
  const group=element('details','seq-property-group');group.id='seq-smart-reframe';group.append(element('summary','','Căn khung thông minh · theo mặt'));
  const ratio=element('select');ratio.id='seq-reframe-ratio';for(const v of ['9:16','1:1','16:9','4:5']){const o=element('option','',v);o.value=v;ratio.append(o);}
  group.append(element('small','hint','Chọn một/nhiều clip nguồn. Dò → duyệt → xem thử → áp dụng. Không tự nhận diện người nói; mỗi clip tối đa 60s.'),ratio,seqButton('Dò & duyệt khung mới…',()=>seqReframe(ratio.value)));panel.append(group);
}
