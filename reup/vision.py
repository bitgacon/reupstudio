"""Optional visual AI in a separate runtime; never import ONNX/OpenCV in UI."""
import os
import subprocess
import time
from pathlib import Path
from . import media, storage, timeline, speed

def run(request, folder, event, progress):
    if event.is_set():raise InterruptedError('Đã dừng AI hình.')
    from .libraries import installed_path
    runtime=installed_path('vision',storage.ROOT/'vision-env')
    python=runtime/'Scripts'/'python.exe'
    if not python.is_file():raise ValueError('Chưa cài AI hình. Vào Cài đặt → Thư viện → AI hình để tải/cài.')
    folder.mkdir(parents=True,exist_ok=True)
    request={**request,'ffmpeg':media.binary(),'folder':str(folder)}
    storage.atomic_json(folder/'request.json',request)
    env={**os.environ,'PYTHONUTF8':'1','PYTHONUNBUFFERED':'1','U2NET_HOME':str(runtime/'models') if runtime!=storage.ROOT/'vision-env' else str(storage.ROOT/'vision-models')}
    with (folder/'vision.log').open('w',encoding='utf-8') as log:
        proc=subprocess.Popen([str(python),str(storage.ROOT/'VISION_WORKER.py'),str(folder/'request.json')],env=env,stdout=log,stderr=subprocess.STDOUT,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
        start=time.monotonic();last=None;reported=0
        try:
            while proc.poll() is None:
                if event.wait(.5):raise InterruptedError('Đã dừng AI hình; nguồn giữ nguyên.')
                if time.monotonic()-start>7200:raise RuntimeError('AI hình quá 2 giờ; dùng đoạn ngắn hơn.')
                status=storage.read_json(folder/'progress.json',{})
                if status!=last or time.monotonic()-reported>10:
                    progress(min(95,status.get('percent',5)),status.get('message','Đang khởi động AI hình trên CPU…'))
                    last=status;reported=time.monotonic()
            if proc.returncode:raise RuntimeError('AI hình thất bại: '+(folder/'vision.log').read_text(encoding='utf-8',errors='replace')[-1800:])
        finally:media.stop_owned_process(proc)
    if event.is_set():raise InterruptedError('Đã dừng AI hình.')
    return storage.read_json(folder/'result.json',{})

def clip_request(payload):
    project=storage.project(payload['project_id']);doc=timeline.load(project['id'])
    if payload.get('revision')!=doc['revision']:raise ValueError('Timeline đã đổi; lưu rồi chạy AI lại.')
    found=next(((t,c) for t in doc['tracks'] for c in t['clips'] if c['id']==payload.get('clip_id')),None)
    if not found or found[0]['kind']!='video' or found[0]['locked']:raise ValueError('Chọn clip hình/video trên track chưa khóa.')
    clip=found[1];source,_=storage.project_asset(project,clip['asset']);item=timeline.describe(project,clip['asset'])
    return project,doc,clip,source,item

def face_keys(clip,doc,item,rows):
    # Contain + cover-equivalent zoom retains uncropped source for recentering.
    w,h=item['width'],item['height'];W,H=doc['width'],doc['height']
    zoom=max(W/w,H/h)/min(W/w,H/h)
    if zoom>4:raise ValueError('Tỷ lệ cần zoom hơn 4×; đổi canvas gần tỷ lệ nguồn hơn.')
    iw=w*max(W/w,H/h);ih=h*max(W/w,H/h)
    clamp=lambda v,lo,hi:max(lo,min(hi,v))
    keys=[];center=(.5,.5);hits=0
    for row in rows:
        if row.get('face'):
            cx,cy=row['face'];hits+=1
            # Low-pass detected centers, hold previous center on missed samples.
            center=(cx,cy) if hits==1 else (.65*center[0]+.35*cx,.65*center[1]+.35*cy)
        x=clamp(50+(.5-center[0])*iw/W*100,max(-100,100-iw/W*50),min(200,iw/W*50))
        y=clamp(50+(.5-center[1])*ih/H*100,max(-100,100-ih/H*50),min(200,ih/H*50))
        keys.append({'ms':row['ms'],'x':x,'y':y,'scale':zoom,'rotation':0,'opacity':clip['opacity']})
    if not hits:raise ValueError('Không tìm được khuôn mặt; bố cục hiện tại không thay đổi.')
    return {'keyframes':keys,'fit':'contain','scale':zoom,'rotation':0,'motion_easing':'linear','detected_samples':hits,'total_samples':len(rows)}

def tracking(payload,folder,event,progress):
    project,doc,clip,source,item=clip_request(payload)
    if clip['duration_ms']>60_000:raise ValueError('Tracking CPU hỗ trợ clip tối đa 60s mỗi lần; chia clip trước.')
    if clip['flip_h'] or clip['flip_v'] or clip['transition_in']!='none':raise ValueError('Bỏ lật/chuyển cảnh trước khi căn mặt.')
    n=min(63,max(1,(clip['duration_ms']+999)//1000))
    times=[round(clip['duration_ms']*i/n) for i in range(n+1)]
    samples=[{'ms':ms,'source_ms':clip['in_ms']+speed.source_ms(clip,min(ms,clip['duration_ms']-1))} for ms in times]
    result=run({'kind':'face','source':str(source),'samples':samples,'image':item['kind']=='image'},folder,event,progress)
    return {'project_id':project['id'],'clip_id':clip['id'],'revision':doc['revision'],'proposal':face_keys(clip,doc,item,result['rows']),'message':'Căn mặt theo mẫu ~1s: duyệt rồi áp dụng, không nhận diện danh tính.'}

def background(payload,folder,event,progress):
    project,doc,clip,source,item=clip_request(payload)
    span=speed.source_ms(clip,clip['duration_ms'])/1000
    if item['kind']!='image' and span<.25:raise ValueError('Đoạn nguồn tách nền video cần ít nhất 0,25s.')
    if item['kind']!='image' and span>15:raise ValueError('Tách nền video CPU tối đa 15s nguồn mỗi lần; chia/trim clip trước.')
    result=run({'kind':'background','source':str(source),'image':item['kind']=='image','start':clip['in_ms']/1000,'seconds':span},folder,event,progress)
    output=folder/result['file']
    if output.parent!=folder or not output.is_file():raise RuntimeError('Thiếu kết quả AI hình.')
    return project,output

def object_tracking(payload,folder,event,progress):
    import math
    project,doc,c,source,item=clip_request(payload)
    if item['kind']!='video' or c['keyframes'] or c['rotation'] or c['flip_h'] or c['flip_v'] or c['transition_in']!='none':raise ValueError('Tracking vùng cần video không xoay/lật/mốc chuyển động/chuyển cảnh.')
    start=int(payload.get('at_ms',c['start_ms']))-c['start_ms'];remaining=c['duration_ms']-start
    if start<0 or not 250<=remaining<=12_000:raise ValueError('Con trỏ trong clip; đoạn còn lại 0,25–12s. Chia clip để bám từng đoạn.')
    region=payload.get('region',{});values=[float(region.get(k,float('nan'))) for k in ('x','y','region_w','region_h')]
    if any(not math.isfinite(v) for v in values) or not all(1<=v<=100 for v in values[2:]):raise ValueError('Vùng chọn không hợp lệ.')
    W,H=doc['width'],doc['height'];w,h=item['width'],item['height'];factor=(max(W/w,H/h) if c['fit']=='cover' else min(W/w,H/h))*c['scale'];sw,sh=w*factor,h*factor;left=W*c['x']/100-sw/2;top=H*c['y']/100-sh/2
    x,y,rw,rh=values;box=[((x-rw/2)*W/100-left)/sw,((y-rh/2)*H/100-top)/sh,rw*W/100/sw,rh*H/100/sh]
    if box[0]<0 or box[1]<0 or box[0]+box[2]>1 or box[1]+box[3]>1:raise ValueError('Vùng chọn phải nằm hoàn toàn trong hình nguồn.')
    n=min(63,max(1,round(remaining/200)));samples=[{'ms':round(remaining*i/n),'source_ms':c['in_ms']+speed.source_ms(c,start+min(remaining-min(100,remaining//4),round(remaining*i/n)))} for i in range(n+1)]
    reidentify=payload.get('reidentify') is True
    from .advanced_ai import config
    model=config()['reid_model'] if reidentify else ''
    if model and not Path(model).is_file():raise ValueError('Model ReID ONNX đã chọn không tồn tại; kết nối lại hoặc bỏ model để dùng tái tìm mẫu.')
    result=run({'kind':'reidentify' if reidentify else 'object','source':str(source),'samples':samples,'box':box,'reid_model':model},folder,event,progress)
    keys=[{'ms':r['ms'],'x':(left+r['center'][0]*sw)/W*100,'y':(top+r['center'][1]*sh)/H*100} for r in result['rows']]
    if any(not 0<=r['x']<=100 or not 0<=r['y']<=100 for r in keys):raise ValueError('Vật thể ra ngoài canvas; dùng đoạn ngắn hơn.')
    duration=result.get('duration_ms',remaining)
    if not 100<=duration<=remaining:raise ValueError('Thời lượng tracking không hợp lệ.')
    segments=[{'start':s['start'],'end':s['end'],'keyframes':[{'ms':r['ms']-s['start'],'x':(left+r['center'][0]*sw)/W*100,'y':(top+r['center'][1]*sh)/H*100} for r in s['rows']]} for s in result.get('segments',[])]
    return {'clip_id':c['id'],'revision':doc['revision'],'start_ms':c['start_ms']+start,'duration_ms':duration,'keyframes':keys,'region_w':rw,'region_h':rh,'segments':segments,'method':result.get('method','local-template'),
            'stopped':result.get('stopped'),'held_samples':result.get('held_samples',0),
            'review_rows':[{k:r.get(k) for k in ('ms','confidence','state')} for r in result['rows']],
            'message':'Template CPU: giữ vị trí khi che khuất ngắn; dừng ở đổi cảnh/mất mẫu lâu. Không nhận diện danh tính; duyệt trước khi thêm lớp.'}
