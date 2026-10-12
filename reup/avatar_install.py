"""Opt-in pinned MuseTalk install. Publish only after model and CUDA checks."""
import os,re,shutil,subprocess,zipfile
from pathlib import Path,PurePosixPath
from . import storage,media
from .avatar_manifest import COMMIT,SOURCE


def checkpoint(event):
    if event.is_set():raise InterruptedError('Đã dừng cài avatar; chưa kích hoạt runtime mới.')


def gpu_preflight():
    command=shutil.which('nvidia-smi')
    if not command:raise ValueError('Không tìm thấy NVIDIA/driver nvidia-smi; chưa tải avatar. Dùng máy có GPU NVIDIA CUDA.')
    try:
        result=subprocess.run([command,'--query-gpu=name,memory.total,driver_version','--format=csv,noheader'],
            capture_output=True,text=True,timeout=15,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
    except (OSError,subprocess.SubprocessError):raise ValueError('Không kiểm tra được GPU NVIDIA; chưa tải avatar.') from None
    if result.returncode or not result.stdout.strip():raise ValueError('Driver NVIDIA chưa sẵn sàng; chưa tải avatar.')
    return result.stdout.strip()[:2000]


def extract_source(archive,home,event):
    prefix='MuseTalk-'+COMMIT
    with zipfile.ZipFile(archive) as z:
        entries=z.infolist();total=0;seen=set()
        for entry in entries:
            path=PurePosixPath(entry.filename);total+=entry.file_size
            if not path.parts or path.parts[0]!=prefix or path.is_absolute() or any(p in {'.','..'} or ':' in p or '\\' in p for p in path.parts) or (entry.external_attr>>16)&0o170000==0o120000:
                raise ValueError('Gói mã nguồn MuseTalk có đường dẫn không hợp lệ.')
            relative=Path(*path.parts[1:]);target=(home/relative).resolve()
            if not target.is_relative_to(home.resolve()) or target in seen:raise ValueError('Đường dẫn mã nguồn trùng/ngoài thư mục.')
            seen.add(target)
        if len(entries)>10_000 or total>512*1024**2:raise ValueError('Gói mã nguồn MuseTalk vượt giới hạn.')
        for entry in entries:
            checkpoint(event);relative=Path(*PurePosixPath(entry.filename).parts[1:]);target=home/relative
            if entry.is_dir():target.mkdir(parents=True,exist_ok=True)
            else:
                target.parent.mkdir(parents=True,exist_ok=True)
                with z.open(entry) as source,target.open('wb') as destination:shutil.copyfileobj(source,destination)


def worker(python,home,mode,root,log,event,progress):
    from . import libraries
    request=log.parent/('avatar-'+mode+'.json');result=log.parent/('avatar-'+mode+'-result.json')
    storage.atomic_json(request,{'home':str(home),'mode':mode,'cache':str(root/'downloads/avatar-model-cache'),'result':str(result)})
    libraries.run([str(python),str(storage.ROOT/'AVATAR_INSTALL_WORKER.py'),str(request)],home,log,event,progress)
    checkpoint(event);report=storage.read_json(result,{})
    if not report.get('gpu') or not report.get('cuda'):raise ValueError('Runtime chưa vượt kiểm tra GPU/model; chưa kích hoạt.')
    return report


def install(payload,folder,root,log,event,progress):
    from . import libraries
    if payload.get('accept_avatar_models') is not True:raise ValueError('Cần xác nhận tải runtime/model avatar và quyền sử dụng các thành phần upstream.')
    checkpoint(event)
    if os.name!='nt':raise ValueError('Profile cài avatar này dành cho Windows; nền tảng khác nối runtime riêng.')
    home=folder/'MuseTalk'
    if not re.fullmatch(r'[A-Za-z0-9_:\\/-]+',str(home.resolve())):raise ValueError('Chọn thư mục thư viện không dấu/khoảng trắng, ví dụ D:\\AI\\ReupLibraries; chưa tải avatar.')
    gpu_preflight()
    if shutil.disk_usage(root).free<25_000_000_000:raise ValueError('Cần ít nhất 25 GB trống cho runtime/model/cache avatar.')
    existing=libraries.available().get('avatar',{})
    if existing.get('python') and existing.get('home') and Path(existing['python']).is_file() and (Path(existing['home'])/'models/musetalkV15/unet.pth').is_file():
        report=worker(Path(existing['python']),Path(existing['home']),'check',root,log,event,progress)
        return {**existing,'gpu_checked':report,'inference_tested':False}
    home.mkdir(parents=True,exist_ok=True)
    source=root/'downloads'/('MuseTalk-'+COMMIT+'.zip');source.parent.mkdir(parents=True,exist_ok=True)
    libraries.download(SOURCE,source,event,progress);extract_source(source,home,event)
    python=libraries.environment(folder,log,event,progress)
    libraries.run([str(python),'-m','pip','install','torch==2.0.1','torchvision==0.15.2','torchaudio==2.0.2',
        '--index-url','https://download.pytorch.org/whl/cu118'],home,log,event,progress)
    libraries.run([str(python),'-m','pip','install','-r',str(home/'requirements.txt')],home,log,event,progress)
    libraries.run([str(python),'-m','pip','install','mmcv==2.0.1','--only-binary=:all:',
        '-f','https://download.openmmlab.com/mmcv/dist/cu118/torch2.0/index.html'],home,log,event,progress)
    libraries.run([str(python),'-m','pip','install','mmengine==0.10.7','mmdet==3.1.0','mmpose==1.1.0'],home,log,event,progress)
    progress(65,'Kiểm tra CUDA/dependency trước khi tải model avatar…')
    worker(python,home,'probe',root,log,event,progress)
    tools=home/'ffmpeg';tools.mkdir(exist_ok=True)
    for name in ('ffmpeg','ffprobe'):shutil.copy2(media.binary(name),tools/(name+'.exe'))
    progress(70,'Tải model avatar đúng revision/checksum; cần nhiều GB, xem log…')
    report=worker(python,home,'models',root,log,event,progress)
    return {'path':str(folder),'home':str(home),'python':str(python),'source_commit':COMMIT,
        'gpu_checked':report,'inference_tested':False}
