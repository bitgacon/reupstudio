"""Reviewable face-based reframing. Never saves or modifies the original timeline."""
from . import storage, timeline, vision, speed

SIZES={'16:9':(1280,720),'9:16':(720,1280),'1:1':(1080,1080),'4:5':(864,1080)}

def proposal(payload,folder,event,progress):
    project=storage.project(payload['project_id']);doc=timeline.load(project['id'])
    if payload.get('revision')!=doc['revision']:raise ValueError('Timeline đã đổi; lưu rồi chạy lại reframe.')
    ratio=payload.get('ratio')
    if ratio not in SIZES:raise ValueError('Chọn tỷ lệ 16:9, 9:16, 1:1 hoặc 4:5.')
    ids=payload.get('clip_ids')
    if not isinstance(ids,list) or not 1<=len(ids)<=12 or len(set(ids))!=len(ids):raise ValueError('Chọn 1–12 clip để căn lại khung hình.')
    for key in ids:storage.identifier(key)
    clips={c['id']:(t,c) for t in doc['tracks'] for c in t['clips']}
    if set(ids)-set(clips):raise ValueError('Clip được chọn không còn trong timeline.')
    if sum(clips[key][1]['duration_ms'] for key in ids)>240_000:raise ValueError('Một lượt reframe tối đa 4 phút clip được chọn; chia thành nhiều lượt.')
    W,H=SIZES[ratio];target={**doc,'width':W,'height':H};proposals=[];skipped=[]
    for i,key in enumerate(ids):
        if event.is_set():raise InterruptedError('Đã dừng reframe; timeline gốc không thay đổi.')
        track,clip=clips[key];reason=''
        if track['kind']!='video' or not clip['asset']:reason='Không phải clip hình/video.'
        elif track['locked'] or track['hidden']:reason='Track khóa/ẩn; giữ nguyên.'
        elif clip['duration_ms']>60_000:reason='Clip dài hơn 60s; chia clip trước.'
        elif clip['flip_h'] or clip['flip_v'] or clip['transition_in']!='none':reason='Có lật/chuyển cảnh; bỏ trước khi căn mặt.'
        if reason:skipped.append({'clip_id':key,'label':clip['label'],'reason':reason});continue
        source,_=storage.project_asset(project,clip['asset']);item=timeline.describe(project,clip['asset'])
        n=min(63,max(1,(clip['duration_ms']+999)//1000))
        samples=[{'ms':round(clip['duration_ms']*j/n),'source_ms':clip['in_ms']+speed.source_ms(clip,min(round(clip['duration_ms']*j/n),clip['duration_ms']-1))} for j in range(n+1)]
        result=vision.run({'kind':'face','source':str(source),'samples':samples,'image':item['kind']=='image'},folder/key,event,lambda p,m:progress((i*100+p)/len(ids),f'{i+1}/{len(ids)} · '+m))
        try:layout=vision.face_keys(clip,target,item,result['rows'])
        except ValueError as exc:skipped.append({'clip_id':key,'label':clip['label'],'reason':str(exc)});continue
        layout['x']=layout['keyframes'][0]['x'];layout['y']=layout['keyframes'][0]['y']
        layout['opacity']=clip['opacity']
        timeline.Clip.model_validate({**clip,**{k:v for k,v in layout.items() if k not in {'detected_samples','total_samples'}}})
        proposals.append({'clip_id':key,'label':clip['label'],'layout':layout,'replaces_motion':bool(clip['keyframes'] or clip['rotation'] or clip['scale']!=1)})
    result={'project_id':project['id'],'revision':doc['revision'],'ratio':ratio,'width':W,'height':H,'proposals':proposals,'skipped':skipped,'message':'Đề xuất theo mặt mẫu ~1s; duyệt crop trước khi lưu. Chưa nhận diện người nói; các lớp chữ/logo/vùng mờ giữ tọa độ %.'}
    storage.atomic_json(folder/'reframe-proposal.json',result)
    return result
