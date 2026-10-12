from __future__ import annotations

import os
from pathlib import Path
import re
import secrets
import socket
import subprocess
import threading
import time
from uuid import uuid4

import requests

from . import media, storage


def find_home() -> Path:
    choices = [storage.ROOT / "VieNeuLocal", storage.ROOT.parent / "VieNeuLocal",
               storage.ROOT.parent / "release" / "MPT" / "VieNeuLocal"]
    configured = storage.settings()["vieneu_home"] or os.environ.get("REUP_VIENEU_HOME", "")
    if configured:
        choices.insert(0, Path(configured))
    registered=storage.read_json(storage.DATA/'library-index.json',{}).get('vieneu',{}).get('path')
    if registered:choices.insert(0,Path(registered))
    disconnected=storage.read_json(storage.DATA/'library-excluded.json',{}).get('vieneu')
    for path in choices:
        if disconnected and path.resolve()==Path(disconnected).resolve():continue
        if (path / "runtime" / "python.exe").is_file() or (path / ".venv" / "Scripts" / "python.exe").is_file():
            return path.resolve()
    raise RuntimeError("Chưa cài VieNeu. Vào Cài đặt → Thư viện tùy chọn → VieNeu để tải/cài, hoặc kết nối bộ VieNeu đã có.")


class Engine:
    """Own a separate authenticated engine; never stop or enrol into MPT's API."""

    def __init__(self):
        self.process = None
        self.base = ""
        self.key = secrets.token_urlsafe(32)
        self.lock = threading.RLock()
        self.session = requests.Session()
        self.session.trust_env = False
        self.session.headers["Authorization"] = "Bearer " + self.key
        self.voices = storage.read_json(storage.DATA / "voice-cache.json", [])
        self.enrolled = set()
        self.precision = ""

    def status(self) -> dict:
        return {"running": bool(self.process and self.process.poll() is None), "precision": self.precision,
                "voices": len(self.voices), "backend": "VieNeu v3 Turbo · CPU · 48 kHz"}

    def start(self, progress=lambda *_: None, cancelled=lambda: False):
        with self.lock:
            if self.process and self.process.poll() is None:
                return
            home = find_home()
            python = home / "runtime" / "python.exe"
            if not python.is_file():
                python = home / ".venv" / "Scripts" / "python.exe"
            with socket.socket() as sock:
                sock.bind(("127.0.0.1", 0))
                port = sock.getsockname()[1]
            self.base = f"http://127.0.0.1:{port}"
            env = os.environ.copy()
            for key in ("PYTHONHOME", "PYTHONPATH", "HF_HUB_CACHE", "HUGGINGFACE_HUB_CACHE",
                        "TRANSFORMERS_CACHE", "VIENEU_ONNX_DIR"):
                env.pop(key, None)
            self.precision = storage.settings()["precision"]
            cache = home / "models_cache_latest" if (home / "models_cache_latest").is_dir() else home / "models_cache"
            env.update({"HF_HOME": str(cache), "HF_HUB_OFFLINE": "1", "TRANSFORMERS_OFFLINE": "1",
                        "VIENEU_BACKEND": "onnx", "VIENEU_DEVICE": "cpu", "VIENEU_PRECISION": self.precision,
                        "VIENEU_API_KEY": self.key, "VIENEU_MAX_STREAMS": "1", "VIENEU_WATERMARK": "0",
                        "HOST": "127.0.0.1", "PORT": str(port), "PYTHONUTF8": "1", "PYTHONNOUSERSITE": "1",
                        "PYTHONDONTWRITEBYTECODE": "1"})
            storage.DATA.mkdir(parents=True, exist_ok=True)
            with (storage.DATA / "vieneu.log").open("ab") as log:
                self.process = subprocess.Popen([str(python), "-s", str(storage.ROOT / "reup" / "engine_entry.py")], cwd=home,
                                                env=env, stdin=subprocess.DEVNULL, stdout=log, stderr=log,
                                                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
            self.enrolled.clear()
            deadline = time.monotonic() + 900
            while time.monotonic() < deadline:
                if cancelled():
                    self.stop()
                    raise InterruptedError("Đã dừng nạp model.")
                if self.process.poll() is not None:
                    raise RuntimeError("VieNeu không khởi động được. Xem data/vieneu.log; thử FP32 nếu CPU không hỗ trợ INT8.")
                try:
                    ready = self.session.get(self.base + "/health", timeout=1)
                    if ready.ok:
                        self.refresh()
                        return
                except requests.RequestException:
                    pass
                progress(5, "Đang nạp VieNeu " + self.precision.upper() + " — giao diện vẫn sử dụng được…")
                time.sleep(0.5)
            self.stop()
            raise TimeoutError("VieNeu nạp model quá 15 phút; xem data/vieneu.log.")

    def refresh(self):
        response = self.session.get(self.base + "/v1/voices", timeout=20)
        response.raise_for_status()
        saved = {v["name"]: v for v in storage.voice_library()}
        rows = response.json()["data"]
        for row in rows:
            row["custom"] = row["id"] in saved
        ids = {v["id"] for v in rows}
        rows += [{"id": name, "name": name, "description": "Giọng clone của bạn", "gender": "", "custom": True}
                 for name in saved if name not in ids]
        preferred = ["Minh Đức", "Trúc Ly", "Mai Anh", "Phạm Tuyên", "Thái Sơn", "Xuân Vĩnh", "Thanh Bình"]
        rows.sort(key=lambda row: (preferred.index(row["id"]) if row["id"] in preferred else 100, row["name"]))
        self.voices = rows
        storage.atomic_json(storage.DATA / "voice-cache.json", rows)

    def stop(self):
        with self.lock:
            if self.process and self.process.poll() is None:
                media.stop_owned_process(self.process)
            self.process = None
            self.enrolled.clear()

    def register(self, name: str, path: Path, denoise=True):
        with path.open("rb") as stream:
            response = self.session.post(self.base + "/v1/voices",
                                         data={"name": name, "denoise": str(bool(denoise)).lower()},
                                         files={"file": ("reference.wav", stream, "audio/wav")}, timeout=(10, 900))
        if not response.ok:
            raise RuntimeError("Clone VieNeu: " + response.text[:1000])
        self.enrolled.add(name)

    def clone(self, name: str, source: Path, denoise=True) -> dict:
        name = name.strip()
        if not re.fullmatch(r"[^\W_][\w .\-]{0,63}", name):
            raise ValueError("Tên giọng: 1–64 ký tự chữ/số, khoảng trắng, dấu chấm/gạch nối.")
        if any(v["id"].casefold() == name.casefold() for v in self.voices):
            raise ValueError("Tên giọng đã có. Hãy chọn tên mới để giữ nguyên giọng cũ.")
        folder = storage.DATA / "voices" / uuid4().hex
        folder.mkdir(parents=True)
        reference = folder / "reference.wav"
        media.command([media.binary(), "-y", "-v", "error", "-i", str(source), "-t", "8",
                       "-vn", "-ar", "48000", "-ac", "1", str(reference)], timeout=120)
        info = media.probe(reference)
        if float(info["format"]["duration"]) < 1:
            raise ValueError("Mẫu quá ngắn. Chọn 3–8 giây nói rõ, chỉ một người, ít nhạc nền.")
        self.register(name, reference, denoise)
        value = {"name": name, "folder": folder.name, "denoise": bool(denoise), "created": time.time()}
        storage.atomic_json(folder / "voice.json", value)
        self.refresh()
        return value

    def speak(self, text: str, voice: str, output: Path, temperature=0.8):
        if voice not in {row["id"] for row in self.voices}:
            raise ValueError("Chưa chọn giọng hợp lệ. Bấm Nạp giọng trước.")
        for saved in storage.voice_library():
            if saved["name"] == voice and voice not in self.enrolled:
                self.register(voice, storage.DATA / "voices" / saved["folder"] / "reference.wav", saved["denoise"])
        temporary = output.with_suffix(".stream.wav")
        output.parent.mkdir(parents=True, exist_ok=True)
        try:
            with self.session.post(self.base + "/v1/audio/speech", json={
                "input": text, "voice": voice, "response_format": "wav", "temperature": temperature,
                "sample_rate": 48000, "max_chars": 256}, stream=True, timeout=(10, 900)) as response:
                if not response.ok:
                    raise RuntimeError("VieNeu: " + response.text[:1000])
                with temporary.open("wb") as file:
                    for block in response.iter_content(65536):
                        file.write(block)
            # The upstream streaming WAV uses 0xffffffff sizes. Finalize its header.
            media.transcode(temporary, output)
        finally:
            temporary.unlink(missing_ok=True)
