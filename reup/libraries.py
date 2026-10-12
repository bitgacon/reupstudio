"""Opt-in libraries, installed independently and published only after validation."""
from pathlib import Path, PureWindowsPath
import hashlib
import os
import shutil
import sys
from uuid import uuid4
import requests
from . import storage, subtitle_removal as vsr

VSR_ASSET = {
    'name':'vsr-v1.1.1-windows-directml.7z', 'bytes':1701654444,
    'sha256':'ef59cc93346000d6382384d446ebc39d4d7ac102ef8a0e5ec3534366385a88b4',
    'url':'https://github.com/YaoFANGUK/video-subtitle-remover/releases/download/1.1.1/vsr-v1.1.1-windows-directml.7z'}
SEVEN_ASSET = {
    'name': '7zr.exe', 'label': '7-Zip console 26.04', 'bytes': 602624,
    'sha256': '256feca8e274e5da655e2a284fabafd9f554365eb164862089dacd4e8276d282',
    'url': 'https://github.com/ip7z/7zip/releases/download/26.04/7zr.exe'}
CATALOG = [
    {'id':'inpaint','title':'Xóa nhẹ OpenCV · Telea / Navier–Stokes','description':'OpenCV + NumPy riêng, không model AI. Cài khi cần; FFmpeg xóa nhanh không cần bộ này.'},
    {'id':'vsr-directml','title':'VSR portable 1.1.1 · DirectML', 'description':'1,70 GB tải; cần tối thiểu 10 GB trống. STTN auto; nhiều vùng chạy tuần tự. DirectML phụ thuộc GPU/driver, CPU có thể rất chậm.'},
    {'id':'whisper','title':'Model Whisper đang chọn', 'description':'Tải model trong Cài đặt, từ khoảng 75 MB đến 3 GB. Dùng chung nhận dạng, karaoke và SRT gốc.'},
    {'id':'vision','title':'AI hình · căn mặt / tách nền', 'description':'Runtime riêng OpenCV + rembg. Model tách nền tải ở lần sử dụng đầu. Có thể cần hơn 1 GB.'},
    {'id':'separation','title':'AI tách giọng / nhạc · Demucs CPU', 'description':'Runtime riêng Torch + Demucs và model htdemucs. Có thể cần hơn 3 GB.'},
    {'id':'alignment','title':'Forced alignment · CTC đa ngôn ngữ', 'description':'Runtime CPU + MMS 300M riêng, vài GB. Model CC-BY-NC-4.0: chỉ phi thương mại; có thể kết nối model riêng trong AI nâng cao.'},
    {'id':'avatar','title':'Avatar · MuseTalk v1.5 / NVIDIA', 'description':'Cài theo yêu cầu; profile Windows CUDA 11.8, cần NVIDIA và 25 GB trống. Model nhiều GB được ghim revision/checksum. Kiểm tra runtime/GPU trước khi nối; cần thử avatar thật.'},
    {'id':'tts-kokoro','title':'TTS Kokoro · local nhẹ / tiếng Anh','description':'Model + giọng khoảng 354 MB, runtime riêng; cần 2 GB trống. Không có cảm xúc điều khiển trực tiếp. Kiểm tra tạo audio trước khi kích hoạt.'},
    {'id':'tts-chatterbox','title':'TTS Chatterbox · đa ngôn ngữ / biểu cảm','description':'Model lớn + runtime Torch riêng; cần 12 GB trống. Điều chỉnh độ biểu cảm, không chọn được chính xác vui/buồn. CPU chậm; CUDA chọn trong Cài đặt TTS.'},
    {'id':'tts-qwen','title':'TTS Qwen3 · cảm xúc / mô tả diễn xuất','description':'CustomVoice 1.7B, nhiều GB; cần 15 GB trống. CPU có thể rất chậm; khuyến nghị NVIDIA đủ VRAM. Chọn CPU/CUDA trước khi cài.'},
    {'id':'vieneu','title':'VieNeu · giọng Việt / clone','description':'Runtime ONNX riêng và model Turbo; tải vài GB khi bấm cài, cần tối thiểu 8 GB trống. Không kèm bản setup Lite. Cài xong tự kết nối.'}]

def config(value=None):
    with storage.LOCK:
        current=storage.read_json(storage.DATA/'libraries-settings.json',{'root':str(storage.DATA/'libraries')})
        if value is not None:
            if set(value)!={'root'}:raise ValueError('Chỉ chọn thư mục cài thư viện.')
            path=Path(str(value['root']).strip().strip('"'))
            if not path.is_absolute() or len(str(path))>4096:raise ValueError('Nhập thư mục đầy đủ.')
            if path.exists() and not path.is_dir():raise ValueError('Đây không phải thư mục.')
            current={'root':str(path.resolve())};storage.atomic_json(storage.DATA/'libraries-settings.json',current)
        return current

def registry():return storage.read_json(storage.DATA/'library-index.json',{})

def available():
    """Known local runtimes only. No recursive scan, imports or downloads on GET."""
    rows=dict(registry())
    from .advanced_ai import config as ai_config
    ai=ai_config()
    if 'avatar' not in rows and ai['avatar_home'] and ai['avatar_python'] and Path(ai['avatar_python']).is_file() and (Path(ai['avatar_home'])/'scripts/inference.py').is_file():
        rows['avatar']={'path':ai['avatar_home'],'home':ai['avatar_home'],'python':ai['avatar_python']}
    current=vsr.config()
    home=vsr.home_path(current.get('home',''));python=Path(current.get('python',''))
    if current.get('home') and vsr.backend_kind(home) and python.is_file():
        path=str(home.parent if home.name.lower()=='resources' else home)
        prior=rows.get('vsr-directml',{}) if rows.get('vsr-directml',{}).get('path')==path else {}
        rows['vsr-directml']={**prior,'path':path,'home':str(home),'python':str(python)}
    for key,name in [('vision','vision-env'),('separation','separation-env')]:
        fallback=storage.ROOT/name
        if key not in rows and (fallback/'Scripts/python.exe').is_file():rows[key]={'path':str(fallback),'python':str(fallback/'Scripts/python.exe')}
    cache=storage.DATA/'models/whisper';model=storage.settings()['whisper_model']
    if 'whisper' not in rows and cache.is_dir() and any((cache/('models--Systran--faster-whisper-'+model)/'snapshots').glob('*/model.bin')):
        rows['whisper']={'path':str(cache),'model':model}
    if 'vieneu' not in rows:
        from .engine import find_home
        try:
            home=find_home();python=home/'runtime/python.exe'
            if not python.is_file():python=home/'.venv/Scripts/python.exe'
            rows['vieneu']={'path':str(home),'python':str(python)}
        except RuntimeError:pass
    excluded=storage.read_json(storage.DATA/'library-excluded.json',{})
    return {key:entry for key,entry in rows.items() if excluded.get(key)!=entry.get('path')}

def remember_vsr(home,python):
    result={'path':str(home.parent if home.name.lower()=='resources' else home),'home':str(home),'python':str(python)}
    with storage.LOCK:
        rows=registry();prior=rows.get('vsr-directml',{})
        if prior.get('path')==result['path']:result={**prior,**result}
        rows['vsr-directml']=result;storage.atomic_json(storage.DATA/'library-index.json',rows)
        excluded=storage.read_json(storage.DATA/'library-excluded.json',{})
        if 'vsr-directml' in excluded:excluded.pop('vsr-directml');storage.atomic_json(storage.DATA/'library-excluded.json',excluded)
        vsr.config({k:result[k] for k in ('home','python')})
    return result

def connect_registered_vsr():
    current=vsr.config()
    if current.get('home') and vsr.backend_kind(vsr.home_path(current['home'])) and Path(current.get('python','')).is_file():return
    entry=registry().get('vsr-directml',{})
    if entry.get('home') and vsr.backend_kind(Path(entry['home'])) and Path(entry.get('python','')).is_file():
        vsr.config({k:entry[k] for k in ('home','python')})

def installed_path(kind, fallback):
    raw=available().get(kind,{}).get('path','')
    if not raw and storage.read_json(storage.DATA/'library-excluded.json',{}).get(kind)==str(fallback):
        raise ValueError('Thư viện đã ngắt kết nối. Cài/kết nối lại trước khi chạy.')
    return Path(raw) if raw and Path(raw).is_dir() else fallback

def whisper_python():
    entry=registry().get('whisper',{})
    if entry.get('python') and Path(entry['python']).is_file():return entry['python']
    if storage.read_json(storage.DATA/'library-excluded.json',{}).get('whisper'):
        raise ValueError('Whisper đã ngắt kết nối. Cài/kết nối lại tại Thư viện.')
    import importlib.util
    if 'faster_whisper' in sys.modules or importlib.util.find_spec('faster_whisper'):return sys.executable
    raise ValueError('Chưa cài Whisper. Vào Cài đặt → Thư viện tùy chọn → Model Whisper để tải/cài runtime và model.')

def status():
    connect_registered_vsr()
    rows=available()
    return {**config(),'catalog':[{**row,'installed':bool(rows.get(row['id'],{}).get('path')) and Path(rows[row['id']]['path']).is_dir(),'path':rows.get(row['id'],{}).get('path',''),
             'managed':bool(rows.get(row['id'],{}).get('managed')), 'model':rows.get(row['id'],{}).get('model','')} for row in CATALOG], 'runtime':vsr.status()}

def owned_folder(entry,key):
    """Never remove external/fallback runtimes, junctions, roots or project data."""
    import re
    if entry.get('managed') is not True: raise ValueError('Bộ kết nối ngoài chỉ được ngắt kết nối, không xóa file.')
    root=Path(entry.get('managed_root',''));folder=Path(entry.get('install_root',''))
    if not root.is_absolute() or not folder.is_absolute(): raise ValueError('Thiếu thông tin sở hữu thư viện.')
    if folder.parent.resolve()!=root.resolve() or not re.fullmatch(re.escape(key)+r'-[a-f0-9]{32}',folder.name):
        raise ValueError('Từ chối gỡ đường dẫn ngoài bộ cài được quản lý.')
    if folder.resolve()!=folder.absolute() or folder.is_symlink() or getattr(folder,'is_junction',lambda:False)():
        raise ValueError('Không gỡ thư mục liên kết/junction.')
    # Python 3.11 lacks is_junction; Windows reparse points also include junctions.
    if os.name=='nt' and folder.stat().st_file_attributes & 1024:
        raise ValueError('Không gỡ thư mục reparse point.')
    for path in folder.rglob('*'):
        if path.is_symlink() or (os.name=='nt' and path.lstat().st_file_attributes & 1024):
            raise ValueError('Thư viện có liên kết/reparse point; chỉ ngắt kết nối để bảo vệ file.')
    protected=[storage.DATA.resolve()]
    protected.extend(Path(p).resolve() for k,p in storage.settings().items()
                     if (k=='project_root' or k=='output_root' or k.endswith('_output')) and p)
    for index in ('project-index.json','output-index.json'):
        protected.extend(Path(p).resolve() for p in storage.read_json(storage.DATA/index,{}).values())
    if any(p==folder.resolve() or p.is_relative_to(folder.resolve()) for p in protected):
        raise ValueError('Thư mục đang chứa dữ liệu/dự án; không được gỡ file.')
    return root.resolve(),folder.resolve()

def remove(body):
    if set(body)-{'library','delete_files'} or type(body.get('delete_files',False)) is not bool:
        raise ValueError('Yêu cầu gỡ thư viện không hợp lệ.')
    key=body.get('library')
    if key not in {r['id'] for r in CATALOG}: raise ValueError('Thư viện không hợp lệ.')
    with storage.LOCK:
        entries=registry();entry=available().get(key)
        if not entry: raise ValueError('Thư viện chưa được kết nối.')
        root=folder=None
        if body.get('delete_files'): root,folder=owned_folder(entry,key)
        entries.pop(key,None)
        exclusions=storage.read_json(storage.DATA/'library-excluded.json',{})
        exclusions[key]=entry.get('path','')
        # Disable first. A failed delete leaves an unconnected, recoverable folder.
        storage.atomic_json(storage.DATA/'library-index.json',entries)
        storage.atomic_json(storage.DATA/'library-excluded.json',exclusions)
        if key=='vsr-directml': vsr.config({'home':'','python':''})
        if key=='alignment':
            from . import advanced_ai
            c=advanced_ai.config()
            if c['alignment_python']==entry.get('python'): advanced_ai.config({'alignment_python':'','alignment_model':''})
        if key=='avatar':
            from . import advanced_ai
            c=advanced_ai.config()
            if c['avatar_python']==entry.get('python'):advanced_ai.config({'avatar_python':'','avatar_home':''})
        if key=='vieneu' and storage.settings()['vieneu_home']==entry.get('path'):
            storage.save_settings({'vieneu_home':''})
        if folder is not None: shutil.rmtree(folder)
    return {'library':key,'deleted_files':folder is not None,
            'message':'Đã gỡ và xóa bộ thư viện được quản lý; dự án/kết quả không thay đổi.' if folder else 'Đã ngắt kết nối; mọi file thư viện vẫn giữ nguyên.'}

def find_vsr(raw):
    root=vsr.home_path(raw)
    if not root.is_dir():raise ValueError('Chọn thư mục VSR đã giải nén, không chọn mục Python ở Start Menu.')
    queue=[(root,0)];homes=[];pythons=[];visited=0
    while queue and visited<1500:
        path,depth=queue.pop(0);visited+=1
        if vsr.backend_kind(path):homes.append(path)
        for name in ('python.exe','python'):
            if (path/name).is_file():pythons.append(path/name)
        if depth<4:
            for child in path.iterdir():
                if child.is_dir() and not child.is_symlink() and child.name.lower() not in {'models','site-packages','.git','__pycache__'}:queue.append((child,depth+1))
    if not homes:raise ValueError('Không tìm thấy backend VSR tương thích trong thư mục đã chọn.')
    if not pythons:raise ValueError('Bạn tải mã nguồn (Source code), chưa có Python/model. Chọn Tải / cài VSR portable trong Thư viện tùy chọn để lấy bộ đầy đủ.')
    home=homes[0];python=next((p for p in pythons if p.is_relative_to(home)),pythons[0])
    return home.resolve(),python.resolve()

def detect_vsr(raw):
    home,python=find_vsr(raw)
    vsr.config({'home':str(home),'python':str(python)})
    return vsr.status()

def valid_member(name):
    text=name.replace('\\','/')
    return bool(text) and not PureWindowsPath(text).is_absolute() and not text.startswith('/') and ':' not in text and '..' not in text.split('/')

def download(asset, target, event, progress):
    def digest(path):
        h=hashlib.sha256()
        with path.open('rb') as f:
            for block in iter(lambda:f.read(1024*1024),b''):
                if event.is_set():raise InterruptedError('Đã dừng tải thư viện.')
                h.update(block)
        return h.hexdigest()
    if target.is_file() and target.stat().st_size==asset['bytes'] and digest(target)==asset['sha256']:return
    partial=target.with_suffix(target.suffix+'.partial')
    try:
        session=requests.Session();session.trust_env=False
        with session,session.get(asset['url'],stream=True,timeout=(20,60)) as response,partial.open('wb') as out:
            response.raise_for_status();total=0;h=hashlib.sha256()
            for block in response.iter_content(1024*1024):
                if event.is_set():raise InterruptedError('Đã dừng tải thư viện.')
                total+=len(block)
                if total>asset['bytes']:raise ValueError('Gói tải vượt kích thước đã xác minh.')
                out.write(block);h.update(block);progress(5+55*total/asset['bytes'],f'Tải {asset.get("label","VSR")}: {total/1e6:.0f}/{asset["bytes"]/1e6:.0f} MB')
        if total!=asset['bytes'] or h.hexdigest()!=asset['sha256']:raise ValueError('Gói VSR không đúng SHA256/kích thước; chưa cài.')
        partial.replace(target)
    finally:partial.unlink(missing_ok=True)

def run(args,cwd,log,event,progress):
    vsr.run_worker(args,cwd,log,event,lambda p,m:progress(75,'Đang cài / kiểm tra thư viện; chi tiết trong log…'),timeout=7200)

def environment(path,log,event,progress):
    run([sys.executable,'-m','venv',str(path)],storage.ROOT,log,event,progress)
    python=path/'Scripts'/'python.exe' if os.name=='nt' else path/'bin'/'python'
    if not python.is_file():raise ValueError('Không tạo được runtime riêng. Xem log cài thư viện.')
    return python

def seven_zip(root, event, progress):
    seven=next((p for p in (Path(os.environ.get('ProgramFiles','C:/Program Files'))/'7-Zip'/'7z.exe',
                            Path(os.environ.get('ProgramFiles(x86)','C:/Program Files (x86)'))/'7-Zip'/'7z.exe',
                            storage.ROOT/'tools'/'7z.exe') if p.is_file()),None)
    if seven or os.name != 'nt': return seven
    # The VSR release uses ARM64 (method 0x0A) + BCJ2. py7zr 1.0.0
    # cannot decode ARM64; use a checksum-pinned official native console.
    folder=root/'extractor-7zip-26.04';folder.mkdir(parents=True,exist_ok=True)
    seven=folder/'7zr.exe'
    download(SEVEN_ASSET,seven,event,lambda p,m:progress(60+min(10,max(0,(p-5)*10/55)),m))
    storage._durable_replace(folder/'SOURCE.txt',
        (SEVEN_ASSET['url']+'\nSHA256 '+SEVEN_ASSET['sha256']+'\nOfficial 7-Zip console, downloaded on demand; source/license: https://www.7-zip.org/\n').encode('utf-8'))
    return seven


def extract(archive,folder,log,event,progress,root):
    seven=seven_zip(root,event,progress)
    if seven:
        run([str(seven),'l','-slt','-sccUTF-8',str(archive)],root,log,event,progress)
        listing=log.read_text(encoding='utf-8',errors='replace').split('----------',1)
        if len(listing)!=2:raise ValueError('Không đọc được danh mục gói 7z.')
        for line in listing[1].splitlines():
            if line.startswith('Path = ') and not valid_member(line[7:]):raise ValueError('Gói chứa đường dẫn không an toàn.')
            if line.startswith(('Symbolic Link = ','Hard Link = ')):raise ValueError('Gói chứa liên kết không được hỗ trợ.')
        run([str(seven),'x','-y','-sccUTF-8','-o'+str(folder),str(archive)],root,log,event,progress)
    else:
        tools=root/'extractor-env';python=tools/'Scripts'/'python.exe' if os.name=='nt' else tools/'bin'/'python'
        if not python.is_file():python=environment(tools,log,event,progress)
        run([str(python),'-m','pip','install','--disable-pip-version-check','py7zr==1.0.0'],root,log,event,progress)
        run([str(python),str(storage.ROOT/'LIBRARY_WORKER.py'),'extract',str(archive),str(folder)],root,log,event,progress)
    if any(p.is_symlink() for p in folder.rglob('*')):raise ValueError('Gói chứa symlink; chưa kích hoạt.')

def install(payload,job_id,progress,event):
    key=payload.get('library')
    if key not in {r['id'] for r in CATALOG}:raise ValueError('Thư viện không hợp lệ.')
    root=Path(config()['root']);root.mkdir(parents=True,exist_ok=True)
    folder=root/(key+'-'+uuid4().hex);candidate=folder;logdir=storage.output_folder('removal',job_id);log=logdir/'library-install.log'
    progress(2,'Chuẩn bị cài thư viện riêng; không sửa runtime của ứng dụng…')
    if key=='inpaint':
        existing=available().get(key,{})
        if existing.get('python') and Path(existing['python']).is_file():
            folder=Path(existing['path']);python=Path(existing['python'])
        else:
            python=environment(folder,log,event,progress)
            run([str(python),'-m','pip','install','--disable-pip-version-check','opencv-python-headless==4.13.0.92','numpy==2.4.6'],root,log,event,progress)
        run([str(python),'-c','import cv2,numpy; print(cv2.__version__)'],root,log,event,progress)
        result={'path':str(folder),'python':str(python)}
    elif key=='vieneu':
        if shutil.disk_usage(root).free<8_000_000_000:raise ValueError('Cần ít nhất 8 GB trống để cài VieNeu.')
        python=environment(folder/'.venv',log,event,progress)
        run([str(python),'-m','pip','install','vieneu==3.8.3','fastapi==0.136.3','uvicorn==0.32.1','python-multipart==0.0.27'],folder,log,event,progress)
        run([str(python),str(storage.ROOT/'VIENEU_INSTALL_WORKER.py'),'install',str(folder),storage.settings()['precision']],folder,log,event,progress)
        run([str(python),str(storage.ROOT/'VIENEU_INSTALL_WORKER.py'),'check',str(folder),storage.settings()['precision']],folder,log,event,progress)
        if 'VIENEU_READY' not in log.read_text(encoding='utf-8',errors='replace'):raise ValueError('VieNeu chưa qua kiểm tra offline; chưa kích hoạt.')
        result={'path':str(folder),'python':str(python)}
    elif key=='vsr-directml':
        connect_registered_vsr()
        existing=available().get(key)
        if existing:
            home,python=Path(existing['home']),Path(existing['python']);folder=Path(existing['path'])
            progress(5,'Đã nhận bộ VSR trên máy; kiểm tra và dùng lại, không tải bản trùng…')
        else:
            if shutil.disk_usage(root).free<10_000_000_000:raise ValueError('Cần tối thiểu 10 GB trống để tải/giải nén VSR.')
            cache=root/'downloads';cache.mkdir(exist_ok=True);archive=cache/VSR_ASSET['name']
            download(VSR_ASSET,archive,event,progress);folder.mkdir();extract(archive,folder,log,event,progress,root)
            home,python=find_vsr(folder)
        vsr.prepare_runtime(home,python,logdir,event,progress)
        kind=vsr.backend_kind(home)
        args=[str(python),str(storage.ROOT/'VSR_LEGACY_WORKER.py'),'--check',str(home)] if kind=='legacy111' else [str(python),str(home/'backend/main.py'),'--help']
        run(args,home,log,event,progress)
        text=log.read_text(encoding='utf-8',errors='replace')
        if ('VSR_LEGACY_RUNTIME_OK' if kind=='legacy111' else '--subtitle-area-coords') not in text:raise ValueError('Runtime tải xong nhưng chưa vượt kiểm tra; chưa kích hoạt.')
        result={'path':str(folder),'home':str(home),'python':str(python)}
    elif key=='whisper':
        model=storage.settings()['whisper_model']
        if model not in {'tiny','base','small','medium','large-v3','large-v3-turbo'}:raise ValueError('Model Whisper không hợp lệ.')
        python=environment(folder,log,event,progress)
        run([str(python),'-m','pip','install','faster-whisper==1.1.0','requests==2.33.1','pydantic==2.12.5','pydub==0.25.1','Pillow==11.3.0'],root,log,event,progress)
        cache=folder/'models';cache.mkdir()
        run([str(python),str(storage.ROOT/'LIBRARY_WORKER.py'),'whisper',model,str(cache)],root,log,event,progress)
        result={'path':str(cache),'python':str(python),'model':model}
    elif key.startswith('tts-'):
        from .tts_install import install as install_tts
        result=install_tts(key,folder,log,event,progress)
    elif key=='avatar':
        from .avatar_install import install as install_avatar
        result=install_avatar(payload,folder,root,log,event,progress);folder=Path(result['path'])
    elif key=='alignment':
        from .advanced_ai import install_alignment,config as ai_config
        existing=available().get(key,{})
        if existing.get('python') and existing.get('model') and Path(existing['python']).is_file() and (Path(existing['model'])/'config.json').is_file():
            folder=Path(existing['path']);check=logdir/'alignment-check.json'
            storage.atomic_json(check,{'check':True,'model':existing['model']})
            run([existing['python'],str(storage.ROOT/'ALIGNMENT_WORKER.py'),str(check)],root,log,event,progress)
            if event.is_set():raise InterruptedError('Đã dừng; chưa nối CTC.')
            ai_config({'alignment_python':existing['python'],'alignment_model':existing['model']});result=existing
        else:result=install_alignment(payload,folder,log,event,progress)
    else:
        existing=available().get(key)
        if existing:
            folder=Path(existing['path']);python=Path(existing.get('python',str(folder/'Scripts/python.exe')))
            test='import cv2,rembg,onnxruntime' if key=='vision' else 'import demucs,torch,torchaudio'
            run([str(python),'-c',test],root,log,event,progress)
            result={'path':str(folder),'python':str(python)}
            if event.is_set():raise InterruptedError('Đã dừng; chưa xác nhận thư viện.')
            with storage.LOCK:
                rows=registry();rows[key]=result;storage.atomic_json(storage.DATA/'library-index.json',rows)
            return {'files':[vsr.artifact(log)],'message':'Đã kiểm tra bộ trên máy và nối tự động, không cài bản trùng. Model còn thiếu được báo khi sử dụng.','library':key}
        python=environment(folder,log,event,progress)
        if key=='vision':args=['-r',str(storage.ROOT/'requirements-vision.txt')];test='import cv2,rembg,onnxruntime'
        else:
            run([str(python),'-m','pip','install','--disable-pip-version-check','torch==2.5.1','torchaudio==2.5.1','--index-url','https://download.pytorch.org/whl/cpu'],root,log,event,progress)
            args=['demucs==4.0.1','numpy<2'];test='import demucs,torch,torchaudio'
        run([str(python),'-m','pip','install','--disable-pip-version-check',*args],root,log,event,progress)
        run([str(python),'-c',test],root,log,event,progress)
        if key=='separation':run([str(python),str(storage.ROOT/'LIBRARY_WORKER.py'),'demucs',str(folder/'models')],root,log,event,progress)
        result={'path':str(folder),'python':str(python)}
    if event.is_set():raise InterruptedError('Đã dừng; chưa kích hoạt thư viện.')
    with storage.LOCK:
        rows=registry()
        if folder==candidate:
            result.update(managed=True,install_root=str(folder.resolve()),managed_root=str(root.resolve()))
        elif rows.get(key,{}).get('path')==result.get('path'):
            for field in ('managed','install_root','managed_root'):
                if field in rows[key]: result[field]=rows[key][field]
        rows[key]=result;storage.atomic_json(storage.DATA/'library-index.json',rows)
        excluded=storage.read_json(storage.DATA/'library-excluded.json',{})
        if key in excluded: excluded.pop(key);storage.atomic_json(storage.DATA/'library-excluded.json',excluded)
        if key=='vsr-directml':vsr.config({k:result[k] for k in ('home','python')})
        if key=='avatar':
            from .advanced_ai import config as ai_config
            ai_config({'avatar_home':result['home'],'avatar_python':result['python']})
    return {'files':[vsr.artifact(log)],'message':'Đã cài/kiểm tra và nhận diện thư viện. Cần thử đoạn ngắn để xác nhận chất lượng model trên máy.','library':key}
