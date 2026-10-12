"""Explicit optional runtimes; read-only proposals, cancellable owned processes."""
import os,re,shutil,subprocess,time
from pathlib import Path
from uuid import uuid4
from . import storage,media,timeline,studio_tools

DEFAULT_MODEL='MahmoudAshraf/mms-300m-1130-forced-aligner'
DEFAULTS={'alignment_python':'','alignment_model':'','alignment_language':'vie','alignment_romanize':True,
          'avatar_home':'','avatar_python':'','reid_model':''}

def config(value=None):
    with storage.LOCK:
        current={**DEFAULTS,**storage.read_json(storage.DATA/'advanced-ai.json',{})}
        if value is not None:
            if set(value)-set(DEFAULTS):raise ValueError('Cấu hình AI không hợp lệ.')
            for key,raw in value.items():
                if key=='alignment_romanize':
                    if type(raw) is not bool:raise ValueError('Romanize phải là bật/tắt.')
                elif key=='alignment_language':
                    if not isinstance(raw,str) or not re.fullmatch('[a-z]{3}',raw):raise ValueError('Mã ngôn ngữ ISO 639-3, ví dụ vie.')
                elif not isinstance(raw,str) or len(raw)>4096 or (raw and not Path(raw).is_absolute()):raise ValueError('Nhập đường dẫn đầy đủ; model phải nằm trên máy.')
                current[key]=raw
            storage.atomic_json(storage.DATA/'advanced-ai.json',current)
        return current

def readiness():
    """Read-only file checks, not a claim that inference/GPU has been tested."""
    from .libraries import registry
    current=config();entry=registry().get('alignment',{})
    # Repair missing auto-links only in memory for this GET; never migrate settings silently.
    python=current['alignment_python'] or entry.get('python','')
    model=current['alignment_model'] or entry.get('model','')
    avatar_home=Path(current['avatar_home'])
    ctc=bool(python and model and Path(python).is_file() and (Path(model)/'config.json').is_file())
    avatar=bool(current['avatar_home'] and current['avatar_python'] and Path(current['avatar_python']).is_file()
                and (avatar_home/'scripts/inference.py').is_file() and (avatar_home/'models/musetalkV15/unet.pth').is_file())
    return {'features':[
        {'id':'alignment','name':'Forced alignment · CTC','files_ready':ctc,
         'message':'Cần audio đúng lời dịch; kiểm tra suy luận offline bằng đoạn ngắn. Model MMS mặc định chỉ phi thương mại.'},
        {'id':'avatar','name':'Avatar · MuseTalk','files_ready':avatar,
         'message':'Cài MuseTalk trong Thư viện theo yêu cầu, hoặc nối runtime riêng. Cần GPU NVIDIA; kiểm tra chất lượng bằng avatar ngắn trên máy thực.'},
        {'id':'reid','name':'Tracking · ReID ONNX','files_ready':bool(current['reid_model'] and Path(current['reid_model']).is_file()),
         'message':'Model ReID riêng là tùy chọn. Tracking OpenCV vẫn dùng được; không phải nhận diện danh tính.'},
        {'id':'compose','name':'Phối nhiều lớp','files_ready':True,
         'message':'Có phối local và đề xuất bằng prompt LLM. Chỉ gửi thông tin media đã chọn khi cho phép; duyệt trước khi áp dụng.'}]}

def execute(args,cwd,folder,event,progress,label,timeout=1800):
    if event.is_set():raise InterruptedError('Đã dừng '+label)
    folder.mkdir(parents=True,exist_ok=True);logfile=folder/'ai-worker.log'
    env={**os.environ,'PYTHONUTF8':'1','PYTHONUNBUFFERED':'1','HF_HUB_OFFLINE':'1','TRANSFORMERS_OFFLINE':'1'}
    env.pop('PYTHONHOME',None);env.pop('PYTHONPATH',None);env['PYTHONNOUSERSITE']='1'
    with logfile.open('w',encoding='utf-8') as log:
        proc=subprocess.Popen([str(x) for x in args],cwd=cwd,stdout=log,stderr=subprocess.STDOUT,env=env,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
        started=time.monotonic();reported=0
        try:
            while proc.poll() is None:
                if event.wait(.5):raise InterruptedError('Đã dừng '+label+'; timeline giữ nguyên.')
                elapsed=time.monotonic()-started
                if elapsed>timeout:raise RuntimeError(label+' quá thời gian; dùng đoạn ngắn hơn.')
                if elapsed-reported>=10:progress(30,label+' đang xử lý, '+str(round(elapsed))+'s; chưa có phần trăm từ engine.');reported=elapsed
            if proc.returncode:raise RuntimeError(label+' thất bại: '+logfile.read_text(encoding='utf-8',errors='replace')[-1800:])
        finally:media.stop_owned_process(proc)
    if event.is_set():raise InterruptedError('Đã dừng '+label)

def extract_audio(c,source,wav,event):
    if c['speed_curve'] or c['duration_ms']>30_000:raise ValueError('AI này xử lý clip audio tối đa 30s, tốc độ cố định; chia clip trước.')
    timeline.run_cancel([media.binary(),'-y','-v','error','-ss',str(c['in_ms']/1000),'-t',str(c['duration_ms']*c['speed']/1000),'-i',str(source),'-vn','-af',timeline.tempo_filters(c['speed']),'-t',str(c['duration_ms']/1000),'-ac','1','-ar','16000','-c:a','pcm_s16le',str(wav)],event)

def alignment(payload,folder,event,progress):
    project,doc,track,c,source,item=studio_tools.selected(payload);settings=config()
    reference=payload.get('reference','')
    if not isinstance(reference,str) or not 1<=len(reference.split())<=400 or len(reference)>5000:raise ValueError('Nhập 1–400 từ thực sự được nói trong audio đang chọn.')
    python=Path(settings['alignment_python']);model=Path(settings['alignment_model'])
    if not settings['alignment_python'] or not python.is_file() or not settings['alignment_model'] or not (model/'config.json').is_file():raise ValueError('Chưa cài/kết nối CTC. Vào Cài đặt → AI nâng cao; không tự tải model khi chạy.')
    if not item['has_audio']:raise ValueError('Clip không có audio. Chọn clip audio lồng tiếng nếu căn lời dịch.')
    folder.mkdir(parents=True,exist_ok=True);wav=folder/'alignment.wav';progress(5,'Trích audio đúng clip/tốc độ…');extract_audio(c,source,wav,event)
    request={'model':str(model),'audio':str(wav),'reference':reference,'duration_ms':c['duration_ms'],
             'language':settings['alignment_language'],'romanize':settings['alignment_romanize'],'result':str(folder/'alignment-result.json')}
    storage.atomic_json(folder/'alignment-request.json',request)
    execute([python,storage.ROOT/'ALIGNMENT_WORKER.py',folder/'alignment-request.json'],storage.ROOT,folder,event,progress,'Forced alignment CTC')
    result=storage.read_json(folder/'alignment-result.json',{})
    words=result.get('words',[]);previous=0
    if [w.get('word') for w in words]!=reference.split():raise ValueError('Engine chưa căn đủ lời; không áp dụng.')
    for row in words:
        if not previous<=row['start']<row['end']<=c['duration_ms']:raise ValueError('Mốc CTC không hợp lệ.')
        previous=row['end']
    return {**result,'clip_id':c['id'],'revision':doc['revision'],'start_ms':c['start_ms'],'duration_ms':c['duration_ms']}

def install_alignment(payload,folder,log,event,progress):
    from . import libraries
    if payload.get('accept_noncommercial') is not True:raise ValueError('Model mặc định CC-BY-NC-4.0: cần xác nhận chỉ dùng phi thương mại. Dùng model riêng có quyền phù hợp cho bản thương mại.')
    python=libraries.environment(folder,log,event,progress)
    libraries.run([str(python),'-m','pip','install','torch==2.5.1','--index-url','https://download.pytorch.org/whl/cpu'],folder,log,event,progress)
    libraries.run([str(python),'-m','pip','install','transformers==4.49.0','numpy<2','uroman==1.3.1','safetensors'],folder,log,event,progress)
    request={'install':True,'model':DEFAULT_MODEL,'destination':str(folder/'model')}
    path=folder/'install-model.json';storage.atomic_json(path,request)
    libraries.run([str(python),str(storage.ROOT/'ALIGNMENT_WORKER.py'),str(path)],folder,log,event,progress)
    if not (folder/'model'/'config.json').is_file():raise ValueError('Model chưa đầy đủ; chưa kích hoạt.')
    if event.is_set():raise InterruptedError('Đã dừng; chưa nối CTC.')
    config({'alignment_python':str(python),'alignment_model':str(folder/'model'),'alignment_language':'vie','alignment_romanize':True})
    return {'path':str(folder),'python':str(python),'model':str(folder/'model')}

def avatar(payload,folder,event,progress):
    if payload.get('portrait_consent') is not True:raise ValueError('Cần xác nhận quyền sử dụng hình/giọng trước khi tạo avatar.')
    project,doc,track,c,source,item=studio_tools.selected(payload);settings=config();home=Path(settings['avatar_home']);python=Path(settings['avatar_python'])
    # Upstream uses unquoted ffmpeg shell paths: only our ASCII fixed names are passed.
    if not settings['avatar_home'] or not re.fullmatch(r'[A-Za-z0-9_:\\/-]+',str(home)) or not (home/'scripts/inference.py').is_file():raise ValueError('Kết nối MuseTalk tại đường dẫn không có dấu/khoảng trắng/ký tự shell, ví dụ D:\\AI\\MuseTalk.')
    if not settings['avatar_python'] or not python.is_file():raise ValueError('Chưa kết nối Python riêng của MuseTalk.')
    if not item['has_audio']:raise ValueError('Chọn clip có audio để điều khiển môi avatar.')
    if payload.get('portrait') not in doc['assets']:raise ValueError('Ảnh chân dung phải được nhập vào thư viện của dự án này.')
    portrait,meta=storage.project_asset(project,payload.get('portrait',''))
    portrait_item=timeline.describe(project,payload['portrait'])
    if portrait_item['kind']!='image':raise ValueError('Chọn ảnh chân dung trong thư viện media.')
    if not (home/'models/musetalkV15/unet.pth').is_file():raise ValueError('Chưa có model MuseTalk v1.5; không tải ngầm khi tạo avatar.')
    folder.mkdir(parents=True,exist_ok=True);stage=home/('reup_'+uuid4().hex);stage.mkdir()
    # Leave owned staging for diagnostics, never delete paths supplied by the user.
    from PIL import Image
    with Image.open(portrait) as image:image.convert('RGB').save(stage/'portrait.png')
    extract_audio(c,source,stage/'speech.wav',event)
    task={'task_0':{'video_path':stage.name+'/portrait.png','audio_path':stage.name+'/speech.wav'}}
    storage.atomic_json(stage/'request.yaml',task)
    # JSON is valid YAML. Probe CUDA/dependencies in the isolated runtime first.
    execute([python,'-c','import torch,cv2,mmcv; assert torch.cuda.is_available(), "MuseTalk cần GPU CUDA NVIDIA"'],home,folder,event,progress,'Kiểm tra MuseTalk',120)
    ffmpeg_dir=Path(media.binary()).resolve().parent
    if (home/'ffmpeg/ffmpeg.exe').is_file():ffmpeg_dir=home/'ffmpeg'
    if not re.fullmatch(r'[A-Za-z0-9_:\\/-]+',str(ffmpeg_dir)):
        ffmpeg_dir=stage/'ffmpeg';ffmpeg_dir.mkdir();shutil.copy2(media.binary(),ffmpeg_dir/'ffmpeg.exe')
    if not re.fullmatch(r'[A-Za-z0-9_:\\/-]+',str(ffmpeg_dir)):raise ValueError('MuseTalk cần đường dẫn FFmpeg không có khoảng trắng/ký tự shell.')
    execute([python,'-m','scripts.inference','--inference_config',stage.name+'/request.yaml','--result_dir',stage.name+'/results',
             '--unet_model_path','models/musetalkV15/unet.pth','--unet_config','models/musetalkV15/musetalk.json','--version','v15','--ffmpeg_path',ffmpeg_dir],home,folder,event,progress,'Avatar MuseTalk',3600)
    candidates=list((stage/'results').rglob('*.mp4'))
    if len(candidates)!=1:raise ValueError('MuseTalk chưa trả đúng một MP4; xem log/staging, chưa thêm media.')
    result=candidates[0];info=media.probe(result)
    if not any(s.get('codec_type')=='video' for s in info.get('streams',[])):raise ValueError('MP4 avatar không có hình.')
    progress(90,'Nhập avatar vào thư viện; chưa thay clip gốc…')
    generated=studio_tools.register(project,result,event,'Avatar MuseTalk')
    return {'media':generated,'clip_id':c['id'],'revision':doc['revision'],'start_ms':c['start_ms'],
            'duration_ms':min(c['duration_ms'],generated['duration_ms']),'message':'Avatar đã tạo; duyệt trước khi thêm track. Staging riêng được giữ để chẩn đoán.'}
