"""Isolated optional Whisper runtime for full-video subtitle recognition."""
import os
import subprocess
import time
from . import storage, media


def recognize(python, wav, folder, model, cache, language, allow_download, event, progress):
    folder.mkdir(parents=True, exist_ok=False)
    duration = round(float(media.probe(wav)['format']['duration']) * 1000)
    request = folder / 'request.json'
    storage.atomic_json(request, {'audio': str(wav), 'folder': str(folder), 'model': model,
        'cache': str(cache), 'language': language or None, 'allow_download': bool(allow_download),
        'segments_only': True, 'duration_ms': duration})
    env = {**os.environ, 'PYTHONUTF8': '1', 'PYTHONUNBUFFERED': '1'}
    for name in ('PYTHONPATH', 'PYTHONHOME', 'QT_PLUGIN_PATH', 'QT_QPA_PLATFORM_PLUGIN_PATH'):
        env.pop(name, None)
    logfile = folder / 'worker.log'
    with logfile.open('w', encoding='utf-8') as log:
        proc = subprocess.Popen([str(python), str(storage.ROOT / 'WORD_TIMING_WORKER.py'), str(request)],
            cwd=storage.ROOT, stdout=log, stderr=subprocess.STDOUT, env=env,
            creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
        started = time.monotonic()
        try:
            while proc.poll() is None:
                if event.wait(.5): raise InterruptedError('Đã dừng nhận dạng; dự án chưa thay đổi.')
                if time.monotonic() - started > 7200: raise RuntimeError('Whisper quá 2 giờ; dùng model nhỏ hơn hoặc chia video.')
                status = storage.read_json(folder / 'word-progress.json', {})
                progress(min(95, max(10, status.get('percent', 10))), status.get('message', 'Đang nạp Whisper CPU…'))
            if proc.returncode:
                raise RuntimeError('Whisper thất bại: ' + logfile.read_text(encoding='utf-8', errors='replace')[-2000:])
        finally:
            media.stop_owned_process(proc)
    if event.is_set(): raise InterruptedError('Đã dừng nhận dạng.')
    return storage.read_json(folder / 'word-result.json', {}).get('cues', [])
