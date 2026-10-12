"""Non-destructive clip timeline. Separate from the legacy dubbing settings."""
from __future__ import annotations

from pathlib import Path
from functools import lru_cache
import subprocess
import threading

from pydantic import BaseModel, ConfigDict, Field, model_validator
from . import media, storage, speed


class PositionKeyframe(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)
    ms: int = Field(ge=0, le=3_600_000)
    x: float = Field(ge=-100, le=200)
    y: float = Field(ge=-100, le=200)
    scale: float | None = Field(default=None, ge=.05, le=4)
    rotation: float | None = Field(default=None, ge=-180, le=180)
    opacity: float | None = Field(default=None, ge=0, le=1)
    ease_start: float = Field(default=0, ge=0, le=1)
    ease_end: float = Field(default=1, ge=0, le=1)

    @model_validator(mode='after')
    def phase(self):
        if self.ease_end-self.ease_start < 1e-9:
            raise ValueError('Khoảng easing phải tăng dần.')
        return self


class SpeedPoint(BaseModel):
    model_config = ConfigDict(extra='forbid',allow_inf_nan=False)
    ms: int = Field(ge=0,le=3_600_000)
    speed: float = Field(ge=.25,le=4)


class WordCue(BaseModel):
    model_config = ConfigDict(extra='forbid',allow_inf_nan=False)
    word: str = Field(min_length=1,max_length=300)
    start: int = Field(ge=0,le=3_600_000)
    end: int = Field(ge=1,le=3_600_000)


class Clip(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)
    id: str = Field(pattern=r"^[a-f0-9]{32}$")
    asset: str = Field(default="", pattern=r"^(?:[a-f0-9]{32})?$")
    label: str = Field(default="Clip", max_length=200)
    start_ms: int = Field(ge=0, le=3_600_000)
    in_ms: int = Field(default=0, ge=0, le=3_600_000)
    duration_ms: int = Field(ge=100, le=3_600_000)
    volume: float = Field(default=1, ge=0, le=2)
    speed: float = Field(default=1, ge=.25, le=4)
    speed_curve: list[SpeedPoint] = Field(default_factory=list,max_length=16)
    flip_h: bool = False
    flip_v: bool = False
    x: float = Field(default=50, ge=-100, le=200)
    y: float = Field(default=50, ge=-100, le=200)
    scale: float = Field(default=1, ge=.05, le=4)
    rotation: float = Field(default=0, ge=-180, le=180)
    opacity: float = Field(default=1, ge=0, le=1)
    fit: str = Field(default="contain", pattern=r"^(contain|cover)$")
    blend: str = Field(default="normal", pattern=r"^(normal|screen|multiply|addition)$")
    color_filter: str = Field(default='none',pattern=r'^(none|mono|sepia|warm|cool|cinema|neon|dream)$')
    filter_strength: float = Field(default=1,ge=0,le=1)
    keyframes: list[PositionKeyframe] = Field(default_factory=list, max_length=64)
    motion_easing: str = Field(default="linear", pattern=r"^(linear|smooth|hold)$")
    fade_in_ms: int = Field(default=0, ge=0, le=10000)
    fade_out_ms: int = Field(default=0, ge=0, le=10000)
    transition_in: str = Field(default="none", pattern=r"^(none|crossfade|wipeleft|wiperight)$")
    transition_ms: int = Field(default=0, ge=0, le=10000)
    audio_fade_out_ms: int = Field(default=0, ge=0, le=10000)
    text: str = Field(default="", max_length=3000)
    text_animation: str = Field(default='none',pattern=r'^(none|karaoke|typewriter|pop)$')
    word_cues: list[WordCue] = Field(default_factory=list,max_length=200)
    font: str = Field(default="Arial", pattern=r"^(Arial|Segoe UI|Times New Roman|Be Vietnam Pro)$")
    font_size: int = Field(default=36, ge=10, le=160)
    color: str = Field(default="#ffffff", pattern=r"^#[a-fA-F0-9]{6}$")
    box: bool = False
    box_color: str = Field(default="#000000", pattern=r"^#[a-fA-F0-9]{6}$")
    box_opacity: float = Field(default=.6, ge=0, le=1)
    region_w: float = Field(default=30, ge=1, le=100)
    region_h: float = Field(default=15, ge=1, le=100)
    blur: int = Field(default=12, ge=1, le=40)

    @model_validator(mode="after")
    def bounds(self):
        if self.word_cues:
            if self.text.split()!=[w.word for w in self.word_cues] or any(len(w.word.split())!=1 for w in self.word_cues):
                raise ValueError('Mốc từ phải khớp nội dung chữ; sửa chữ cần bỏ/nhận dạng lại mốc.')
            previous=0
            for word in self.word_cues:
                if not previous<=word.start<word.end<=self.duration_ms:
                    raise ValueError('Mốc từ phải tăng dần, không chồng và nằm trong clip.')
                previous=word.end
        if self.start_ms + self.duration_ms > 3_600_000:
            raise ValueError("Timeline tối đa 60 phút.")
        times = [point.ms for point in self.keyframes]
        curve=[p.ms for p in self.speed_curve]
        if curve and (len(curve)<2 or curve[0]!=0 or curve[-1]!=self.duration_ms or curve!=sorted(set(curve))):
            raise ValueError('Curve cần 2–16 mốc tăng dần, bắt đầu 0 và kết thúc đúng thời lượng clip.')
        if times != sorted(set(times)) or any(ms > self.duration_ms for ms in times):
            raise ValueError("Mốc keyframe phải tăng dần, không trùng và nằm trong clip.")
        if self.fade_in_ms + self.fade_out_ms > self.duration_ms:
            raise ValueError("Tổng thời gian mờ vào/ra không được vượt độ dài clip.")
        if self.fade_in_ms + self.audio_fade_out_ms > self.duration_ms:
            raise ValueError("Fade âm thanh phải nằm trong clip.")
        if self.transition_in != "none":
            if curve:raise ValueError('Bỏ chuyển cảnh trước khi dùng speed curve.')
            if not 100 <= self.transition_ms <= self.duration_ms or self.fade_in_ms:
                raise ValueError("Chuyển cảnh cần 0,1–10s trong clip; không dùng đồng thời fade vào.")
            if self.keyframes or (self.x,self.y,self.scale,self.rotation,self.opacity,self.fit,self.blend)!=(50,50,1,0,1,"cover","normal"):
                raise ValueError("Chuyển cảnh phủ toàn canvas: tâm 50/50, zoom 1, không xoay/keyframe, độ hiện 1, cover và normal.")
        return self


class LayoutPreset(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str = Field(min_length=1, max_length=80)
    kind: str = Field(pattern=r"^(video|text|blur)$")
    layout: dict

    @model_validator(mode="after")
    def validate_layout(self):
        self.name = self.name.strip()
        if not self.name:
            raise ValueError("Nhập tên preset.")
        keys = {"x", "y", "scale", "rotation", "opacity"}
        if self.kind == "video":
            keys |= {"fit", "blend", "flip_h", "flip_v",'color_filter','filter_strength'}
        if self.kind == "text":
            keys |= {"font", "font_size", "color", "box", "box_color", "box_opacity"}
        if self.kind == "blur":
            keys = {"x", "y", "region_w", "region_h", "blur"}
        if not self.layout or set(self.layout) - keys:
            raise ValueError("Preset chỉ lưu bố cục, không lưu file/nội dung/thời gian.")
        clip = Clip(id="0" * 32, start_ms=0, duration_ms=100, **self.layout)
        if self.kind == "blur" and not (0 <= clip.x <= 100 and 0 <= clip.y <= 100):
            raise ValueError("Tâm vùng mờ phải nằm trong canvas.")
        self.layout = {key: value for key, value in clip.model_dump().items() if key in keys}
        return self


class Track(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str = Field(pattern=r"^[a-f0-9]{32}$")
    name: str = Field(max_length=80)
    kind: str = Field(pattern=r"^(video|audio|text|blur)$")
    locked: bool = False
    hidden: bool = False
    muted: bool = False
    clips: list[Clip] = Field(default_factory=list, max_length=500)


class Timeline(BaseModel):
    model_config = ConfigDict(extra="forbid")
    version: int = Field(default=1, ge=1, le=1)
    revision: int = Field(default=0, ge=0)
    width: int = Field(default=1280, ge=64, le=3840, multiple_of=2)
    height: int = Field(default=720, ge=64, le=3840, multiple_of=2)
    fps: int = Field(default=25, ge=15, le=60)
    render_threads: int = Field(default=2,ge=1,le=8)
    encoder: str = Field(default='libx264',pattern=r'^(libx264|h264_nvenc|h264_qsv|h264_amf)$')
    assets: list[str] = Field(default_factory=list, max_length=200)
    tracks: list[Track] = Field(default_factory=list, max_length=64)

    @model_validator(mode="after")
    def identities(self):
        for key in self.assets:
            storage.identifier(key)
        if len(self.assets) != len(set(self.assets)):
            raise ValueError("Media trùng mã.")
        ids = [t.id for t in self.tracks] + [c.id for t in self.tracks for c in t.clips]
        if len(ids) != len(set(ids)):
            raise ValueError("Track/clip trùng mã.")
        if sum(len(t.clips) for t in self.tracks) > 500:
            raise ValueError("Tối đa 500 clip, tính cả phụ đề.")
        if sum(len(t.clips) for t in self.tracks if t.kind in {"video", "audio"}) > 100:
            raise ValueError("Tối đa 100 clip media; chữ/phụ đề/vùng mờ không tính vào giới hạn này.")
        for track in self.tracks:
            for clip in track.clips:
                if track.kind in {"video", "audio"} and not clip.asset:
                    raise ValueError("Clip media cần file nguồn.")
                if track.kind in {"text", "blur"} and (clip.asset or clip.in_ms):
                    raise ValueError("Chữ/vùng mờ không có file hoặc điểm cắt nguồn.")
                if track.kind == "text" and not clip.text.strip():
                    raise ValueError("Chữ/phụ đề không được để trống.")
                if track.kind == "blur" and not (0 <= clip.x <= 100 and 0 <= clip.y <= 100):
                    raise ValueError("Tâm vùng mờ phải nằm trong canvas.")
                if clip.keyframes and track.kind not in {'video','blur'}:
                    raise ValueError("Keyframe vị trí hỗ trợ video/ảnh/vùng mờ.")
                if track.kind!='text' and clip.text_animation!='none':raise ValueError('Chữ động chỉ dùng track chữ.')
                if track.kind!='text' and clip.word_cues:raise ValueError('Mốc từ chỉ dùng track chữ.')
                if track.kind=='text' and clip.text_animation!='none' and len(clip.text.split())>200:raise ValueError('Chữ động tối đa 200 từ mỗi clip; chia câu trước.')
                if track.kind=='blur' and any(p.scale is not None or p.rotation is not None or p.opacity is not None or not 0<=p.x<=100 or not 0<=p.y<=100 for p in clip.keyframes):raise ValueError('Vùng mờ chỉ nhận mốc X/Y trong canvas.')
                if track.kind == "blur" and (clip.fade_in_ms or clip.fade_out_ms):
                    raise ValueError("Vùng mờ chưa hỗ trợ hiệu ứng vào/ra.")
                if track.kind in {"text", "blur"} and clip.speed != 1:
                    raise ValueError("Tốc độ chỉ hỗ trợ video/audio.")
                if track.kind not in {'video','audio'} and clip.speed_curve:raise ValueError('Speed curve chỉ dùng video/audio.')
                if track.kind != "video" and (clip.flip_h or clip.flip_v):
                    raise ValueError("Lật hình chỉ hỗ trợ video/ảnh.")
                if track.kind != 'video' and clip.color_filter!='none':raise ValueError('Bộ lọc chỉ áp dụng hình/video.')
                if track.kind != "video" and clip.transition_in != "none":
                    raise ValueError("Chuyển cảnh hình chỉ hỗ trợ video/ảnh.")
            rows = sorted(track.clips, key=lambda c: c.start_ms)
            if any(a.start_ms + a.duration_ms > b.start_ms for a, b in zip(rows, rows[1:])):
                raise ValueError("Clip cùng track chồng nhau. Dùng track khác để chồng lớp.")
        return self


class TrackPreset(BaseModel):
    model_config = ConfigDict(extra='forbid')
    name: str = Field(min_length=1,max_length=80)
    timeline: Timeline

    @model_validator(mode='after')
    def nonempty(self):
        self.name=self.name.strip()
        if not self.name or not any(t.clips for t in self.timeline.tracks):raise ValueError('Nhập tên và chọn timeline có clip.')
        return self


def path(project_id):
    return storage.project_path(project_id) / "editor-timeline.json"


def load(project_id):
    storage.project(project_id)
    return Timeline.model_validate(storage.read_json(path(project_id), {})).model_dump()


@lru_cache(maxsize=256)
def _probe(source, mtime, size):
    info = media.probe(source)
    streams = info.get("streams", [])
    image = source.suffix.lower() in {".png", ".jpg", ".jpeg", ".webp"}
    video = next((s for s in streams if s["codec_type"] == "video"), None)
    audio = any(s["codec_type"] == "audio" for s in streams)
    if not video and not audio:
        raise ValueError("Editor chỉ nhận video, ảnh và audio.")
    duration = 0 if image else round(float(info.get("format", {}).get("duration", 0)) * 1000)
    if not image and duration < 100:
        raise ValueError("Media không có thời lượng hợp lệ.")
    return {"kind": "image" if image else "video" if video else "audio",
            "duration_ms": duration, "has_audio": audio,
            "width": video.get("width", 0) if video else 0, "height": video.get("height", 0) if video else 0,
            "alpha_video": bool(video and video.get('tags',{}).get('alpha_mode')=='1')}


def describe(project, asset_id):
    source, meta = storage.project_asset(project, asset_id)
    stat = source.stat()
    item = {**meta, **_probe(source, stat.st_mtime_ns, stat.st_size), "url": storage.file_url(source)}
    if item['alpha_video']:item['preview_url']=item['url']
    proxy = proxy_path(project, asset_id, source)
    if proxy.is_file() and not item['alpha_video']:
        item["preview_url"] = storage.file_url(proxy)
    folder = proxy.parent
    samples = storage.read_json(folder / "filmstrip.json", {})
    if samples.get("stamp") == f"{stat.st_mtime_ns}-{stat.st_size}":
        item["thumbnails"] = [{"ms": row["ms"], "url": storage.file_url(folder / row["file"])}
                              for row in samples.get("frames", []) if (folder / row["file"]).is_file()]
    return item


def proxy_path(project, asset_id, source):
    # Cache identity changes when the source changes. No edits to project revisions.
    stat = source.stat()
    return storage.project_path(project["id"]) / "editor-media" / asset_id / f"proxy-v2-{stat.st_mtime_ns}-{stat.st_size}.webm"


def prepare_proxy(project, asset_id, event, progress):
    item = describe(project, asset_id)
    if item["kind"] == "image" or "preview_url" in item:
        return item
    source, _ = storage.project_asset(project, asset_id)
    output = proxy_path(project, asset_id, source)
    output.parent.mkdir(parents=True, exist_ok=True)
    partial = output.with_name(output.stem + ".partial.webm")
    args = [media.binary(), "-y", "-v", "error", "-i", str(source)]
    if item["kind"] == "video":
        long_video = item["duration_ms"] > 300_000
        size, fps = (640, 24) if long_video else (960, 30)
        args += ["-map", "0:v:0", "-map", "0:a:0?", "-vf",
                 f"scale=w='min({size},iw)':h='min({size},ih)':force_original_aspect_ratio=decrease:force_divisible_by=2,fps={fps}",
                 "-c:v", "libvpx-vp9", "-deadline", "realtime", "-cpu-used", "8", "-crf", "36", "-b:v", "0", "-pix_fmt", "yuv420p"]
    else:
        args += ["-map", "0:a:0", "-vn"]
    args += ["-threads", "2", "-c:a", "libopus", "-progress", "pipe:1", str(partial)]
    try:
        run_cancel(args, event, progress, item["duration_ms"])
        partial.replace(output)
    finally:
        partial.unlink(missing_ok=True)
    return describe(project, asset_id)


def save(project_id, value):
    model = Timeline.model_validate(value)
    with storage.LOCK:
        project = storage.project(project_id)
        previous = load(project_id)
        if model.revision != previous["revision"]:
            raise ValueError("Timeline đã thay đổi ở phiên khác. Mở lại dự án; bản nháp của bạn vẫn giữ.")
        assets = {key: describe(project, key) for key in model.assets}
        for track in model.tracks:
            for clip in track.clips:
                if track.kind not in {"video", "audio"}:
                    continue
                if clip.asset not in assets:
                    assets[clip.asset] = describe(project, clip.asset)
                item = assets[clip.asset]
                if track.kind == "video" and item["kind"] == "audio":
                    raise ValueError("Audio phải đặt trên track audio.")
                if track.kind == "audio" and not item["has_audio"]:
                    raise ValueError("File không có audio.")
                if item["kind"] == "image" and clip.in_ms:
                    raise ValueError("Ảnh tĩnh không có điểm cắt nguồn.")
                if item["kind"] == "image" and (clip.speed != 1 or clip.speed_curve):
                    raise ValueError("Ảnh tĩnh không có tốc độ phát.")
                if item["kind"] != "image" and clip.in_ms + speed.source_ms(clip.model_dump(),clip.duration_ms) > item["duration_ms"] + 40:
                    raise ValueError("Clip vượt quá thời lượng nguồn: " + clip.label)
        # Retain sources beside the project. Never alter or move originals.
        for asset_id in assets:
            source, meta = storage.project_asset(project, asset_id)
            target = storage.project_path(project_id) / "assets" / (asset_id + source.suffix)
            target.parent.mkdir(parents=True, exist_ok=True)
            if not target.exists():
                import shutil
                shutil.copy2(source, target)
            project.setdefault("local_assets", {})[asset_id] = {**meta, "file": target.name}
        if path(project_id).exists():
            backup = path(project_id).parent / "editor-backups" / f"revision-{previous['revision']}.json"
            storage.atomic_json(backup, previous)
        result = model.model_dump()
        result["revision"] += 1
        storage.atomic_json(path(project_id), result)
        # Do not change the legacy project's revision/cues/exports for editor operations.
        storage.atomic_json(storage.project_path(project_id) / "project.json", project)
        return result


def duration(value):
    return max((c["start_ms"] + c["duration_ms"] for t in value["tracks"] for c in t["clips"]), default=0)


def run_cancel(args, event, progress=None, total_ms=1, cwd=None):
    """Read ffmpeg progress in a helper; cancellation terminates only our process."""
    process = subprocess.Popen(args, cwd=cwd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
                               encoding="utf-8", errors="replace",
                               creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    errors = []
    reader = threading.Thread(target=lambda: errors.append(process.stderr.read()), daemon=True)
    reader.start()
    def read_progress():
        for line in process.stdout:
            if progress and line.startswith("out_time_us="):
                try:
                    progress(min(98, int(line.split("=", 1)[1]) / max(1, total_ms * 1000) * 100), "Đang render timeline…")
                except ValueError:
                    pass
    output_reader = threading.Thread(target=read_progress, daemon=True)
    output_reader.start()
    try:
        while process.poll() is None:
            if event.wait(.15):
                media.stop_owned_process(process)
                raise InterruptedError("Đã dừng render; timeline vẫn được lưu.")
        reader.join(timeout=5)
        output_reader.join(timeout=5)
        if process.returncode:
            raise RuntimeError("".join(errors)[-2000:])
    finally:
        if process.poll() is None:
            media.stop_owned_process(process)
        process.stdout.close()
        process.stderr.close()


def prepare(project, asset_id, event):
    item = describe(project, asset_id)
    source, _ = storage.project_asset(project, asset_id)
    folder = storage.project_path(project["id"]) / "editor-media" / asset_id
    folder.mkdir(parents=True, exist_ok=True)
    output = folder / "thumbnail.png"
    if item["kind"] != "audio" and not output.exists():
        run_cancel([media.binary(), "-y", "-v", "error", "-i", str(source), "-frames:v", "1",
                    "-vf", "scale=240:135:force_original_aspect_ratio=decrease", str(output)], event)
    if output.exists():
        item["thumbnail"] = storage.file_url(output)
    wave = folder / "waveform.png"
    if item["has_audio"] and not wave.exists():
        run_cancel([media.binary(), "-y", "-v", "error", "-i", str(source), "-filter_complex",
                    "[0:a]aformat=channel_layouts=mono,aresample=2000,showwavespic=s=800x64:colors=0x009c90[v]",
                    "-map", "[v]", "-frames:v", "1", str(wave)], event)
    if wave.exists():
        item["waveform"] = storage.file_url(wave)
    if item["kind"] == "video":
        stat = source.stat()
        stamp = f"{stat.st_mtime_ns}-{stat.st_size}"
        cached = storage.read_json(folder / "filmstrip.json", {})
        if cached.get("stamp") != stamp:
            frames = []
            for index in range(16):
                if event.is_set():
                    raise InterruptedError("Đã dừng tạo thumbnail.")
                ms = round(max(0, item["duration_ms"] - 80) * index / 15)
                name = f"frame-{stamp}-{index}.png"
                target = folder / name
                if not target.exists():
                    partial = target.with_name(target.stem + ".partial.png")
                    try:
                        run_cancel([media.binary(), "-y", "-v", "error", "-ss", str(ms / 1000), "-i", str(source),
                                    "-frames:v", "1", "-vf", "scale=160:90:force_original_aspect_ratio=decrease", str(partial)], event)
                        if partial.is_file():
                            partial.replace(target)
                    finally:
                        partial.unlink(missing_ok=True)
                if target.is_file():
                    frames.append({"ms": ms, "file": name})
            storage.atomic_json(folder / "filmstrip.json", {"stamp": stamp, "frames": frames})
        item["thumbnails"] = describe(project, asset_id).get("thumbnails", [])
    return item


def transform_expression(clip, key, global_time=True, variable='t'):
    """Validated numeric keyframes only; time is local for scale/rotate/geq."""
    points = clip["keyframes"]
    if not points:
        return str(clip[key])
    value=lambda point: clip[key] if point.get(key) is None else point[key]
    expression = str(value(points[-1]))
    for left, right in reversed(list(zip(points, points[1:]))):
        begin = ((clip['start_ms'] if global_time else 0) + left["ms"]) / 1000
        end = ((clip['start_ms'] if global_time else 0) + right["ms"]) / 1000
        u = f"(({variable}-{begin})/{end-begin})"
        mode = clip.get("motion_easing", "linear")
        if mode == 'smooth':
            a=left.get('ease_start',0); b=left.get('ease_end',1)
            lo=a*a*(3-2*a); hi=b*b*(3-2*b)
            phase=f'({a}+({b-a})*{u})'
            factor=f'(({phase}*{phase}*(3-2*{phase})-{lo})/{hi-lo})'
        else:
            factor = "0" if mode == "hold" else u
        expression = f"if(lt({variable},{end}),{value(left)}+({value(right)-value(left)})*({factor}),{expression})"
    first = ((clip['start_ms'] if global_time else 0) + points[0]["ms"]) / 1000
    return f"if(lt({variable},{first}),{value(points[0])},{expression})"


def position_expression(clip,key):
    return transform_expression(clip,key)


def tempo_filters(speed):
    """Keep each atempo stage inside 0.5..2, preserving pitch."""
    parts = []
    while speed < .5:
        parts.append("atempo=0.5")
        speed /= .5
    while speed > 2:
        parts.append("atempo=2")
        speed /= 2
    parts.append(f"atempo={speed}")
    return ",".join(parts)


def render(project, value, output: Path, event, progress):
    value = Timeline.model_validate(value).model_dump()
    length = duration(value)
    if not length:
        raise ValueError("Timeline chưa có clip.")
    seconds = length / 1000
    width, height, fps = value["width"], value["height"], value["fps"]
    args = [media.binary(), "-y", "-v", "error", "-filter_complex_threads", "1"]
    entries = []
    input_index = 0
    output = output.resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    for track in value["tracks"]:
        for clip in sorted(track["clips"], key=lambda c: c["start_ms"]):
            if track["kind"] != "audio" and track["hidden"] or track["kind"] == "audio" and track["muted"]:
                continue
            if track["kind"] in {"text", "blur"}:
                entries.append((track, clip, {}, None))
                continue
            item = describe(project, clip["asset"])
            source, _ = storage.project_asset(project, clip["asset"])
            if item["kind"] == "image":
                if clip["speed"] != 1:
                    raise ValueError("Ảnh tĩnh không có tốc độ phát.")
                args += ["-loop", "1", "-framerate", str(fps)]
            else:
                args += ["-ss", str(clip["in_ms"] / 1000)]
            if item['kind']=='image' and clip['speed_curve']:raise ValueError('Ảnh tĩnh không dùng speed curve.')
            if item.get('alpha_video'):args += ['-c:v','libvpx-vp9']
            span = clip["duration_ms"] if item["kind"] == "image" else speed.source_ms(clip,clip['duration_ms'])
            args += ["-t", str(span / 1000), "-i", str(source)]
            entries.append((track, clip, item, input_index))
            input_index += 1
    graph = [f"color=c=black:s={width}x{height}:r={fps}:d={seconds}[base]",
             f"anullsrc=r=48000:cl=stereo,atrim=duration={seconds}[silence]"]
    current = "base"
    sounds = ["silence"]
    for number, (track, clip, item, i) in enumerate(entries):
        start, end = clip["start_ms"] / 1000, (clip["start_ms"] + clip["duration_ms"]) / 1000
        if track["kind"] == "text":
            from . import editor
            import shutil
            ass = output.parent / f"text-{number}.ass"
            settings = editor.config({"subtitle_font": clip["font"], "subtitle_size": clip["font_size"],
                "subtitle_color": clip["color"], "subtitle_x": min(100,max(0,clip["x"])),
                "subtitle_y": min(100,max(0,clip["y"])), "subtitle_style": "box" if clip["box"] else "outline",
                "subtitle_box_color": clip.get('box_color', '#000000'), "subtitle_box_opacity": clip.get('box_opacity', .6)})
            editor.write_ass(ass,[{"start_ms":clip["start_ms"],"end_ms":clip["start_ms"]+clip["duration_ms"],"text":clip["text"]}],settings,width,height,length)
            # Controlled numeric ASS overrides; user text remains escaped by write_ass.
            body=ass.read_text(encoding="utf-8-sig")
            old_pos=f"\\pos({width*settings['subtitle_x']/100:.1f},{height*settings['subtitle_y']/100:.1f})"
            body=body.replace(old_pos,f"\\pos({width*clip['x']/100:.1f},{height*clip['y']/100:.1f})")
            alpha=round((1-clip["opacity"])*255)
            box_alpha=round((1-clip['opacity']*clip.get('box_opacity', .6))*255)
            box_tags=f'\\3a&H{box_alpha:02X}&\\4a&H{box_alpha:02X}&' if clip['box'] else ''
            body=body.replace("{\\pos(",f"{{\\fad({clip['fade_in_ms']},{clip['fade_out_ms']})\\fscx{clip['scale']*100}\\fscy{clip['scale']*100}\\frz{-clip['rotation']}\\alpha&H{alpha:02X}&{box_tags}\\pos(")
            from .captions import animate_ass
            ass.write_text(animate_ass(body,clip),encoding="utf-8-sig")
            fonts=output.parent/"fonts";fonts.mkdir(exist_ok=True)
            for font in (storage.ROOT/"web").glob("*.ttf"):
                if not (fonts/font.name).exists():shutil.copy2(font,fonts/font.name)
            graph.append(f"[{current}]ass=filename='{ass.name}':fontsdir='fonts'[text{number}]")
            current=f"text{number}"
            continue
        if track["kind"] == "blur":
            mw=max(2,min(width,round(width*clip["region_w"]/100)))
            mh=max(2,min(height,round(height*clip["region_h"]/100)))
            x=max(0,min(width-mw,round(width*clip["x"]/100-mw/2)))
            y=max(0,min(height-mh,round(height*clip["y"]/100-mh/2)))
            if clip['keyframes']:
                x=f"max(0,min({width-mw},{width}*({position_expression(clip,'x')})/100-{mw}/2))"
                y=f"max(0,min({height-mh},{height}*({position_expression(clip,'y')})/100-{mh}/2))"
            radius=min(clip["blur"],(min(mw,mh)-1)//2)
            graph += [f"[{current}]format=yuv444p,split=2[bb{number}][bc{number}]",
                f"[bc{number}]crop={mw}:{mh}:x='{x}':y='{y}':exact=1,boxblur={radius}:2[bp{number}]",
                f"[bb{number}][bp{number}]overlay=x='{x}':y='{y}':eval=frame:format=auto:enable='gte(t,{start})*lt(t,{end})'[blur{number}]"]
            current=f"blur{number}"
            continue
        if track["kind"] == "video":
            flip = (",hflip" if clip["flip_h"] else "") + (",vflip" if clip["flip_v"] else "")
            scaled_w = max(2, round(width * clip['scale'] / 2) * 2)
            scaled_h = max(2, round(height * clip['scale'] / 2) * 2)
            angle = clip['rotation'] * 3.141592653589793 / 180
            sizing = (f"scale={scaled_w}:{scaled_h}:force_original_aspect_ratio=increase,crop={scaled_w}:{scaled_h}" if clip["fit"] == "cover"
                      else f"scale={scaled_w}:{scaled_h}:force_original_aspect_ratio=decrease")
            layout=f"{sizing},format=rgba,pad={scaled_w}:{scaled_h}:(ow-iw)/2:(oh-ih)/2:color=black@0,setsar=1{flip},rotate={angle}:ow=rotw({angle}):oh=roth({angle}):c=black@0"
            if any(p.get(k) is not None and p[k]!=clip[k] for p in clip['keyframes'] for k in ('scale','rotation')):
                import math
                maximum=max([clip['scale']]+[p['scale'] for p in clip['keyframes'] if p.get('scale') is not None])
                mw=math.ceil(width*maximum/2)*2;mh=math.ceil(height*maximum/2)*2;diagonal=math.ceil(math.hypot(mw,mh)/2)*2
                if diagonal*diagonal>64_000_000:raise ValueError('Keyframe zoom ở canvas này quá lớn cho bộ dựng CPU; giảm zoom hoặc kích thước canvas.')
                base=(f'scale={width}:{height}:force_original_aspect_ratio=increase,crop={width}:{height}' if clip['fit']=='cover' else f'scale={width}:{height}:force_original_aspect_ratio=decrease')
                scale=transform_expression(clip,'scale',False);rotation=transform_expression(clip,'rotation',False)
                layout=(f"{base},format=rgba,pad={width}:{height}:(ow-iw)/2:(oh-ih)/2:color=black@0,setsar=1{flip},"
                    f"scale=w='max(2,round({width}*({scale})/2)*2)':h='max(2,round({height}*({scale})/2)*2)':eval=frame,"
                    f"pad={mw}:{mh}:(ow-iw)/2:(oh-ih)/2:color=black@0:eval=frame,"
                    f"rotate='({rotation})*PI/180':ow={diagonal}:oh={diagonal}:c=black@0")
            alpha=f"colorchannelmixer=aa={clip['opacity']}"
            if any(p.get('opacity') is not None and p['opacity']!=clip['opacity'] for p in clip['keyframes']):
                opacity=transform_expression(clip,'opacity',False,'T')
                alpha=f"geq=r='r(X,Y)':g='g(X,Y)':b='b(X,Y)':a='alpha(X,Y)*({opacity})':interpolation=nearest"
            fades = ""
            if clip['transition_in'] != 'none':
                d=clip['transition_ms']/1000
                factor=f'min(1,max(0,T/{d}))'
                if clip['transition_in']=='wipeleft':factor=f'if(lt(T,{d}),lte(X,W*T/{d}),1)'
                elif clip['transition_in']=='wiperight':factor=f'if(lt(T,{d}),gte(X,W*(1-T/{d})),1)'
                alpha=f"geq=r='r(X,Y)':g='g(X,Y)':b='b(X,Y)':a='alpha(X,Y)*({factor})':interpolation=nearest"
            if clip["fade_in_ms"]:
                fades += f",fade=t=in:st=0:d={clip['fade_in_ms']/1000}:alpha=1"
            if clip["fade_out_ms"]:
                fades += f",fade=t=out:st={(clip['duration_ms']-clip['fade_out_ms'])/1000}:d={clip['fade_out_ms']/1000}:alpha=1"
            retime=speed.pts(clip) if clip['speed_curve'] else f"setpts=(PTS-STARTPTS)/{clip['speed']}"
            from .creative import ffmpeg_filter
            graph += [f"[{i}:v]{retime},fps={fps},{layout}{ffmpeg_filter(clip)},{alpha}{fades},"
                      f"setpts=PTS+{start}/TB[v{i}]"]
            position = f"x='W*({position_expression(clip,'x')})/100-w/2':y='H*({position_expression(clip,'y')})/100-h/2':eval=frame:eof_action=pass:repeatlast=0:enable='gte(t,{start})*lt(t,{end})'"
            if clip["blend"] == "normal":
                graph.append(f"[{current}][v{i}]overlay={position}[base{i}]")
            else:
                neutral = "white" if clip["blend"] == "multiply" else "black"
                graph += [f"color=c={neutral}:s={width}x{height}:r={fps}:d={seconds}[neutral{i}]",
                          f"[neutral{i}][v{i}]overlay={position},format=gbrp[layer{i}]",
                          f"[{current}]format=gbrp[under{i}]",
                          f"[layer{i}][under{i}]blend=all_mode={clip['blend']}:shortest=1[base{i}]"]
            current = f"base{i}"
        if item["has_audio"] and not track["muted"]:
            fades = ""
            if clip['transition_in']!='none':
                fades += f",afade=t=in:st=0:d={clip['transition_ms']/1000}"
            if clip["fade_in_ms"]:
                fades += f",afade=t=in:st=0:d={clip['fade_in_ms']/1000}"
            audio_out=max(clip['fade_out_ms'],clip['audio_fade_out_ms'])
            if audio_out:
                fades += f",afade=t=out:st={(clip['duration_ms']-audio_out)/1000}:d={audio_out/1000}"
            tempo=speed.audio(clip,i,output.parent) or tempo_filters(clip['speed'])
            graph += [f"[{i}:a]asetpts=PTS-STARTPTS,{tempo},aresample=48000,aformat=channel_layouts=stereo,"
                      f"volume={clip['volume']}{fades},adelay={clip['start_ms']}:all=1[a{i}]"]
            sounds.append(f"a{i}")
    graph += ["".join(f"[{s}]" for s in sounds) + f"amix=inputs={len(sounds)}:normalize=0,alimiter=limit=0.95:latency=1,atrim=duration={seconds}[sound]"]
    # Keyframe graphs may exceed the Windows command-line limit. Keep filters in a file.
    graph_path = output.parent / (output.stem + "-filters.txt")
    graph_path.write_text(";".join(graph), encoding="utf-8")
    args += ["-filter_complex_script", str(graph_path), "-map", f"[{current}]", "-map", "[sound]",
             "-t", str(seconds), "-c:v", "libvpx-vp9" if output.suffix == ".webm" else value['encoder'],
             "-pix_fmt", "yuv420p", "-threads",str(value['render_threads']), "-c:a", "libopus" if output.suffix == ".webm" else "aac"]
    if output.suffix == ".webm":
        args += ["-deadline", "realtime", "-cpu-used", "6", "-crf", "35", "-b:v", "0"]
    elif value['encoder']=='libx264':
        args += ["-preset", "veryfast", "-crf", "20", "-movflags", "+faststart"]
    else:
        # Hardware encode only; composition/AI remains on CPU. Never silently downgrade.
        bitrate=max(2_000_000,min(60_000_000,round(width*height*fps*.15)))
        args += ['-b:v',str(bitrate),'-movflags','+faststart']
    args += ["-progress", "pipe:1", str(output)]
    try:
        run_cancel(args, event, progress, length, cwd=output.parent)
    except BaseException:
        output.unlink(missing_ok=True)
        raise
    return output
