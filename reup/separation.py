"""Isolated optional Demucs process. Main UI/TTS runtime never imports torch."""
from __future__ import annotations

import os
from pathlib import Path
import shutil
import subprocess
import time

from . import media, storage


def separate(source, folder, progress, event):
    from .libraries import installed_path
    runtime = installed_path('separation',storage.ROOT/'separation-env')
    python = runtime / "Scripts" / "python.exe"
    if runtime==storage.ROOT/'separation-env' and (storage.ROOT / "separation-runtime" / "python.exe").is_file():
        python = storage.ROOT / "separation-runtime" / "python.exe"
    if not python.is_file():
        raise ValueError("Chưa cài bộ tách giọng. Vào Cài đặt → Thư viện → AI tách giọng / nhạc để tải/cài.")
    if float(media.probe(source)["format"].get("duration", 0)) > 3600:
        raise ValueError("Tách AI hỗ trợ tối đa 60 phút mỗi lần; chia video dài thành phần.")
    folder.mkdir(parents=True, exist_ok=True)
    wav = folder / "input.wav"
    progress(5, "Đang trích audio để tách giọng AI…")
    media.command([media.binary(), "-y", "-v", "error", "-i", str(source), "-vn", "-ac", "2", "-ar", "44100", str(wav)])
    env = os.environ.copy()
    env["TORCH_HOME"] = str(runtime/'models') if runtime != storage.ROOT/'separation-env' else str(storage.ROOT/'separation-models')
    env["PYTHONUTF8"] = "1"
    env["PYTHONUNBUFFERED"] = "1"
    env["PATH"] = str(Path(media.binary()).parent) + os.pathsep + env.get("PATH", "")
    progress(10, "Tách AI trên CPU; lần đầu tải model. Tiến độ theo giai đoạn, có thể mất nhiều phút…")
    started = time.monotonic()
    with (folder / "demucs.log").open("w", encoding="utf-8") as log:
        process = subprocess.Popen([str(python), "-m", "demucs", "-n", "htdemucs", "--two-stems", "vocals", "-d", "cpu",
                                    "--shifts", "0", "--segment", "7", "-j", "1", "-o", str(folder / "work"), str(wav)],
                                   stdout=log, stderr=subprocess.STDOUT, env=env, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        try:
            while process.poll() is None:
                if event.wait(1):
                    media.stop_owned_process(process)
                    raise InterruptedError("Đã dừng tách giọng; video gốc được giữ nguyên.")
                if time.monotonic() - started > 7200:
                    media.stop_owned_process(process)
                    raise RuntimeError("Tách giọng quá 2 giờ. Hãy chia video thành phần ngắn.")
            if process.returncode:
                raise RuntimeError("Demucs thất bại. " + (folder / "demucs.log").read_text(encoding="utf-8", errors="replace")[-1500:])
        finally:
            media.stop_owned_process(process)
    result = []
    for name in ("vocals.wav", "no_vocals.wav"):
        output = folder / name
        shutil.copy2(folder / "work" / "htdemucs" / "input" / name, output)
        media.probe(output)
        result.append(output)
    progress(98, "Đã tách, đang lưu nhạc và giọng riêng…")
    return result
