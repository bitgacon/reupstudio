"""Validated, reusable edit settings and FFmpeg rendering (no shell/filter text from users)."""
from __future__ import annotations

import math
from functools import lru_cache
from pathlib import Path
import shutil
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from . import media, storage

LANGUAGES = {"vi": "tiếng Việt", "en": "tiếng Anh", "zh": "tiếng Trung", "ja": "tiếng Nhật",
             "ko": "tiếng Hàn", "fr": "tiếng Pháp", "de": "tiếng Đức", "th": "tiếng Thái"}
FONTS = ["Arial", "Segoe UI", "Times New Roman", "Be Vietnam Pro"]


class TimedRegion(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)
    start_ms: int = Field(default=0, ge=0, le=86400000)
    end_ms: int | None = Field(default=None, ge=1, le=86400000)

    @model_validator(mode="after")
    def valid_interval(self):
        if self.end_ms is not None and self.end_ms <= self.start_ms:
            raise ValueError("Thời gian kết thúc phải lớn hơn bắt đầu.")
        return self


class VisualLayer(TimedRegion):
    asset: str = Field(default="", pattern=r"^(?:[a-f0-9]{32})?$")
    x: float = Field(default=50, ge=0, le=100)
    y: float = Field(default=50, ge=0, le=100)
    width: float = Field(default=100, ge=1, le=200)
    opacity: float = Field(default=1, ge=0, le=1)
    mode: Literal["normal", "screen", "multiply"] = "normal"


class BlurRegion(TimedRegion):
    mask_x: float = Field(default=0, ge=0, le=99)
    mask_y: float = Field(default=0, ge=0, le=99)
    mask_w: float = Field(default=20, ge=1, le=100)
    mask_h: float = Field(default=20, ge=1, le=100)
    mask_blur: int = Field(default=12, ge=1, le=40)


class EditSettings(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)
    target_language: Literal["vi", "en", "zh", "ja", "ko", "fr", "de", "th"] = "vi"
    translation_provider: Literal["google_v1", "google", "api"] = "google_v1"
    source_language: Literal["auto", "vi", "en", "zh", "ja", "ko", "fr", "de", "th"] = "auto"
    output_ratio: Literal["source", "16:9", "9:16", "1:1", "4:5", "4:3", "custom"] = "source"
    output_short_side: Literal[720, 1080, 1440, 2160] = 720
    output_width: int = Field(default=1080, ge=64, le=3840)
    output_height: int = Field(default=1920, ge=64, le=3840)
    video_fit: Literal["contain", "cover"] = "contain"
    canvas_color: str = Field(default="#000000", pattern=r"^#[0-9a-fA-F]{6}$")
    zoom: float = Field(default=1, ge=.25, le=3)
    rotation: float = Field(default=0, ge=-180, le=180)
    video_x: float = Field(default=50, ge=0, le=100)
    video_y: float = Field(default=50, ge=0, le=100)
    subtitle_font: Literal["Arial", "Segoe UI", "Times New Roman", "Be Vietnam Pro"] = "Arial"
    subtitle_size: int = Field(default=36, ge=10, le=160)
    subtitle_x: float = Field(default=50, ge=0, le=100)
    subtitle_y: float = Field(default=88, ge=0, le=100)
    subtitle_color: str = Field(default="#ffffff", pattern=r"^#[0-9a-fA-F]{6}$")
    subtitle_box_color: str = Field(default="#000000", pattern=r"^#[0-9a-fA-F]{6}$")
    subtitle_box_opacity: float = Field(default=.6, ge=0, le=1)
    subtitle_style: Literal["outline", "box", "fade", "karaoke"] = "outline"
    original_subtitles: Literal["keep", "cover", "blur"] = "keep"
    mask_x: float = Field(default=0, ge=0, le=99)
    mask_y: float = Field(default=78, ge=0, le=99)
    mask_w: float = Field(default=100, ge=1, le=100)
    mask_h: float = Field(default=18, ge=1, le=100)
    mask_blur: int = Field(default=12, ge=1, le=40)
    blur_regions: list[BlurRegion] = Field(default_factory=list, max_length=20)
    mask_start_ms: int = Field(default=0, ge=0, le=86400000)
    mask_end_ms: int | None = Field(default=None, ge=1, le=86400000)
    visual_background: VisualLayer = Field(default_factory=VisualLayer)
    overlay_layer: VisualLayer = Field(default_factory=VisualLayer)
    blend_layer: VisualLayer = Field(default_factory=lambda: VisualLayer(mode="screen", opacity=.5))
    logo: str = Field(default="", pattern=r"^(?:[a-f0-9]{32})?$")
    logo_x: float = Field(default=88, ge=0, le=100)
    logo_y: float = Field(default=8, ge=0, le=100)
    logo_size: float = Field(default=12, ge=2, le=70)
    title: str = Field(default="", max_length=300)
    title_x: float = Field(default=50, ge=0, le=100)
    title_y: float = Field(default=10, ge=0, le=100)
    title_size: int = Field(default=42, ge=10, le=160)
    title_color: str = Field(default="#ffffff", pattern=r"^#[0-9a-fA-F]{6}$")
    title_box: bool = False
    title_box_color: str = Field(default="#000000", pattern=r"^#[0-9a-fA-F]{6}$")
    title_box_opacity: float = Field(default=.6, ge=0, le=1)
    background: str = Field(default="", pattern=r"^(?:[a-f0-9]{32})?$")
    background_volume: float = Field(default=.15, ge=0, le=2)
    original_audio: Literal["mute", "original", "instrumental", "vocals"] = "mute"
    original_volume: float = Field(default=.15, ge=0, le=2)
    voice_volume: float = Field(default=1, ge=0, le=2)
    ducking: bool = True
    denoise: bool = False
    normalize: bool = True

    @field_validator("output_width", "output_height")
    @classmethod
    def even_dimensions(cls, value):
        if value % 2:
            raise ValueError("Kích thước xuất phải là số chẵn để mã hóa H.264.")
        return value

    @model_validator(mode="after")
    def valid_mask_interval(self):
        if self.mask_end_ms is not None and self.mask_end_ms <= self.mask_start_ms:
            raise ValueError("Vùng phụ đề gốc: kết thúc phải sau bắt đầu.")
        return self


def config(value=None):
    return EditSettings.model_validate(value or {}).model_dump()


def even(value):
    return max(2, math.floor(value / 2 + .5) * 2)


def display_size(stream):
    w, h = int(stream["width"]), int(stream["height"])
    try:
        n, d = map(int, stream.get("sample_aspect_ratio", "1:1").split(":"))
        if n > 0 and d > 0:
            w = even(w * n / d)
    except (ValueError, TypeError):
        pass
    rotation = float(stream.get("tags", {}).get("rotate", 0))
    for side in stream.get("side_data_list", []):
        if "rotation" in side:
            rotation = float(side["rotation"])
    if round(rotation) % 180 == 90:
        w, h = h, w
    return even(w), even(h)


@lru_cache(maxsize=64)
def _video_info(path, mtime, size):
    info = media.probe(Path(path))
    stream = next(s for s in info["streams"] if s["codec_type"] == "video")
    w, h = display_size(stream)
    return {"width": w, "height": h, "duration_ms": round(float(info.get("format", {}).get("duration", 0))*1000)}


def video_info(path):
    stat = path.stat()
    return dict(_video_info(str(path.resolve()), stat.st_mtime_ns, stat.st_size))


def geometry(source_width, source_height, c):
    """Same geometry as canvasGeometry in editor-ui.js, in output pixels."""
    ratio = c["output_ratio"]
    if ratio == "source":
        w, h = even(source_width), even(source_height)
    elif ratio == "custom":
        w, h = c["output_width"], c["output_height"]
    else:
        a, b = map(int, ratio.split(":"))
        unit = c["output_short_side"] / min(a, b)
        w, h = even(a * unit), even(b * unit)
    fit = (max if c["video_fit"] == "cover" else min)(w/source_width, h/source_height)
    sw, sh = even(source_width*fit*c["zoom"]), even(source_height*fit*c["zoom"])
    return w, h, sw, sh


def caption(cue, settings):
    if settings["target_language"] != "vi":
        if cue.get("translation_language", settings["target_language"]) == settings["target_language"]:
            return cue.get("translation") or cue["text"]
    return cue["text"]


def ass_color(value, opacity=1):
    return f"&H{round((1-opacity)*255):02X}" + value[5:7] + value[3:5] + value[1:3]


def ass_text(text):
    # Strip ASS control syntax and preserve human-readable Unicode.
    return str(text).replace("\\", "／").replace("{", "(").replace("}", ")").replace("\r", "").replace("\n", "\\N")


def ass_time(ms):
    cs = round(ms / 10)
    return f"{cs // 360000}:{cs // 6000 % 60:02}:{cs // 100 % 60:02}.{cs % 100:02}"


def write_ass(path, cues, c, width, height, duration, burn=True):
    caption_box = ass_color(c.get('subtitle_box_color', '#000000'), c.get('subtitle_box_opacity', .6))
    title_box = ass_color(c.get('title_box_color', '#000000'), c.get('title_box_opacity', .6))
    header = f"""[Script Info]
ScriptType: v4.00+
PlayResX: {width}
PlayResY: {height}
WrapStyle: 0
[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Caption,{c['subtitle_font']},{c['subtitle_size']},{ass_color(c['subtitle_color'])},&H0000FFFF,{caption_box if c['subtitle_style']=='box' else '&H00101010'},{caption_box},0,0,0,0,100,100,0,0,{3 if c['subtitle_style']=='box' else 1},2,0,5,20,20,20,1
Style: Title,{c['subtitle_font']},{c['title_size']},{ass_color(c['title_color'])},&H00FFFFFF,{title_box if c.get('title_box') else '&H00101010'},{title_box},-1,0,0,0,100,100,0,0,{3 if c.get('title_box') else 1},2,0,5,20,20,20,1
[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
    lines = [header]
    if burn:
        for cue in cues:
            pos = f"\\pos({width*c['subtitle_x']/100:.1f},{height*c['subtitle_y']/100:.1f})"
            text = ass_text(caption(cue, c))
            if c["subtitle_style"] == "fade":
                pos += "\\fad(120,120)"
            elif c["subtitle_style"] == "karaoke":
                words = text.split()
                step = max(1, round((cue["end_ms"]-cue["start_ms"])/10/max(1, len(words))))
                text = " ".join("{\\kf" + str(step) + "}" + word for word in words)
            lines.append(f"Dialogue: 0,{ass_time(cue['start_ms'])},{ass_time(cue['end_ms'])},Caption,,0,0,0,,{{{pos}}}{text}\n")
    if c["title"].strip():
        pos = f"\\pos({width*c['title_x']/100:.1f},{height*c['title_y']/100:.1f})"
        lines.append(f"Dialogue: 1,0:00:00.00,{ass_time(duration)},Title,,0,0,0,,{{{pos}}}{ass_text(c['title'])}\n")
    path.write_text("".join(lines), encoding="utf-8-sig")


def time_enable(region):
    start = region.get("start_ms", 0)/1000
    end = region.get("end_ms")
    return f"gte(t,{start})" + (f"*lt(t,{end/1000})" if end is not None else "")


def render_video(project, video, audio, output: Path, duration, burn=True):
    c = config(project.get("edit"))
    info = media.probe(video)
    stream = next(s for s in info["streams"] if s["codec_type"] == "video")
    source_w, source_h = display_size(stream)
    w, h, sw, sh = geometry(source_w, source_h, c)
    folder = output.parent
    write_ass(folder / "styled.ass", project["cues"], c, w, h, duration, burn)
    (folder / "fonts").mkdir(exist_ok=True)
    for font in (storage.ROOT / "web").glob("*.ttf"):
        shutil.copy2(font, folder / "fonts" / font.name)
    args = [media.binary(), "-y", "-v", "error", "-i", str(video), "-i", str(audio)]
    # Normalize square pixels after FFmpeg autorotation, before source-relative masks.
    filters, source, index = [f"[0:v]scale={source_w}:{source_h},setsar=1[normalized]"], "normalized", 2
    regions = ([(c | {"start_ms": c["mask_start_ms"], "end_ms": c["mask_end_ms"]}, c["original_subtitles"])] if c["original_subtitles"] != "keep" else [])
    regions += [(region, "blur") for region in c["blur_regions"]]
    for number, (region, mode) in enumerate(regions):
        enable = time_enable(region)
        x, y = min(source_w-1, round(source_w*region["mask_x"]/100)), min(source_h-1, round(source_h*region["mask_y"]/100))
        mw, mh = max(1, min(source_w-x, round(source_w*region["mask_w"]/100))), max(1, min(source_h-y, round(source_h*region["mask_h"]/100)))
        clean, base, crop, masked = [f"{name}{number}" for name in ("clean", "maskbase", "maskregion", "masked")]
        if mode == "cover":
            filters.append(f"[{source}]drawbox=x={x}:y={y}:w={mw}:h={mh}:color=black:t=fill:enable='{enable}'[{clean}]")
        else:
            # Blur the chosen source rectangle before zoom/rotation, matching the UI.
            radius = min(region["mask_blur"], max(0, (min(mw,mh)-1)//2))
            filters += [f"[{source}]format=yuv444p,split=2[{base}][{crop}]",
                        f"[{crop}]crop=w={mw}:h={mh}:x={x}:y={y}:exact=1,boxblur={radius}:2[{masked}]",
                        f"[{base}][{masked}]overlay=x={x}:y={y}:format=auto:enable='{enable}'[{clean}]"]
        source = clean
    angle = c['rotation']*math.pi/180
    filters += [f"[{source}]scale={sw}:{sh},setsar=1,format=rgba,rotate={angle:.8f}:ow=rotw({angle:.8f}):oh=roth({angle:.8f}):c=black@0[transformed]",
                f"color=c={c['canvas_color']}:s={w}x{h}:r=30:d={duration/1000}[canvas]"]
    def visual(key, base):
        nonlocal index
        layer = c[key]
        if not layer["asset"]:
            return base
        path, _ = storage.project_asset(project, layer["asset"])
        args.extend((["-loop", "1"] if path.suffix.lower() in {".png", ".jpg", ".jpeg", ".webp"} else ["-stream_loop", "-1"]) + ["-i", str(path)])
        name = key
        alpha = 1 if key == "blend_layer" and layer["mode"] != "normal" else layer["opacity"]
        filters.append(f"[{index}:v]setpts=PTS-STARTPTS+{layer['start_ms']/1000}/TB,scale={max(2,round(w*layer['width']/100))}:-2,setsar=1,format=rgba,colorchannelmixer=aa={alpha}[{name}]")
        index += 1
        if key == "blend_layer" and layer["mode"] != "normal":
            # Build a canvas-sized blend plate, then apply only during its interval.
            neutral = "white" if layer["mode"] == "multiply" else "black"
            filters.extend([f"color=c={neutral}:s={w}x{h}:r=30:d={duration/1000},format=rgba[plate]",
                            f"[plate][{name}]overlay=x=(W-w)*{layer['x']/100}:y=(H-h)*{layer['y']/100}:eof_action=pass[blendplate]",
                            f"[{base}]split[bkeep][bmix]",
                            f"[bmix][blendplate]blend=all_mode={layer['mode']}:all_opacity={layer['opacity']}[blended]",
                            f"[bkeep][blended]overlay=enable='{time_enable(layer)}'[visual_{name}]"])
        else:
            filters.append(f"[{base}][{name}]overlay=x=(W-w)*{layer['x']/100}:y=(H-h)*{layer['y']/100}:eof_action=pass:enable='{time_enable(layer)}'[visual_{name}]")
        return f"visual_{name}"
    canvas = visual("visual_background", "canvas")
    filters.append(f"[{canvas}][transformed]overlay=x=(W-w)*{c['video_x']/100}:y=(H-h)*{c['video_y']/100}:shortest=1[frame]")
    source = "frame"
    source = visual("overlay_layer", source)
    source = visual("blend_layer", source)
    if c["logo"]:
        logo, _ = storage.project_asset(project, c["logo"])
        args += ["-loop", "1", "-i", str(logo)]
        filters += [f"[{index}:v]scale={max(2,round(w*c['logo_size']/100))}:-1[logo]",
                    f"[{source}][logo]overlay=x=(W-w)*{c['logo_x']/100}:y=(H-h)*{c['logo_y']/100}:shortest=1[branded]"]
        source, index = "branded", index+1
    filters.append(f"[{source}]ass=styled.ass:fontsdir=fonts,format=yuv420p[finalv]")
    args += ["-filter_complex", ";".join(filters), "-map", "[finalv]", "-map", "1:a:0",
             "-c:v", "libx264", "-preset", "veryfast", "-crf", "20", "-c:a", "aac", "-b:a", "192k",
             "-t", str(duration/1000), "-movflags", "+faststart", str(output)]
    media.command(args, cwd=folder)


def mix_audio(project, voice: Path, output: Path, duration):
    c = config(project.get("edit"))
    args = [media.binary(), "-y", "-v", "error", "-i", str(voice)]
    sources, index = [], 1
    if c["original_audio"] != "mute" and project.get("video"):
        source, _ = storage.project_asset(project, project["video"])
        if c["original_audio"] in {"instrumental", "vocals"}:
            stems = project.get("stems", {})
            if stems.get("video") != project["video"]:
                raise ValueError("Bấm Tách giọng AI cho video hiện tại trước khi dùng nhạc/giọng đã tách.")
            source = storage.project_path(project["id"]) / "stems" / ("no_vocals.wav" if c["original_audio"] == "instrumental" else "vocals.wav")
            if not source.is_file():
                raise ValueError("Không tìm thấy stem đã tách. Hãy tách giọng lại.")
        if any(s["codec_type"] == "audio" for s in media.probe(source)["streams"]):
            args += ["-i", str(source)]
            sources.append((index, c["original_volume"]))
            index += 1
    if c["background"]:
        source, _ = storage.project_asset(project, c["background"])
        args += ["-stream_loop", "-1", "-i", str(source)]
        sources.append((index, c["background_volume"]))
    vf = f"volume={c['voice_volume']}" + (",highpass=f=80,afftdn=nf=-25" if c["denoise"] else "")
    filters = [f"[0:a]{vf},apad,atrim=duration={duration/1000}[voice]"]
    if sources:
        for i, volume in sources:
            filters.append(f"[{i}:a]volume={volume},apad,atrim=duration={duration/1000}[b{i}]")
        labels = "".join(f"[b{i}]" for i,_ in sources)
        filters.append(f"{labels}amix=inputs={len(sources)}:normalize=0[background]")
        if c["ducking"]:
            filters += ["[voice]asplit=2[side][spoken]", "[background][side]sidechaincompress=threshold=0.02:ratio=8:attack=20:release=350[ducked]",
                        "[spoken][ducked]amix=inputs=2:normalize=0[mixed]"]
        else:
            filters.append("[voice][background]amix=inputs=2:normalize=0[mixed]")
        last = "mixed"
    else:
        last = "voice"
    final = "loudnorm=I=-14:TP=-1.5:LRA=11" if c["normalize"] else "alimiter=limit=0.95:latency=1"
    filters.append(f"[{last}]{final}[out]")
    args += ["-filter_complex", ";".join(filters), "-map", "[out]", "-ar", "48000", "-ac", "2", "-t", str(duration/1000), str(output)]
    media.command(args)
