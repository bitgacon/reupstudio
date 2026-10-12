"""Bounded creative proposals and portable editor data, never source mutation."""
import copy,json,math,re,time,zipfile,hashlib
from pathlib import Path
from uuid import uuid4
from PIL import Image,ImageOps,ImageFilter
from . import storage,media,timeline,speed

def selected(payload):
    project=storage.project(payload['project_id']);doc=timeline.load(project['id'])
    if payload.get('revision')!=doc['revision']:raise ValueError('Timeline đã đổi; lưu rồi thử lại.')
    for track in doc['tracks']:
        for clip in track['clips']:
            if clip['id']==payload.get('clip_id'):
                if track['locked'] or not clip['asset']:raise ValueError('Chọn media trên track chưa khóa.')
                source,_=storage.project_asset(project,clip['asset'])
                return project,doc,track,clip,source,timeline.describe(project,clip['asset'])
    raise ValueError('Clip không còn trong timeline.')

def register(project,source,event,name):
    import shutil
    key=uuid4().hex;dest=storage.DATA/'uploads'/key;dest.mkdir(parents=True)
    target=dest/('source'+source.suffix);shutil.copy2(source,target)
    storage.atomic_json(dest/'asset.json',{'id':key,'name':name,'file':target.name})
    return timeline.prepare(project,key,event)

def analyze(payload,folder,event,progress):
    import numpy as np
    project,doc,track,c,source,item=selected(payload);folder.mkdir(parents=True,exist_ok=True)
    if c['speed_curve'] or c['duration_ms']>600_000:raise ValueError('Phân tích tối đa 10 phút, tốc độ cố định; chia clip/ bỏ curve trước.')
    span=c['duration_ms']*c['speed']/1000;beats=[];scenes=[]
    if item['has_audio']:
        pcm=folder/'rhythm.f32'
        timeline.run_cancel([media.binary(),'-y','-v','error','-ss',str(c['in_ms']/1000),'-i',str(source),'-t',str(span),'-vn','-ac','1','-ar','8000','-f','f32le',str(pcm)],event)
        samples=np.fromfile(pcm,dtype='<f4');block=400;count=len(samples)//block
        if count>2:
            rms=np.sqrt(np.mean(samples[:count*block].reshape(count,block)**2,axis=1));onsets=np.maximum(0,np.diff(rms,prepend=rms[0]));threshold=max(.008,float(np.percentile(onsets,80)))
            for i in range(1,count-1):
                ms=round(i*50/c['speed'])
                if onsets[i]>threshold and onsets[i]>=onsets[i-1] and onsets[i]>=onsets[i+1] and (not beats or ms-beats[-1]>=250):beats.append(ms)
    progress(45,'Đang dò cảnh và điểm nhấn…')
    if item['kind']=='video':
        log=folder/'scenes.log'
        # metadata goes to a controlled relative filename, not a user filter expression.
        timeline.run_cancel([media.binary(),'-y','-v','error','-ss',str(c['in_ms']/1000),'-i',str(source),'-t',str(span),'-an','-vf',"scale=160:-2,select='gt(scene,0.35)',metadata=print:file=scenes.log",'-f','null','-'],event,cwd=folder)
        if log.exists():scenes=[round(float(x)*1000/c['speed']) for x in re.findall(r'pts_time:([0-9.]+)',log.read_text(errors='replace'))]
    points=sorted(set(x for x in beats+scenes if 100<=x<=c['duration_ms']-100))[:64]
    result={'clip_id':c['id'],'revision':doc['revision'],'beats':beats[:2000],'scenes':scenes[:2000],'points':points,'message':'Điểm nhấn năng lượng, không phải beat tracker AI; duyệt trước khi cắt.'}
    storage.atomic_json(folder/'proposal.json',result);return result

def comic(payload,folder,event,progress):
    project,doc,track,c,source,item=selected(payload)
    if track['kind']!='video':raise ValueError('Chọn video/ảnh.')
    ms=int(payload.get('at_ms',c['start_ms']))-c['start_ms']
    if not 0<=ms<c['duration_ms']:raise ValueError('Con trỏ phải nằm trong clip.')
    folder.mkdir(parents=True,exist_ok=True);raw=folder/'frame.png'
    seek=[] if item['kind']=='image' else ['-ss',str((c['in_ms']+speed.source_ms(c,ms))/1000)]
    timeline.run_cancel([media.binary(),'-y','-v','error',*seek,'-i',str(source),'-frames:v','1','-vf','scale=1280:1280:force_original_aspect_ratio=decrease',str(raw)],event)
    with Image.open(raw) as image:
        base=ImageOps.posterize(image.convert('RGB'),4);edge=ImageOps.invert(base.convert('L').filter(ImageFilter.FIND_EDGES));edge=Image.merge('RGB',(edge,edge,edge));image=Image.blend(base,edge,.25);out=folder/'comic.png';image.save(out)
    progress(85,'Đang nhập khung truyện tranh…')
    return {'media':register(project,out,event,'Comic Freeze'),'message':'Ảnh freeze riêng; thêm lớp tại con trỏ, nguồn không đổi.'}

def stage(payload,folder,event,progress):
    project,doc,track,c,source,item=selected(payload)
    if not item['has_audio'] or c['speed_curve'] or c['duration_ms']>60_000:raise ValueError('Chọn clip có audio tối đa 60s, tốc độ cố định.')
    folder.mkdir(parents=True,exist_ok=True);out=folder/'podcast-stage.mp4'
    seconds=c['duration_ms']/1000
    # Video can outlast its audio stream; atempo can also finish short due to DSP.
    # Pad silence before visualization and retain the last frame for frame rounding.
    timeline.run_cancel([media.binary(),'-y','-v','error','-ss',str(c['in_ms']/1000),'-t',str(c['duration_ms']*c['speed']/1000),'-i',str(source),'-filter_complex',f"[0:a]{timeline.tempo_filters(c['speed'])},apad,atrim=duration={seconds},showwaves=s=960x540:mode=cline:colors=0x00d5bb:rate=24,setpts=PTS-STARTPTS,tpad=stop_mode=clone:stop_duration=1,fps=24,trim=end_frame={math.ceil(c['duration_ms']*24/1000)},format=yuv420p[v]",'-map','[v]','-an','-c:v','libx264','-preset','veryfast','-t',str(seconds),str(out)],event)
    return {'media':register(project,out,event,'Sân khấu podcast · sóng âm'),'message':'Lớp sóng âm im tiếng; giữ audio gốc, dùng Screen nếu cần.'}

def export_bundle(payload,folder,event,progress):
    project=storage.project(payload['project_id']);doc=timeline.load(project['id'])
    if payload.get('revision')!=doc['revision']:raise ValueError('Lưu timeline mới nhất trước.')
    if sum(storage.project_asset(project,key)[0].stat().st_size for key in doc['assets'])>1900*1024**2:raise ValueError('Gói chuyển máy tối đa 1900 MB media; tách dự án trước để giữ gói dưới hạn upload 2 GB.')
    folder.mkdir(parents=True,exist_ok=True);out=folder/'editor-project.rvp';manifest={'format':'reup-editor-1','name':project['name'],'timeline':doc,'assets':{}}
    with zipfile.ZipFile(out,'w',zipfile.ZIP_STORED) as archive:
        for i,key in enumerate(doc['assets']):
            if event.is_set():raise InterruptedError('Đã dừng đóng gói dữ liệu dự án.')
            source,meta=storage.project_asset(project,key);name='assets/'+key+source.suffix.lower()
            digest=hashlib.sha256()
            with source.open('rb') as src,archive.open(name,'w',force_zip64=True) as dest:
                while chunk:=src.read(1024*1024):
                    if event.is_set():raise InterruptedError('Đã dừng.')
                    digest.update(chunk);dest.write(chunk)
            manifest['assets'][key]={'path':name,'name':meta.get('name',source.name),'sha256':digest.hexdigest(),'attribution':meta.get('attribution','')};progress(90*(i+1)/max(1,len(doc['assets'])),'Đang sao chép media dự án…')
        archive.writestr('manifest.json',json.dumps(manifest,ensure_ascii=False))
    return out

def import_bundle(source,event):
    import shutil
    # No extractall: allowlisted files only, count/size limits, remapped identifiers.
    with zipfile.ZipFile(source) as archive:
        infos=archive.infolist();names=[i.filename for i in infos]
        if len(infos)>201 or len(names)!=len(set(names)) or sum(i.file_size for i in infos)>2*1024**3 or 'manifest.json' not in names:raise ValueError('Gói dự án vượt giới hạn hoặc trùng file.')
        manifest_info=archive.getinfo('manifest.json')
        if manifest_info.file_size>4*1024**2:raise ValueError('Manifest quá lớn.')
        m=json.loads(archive.read('manifest.json'));doc=timeline.Timeline.model_validate(m['timeline']).model_dump()
        if m.get('format')!='reup-editor-1' or set(m['assets'])!=set(doc['assets']):raise ValueError('Gói dự án không hợp lệ.')
        if len(infos)!=len(doc['assets'])+1:raise ValueError('Gói chứa file ngoài manifest.')
        mapping={};staged=[]
        try:
            for key,entry in m['assets'].items():
                storage.identifier(key);name=entry['path'];suffix=Path(name).suffix.lower()
                if name!='assets/'+key+suffix or suffix not in {'.mp4','.webm','.mkv','.mov','.avi','.png','.jpg','.jpeg','.webp','.wav','.mp3','.m4a','.ogg','.flac'}:raise ValueError('File media không hợp lệ.')
                new=uuid4().hex;dest=storage.DATA/'uploads'/new;dest.mkdir(parents=True);staged.append(dest);target=dest/('source'+suffix);digest=hashlib.sha256()
                with archive.open(name) as src,target.open('wb') as out:
                    while chunk:=src.read(1024*1024):
                        if event.is_set():raise InterruptedError('Đã dừng nhập.')
                        out.write(chunk);digest.update(chunk)
                if digest.hexdigest()!=entry['sha256']:raise ValueError('Media sai checksum.')
                storage.atomic_json(dest/'asset.json',{'id':new,'name':str(entry['name'])[:200],'file':target.name,'attribution':str(entry.get('attribution',''))[:10000]});mapping[key]=new
            for t in doc['tracks']:
                t['id']=uuid4().hex
                for c in t['clips']:
                    c['id']=uuid4().hex
                    if c['asset']:c['asset']=mapping[c['asset']]
            doc['assets']=[mapping[x] for x in doc['assets']];doc['revision']=0
            # Probe every source before committing a new project.
            for key in mapping.values():
                p=storage.asset(key)[0];timeline._probe(p,p.stat().st_mtime_ns,p.stat().st_size)
            project=storage.new_project(str(m.get('name','Dự án nhập'))[:80]+' · nhập',kind='edit');timeline.save(project['id'],doc)
            return project
        except BaseException:
            for dest in staged:
                if dest.resolve().parent!=(storage.DATA/'uploads').resolve():raise RuntimeError('Không dọn thư mục ngoài uploads.')
                shutil.rmtree(dest)  # only UUID directories created in this call
            raise

def multi_export(payload,folder,event,progress):
    project=storage.project(payload['project_id']);doc=timeline.load(project['id'])
    if payload.get('revision')!=doc['revision']:raise ValueError('Lưu trước khi xuất.')
    sizes={'16:9':(1280,720),'9:16':(720,1280),'1:1':(1080,1080)};ratios=payload.get('ratios',list(sizes))
    if 'quality' in payload:
        p=payload['quality']
        if type(p) is not int or p not in {720,1080,1440,2160}:raise ValueError('Chọn chất lượng 720p, 1080p, 2K hoặc 4K.')
        long=round(p*16/9/2)*2
        sizes={'16:9':(long,p),'9:16':(p,long),'1:1':(p,p)}
    if not isinstance(ratios,list) or not ratios or len(ratios)>3 or len(set(ratios))!=len(ratios) or any(x not in sizes for x in ratios):raise ValueError('Tỷ lệ không hợp lệ.')
    files=[]
    for i,ratio in enumerate(ratios):
        version=copy.deepcopy(doc);version['width'],version['height']=sizes[ratio];out=folder/('video-'+ratio.replace(':','x')+'.mp4')
        timeline.render(project,version,out,event,lambda p,msg:progress((i*100+p)/len(ratios),ratio+' · '+msg));files.append(out)
    credits={storage.project_asset(project,key)[1].get('attribution','') for key in doc['assets']};credits.discard('')
    if credits:
        notice=folder/'ATTRIBUTION.txt';notice.write_text('\n\n'.join(sorted(credits)),encoding='utf-8');files.append(notice)
    return files

def benchmark(payload,folder,event,progress):
    project=storage.project(payload['project_id']);doc=timeline.load(project['id'])
    if payload.get('revision')!=doc['revision']:raise ValueError('Lưu trước khi đo.')
    if timeline.duration(doc)>30_000:raise ValueError('Benchmark cần dự án thử riêng tối đa 30s để tránh render dài ngoài ý muốn.')
    out=folder/'benchmark.mp4';start=time.monotonic();timeline.render(project,doc,out,event,progress);elapsed=time.monotonic()-start
    result={'seconds':round(elapsed,3),'duration_ms':timeline.duration(doc),'width':doc['width'],'height':doc['height'],'fps':doc['fps'],'encoder':doc['encoder'],'encoder_threads':doc['render_threads'],'realtime_factor':round(elapsed/max(.001,timeline.duration(doc)/1000),3)}
    storage.atomic_json(folder/'benchmark.json',result);return result
