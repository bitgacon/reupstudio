"""Media and subtitle primitives adapted from the MIT MPT SRT workflow."""
from __future__ import annotations

import json
import math
import os
from pathlib import Path
import re
import shutil
import subprocess
import zipfile
from xml.etree import ElementTree

from pydub import AudioSegment
from pydub.silence import detect_nonsilent

from .storage import ROOT


def binary(name="ffmpeg") -> str:
    candidates = [ROOT / "tools" / f"{name}.exe",
                  ROOT.parent / "release" / "MPT" / "tools" / f"{name}.exe"]
    explicit = os.environ.get("REUP_" + name.upper())
    if explicit:
        candidates.insert(0, Path(explicit))
    for candidate in candidates:
        if candidate.is_file():
            return str(candidate)
    found = shutil.which(name)
    if found:
        return found
    raise RuntimeError(f"Thiếu {name}. Đặt {name}.exe vào thư mục tools.")


def command(args: list[str], timeout=7200, cwd=None) -> str:
    done = subprocess.run(args, cwd=cwd, capture_output=True, text=True, encoding="utf-8",
                          errors="replace", timeout=timeout,
                          creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    if done.returncode:
        raise RuntimeError((done.stderr or done.stdout)[-1600:])
    return done.stdout


def stop_owned_process(process):
    """Stop only a Popen owned by this app, including Windows venv launcher children."""
    if process.poll() is not None:
        return
    if os.name == "nt":
        subprocess.run(["taskkill", "/PID", str(process.pid), "/T", "/F"], capture_output=True,
                       timeout=15, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    else:
        process.terminate()
    try:
        process.wait(timeout=10)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait(timeout=10)


def configure_audio() -> None:
    AudioSegment.converter = binary()
    os.environ["PATH"] = str(Path(binary()).parent) + os.pathsep + os.environ.get("PATH", "")


def probe(path: Path) -> dict:
    return json.loads(command([binary("ffprobe"), "-v", "error", "-show_format", "-show_streams",
                               "-of", "json", str(path)], timeout=90))


def atempo(speed: float) -> str:
    if not math.isfinite(speed) or speed <= 0:
        raise ValueError("Tốc độ không hợp lệ.")
    parts = []
    while speed > 2:
        parts.append("atempo=2")
        speed /= 2
    while speed < 0.5:
        parts.append("atempo=0.5")
        speed /= 0.5
    return ",".join(parts + [f"atempo={speed:.8f}"])


def transcode(source: Path, output: Path, speed=1.0) -> None:
    command([binary(), "-y", "-v", "error", "-i", str(source), "-vn", "-af", atempo(speed),
             "-ar", "48000", "-ac", "1", str(output)])


def fit_cue(source: Path, output: Path, duration_ms: int) -> dict:
    if duration_ms <= 0:
        raise ValueError("Cue có thời lượng bằng 0 hoặc âm; sửa trước khi tạo giọng.")
    clip = AudioSegment.from_file(source)
    if len(clip) <= 0:
        raise ValueError("Audio tổng hợp rỗng.")
    spans = detect_nonsilent(clip, min_silence_len=40, silence_thresh=-45, seek_step=5)
    start, end = (max(0, spans[0][0] - 30), min(len(clip), spans[-1][1] + 30)) if spans else (0, len(clip))
    factor = max(1.0, (end - start) / duration_ms)
    filters = f"atrim=start={start / 1000:.6f}:end={end / 1000:.6f},asetpts=PTS-STARTPTS,"
    filters += atempo(factor) + f",apad,atrim=duration={duration_ms / 1000:.6f}"
    command([binary(), "-y", "-v", "error", "-i", str(source), "-af", filters,
             "-ac", "1", "-ar", "48000", "-sample_fmt", "s16", str(output)])
    return {"speed_factor": round(factor, 3), "raw_ms": len(clip),
            "voiced_ms": end - start, "fit_duration_ms": duration_ms}


def timecode(value: int) -> str:
    hours, rem = divmod(int(value), 3600000)
    minutes, rem = divmod(rem, 60000)
    seconds, millis = divmod(rem, 1000)
    return f"{hours:02}:{minutes:02}:{seconds:02},{millis:03}"


def milliseconds(value: str) -> int:
    match = re.fullmatch(r"(\d{1,3}):(\d{2}):(\d{2})[,.](\d{1,3})", value.strip())
    if not match:
        raise ValueError("Mốc thời gian không hợp lệ: " + value)
    h, m, s, ms = match.groups()
    if int(m) > 59 or int(s) > 59:
        raise ValueError("Phút/giây ngoài phạm vi: " + value)
    return int(h) * 3600000 + int(m) * 60000 + int(s) * 1000 + int(ms.ljust(3, "0"))


def validate_cues(cues: list[dict]) -> list[dict]:
    issues = []
    last_start, last_end = -1, -1
    for i, cue in enumerate(cues, 1):
        start, end = cue["start_ms"], cue["end_ms"]
        if start < 0 or end <= start:
            issues.append({"cue": i, "level": "error", "message": "Thời lượng bằng 0/âm hoặc start âm."})
        if not cue["text"].strip():
            issues.append({"cue": i, "level": "error", "message": "Nội dung trống."})
        if start < last_start:
            issues.append({"cue": i, "level": "error", "message": "Sai thứ tự thời gian."})
        if start < last_end:
            issues.append({"cue": i, "level": "warning", "message": "Chồng lấn cue trước; sẽ trộn tiếng."})
        last_start, last_end = start, end
    return issues


def parse_srt(text: str) -> tuple[list[dict], list[dict]]:
    cues, issues = [], []
    for number, block in enumerate(re.split(r"\n\s*\n", text.lstrip("\ufeff").replace("\r", "").strip()), 1):
        lines = block.splitlines()
        index = next((i for i, line in enumerate(lines) if "-->" in line), -1)
        try:
            if index < 0:
                raise ValueError("Thiếu dòng thời gian.")
            left, right = lines[index].split("-->", 1)
            start, end = milliseconds(left), milliseconds(right.strip().split()[0])
            content = "\n".join(lines[index + 1:]).strip()
            cues.append({"id": len(cues) + 1, "start_ms": start, "end_ms": end,
                         "source_text": content, "text": content, "voice": "", "status": "pending"})
        except (ValueError, IndexError) as exc:
            issues.append({"block": number, "level": "error", "message": str(exc)})
    return cues, issues + validate_cues(cues)


def srt(cues: list[dict]) -> str:
    return "\n".join(f"{i}\n{timecode(c['start_ms'])} --> {timecode(c['end_ms'])}\n{c['text'].strip()}\n"
                     for i, c in enumerate(cues, 1))


def decode_text(raw: bytes) -> str:
    if raw.startswith((b"\xff\xfe", b"\xfe\xff")):
        return raw.decode("utf-16")
    try:
        return raw.decode("utf-8-sig")
    except UnicodeDecodeError:
        return raw.decode("cp1258")


def document(path: Path) -> dict:
    suffix = path.suffix.lower()
    warnings = []
    if suffix in {".txt", ".md", ".srt"}:
        text = decode_text(path.read_bytes())
    elif suffix == ".docx":
        with zipfile.ZipFile(path) as archive:
            info = archive.getinfo("word/document.xml")
            if info.file_size > 25_000_000:
                raise ValueError("Nội dung Word quá lớn (giới hạn XML 25 MB).")
            root = ElementTree.fromstring(archive.read(info))
        ns = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
        text = "\n\n".join("".join(t.text or "" for t in p.iter(ns + "t")) for p in root.iter(ns + "p"))
    elif suffix == ".pdf":
        from pypdf import PdfReader
        reader = PdfReader(str(path))
        if reader.is_encrypted and not reader.decrypt(""):
            raise ValueError("PDF có mật khẩu; hãy mở khóa bản sao trước khi nhập.")
        if len(reader.pages) > 1000:
            raise ValueError("Tối đa 1.000 trang mỗi lần. Hãy tách tài liệu.")
        pages = [page.extract_text() or "" for page in reader.pages]
        blank = sum(not p.strip() for p in pages)
        if blank:
            warnings.append(f"{blank} trang không có lớp chữ; có thể cần OCR. Bản này chưa có OCR.")
        text = "\n\n".join(pages)
    else:
        raise ValueError("Dùng TXT, DOCX hoặc PDF. File .doc cũ cần lưu thành .docx.")
    if not text.strip():
        raise ValueError("Không tìm thấy văn bản. PDF scan/ảnh cần OCR trước.")
    if len(text) > 2_000_000:
        raise ValueError("Tài liệu quá dài; hãy chia nhỏ (tối đa 2 triệu ký tự).")
    return {"text": text.strip(), "warnings": warnings}


def split_script(text: str, limit=350) -> list[str]:
    """Bound requests while retaining punctuation; no fabricated word timings."""
    result = []
    for paragraph in re.split(r"\n+", text.strip()):
        current = ""
        for word in paragraph.split():
            if current and len(current) + len(word) + 1 > limit:
                result.append(current)
                current = ""
            while len(word) > limit:
                if current:
                    result.append(current)
                    current = ""
                result.append(word[:limit])
                word = word[limit:]
            current = (current + " " + word).strip()
        if current:
            result.append(current)
    return result


def dialogue(text: str) -> list[dict]:
    rows = []
    for line in text.splitlines():
        if not line.strip():
            continue
        match = re.match(r"^\s*\[([^\]\n]{1,60})\]\s*:\s*(.+)$", line)
        if match:
            rows.append({"speaker": match[1].strip(), "text": match[2].strip()})
        elif rows:
            rows[-1]["text"] += "\n" + line.strip()
        else:
            raise ValueError("Dùng định dạng [Host]: Lời thoại, mỗi lượt một dòng.")
    if not rows:
        raise ValueError("Kịch bản hội thoại trống.")
    return rows
