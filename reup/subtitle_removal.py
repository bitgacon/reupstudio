"""External VSR CLI bridge. No VSR dependencies are loaded into the TTS runtime."""
from pathlib import Path
import math
import re
import os
import shutil
import subprocess
import sys
import time
from uuid import uuid4

from . import storage, media, timeline

MODES = {'sttn-auto', 'sttn-det', 'lama', 'propainter', 'opencv'}


def home_path(raw):
    path=Path(str(raw).strip().strip('"'))
    if path.name.lower()=='main.py' and path.parent.name.lower()=='backend':path=path.parent.parent
    elif path.name.lower()=='backend' and (path/'main.py').is_file():path=path.parent
    return path


def backend_kind(home):
    script=home/'backend'/'main.py';handler=home/'backend'/'tools'/'args_handler.py'
    if not script.is_file():return ''
    if handler.is_file() and '--subtitle-area-coords' in handler.read_text(encoding='utf-8',errors='replace'):return 'cli'
    config_file=home/'backend'/'config.py'
    if config_file.is_file() and 'VERSION = "1.1.1"' in config_file.read_text(encoding='utf-8',errors='replace') and 'sub_area=None' in script.read_text(encoding='utf-8',errors='replace'):return 'legacy111'
    return ''


def config(value=None):
    with storage.LOCK:
        current = storage.read_json(storage.DATA / 'vsr-settings.json', {'home': '', 'python': ''})
        if value is not None:
            if set(value) - {'home', 'python'}:
                raise ValueError('Chỉ cấu hình thư mục VSR và python.exe của VSR.')
            for key in ('home', 'python'):
                raw = str(value.get(key, current[key])).strip()
                if len(raw) > 4096 or (raw and not Path(raw).is_absolute()):
                    raise ValueError('Nhập đường dẫn đầy đủ trên máy này.')
                current[key] = str(home_path(raw)) if key=='home' and raw else raw.strip('"')
            atomic = dict(current)
            storage.atomic_json(storage.DATA / 'vsr-settings.json', atomic)
        return current


def runtime():
    from .libraries import connect_registered_vsr
    connect_registered_vsr()
    c = config()
    home, python = home_path(c['home']), Path(c['python'])
    if not c['home'] or not home.is_dir():raise ValueError('Chưa kết nối VSR: chọn thư mục hoặc dùng Cài đặt → Thư viện tùy chọn.')
    if not c['python'] or not python.is_file():raise ValueError('VSR mới có mã nguồn / chưa có runtime Python. Mục trong Start Menu không phải python.exe. Dùng Cài đặt → Thư viện tùy chọn để tải bộ đầy đủ.')
    if python.name.lower() not in {'python.exe', 'python', 'python3', 'python3.12', 'python3.13'}:
        raise ValueError('Chọn trình thông dịch Python của bộ VSR, không chọn gui.exe hay file .bat.')
    script = home / 'backend' / 'main.py'
    handler = home / 'backend' / 'tools' / 'args_handler.py'
    kind=backend_kind(home)
    if not script.is_file():
        raise ValueError('Bộ VSR này chưa có CLI tương thích backend/main.py và backend/tools/args_handler.py.')
    if not kind:
        raise ValueError('CLI VSR quá cũ; dùng bản hỗ trợ --subtitle-area-coords và --inpaint-mode.')
    return home.resolve(), python.resolve(), script.resolve()


def status():
    try:
        runtime()
        c=config();c['home']=str(home_path(c['home']))
        kind=backend_kind(Path(c['home']))
        return {**c, 'kind':kind, 'connected': True, 'message': ('Portable 1.1.1: hỗ trợ STTN auto; nhiều vùng chạy tuần tự. ' if kind=='legacy111' else '')+'Đường dẫn hợp lệ. Kiểm tra runtime trước khi chạy; chưa xác nhận chất lượng model.'}
    except ValueError as exc:
        return {**config(), 'connected': False, 'message': str(exc)}


def rectangles(rows, width, height):
    if not isinstance(rows, list) or not 1 <= len(rows) <= 12:
        raise ValueError('Vẽ từ 1 đến 12 vùng xóa; không tự xóa mọi chữ trên video.')
    result = []
    for row in rows:
        if not isinstance(row, dict) or set(row) != {'x', 'y', 'w', 'h'}:
            raise ValueError('Vùng xóa không hợp lệ.')
        x, y, w, h = (float(row[k]) for k in ('x', 'y', 'w', 'h'))
        if not all(math.isfinite(v) for v in (x, y, w, h)) or x < 0 or y < 0 or w <= 0 or h <= 0 or x + w > 100.00001 or y + h > 100.00001:
            raise ValueError('Vùng xóa phải nằm trong hình video (đơn vị %).')
        xmin, ymin = math.floor(x * width / 100), math.floor(y * height / 100)
        xmax, ymax = min(width, math.ceil((x + w) * width / 100)), min(height, math.ceil((y + h) * height / 100))
        if xmax - xmin < 2 or ymax - ymin < 2:
            raise ValueError('Vùng xóa quá nhỏ.')
        result.append([ymin, ymax, xmin, xmax])
    return result


def command(home, python, script, source, output, mode, areas):
    if mode not in MODES:
        raise ValueError('Thuật toán VSR không hợp lệ.')
    args = [str(python), str(script), '-i', str(source), '-o', str(output), '--inpaint-mode', mode]
    for area in areas:
        args.extend(['-c', *map(str, area)])
    return args


def removal_command(home,python,script,source,output,mode,areas,device='cpu'):
    if backend_kind(home)=='legacy111':
        if mode!='sttn-auto':raise ValueError('Bộ portable 1.1.1 hiện nối STTN auto. Các thuật toán khác cần bộ CLI mới tương thích.')
        request=output.parent/'legacy-vsr-request.json'
        if device not in {'cpu','auto'}:raise ValueError('Thiết bị VSR không hợp lệ.')
        storage.atomic_json(request,{'home':str(home),'source':str(source),'output':str(output),'areas':areas,'device':device})
        return [str(python),str(storage.ROOT/'VSR_LEGACY_WORKER.py'),str(request)]
    return command(home,python,script,source,output,mode,areas)


def run_worker(args, cwd, log_path, event, progress, timeout=86400, model_progress=False):
    if event.is_set():
        raise InterruptedError('Đã dừng trước khi chạy VSR.')
    env = {**os.environ, 'PYTHONUTF8': '1', 'PYTHONUNBUFFERED': '1'}
    # Inherit neither Reup's import path nor a Qt plugin path into another runtime.
    for key in ('PYTHONHOME', 'PYTHONPATH', 'QT_PLUGIN_PATH', 'QT_QPA_PLATFORM_PLUGIN_PATH'):
        env.pop(key, None)
    # QPT embedded Python's sitecustomize assumes QPT_MODE is a string. Bypass
    # its interactive first-run launcher; dependencies are prepared explicitly.
    if qpt_bundle(cwd,Path(args[0])):
        env['QPT_MODE']='Running'
    with log_path.open('w', encoding='utf-8') as log:
        proc = subprocess.Popen(args, cwd=cwd, stdout=log, stderr=subprocess.STDOUT,
                                env=env, creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
        started = reported = time.monotonic()
        offset = 0
        highest = 0.0
        try:
            while proc.poll() is None:
                if event.wait(.3):
                    raise InterruptedError('Đã dừng VSR; nguồn và SRT đã lấy vẫn được giữ.')
                if time.monotonic() - started > timeout:
                    raise RuntimeError('VSR quá thời gian giới hạn. Thử đoạn ngắn / model phù hợp.')
                if log_path.stat().st_size > 50_000_000:
                    raise RuntimeError('Log VSR quá lớn; dừng để bảo vệ dung lượng.')
                if model_progress:
                    with log_path.open('rb') as reader:
                        reader.seek(offset)
                        data = reader.read()
                    # Re-read a short trailing fragment so split writes are parsed.
                    offset = max(0, offset + len(data) - 128)
                    for value in re.findall(rb'REUP_VSR_PROGRESS=([0-9.]+)\s', data):
                        fraction = float(value)
                        if math.isfinite(fraction) and highest < fraction <= 100:
                            highest = fraction
                            progress(40 + .48 * highest, f'VSR đã xử lý {highest:.1f}% các vùng/khung hình; còn kiểm tra và ghép audio.')
                if time.monotonic() - reported > 5:
                    progress(40 + .48 * highest if model_progress else 45, f'VSR đang chạy · {(time.monotonic()-started)/60:.1f} phút; '+('đang nạp/tính model, chờ mốc xử lý tiếp theo.' if model_progress else 'tiến độ model nằm trong log, chưa có ETA chính xác.'))
                    reported = time.monotonic()
            if proc.returncode:
                with log_path.open('rb') as reader:
                    reader.seek(max(0, log_path.stat().st_size - 2500))
                    tail = reader.read().decode('utf-8', errors='replace')
                raise RuntimeError('VSR CLI thất bại: ' + tail)
        finally:
            media.stop_owned_process(proc)
    if event.is_set():
        raise InterruptedError('Đã dừng VSR.')


def qpt_bundle(home,python):
    home=Path(home);python=Path(python)
    root=home.parent
    hook=python.parent/'Lib/site-packages/sitecustomize.py'
    if home.name.lower()=='resources' and python.parent.resolve()==(root/'Python').resolve() and hook.is_file() and 'QPT' in hook.read_text(encoding='utf-8',errors='replace'):
        return root
    return None


def prepare_runtime(home,python,folder,event,progress):
    root=qpt_bundle(home,python)
    if root is None:return
    packages=root/'opt/packages';requirements=root/'opt/requirements_dev.txt'
    if not packages.is_dir() or not requirements.is_file():
        raise ValueError('Bộ QPT thiếu opt/packages hoặc requirements_dev.txt; giải nén lại bộ đầy đủ.')
    probe=folder/'vsr-dependencies.txt'
    run_worker([str(python),'-c',"import importlib.util; print('VSR_DEPS_OK' if all(importlib.util.find_spec(n) for n in ['torch','torchvision','torch_directml','paddle','paddleocr','cv2','onnxruntime','shapely','numpy','einops','scipy','PIL','yaml','fsplit']) else 'VSR_DEPS_MISSING')"],home,probe,event,progress,timeout=90)
    if 'VSR_DEPS_OK' in probe.read_text(encoding='utf-8',errors='replace'):return
    progress(15,'Chuẩn bị VSR portable lần đầu từ gói offline; không cài vào MPT/VieNeu…')
    # Match the release's frozen wheel set; don't run QPT's serialized .op files
    # or consume/delete its first-run payload. No network or dependency upgrades.
    run_worker([str(python),'-m','pip','install','--disable-pip-version-check','--no-index','--no-deps','--no-build-isolation','--find-links',str(packages),'-r',str(requirements),'torch==2.4.1','torchvision==0.19.1','torch-directml==0.2.5.dev240914','paddlepaddle==3.0.0','paddleocr==2.10.0'],home,folder/'vsr-bootstrap.txt',event,lambda p,m:progress(20,'Đang cài thư viện từ gói VSR offline; chi tiết trong vsr-bootstrap.txt…'),timeout=1800)


def check(job_id, progress, event):
    home, python, script = runtime()
    folder = storage.output_folder('removal', job_id)
    log = folder / 'vsr-cli.txt'
    prepare_runtime(home,python,folder,event,progress)
    progress(10, 'Kiểm tra CLI bằng runtime VSR riêng; không nạp giọng đọc…')
    legacy=backend_kind(home)=='legacy111'
    args=[str(python),str(storage.ROOT/'VSR_LEGACY_WORKER.py'),'--check',str(home)] if legacy else [str(python),str(script),'--help']
    run_worker(args, home, log, event, progress, timeout=180 if legacy else 90)
    help_text = log.read_text(encoding='utf-8', errors='replace')
    if not legacy and ('--subtitle-area-coords' not in help_text or '--inpaint-mode' not in help_text):
        raise ValueError('CLI không trả về các tùy chọn VSR cần thiết.')
    from .libraries import remember_vsr
    remember_vsr(home,python)
    return {'files': [artifact(p) for p in [log,folder/'vsr-bootstrap.txt'] if p.is_file()], 'message': 'CLI VSR chạy được. Chưa xác nhận model/VRAM; cần thử video ngắn.'}


def artifact(path):
    return {'url': storage.file_url(path), 'name': path.name, 'type': path.suffix.lstrip('.'), 'bytes': path.stat().st_size}


def store_asset(path, name):
    key = uuid4().hex
    folder = storage.DATA / 'uploads' / key
    folder.mkdir(parents=True)
    target = folder / ('source' + path.suffix.lower())
    shutil.copy2(path, target)
    meta = {'id': key, 'name': name[:200], 'file': target.name, 'bytes': target.stat().st_size}
    storage.atomic_json(folder / 'asset.json', meta)
    return key


def original_subtitles(payload, source, info, folder, event, progress):
    mode = payload.get('subtitle_mode', 'none')
    output = folder / 'original.srt'
    if mode == 'none':
        return None
    if mode == 'import':
        selected, _ = storage.asset(payload.get('subtitle_asset', ''))
        if selected.suffix.lower() != '.srt':
            raise ValueError('Chọn file SRT gốc trước khi xóa.')
        shutil.copy2(selected, output)
    elif mode == 'embedded':
        streams = [s for s in info.get('streams', []) if s.get('codec_type') == 'subtitle']
        # Bitmap subtitles need OCR, not an FFmpeg conversion to text.
        stream = next((s for s in streams if s.get('codec_name') in {'subrip', 'ass', 'ssa', 'mov_text', 'webvtt', 'text'}), None)
        if not stream:
            raise ValueError('Video không có track phụ đề chữ. Chọn SRT có sẵn hoặc Whisper (audio); OCR chữ trên hình chưa tích hợp.')
        timeline.run_cancel([media.binary(), '-y', '-v', 'error', '-i', str(source), '-map', f'0:{stream["index"]}', '-c:s', 'srt', str(output)], event)
    elif mode == 'whisper':
        recognize(payload, source, info, folder, event, progress)
    else:
        raise ValueError('Cách lấy phụ đề gốc không hợp lệ.')
    if output.stat().st_size > 5_000_000:
        raise ValueError('SRT quá 5 MB; chia nhỏ trước khi xóa.')
    cues, issues = media.parse_srt(media.decode_text(output.read_bytes()))
    if len(cues) > 5000:
        raise ValueError('SRT quá 5000 cue; chia nhỏ trước khi xóa.')
    if not cues or any(i.get('level') == 'error' for i in issues):
        raise ValueError('SRT gốc không hợp lệ; sửa file trước. ' + '; '.join(i['message'] for i in issues[:5]))
    return output


def recognize(payload, source, info, folder, event, progress):
    from .word_timing import MODELS
    language = payload.get('language') or None
    if language not in {None, 'vi', 'en', 'zh', 'ja', 'ko', 'fr', 'de', 'es', 'ru', 'th'}:
        raise ValueError('Ngôn ngữ Whisper không hợp lệ.')
    if not any(s.get('codec_type') == 'audio' for s in info['streams']):
        raise ValueError('Video không có audio để Whisper nhận dạng.')
    wav = folder / 'original-audio.wav'
    timeline.run_cancel([media.binary(), '-y', '-v', 'error', '-i', str(source), '-vn', '-ac', '1', '-ar', '16000', str(wav)], event)
    model = storage.settings()['whisper_model']
    if model not in MODELS:
        raise ValueError('Model Whisper không hợp lệ.')
    from .libraries import installed_path
    cache = installed_path('whisper', storage.DATA / 'models' / 'whisper')
    bundled = storage.ROOT / 'whisper-models' / model
    if bundled.is_dir():
        model = str(bundled)
    else:
        for root in (cache, storage.ROOT / 'data' / 'models' / 'whisper'):
            hub = root / ('models--Systran--faster-whisper-' + model)
            ref = hub / 'refs' / 'main'
            if ref.is_file():
                candidate = hub / 'snapshots' / ref.read_text().strip()
                if candidate.is_dir() and all((candidate / f).is_file() for f in ('model.bin', 'config.json', 'tokenizer.json')):
                    model = str(candidate)
                    break
    request = folder / 'original-asr.json'
    storage.atomic_json(request, {'audio': str(wav), 'folder': str(folder), 'model': model, 'cache': str(cache),
                                'language': language, 'allow_download': payload.get('allow_download') is True,
                                'segments_only': True, 'duration_ms': round(float(info['format']['duration']) * 1000)})
    from .libraries import whisper_python
    run_worker([whisper_python(), str(storage.ROOT / 'WORD_TIMING_WORKER.py'), str(request)], storage.ROOT,
               folder / 'original-asr.log', event,
               lambda p, m: progress(15, 'Whisper đang tạo SRT gốc trước khi xóa…'), timeout=7200)
    result = storage.read_json(folder / 'word-result.json', {})
    cues = result.get('cues', [])
    if not cues:
        raise ValueError('Whisper không tìm thấy lời nói. Chưa chạy xóa chữ.')
    (folder / 'original.srt').write_text(media.srt(cues), encoding='utf-8')


def publish_subtitle(source, meta, source_asset, subtitle, subtitle_asset, job_id):
    if not subtitle:
        return
    row = {'job_id': job_id, 'asset': source_asset, 'name': meta['name'], 'source_url': storage.file_url(source),
           'subtitle_asset': subtitle_asset, 'subtitle': artifact(subtitle)}
    with storage.LOCK:
        rows = storage.read_json(storage.DATA / 'vsr-subtitles.json', [])
        rows.insert(0, row)
        storage.atomic_json(storage.DATA / 'vsr-subtitles.json', rows)


def prepare_subtitle(payload, job_id, progress, event):
    source, meta = storage.asset(payload.get('asset', ''))
    info = media.probe(source)
    if not any(s.get('codec_type') == 'video' for s in info['streams']) or not 0 < float(info.get('format', {}).get('duration', 0)) <= 3600:
        raise ValueError('Chọn video tối đa 60 phút.')
    if payload.get('subtitle_mode', 'none') == 'none':
        raise ValueError('Chọn cách lấy SRT: nhập, track chữ hoặc Whisper.')
    if event.is_set():
        raise InterruptedError('Đã dừng trước khi lấy SRT.')
    folder = storage.output_folder('removal', job_id)
    progress(5, 'Chỉ lấy SRT; không chạy VSR, không đổi video nguồn…')
    subtitle = original_subtitles(payload, source, info, folder, event, progress)
    if subtitle:subtitle=storage.publish_removal(subtitle,job_id,meta['name'])
    if event.is_set():
        raise InterruptedError('Đã dừng; SRT trong thư mục kết quả được giữ.')
    key = store_asset(subtitle, 'Phụ đề gốc · ' + meta['name'] + '.srt')
    publish_subtitle(source, meta, payload['asset'], subtitle, key, job_id)
    return {'files': [artifact(subtitle)], 'message': 'Đã giữ SRT gốc riêng; chưa chạy xóa phụ đề.'}


def remove(payload, job_id, progress, event):
    from . import fast_removal
    if payload.get('mode')=='opencv':payload={**payload,'mode':'telea'}
    mode = payload.get('mode', 'sttn-auto')
    light = mode in fast_removal.MODES
    source, meta = storage.asset(payload.get('asset', ''))
    if source.suffix.lower() in fast_removal.IMAGE_EXTS:
        if not light:raise ValueError('Ảnh: chọn FFmpeg / Telea / Navier–Stokes hoặc chế độ che/chèn/cắt, không dùng VSR video.')
        return fast_removal.remove_image(payload,job_id,progress,event)
    if not light: home, python, script = runtime()
    info = media.probe(source)
    stream = next((s for s in info['streams'] if s.get('codec_type') == 'video'), None)
    duration = float(info.get('format', {}).get('duration', 0))
    if not stream or not 0 < duration <= 3600 or source.suffix.lower() not in {'.mp4', '.mov', '.mkv', '.webm', '.avi'}:
        raise ValueError('Chọn video tối đa 60 phút; thử đoạn ngắn trước vì VSR CPU rất chậm.')
    if any(abs(float(s.get('rotation', 0))) > .1 for s in stream.get('side_data_list', [])) or abs(float(stream.get('tags', {}).get('rotate', 0))) > .1:
        raise ValueError('Video có metadata xoay: render qua mục Tải/biên tập trước để tọa độ vùng khớp hình.')
    areas = rectangles(payload.get('regions'), int(stream['width']), int(stream['height']))
    expected_stream=stream
    if mode=='crop':
        w,h=fast_removal.crop_size(areas);expected_stream={**stream,'width':w,'height':h}
    if mode not in MODES and not light:
        raise ValueError('Thuật toán VSR không hợp lệ.')
    opts=fast_removal.options(payload) if light else {'keep_audio':payload.get('keep_audio',True)}
    fingerprint=fast_removal.fingerprint(source,payload)
    if payload.get('skip_existing') is True:
        for row in storage.read_json(storage.DATA/'vsr-index.json',[]):
            if row.get('fingerprint')==fingerprint:
                try:
                    existing,_=storage.asset(row['asset']);validate_video(existing,expected_stream,duration)
                    return {'entry':row,'files':[row['video']],'message':'Đã có kết quả đúng nguồn / cấu hình; bỏ qua xử lý lại.'}
                except (ValueError,FileNotFoundError):pass
    if event.is_set():
        raise InterruptedError('Đã dừng trước khi lấy phụ đề gốc.')
    folder = storage.output_folder('removal', job_id)
    progress(5, 'Giữ nguyên nguồn; chuẩn bị phụ đề gốc trước khi chạy VSR…')
    subtitle = original_subtitles(payload, source, info, folder, event, progress)
    if subtitle:subtitle=storage.publish_removal(subtitle,job_id,meta['name'])
    subtitle_asset = store_asset(subtitle, 'Phụ đề gốc · ' + meta['name'] + '.srt') if subtitle else ''
    publish_subtitle(source, meta, payload['asset'], subtitle, subtitle_asset, job_id)
    storage.atomic_json(folder / 'source-manifest.json', {'source_asset': payload['asset'], 'source_name': meta['name'],
                        'subtitle_asset': subtitle_asset, 'regions': payload['regions'], 'mode': mode, 'stage': 'subtitles_preserved'})
    raw, output = folder / 'vsr-result.mp4', folder / 'clean.mp4'
    progress(40, 'Đã giữ SRT (nếu chọn); bắt đầu xử lý vùng đã đánh dấu…')
    if light:
        fast_removal.execute(source,raw,info,areas,opts,event,progress,folder)
    else:
        prepare_runtime(home,python,folder,event,progress)
        run_worker(removal_command(home, python, script, source, raw, mode, areas,payload.get('device','cpu')), home, folder / 'vsr.log', event, progress, model_progress=True)
    validate_video(raw, expected_stream, duration)
    progress(90, 'Kiểm tra video sạch và ghép lại audio gốc…')
    args=[media.binary(), '-y', '-v', 'error', '-i', str(raw), '-i', str(source), '-map', '0:v:0']
    if opts['keep_audio']:args+=['-map','1:a?','-c:a','aac']
    timeline.run_cancel(args+['-c:v', 'copy', '-t', str(duration), '-movflags', '+faststart', str(output)], event)
    validate_video(output, expected_stream, duration)
    if opts['keep_audio'] and any(s.get('codec_type') == 'audio' for s in info['streams']) and not any(s.get('codec_type') == 'audio' for s in media.probe(output)['streams']):
        raise ValueError('Bản sạch mất audio; chưa công bố kết quả.')
    if event.is_set():
        raise InterruptedError('Đã dừng; nguồn/SRT giữ nguyên.')
    working_output=output;output=storage.publish_removal(output,job_id,meta['name'])
    key = store_asset(output, 'Đã xóa sub · ' + meta['name'])
    row = {'id': key, 'asset': key, 'source_asset': payload['asset'], 'name': meta['name'], 'subtitle_asset': subtitle_asset,
           'video': artifact(output), 'subtitle': artifact(subtitle) if subtitle else None, 'regions': payload['regions'], 'mode': mode,'fingerprint':fingerprint}
    with storage.LOCK:
        rows = storage.read_json(storage.DATA / 'vsr-index.json', [])
        rows.insert(0, row)
        storage.atomic_json(storage.DATA / 'vsr-index.json', rows)
    # This is only our intermediate VSR output, never an input or user's source.
    # Publish/remux/validate first; keep it on failure for diagnosis.
    raw.unlink()
    working_output.unlink()
    return {'entry': row, 'files': [row['video']] + ([row['subtitle']] if subtitle else []),
            'message': 'Đã tạo bản sạch riêng, giữ video gốc/SRT. Xem kiểm tra vùng xóa trước khi dịch/lồng tiếng.'}


def validate_video(path, original, duration):
    if not path.is_file() or not path.stat().st_size:
        raise ValueError('VSR không tạo được video; xem log trong thư mục kết quả.')
    info = media.probe(path)
    stream = next((s for s in info.get('streams', []) if s.get('codec_type') == 'video'), {})
    if (stream.get('width'), stream.get('height')) != (original['width'], original['height']):
        raise ValueError('VSR đổi kích thước ngoài dự kiến; chưa công bố kết quả.')
    if abs(float(info.get('format', {}).get('duration', 0)) - duration) > .25:
        raise ValueError('VSR đổi thời lượng ngoài dự kiến; chưa dùng SRT để tránh lệch timeline.')


def preview_state(key):
    source,_=storage.asset(key)
    stamp=str(source.stat().st_mtime_ns)+'-'+str(source.stat().st_size)
    state=storage.read_json(source.parent/'vsr-preview.json',{})
    if state.get('stamp')!=stamp:return {}
    result={k:state[k] for k in ('width','height','duration','stamp')}
    for key in ('poster','proxy'):
        path=(source.parent/state.get(key,'missing')).resolve()
        if path.is_relative_to(source.parent.resolve()) and path.is_file() and path.name.startswith('vsr-'):result[key+'_url']=storage.file_url(path)
    return result


def forget_subtitle(job_id):
    """Remove a library listing only; retain files and project references."""
    job_id = storage.identifier(job_id)
    with storage.LOCK:
        path = storage.DATA / 'vsr-subtitles.json'
        rows = storage.read_json(path, [])
        kept = [row for row in rows if row['job_id'] != job_id]
        if len(kept) == len(rows):
            raise ValueError('SRT không còn trong danh sách.')
        storage.atomic_json(path, kept)
    return {'message': 'Đã bỏ SRT khỏi danh sách; file và dự án vẫn được giữ.'}


def prepare_preview(payload,job_id,progress,event):
    source,_=storage.asset(payload.get('asset',''))
    info=media.probe(source);stream=next((s for s in info['streams'] if s.get('codec_type')=='video'),None)
    duration=float(info.get('format',{}).get('duration',0))
    if not stream or not 0<duration<=3600:raise ValueError('Bản xem hỗ trợ video tối đa 60 phút.')
    seconds=float(payload.get('seconds',0))
    if not math.isfinite(seconds) or seconds<0 or seconds>=duration:raise ValueError('Mốc xem ngoài video.')
    stamp=str(source.stat().st_mtime_ns)+'-'+str(source.stat().st_size)
    folder=source.parent;poster=folder/f'vsr-frame-{round(seconds*1000)}-{stamp}.jpg'
    progress(5,'Tạo ảnh khung hình để vẽ vùng ngay, không cần codec MP4 của app…')
    if not poster.exists():timeline.run_cancel([media.binary(),'-y','-v','error','-ss',str(seconds),'-i',str(source),'-frames:v','1','-vf','scale=960:960:force_original_aspect_ratio=decrease','-threads','2',str(poster)],event)
    if not poster.is_file():raise ValueError('Không trích được khung hình. Thử mốc khác.')
    picture=next(s for s in media.probe(poster)['streams'] if s.get('codec_type')=='video')
    cached=storage.read_json(folder/'vsr-preview.json',{})
    state={**(cached if cached.get('stamp')==stamp else {}),'stamp':stamp,'width':picture['width'],'height':picture['height'],'duration':duration,'poster':poster.name}
    storage.atomic_json(folder/'vsr-preview.json',state)
    if payload.get('poster_only') is not True:
        progress(10,'Tạo WebM tương thích Qt; đây là bản xem, không thay video xử lý…')
        proxy=folder/f'vsr-proxy-{stamp}.webm';partial=proxy.with_suffix('.partial.webm')
        if not proxy.is_file():
            try:
                timeline.run_cancel([media.binary(),'-y','-v','error','-i',str(source),'-map','0:v:0','-map','0:a:0?',
                                    '-vf',"scale=640:640:force_original_aspect_ratio=decrease:force_divisible_by=2,fps=24",'-c:v','libvpx-vp9','-deadline','realtime','-cpu-used','8','-crf','36','-b:v','0','-pix_fmt','yuv420p','-threads','2','-c:a','libopus','-progress','pipe:1',str(partial)],event,lambda p,m:progress(10+.85*p,'Tạo bản xem WebM…'),duration*1000)
                partial.replace(proxy)
            finally:partial.unlink(missing_ok=True)
        state['proxy']=proxy.name;storage.atomic_json(folder/'vsr-preview.json',state)
    return {'asset':payload['asset'],'preview':preview_state(payload['asset']),'message':'Bản xem sẵn sàng; vùng áp theo % video gốc. Nguồn xử lý không thay đổi.'}


def send(key, tab):
    with storage.LOCK:
        row = next((r for r in storage.read_json(storage.DATA / 'vsr-index.json', []) if r['id'] == storage.identifier(key)), None)
        if not row:
            raise ValueError('Không tìm thấy kết quả VSR.')
        source, _ = storage.asset(row['asset'])
        duration = round(float(media.probe(source)['format']['duration']) * 1000)
        if tab not in {'dub', 'edit'}:
            raise ValueError('Chọn Lồng tiếng hoặc Biên tập.')
        cues = []
        issues = []
        if row['subtitle_asset']:
            subtitle, _ = storage.asset(row['subtitle_asset'])
            cues, issues = media.parse_srt(media.decode_text(subtitle.read_bytes()))
        doc = None
        if tab == 'edit':
            tracks = [timeline.Track(id=uuid4().hex, name='Video sạch', kind='video', clips=[timeline.Clip(id=uuid4().hex, asset=row['asset'], label=row['name'][:200], start_ms=0, duration_ms=duration)])]
            text_tracks = []
            for c in sorted(cues, key=lambda c: c['start_ms']):
                if c['end_ms']-c['start_ms'] < 100 or c['end_ms'] > 3_600_000:
                    raise ValueError('SRT có cue dưới 100ms / ngoài 60 phút; dùng Lồng tiếng hoặc sửa SRT trước khi đưa vào editor.')
                track = next((t for t in text_tracks if t.clips[-1].start_ms+t.clips[-1].duration_ms <= c['start_ms']), None)
                if track is None:
                    track = timeline.Track(id=uuid4().hex, name='Phụ đề gốc · cần dịch', kind='text', clips=[])
                    text_tracks.append(track)
                track.clips.append(timeline.Clip(id=uuid4().hex, text=c['text'], start_ms=c['start_ms'], duration_ms=c['end_ms']-c['start_ms']))
            video = next(s for s in media.probe(source)['streams'] if s.get('codec_type') == 'video')
            doc = timeline.Timeline(width=video['width'], height=video['height'], assets=[row['asset']], tracks=tracks+text_tracks).model_dump()
        project = storage.new_project(('Đã xóa sub · ' + row['name'])[:100],kind=tab)
        project.update(video=row['asset'], cues=cues, import_issues=issues)
        storage.retain_assets(project)
        storage.save_project(project)
        if doc is not None:
            timeline.save(project['id'], doc)
        return {'project_id': project['id'], 'tab': tab}
