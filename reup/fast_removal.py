"""Local, model-free removal. Keep optional OpenCV outside the app interpreter."""
import hashlib, json, math, os, subprocess, sys
from pathlib import Path
from . import media, storage, timeline

MODES = {'fast-delogo', 'telea', 'navier-stokes', 'smooth', 'blur', 'mosaic', 'solid', 'crop', 'logo'}
IMAGE_EXTS={'.png','.jpg','.jpeg','.webp'}

def options(payload):
    mode = payload.get('mode', 'fast-delogo')
    if mode=='opencv':mode='telea'
    if mode not in MODES: raise ValueError('Chế độ xóa nhẹ không hợp lệ.')
    values = {}
    for key, default, low, high in [('margin',3,0,64),('radius',6,1,32)]:
        value = payload.get(key,default)
        if isinstance(value,bool) or not isinstance(value,(int,float)) or not math.isfinite(value) or not low<=value<=high or int(value)!=value:
            raise ValueError('Nới vùng / bán kính cần là số nguyên trong giới hạn.')
        values[key] = int(value)
    if not isinstance(payload.get('keep_audio',True),bool): raise ValueError('Giữ âm thanh không hợp lệ.')
    return {**values,'mode':mode,'keep_audio':payload.get('keep_audio',True),'logo_asset':payload.get('logo_asset','')}

def padded(areas,width,height,margin):
    return [[max(0,a-margin),min(height,b+margin),max(0,c-margin),min(width,d+margin)] for a,b,c,d in areas]

def filters(areas,mode,radius,width,height):
    # One filter graph and one encode for all regions, never re-encode per region.
    if mode in {'fast-delogo','solid'}:
        rows=[]
        for a,b,c,d in areas:
            if mode=='fast-delogo' and (a==0 or c==0 or b>=height or d>=width):
                raise ValueError('FFmpeg delogo cần viền quanh vùng. Thu vùng / giảm nới vùng hoặc chọn Telea.')
            rows.append(f'delogo=x={c}:y={a}:w={d-c}:h={b-a}' if mode=='fast-delogo' else f'drawbox=x={c}:y={a}:w={d-c}:h={b-a}:color=black:t=fill')
        return '[0:v]'+','.join(rows)+'[out]'
    graph=[];previous='0:v'
    for i,(a,b,c,d) in enumerate(areas):
        effect=f'boxblur=luma_radius={min(radius,max(1,min(d-c,b-a)//2))}:luma_power=2:chroma_radius=0' if mode=='blur' else f'scale={max(1,(d-c)//12)}:{max(1,(b-a)//12)},scale={d-c}:{b-a}:flags=neighbor'
        graph.extend([f'[{previous}]split=2[base{i}][part{i}]',f'[part{i}]crop={d-c}:{b-a}:{c}:{a},{effect}[patch{i}]',f'[base{i}][patch{i}]overlay={c}:{a}[v{i}]'])
        previous=f'v{i}'
    return ';'.join(graph)+f';[{previous}]null[out]'

def crop_size(areas):
    if len(areas)!=1:raise ValueError('Cắt khung cần đúng một vùng giữ lại.')
    a,b,c,d=areas[0];w=(d-c)//2*2;h=(b-a)//2*2
    if min(w,h)<2:raise ValueError('Vùng cắt quá nhỏ.')
    return w,h

def cv_python():
    from .libraries import available
    rows=available()
    for key in ('inpaint','vision','vsr-directml'):
        python=Path(rows.get(key,{}).get('python',''))
        if python.is_file():return python
    raise ValueError('Telea / Navier–Stokes cần OpenCV nhẹ. Vào Cài đặt → Thư viện → Xóa nhẹ OpenCV để cài; không cần model AI.')

def execute(source,output,info,areas,opts,event,progress,folder,seconds=None):
    stream=next(s for s in info['streams'] if s.get('codec_type')=='video')
    width,height=int(stream['width']),int(stream['height'])
    if opts['mode'] not in {'crop','logo'}:areas=padded(areas,width,height,opts['margin'])
    if opts['mode'] in {'telea','navier-stokes','smooth'}:
        from fractions import Fraction
        fps=Fraction(stream.get('avg_frame_rate') or '0')
        nominal=Fraction(stream.get('r_frame_rate') or str(fps))
        if seconds is None and (not 0<float(fps)<=120 or abs(float(fps-nominal))>.01):raise ValueError('OpenCV nhẹ hiện cần video FPS cố định, tối đa 120 FPS. Dùng FFmpeg hoặc chuyển FPS trong Biên tập trước.')
        from .subtitle_removal import run_worker
        request={'source':str(source),'output':str(output),'ffmpeg':media.binary(),'width':width,'height':height,'fps':stream.get('avg_frame_rate') or '25',
                 'duration':float(info.get('format',{}).get('duration',1)),'areas':areas,**opts,'seconds':seconds}
        storage.atomic_json(folder/'inpaint-request.json',request)
        python=cv_python()
        from .libraries import available
        vsr_entry=available().get('vsr-directml',{})
        # QPT portable VSR needs its resources cwd for sitecustomize handling.
        cwd=Path(vsr_entry['home']) if vsr_entry.get('home') and str(python)==vsr_entry.get('python') else storage.ROOT
        run_worker([str(python),str(storage.ROOT/'INPAINT_WORKER.py'),str(folder/'inpaint-request.json')],cwd,folder/'inpaint.log',event,progress,model_progress=True)
    else:
        args=[media.binary(),'-y','-v','error']
        if seconds is not None:args+=['-ss',str(seconds)]
        args+=['-i',str(source)]
        if opts['mode']=='crop':
            w,h=crop_size(areas);a,b,c,d=areas[0];graph=f'[0:v]crop={w}:{h}:{c}:{a}[out]'
        elif opts['mode']=='logo':
            logo,_=storage.asset(opts.get('logo_asset',''));logo_info=media.probe(logo)
            if logo.suffix.lower() not in {'.png','.jpg','.jpeg','.webp'} or not any(s.get('codec_type')=='video' for s in logo_info['streams']):raise ValueError('Chọn ảnh PNG / JPG / WebP làm logo.')
            args+=['-i',str(logo)];parts=[];previous='0:v'
            if len(areas)>1:parts.append('[1:v]split='+str(len(areas))+''.join(f'[logo{i}]' for i in range(len(areas))))
            for i,(a,b,c,d) in enumerate(areas):
                parts.extend([f"[{'1:v' if len(areas)==1 else 'logo'+str(i)}]scale={d-c}:{b-a}:force_original_aspect_ratio=decrease[scaled{i}]",f'[{previous}][scaled{i}]overlay={c}:{a}:eof_action=repeat[v{i}]']);previous=f'v{i}'
            graph=';'.join(parts)+f';[{previous}]null[out]'
        else:graph=filters(areas,opts['mode'],opts['radius'],width,height)
        args+=['-filter_complex_threads','1','-filter_complex',graph,'-map','[out]']
        if seconds is not None:args+=['-frames:v','1']
        else:
            if opts['keep_audio']:args+=['-map','0:a:0?','-c:a','aac']
            args+=['-c:v','libx264','-preset','veryfast','-crf','20','-pix_fmt','yuv420p','-threads','2','-movflags','+faststart','-progress','pipe:1']
        timeline.run_cancel(args+[str(output)],event,lambda p,m:progress(40+.48*p,'Đang xử lý xóa nhẹ…'),float(info.get('format',{}).get('duration',1))*1000)

def preview(payload,job_id,progress,event):
    from .subtitle_removal import rectangles, artifact
    opts=options(payload);source,_=storage.asset(payload.get('asset',''));info=media.probe(source)
    stream=next((s for s in info['streams'] if s.get('codec_type')=='video'),None)
    duration=float(info.get('format',{}).get('duration',0));seconds=0 if source.suffix.lower() in IMAGE_EXTS else float(payload.get('seconds',0))
    if source.suffix.lower() in IMAGE_EXTS:duration=1
    if not stream or not math.isfinite(seconds) or not 0<=seconds<duration:raise ValueError('Mốc xem ngoài video.')
    if any(abs(float(s.get('rotation',0)))>.1 for s in stream.get('side_data_list',[])) or abs(float(stream.get('tags',{}).get('rotate',0)))>.1:raise ValueError('Video có metadata xoay; render qua Biên tập trước để vùng khớp hình.')
    folder=storage.output_folder('removal',job_id);output=folder/'effect-preview.png'
    execute(source,output,info,rectangles(payload.get('regions'),stream['width'],stream['height']),opts,event,progress,folder,seconds)
    return {'asset':payload['asset'],'signature':payload.get('signature',''),'picture':artifact(output),'files':[artifact(output)],'message':'Ảnh kết quả thật tại mốc đã chọn; không phải bản xem video chuyển động.'}

def fingerprint(source,payload):
    # SRT is part of the request: don't silently skip a new transcript.
    stamp=[str(source.resolve()),source.stat().st_mtime_ns,source.stat().st_size,{k:v for k,v in payload.items() if k not in {'ui_tab','skip_existing','signature','seconds'}}]
    return hashlib.sha256(json.dumps(stamp,sort_keys=True,ensure_ascii=False).encode()).hexdigest()

def remove_image(payload,job_id,progress,event):
    from .subtitle_removal import rectangles,artifact,store_asset
    source,meta=storage.asset(payload.get('asset',''));opts=options(payload)
    info=media.probe(source);stream=next((s for s in info['streams'] if s.get('codec_type')=='video'),None)
    if not stream or source.suffix.lower() not in IMAGE_EXTS:raise ValueError('Chọn ảnh PNG / JPG / WebP.')
    fingerprint_value=fingerprint(source,payload)
    if payload.get('skip_existing') is True:
        for row in storage.read_json(storage.DATA/'vsr-index.json',[]):
            if row.get('fingerprint')==fingerprint_value:
                try:
                    existing,_=storage.asset(row['asset'])
                    if existing.is_file():return {'entry':row,'files':[row['video']],'message':'Đã có kết quả ảnh cùng cấu hình.'}
                except ValueError:pass
    if event.is_set():raise InterruptedError('Đã dừng trước khi xử lý ảnh.')
    folder=storage.output_folder('removal',job_id);output=folder/'clean.png'
    execute(source,output,info,rectangles(payload.get('regions'),stream['width'],stream['height']),opts,event,progress,folder,0)
    if event.is_set():raise InterruptedError('Đã dừng; ảnh nguồn giữ nguyên.')
    working_output=output;output=storage.publish_removal(output,job_id,meta['name'])
    key=store_asset(output,'Đã xử lý logo · '+meta['name'])
    row={'id':key,'asset':key,'source_asset':payload['asset'],'name':meta['name'],'kind':'image','mode':opts['mode'],'regions':payload['regions'],'video':artifact(output),'subtitle':None,'fingerprint':fingerprint_value}
    with storage.LOCK:
        rows=storage.read_json(storage.DATA/'vsr-index.json',[]);rows.insert(0,row);storage.atomic_json(storage.DATA/'vsr-index.json',rows)
    working_output.unlink()
    return {'entry':row,'files':[row['video']],'message':'Đã tạo ảnh PNG riêng; ảnh nguồn giữ nguyên.'}
