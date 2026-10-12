from __future__ import annotations

from contextlib import asynccontextmanager
import hmac
import os
from pathlib import Path
from typing import Literal
import secrets
from urllib.parse import urlsplit
from uuid import uuid4

from fastapi import FastAPI, File, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, ConfigDict, Field

from . import VERSION, media, storage, editor, distribution, timeline
from .jobs import JobQueue
from .workflows import Workflows
from .web_build import web_page
from . import tts_providers


class Cue(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: int = Field(ge=1, le=100000)
    start_ms: int = Field(ge=0, le=3_600_000)
    end_ms: int = Field(ge=0, le=3_600_000)
    source_text: str = Field(default="", max_length=5000)
    text: str = Field(max_length=5000)
    translation: str = Field(default="", max_length=5000)
    voice: str = Field(default="", max_length=64)
    rate: float = Field(default=1, ge=0.5, le=2, allow_inf_nan=False)
    tts: tts_providers.SpeechOptions | None = None


class ProjectEdit(BaseModel):
    model_config = ConfigDict(extra="forbid")
    revision: int
    name: str = Field(max_length=100)
    voice: str = Field(default="", max_length=64)
    video: str = ""
    cues: list[Cue] = Field(max_length=5000)
    edit: editor.EditSettings | None = None
    translation_consent: bool | None = Field(default=None, strict=True)
    tts: tts_providers.SpeechOptions | None = None


class CreateProject(BaseModel):
    kind: Literal['dub','edit'] = 'dub'
    name: str = Field(default="Lồng tiếng mới", max_length=100)
    parent: str = Field(default="", max_length=4096)
    edit: editor.EditSettings | None = None

class RetryJob(BaseModel):
    model_config=ConfigDict(extra='forbid')
    confirmed: bool = Field(default=False,strict=True)
    network_confirmed: bool = Field(default=False,strict=True)


class BackupCreate(BaseModel):
    model_config = ConfigDict(extra='forbid')
    project_ids: list[str] = Field(default_factory=list, max_length=100)
    include_settings: bool = Field(default=True, strict=True)
    include_keys: bool = Field(default=False, strict=True)


class BackupRestore(BaseModel):
    model_config = ConfigDict(extra='forbid')
    asset_id: str = Field(pattern=r'^[a-f0-9]{32}$')
    projects: bool = Field(default=True, strict=True)
    settings: bool = Field(default=False, strict=True)
    keys: bool = Field(default=False, strict=True)
    confirmed: bool = Field(default=False, strict=True)


class ReferenceAlignment(BaseModel):
    reference: str = Field(min_length=1,max_length=5000)
    words: list[timeline.WordCue] = Field(min_length=1,max_length=2000)


class Task(BaseModel):
    kind: str
    payload: dict = Field(default_factory=dict)


class RevealFolder(BaseModel):
    model_config = ConfigDict(extra="forbid")
    tab: str = Field(max_length=20)
    artifact: str = Field(default="", max_length=4096)
    project_id: str = Field(default="", max_length=32)


class DownloadSelection(BaseModel):
    model_config = ConfigDict(extra='forbid')
    ids: list[str] = Field(min_length=1,max_length=50)
    tab: str = Field(default='',pattern=r'^(|dub|edit)$')
    delete_files: bool = False


KINDS = {"voices", "clone", "document", "tts", "podcast", "import_srt", "asr", "translate", "dub", "export", "preview", "separate", "editor_media", "editor_proxy", "editor_preview", "editor_export"}
KINDS |= {"download", "download_scan"}
KINDS |= {'subtitle_remove', 'vsr_check', 'subtitle_prepare'}
KINDS |= {'removal_preview','removal_effect_preview','library_install'}
KINDS.add('editor_separate')
KINDS.add('tts_voices')
KINDS |= {'editor_face','editor_background'}
KINDS.add('editor_creative')
KINDS.add('project_transfer')
KINDS |= {'editor_tools','editor_object'}
UPLOAD_EXTS = {".wav", ".mp3", ".m4a", ".ogg", ".flac", ".webm", ".mp4", ".mov", ".mkv", ".avi",
               ".srt", ".txt", ".md", ".docx", ".pdf", ".png", ".jpg", ".jpeg", ".webp",'.rvp', '.rvbackup'}


def make_app() -> FastAPI:
    page_html, web_build = web_page(storage.ROOT / "web")
    flow = Workflows()
    queue = JobQueue(flow)
    token = secrets.token_urlsafe(32)

    @asynccontextmanager
    async def lifespan(app):
        from . import license_session
        storage.recover_pending_transfers()
        refresh_stop,refresh_thread=license_session.start()
        try:yield
        finally:
            refresh_stop.set();refresh_thread.join(1)
            queue.close()
            flow.engine.stop()

    app = FastAPI(title="Reup Voice Studio", version=VERSION, lifespan=lifespan, docs_url=None, redoc_url=None, openapi_url=None)
    app.state.queue = queue
    app.state.flow = flow
    app.state.pick_folder = None
    app.state.open_folder = lambda path: os.startfile(str(path))

    @app.middleware("http")
    async def local_only(request: Request, call_next):
        host = request.headers.get("host", "").split(":")[0]
        if host not in {"127.0.0.1", "localhost", "testserver"}:
            return JSONResponse({"detail": "Chỉ truy cập cục bộ."}, status_code=403)
        protected = request.url.path.startswith(("/api/", "/files/"))
        if protected and not hmac.compare_digest(request.cookies.get("rv-session", ""), token):
            return JSONResponse({"detail": "Mở lại trang chính để tạo phiên."}, status_code=403)
        if request.method not in {"GET", "HEAD", "OPTIONS"}:
            if not hmac.compare_digest(request.headers.get("x-reup-token", ""), token):
                return JSONResponse({"detail": "Phiên không hợp lệ; tải lại trang."}, status_code=403)
            origin = request.headers.get("origin")
            if origin and urlsplit(origin).netloc != request.headers.get("host"):
                return JSONResponse({"detail": "Không cho phép yêu cầu khác nguồn."}, status_code=403)
            if getattr(app.state, 'update_exit', False):
                return JSONResponse({'detail':'Đang đóng ứng dụng để cập nhật.'}, status_code=409)
            if getattr(queue, 'maintenance', False):
                return JSONResponse({'detail':'Đang sao lưu/khôi phục; chờ hoàn tất.'}, status_code=409)
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["X-Frame-Options"] = "DENY"
        if protected or request.url.path.startswith("/static/"):
            response.headers["Cache-Control"] = "no-store"
        return response

    @app.exception_handler(ValueError)
    async def invalid(request, exc):
        return JSONResponse({"detail": str(exc)}, status_code=400)

    @app.get("/", response_class=HTMLResponse)
    def index():
        response = HTMLResponse(page_html)
        response.set_cookie("rv-session", token, httponly=True, samesite="strict")
        response.headers["Cache-Control"] = "no-store"
        return response

    @app.get("/api/state")
    def state():
        jobs = queue.all()
        for row in jobs:
            row["result"] = {k: v for k, v in row.get("result", {}).items() if k not in {"text", "voices"}}
        return {"version": VERSION, "web_build": web_build, "csrf": token, "settings": storage.settings(public=True),
                "engine": flow.engine.status(), "voices": flow.engine.voices,
                "projects": storage.list_projects(), "jobs": jobs,"job_load_issues":queue.load_issues,
                "presets": storage.read_json(storage.DATA / "presets.json", []),
                "editor_defaults": editor.config(), "folder_picker": bool(app.state.pick_folder)}

    @app.get("/api/instance")
    def instance():
        return {"app": "reup-voice-studio", "version": VERSION, "web_build": web_build,
                "root": str(storage.ROOT.resolve()), "data": str(storage.DATA.resolve())}

    @app.post("/api/folder")
    def pick_folder():
        if not app.state.pick_folder:
            raise ValueError("Trình duyệt không chọn được đường dẫn thư mục. Nhập đường dẫn hoặc dùng cửa sổ desktop.")
        return {"path": app.state.pick_folder()}

    @app.post("/api/presets")
    def preset(body: dict):
        name = str(body.get("name", "")).strip()[:80]
        if not name:
            raise ValueError("Nhập tên cấu hình.")
        value = editor.config(body.get("edit"))
        with storage.LOCK:
            rows = storage.read_json(storage.DATA / "presets.json", [])
            rows.append({"id": uuid4().hex, "name": name, "edit": value})
            storage.atomic_json(storage.DATA / "presets.json", rows)
        return rows[-1]

    @app.get("/api/layout-presets")
    def layout_presets():
        return storage.read_json(storage.DATA / "layout-presets.json", [])

    @app.post("/api/layout-presets")
    def add_layout_preset(body: timeline.LayoutPreset):
        with storage.LOCK:
            rows = storage.read_json(storage.DATA / "layout-presets.json", [])
            if len(rows) >= 200:
                raise ValueError("Thư viện tối đa 200 preset bố cục.")
            value = {"id": uuid4().hex, **body.model_dump()}
            rows.append(value)
            storage.atomic_json(storage.DATA / "layout-presets.json", rows)
        return value

    @app.post("/api/open-output-folder")
    def open_output_folder(body: RevealFolder):
        path = storage.reveal_folder(body.tab, body.artifact, body.project_id)
        try:
            app.state.open_folder(path)
        except OSError as exc:
            raise ValueError("Không mở được Explorer. Thư mục: " + str(path)) from exc
        return {"path": str(path)}

    @app.get("/api/jobs/{job_id}")
    def job(job_id: str):
        with queue.lock:
            if storage.identifier(job_id) not in queue.rows:
                raise HTTPException(404)
            return queue.rows[job_id]

    @app.get("/api/reading")
    def get_reading():
        return storage.reading_settings()

    @app.post('/api/cue-estimate')
    def cue_estimate(body: Cue):
        from .subtitle_qc import estimate_cue
        return estimate_cue(body.model_dump())

    @app.post('/api/align-reference')
    def align_reference(body: ReferenceAlignment):
        from .word_timing import align_reference
        words=[w.model_dump() for w in body.words]
        if any(w['end']<=w['start'] or i and w['start']<words[i-1]['end'] for i,w in enumerate(words)):
            raise ValueError('Mốc từ phải tăng dần, không chồng nhau.')
        return align_reference(body.reference,words)

    @app.post("/api/reading")
    def save_reading(value: dict):
        if queue.busy():
            raise HTTPException(409, "Chờ tác vụ xong trước khi đổi luật đọc.")
        from .reading import config
        try:
            return storage.reading_settings(config(value))
        except ValueError as exc:
            raise HTTPException(400, "Luật đọc không hợp lệ: " + str(exc)) from exc

    @app.post("/api/reading-preview")
    def reading_preview(value: dict):
        from .reading import config, pieces
        text=str(value.get("text", ""))
        if len(text)>10000:
            raise HTTPException(400, "Thử tối đa 10.000 ký tự.")
        return {"pieces":pieces(text, config(value.get("settings"))), "source":text}

    @app.get("/api/license")
    def license_status():
        return distribution.license_status()

    @app.post("/api/license")
    def license_activate(body: dict):
        return distribution.activate(body.get("key", ""))

    @app.post('/api/license/refresh')
    def license_refresh():return distribution.refresh_license()

    @app.get("/api/update")
    def update_check():
        return distribution.check_update()

    @app.post("/api/update")
    def update_download():
        if queue.busy():
            raise HTTPException(409, "Chờ tác vụ xong trước khi cập nhật.")
        return distribution.download_update()

    @app.post('/api/update/install')
    def update_install():
        with queue.lock:
            if queue.busy():
                raise HTTPException(409, 'Chờ tác vụ hoàn tất trước khi cập nhật.')
            if not getattr(app.state, 'desktop_update', False):
                raise HTTPException(409, 'Mở bản desktop đã cài để tự cài cập nhật. Bản web chỉ tải bộ cài.')
            result = distribution.launch_update()
            queue.accepting = False
            app.state.update_exit = True
        return result

    @app.get('/api/ui-preferences')
    def ui_preferences_state():
        from .ui_preferences import preferences
        return preferences()

    @app.post('/api/ui-preferences')
    def ui_preferences_save(body:dict):
        from .ui_preferences import preferences
        return preferences(body)

    @app.post('/api/libraries/remove')
    def library_remove(body:dict):
        from . import libraries
        if queue.busy(): raise HTTPException(409,'Chờ tác vụ xong trước khi gỡ thư viện.')
        if body.get('library')=='vieneu': flow.engine.stop()
        return libraries.remove(body)

    @app.get('/api/advanced-ai/status')
    def ai_readiness():
        from .advanced_ai import readiness
        return readiness()

    @app.post("/api/settings")
    def settings(value: dict):
        if queue.busy():
            raise HTTPException(409, "Chờ tác vụ xong hoặc dừng trước khi thay cài đặt.")
        allowed = set(storage.settings())
        if set(value) - allowed or any(not isinstance(v, str) or len(v) > 4096 for v in value.values()):
            raise ValueError("Cài đặt không hợp lệ.")
        previous = storage.settings()
        result = storage.save_settings(value)
        if any(previous[k] != storage.settings()[k] for k in ("precision", "vieneu_home")):
            flow.engine.stop()
        return result

    @app.get('/api/tts-providers')
    def tts_catalog():
        return tts_providers.public()

    @app.post('/api/tts-providers/config')
    def tts_config(value: dict):
        if queue.busy():raise HTTPException(409,'Chờ tác vụ xong trước khi đổi cài đặt TTS.')
        tts_providers.config(value)
        return tts_providers.public()

    @app.get('/api/llm-profiles')
    def llm_profiles():
        from .llm_profiles import public
        return public()

    @app.get('/api/projects/{project_id}/subtitle-qc')
    def subtitle_qc(project_id:str):
        from .subtitle_qc import review
        return review(storage.project(project_id))

    @app.post('/api/llm-profiles/{action}')
    def change_llm_profiles(action:str,body:dict):
        if queue.busy():raise HTTPException(409,'Chờ tác vụ xong hoặc dừng trước khi đổi cấu hình LLM.')
        from . import llm_profiles
        if action=='save':return llm_profiles.save(body)
        if action not in {'activate','delete'}:raise ValueError('Thao tác LLM không hợp lệ.')
        pid=body.get('id')
        if not isinstance(pid,str):raise ValueError('Chọn cấu hình LLM.')
        return llm_profiles.activate(pid) if action=='activate' else llm_profiles.delete(pid)

    @app.post("/api/upload")
    def upload(file: UploadFile = File(...)):
        suffix = Path(file.filename or "").suffix.lower()
        if suffix not in UPLOAD_EXTS and suffix!='.rvp':
            raise ValueError("Định dạng chưa hỗ trợ. Word cần .docx, không phải .doc.")
        limit = 2 * 1024**3 if suffix in {".mp4", ".mov", ".mkv", ".webm", ".avi",'.rvp', '.rvbackup'} else 30 * 1024**2
        file_id = uuid4().hex
        folder = storage.DATA / "uploads" / file_id
        folder.mkdir(parents=True)
        path = folder / ("source" + suffix)
        size = 0
        try:
            with path.open("wb") as target:
                while block := file.file.read(1024 * 1024):
                    size += len(block)
                    if size > limit:
                        raise ValueError("File quá lớn: video tối đa 2 GB, tài liệu/audio tối đa 30 MB.")
                    target.write(block)
            if not size:
                raise ValueError("File rỗng.")
            meta = {"id": file_id, "name": Path(file.filename or "file").name, "file": path.name, "bytes": size}
            storage.atomic_json(folder / "asset.json", meta)
        except Exception:
            path.unlink(missing_ok=True)
            raise
        finally:
            file.file.close()
        return meta | {"url": f"/files/uploads/{file_id}/{path.name}"}

    @app.post('/api/backups/create')
    def backup_create(body: BackupCreate):
        from . import backup
        with backup.idle(queue):
            return backup.create(body.project_ids, body.include_settings, body.include_keys)

    @app.post('/api/backups/inspect')
    def backup_inspect(body: BackupRestore):
        from . import backup
        source, _ = storage.asset(body.asset_id)
        if source.suffix != '.rvbackup': raise ValueError('Chọn file .rvbackup.')
        return backup.inspect(source)

    @app.post('/api/backups/restore')
    def backup_restore(body: BackupRestore):
        from . import backup
        if not body.confirmed: raise ValueError('Xác nhận khôi phục trước khi tiếp tục.')
        source, _ = storage.asset(body.asset_id)
        if source.suffix != '.rvbackup': raise ValueError('Chọn file .rvbackup.')
        with backup.idle(queue):
            result = backup.restore(source, body.projects, body.settings, body.keys)
            if result['settings']: flow.engine.stop()
            return result

    @app.post("/api/projects")
    def new_project(value: CreateProject):
        return storage.new_project(value.name, value.parent, value.edit.model_dump() if value.edit else None, value.kind)

    @app.post('/api/projects/{project_id}/delete')
    def delete_project(project_id:str):
        with storage.LOCK,queue.lock:
            if queue.busy(project_id):raise ValueError('Dự án đang có tác vụ; chờ hoặc dừng trước khi xóa.')
            return storage.delete_project(project_id)

    @app.get('/api/deleted-projects')
    def deleted_projects():return storage.list_projects(deleted=True)

    @app.post('/api/projects/{project_id}/restore')
    def restore_project(project_id:str):return storage.delete_project(project_id,restore=True)

    @app.post('/api/history/clear')
    def clear_history(body:dict):
        ids=body.get('ids')
        if ids is not None and (not isinstance(ids,list) or len(ids)>1000):raise ValueError('Danh sách lịch sử không hợp lệ.')
        return queue.forget(ids)

    @app.get("/api/projects/{project_id}/timeline")
    def get_timeline(project_id: str):
        project = storage.project(project_id)
        value = timeline.load(project_id)
        assets = []
        keys = set(value["assets"]) | {c["asset"] for t in value["tracks"] for c in t["clips"] if c["asset"]}
        for key in sorted(keys):
            item = timeline.describe(project, key)
            for name in ("thumbnail", "waveform"):
                preview = storage.project_path(project_id) / "editor-media" / key / (name + ".png")
                if preview.exists():
                    item[name] = storage.file_url(preview)
            assets.append(item)
        return {"timeline": value, "media": assets, "name": project["name"]}

    @app.get("/api/projects/{project_id}/editor-media/{asset_id}")
    def get_editor_media(project_id: str, asset_id: str):
        item = timeline.describe(storage.project(project_id), asset_id)
        for name in ("thumbnail", "waveform"):
            preview = storage.project_path(project_id) / "editor-media" / asset_id / (name + ".png")
            if preview.exists():
                item[name] = storage.file_url(preview)
        return item

    @app.post("/api/projects/{project_id}/timeline")
    def put_timeline(project_id: str, body: timeline.Timeline):
        with storage.LOCK:
            if queue.busy(project_id):
                raise HTTPException(409, "Dự án đang xử lý; chờ xong trước khi lưu timeline.")
            if body.revision != timeline.load(project_id)["revision"]:
                raise HTTPException(409, "Timeline đã thay đổi ở phiên khác. Mở lại để tránh ghi đè; giữ bản nháp.")
            return timeline.save(project_id, body.model_dump())

    @app.get("/api/projects/{project_id}")
    def project(project_id: str):
        value = storage.project(project_id)
        value["edit"] = editor.config(value.get("edit"))
        value["folder"] = str(storage.project_path(project_id))
        value["issues"] = media.validate_cues(value["cues"]) + [i for i in value.get("import_issues", []) if "block" in i]
        if value.get("video"):
            path, meta = storage.project_asset(value, value["video"])
            value["video_asset"] = meta | {"url": storage.file_url(path)}
            try:
                value["video_info"] = editor.video_info(path)
            except (ValueError, RuntimeError, StopIteration):
                value["video_info"] = None
        from .subtitle_qc import estimate_cue
        reading_rules=storage.reading_settings()
        for cue in value["cues"]:
            try:cue['estimate']=estimate_cue(cue,reading_rules)
            except ValueError:cue['estimate']=None # Invalid pause syntax is shown when edited/reviewed.
            if cue.get("audio"):
                cue["audio_url"] = storage.file_url(storage.project_path(project_id) / "cues" / cue["audio"])
        value["edit_assets"] = {}
        for key in ("logo", "background"):
            if value["edit"][key]:
                path, meta = storage.project_asset(value, value["edit"][key])
                value["edit_assets"][key] = meta | {"url": storage.file_url(path)}
        for key in ("visual_background", "overlay_layer", "blend_layer"):
            if value["edit"][key]["asset"]:
                path, meta = storage.project_asset(value, value["edit"][key]["asset"])
                value["edit_assets"][key] = meta | {"url": storage.file_url(path)}
        return value

    @app.post("/api/projects/{project_id}")
    def edit_project(project_id: str, body: ProjectEdit):
        with storage.LOCK:
            if queue.busy(project_id):
                raise HTTPException(409, "Dự án đang xử lý; chờ xong hoặc dừng trước khi sửa.")
            value = storage.project(project_id)
            if body.revision != value["revision"]:
                raise HTTPException(409, "Dự án đã thay đổi ở phiên khác. Tải lại để tránh ghi đè.")
            if len({c.id for c in body.cues}) != len(body.cues):
                raise ValueError("Cue trùng id.")
            if body.video:
                path, _ = storage.project_asset(value, body.video)
                if path.suffix not in {".mp4", ".mov", ".mkv", ".webm", ".avi"}:
                    raise ValueError("File được chọn không phải video.")
            old_cues = {c["id"]: c for c in value["cues"]}
            rows, changed = [], body.voice != value["voice"] or body.video != value["video"]
            next_tts=body.tts.model_dump() if body.tts else None
            tts_changed='tts' in body.model_fields_set and next_tts!=value.get('tts')
            for entry in body.cues:
                row = entry.model_dump(exclude={'tts'})
                if 'tts' in entry.model_fields_set:row['tts']=entry.tts.model_dump() if entry.tts else None
                old = old_cues.get(row["id"], {})
                different = any(row[k] != old.get(k, 1 if k == "rate" else None if k=='tts' else "") for k in row if k != "translation") or body.voice != value["voice"]
                changed = changed or row["translation"] != old.get("translation", "")
                row = {**old, **row}
                if tts_changed and not row.get('tts'):different=True
                if different:
                    row.update(status="pending", error="")
                    changed = True
                rows.append(row)
            changed = changed or len(rows) != len(value["cues"])
            next_edit = body.edit.model_dump() if body.edit else editor.config(value.get("edit"))
            changed = changed or next_edit != value.get("edit")
            for key, extensions in (("logo", {".png", ".jpg", ".jpeg", ".webp"}),
                                    ("background", {".mp3", ".wav", ".m4a", ".flac", ".ogg"})):
                if next_edit[key]:
                    path, _ = storage.project_asset(value, next_edit[key])
                    if path.suffix.lower() not in extensions:
                        raise ValueError("Sai loại file cho " + key)
            for key in ("visual_background", "overlay_layer", "blend_layer"):
                if next_edit[key]["asset"]:
                    path, _ = storage.project_asset(value, next_edit[key]["asset"])
                    if path.suffix.lower() not in {".png", ".jpg", ".jpeg", ".webp", ".mp4", ".mov", ".mkv", ".avi", ".webm"}:
                        raise ValueError("Lớp hình cần ảnh hoặc video: " + key)
            if value.get("video") != body.video:
                value.pop("preview", None)
                value.pop("stems", None)
            value["edit"] = next_edit
            if body.translation_consent is not None:
                value["translation_consent"] = body.translation_consent
            if 'tts' in body.model_fields_set:value['tts']=next_tts
            changed=changed or tts_changed
            value.update(name=body.name, voice=body.voice, video=body.video, cues=rows)
            storage.retain_assets(value)
            if changed:
                value["exports"] = []
            storage.save_project(value)
            return project(project_id)

    @app.post("/api/jobs")
    def jobs(body: Task):
        if getattr(app.state, 'update_exit', False):
            raise HTTPException(409, 'Đang cập nhật; không nhận tác vụ mới.')
        if not distribution.license_status()["active"]:
            raise HTTPException(403, "Nhập key bản quyền đang có hiệu lực trong Cài đặt trước khi chạy tác vụ.")
        if body.kind not in KINDS:
            raise ValueError("Tác vụ không hỗ trợ.")
        if len(str(body.payload)) > 600_000:
            raise ValueError("Nội dung quá dài.")
        if body.kind in {"project_transfer", "import_srt", "asr", "translate", "dub", "export", "preview", "separate", "editor_media", "editor_proxy", "editor_preview", "editor_export"}:
            storage.project(body.payload.get("project_id", ""))
        if body.kind=='tts':
            body.payload['tts']=tts_providers.options(body.payload.get('tts'))
        if body.kind=='podcast' and 'speaker_tts' in body.payload:
            body.payload['speaker_tts']=tts_providers.podcast_options(body.payload['speaker_tts'])
        return queue.submit(body.kind, body.payload)

    @app.get('/api/downloads')
    def downloaded():
        return storage.read_json(storage.DATA/'download-index.json',[])

    @app.get('/api/subtitle-removal')
    def removal_state():
        from . import subtitle_removal
        return {'runtime':subtitle_removal.status(),'entries':storage.read_json(storage.DATA/'vsr-index.json',[]),'subtitles':storage.read_json(storage.DATA/'vsr-subtitles.json',[])}

    @app.get('/api/subtitle-removal/preview/{asset_id}')
    def removal_preview_state(asset_id:str):
        from . import subtitle_removal
        return subtitle_removal.preview_state(storage.identifier(asset_id))

    @app.post('/api/subtitle-removal/subtitles/{job_id}/delete')
    def removal_forget_subtitle(job_id:str):
        from . import subtitle_removal
        return subtitle_removal.forget_subtitle(job_id)

    @app.post('/api/subtitle-removal/detect')
    def removal_detect(body:dict):
        from . import libraries
        if queue.busy():raise ValueError('Chờ tác vụ xong trước khi đổi kết nối VSR.')
        return libraries.detect_vsr(body.get('home',''))

    @app.get('/api/libraries')
    def library_state():
        from . import libraries
        return libraries.status()

    @app.get('/api/advanced-ai')
    def advanced_ai_state():
        from . import advanced_ai
        return advanced_ai.config()

    @app.post('/api/advanced-ai')
    def advanced_ai_config(body:dict):
        from . import advanced_ai
        if queue.busy():raise ValueError('Chờ tác vụ xong trước khi đổi runtime AI.')
        return advanced_ai.config(body)

    @app.post('/api/libraries/config')
    def library_config(body:dict):
        from . import libraries
        if queue.busy():raise ValueError('Chờ tác vụ xong trước khi đổi nơi cài thư viện.')
        return libraries.config(body)

    @app.post('/api/subtitle-removal/config')
    def removal_config(body: dict):
        from . import subtitle_removal
        if any(j['kind'] in {'subtitle_remove','vsr_check'} and j['status'] in {'running','queued'} for j in queue.all()):
            raise ValueError('Chờ/dừng tác vụ VSR trước khi đổi bộ chạy.')
        subtitle_removal.config(body)
        return subtitle_removal.status()

    @app.post('/api/subtitle-removal/send')
    def removal_send(body: dict):
        from . import subtitle_removal
        return subtitle_removal.send(body.get('id',''),body.get('tab',''))

    @app.post('/api/downloads/send')
    def send_downloads(body: DownloadSelection):
        from . import downloads
        return downloads.send_many(body.ids,body.tab)

    @app.post('/api/downloads/remove')
    def remove_downloads(body: DownloadSelection):
        from . import downloads
        return downloads.remove_many(body.ids,body.delete_files)

    @app.get('/api/track-presets')
    def track_presets():
        return storage.read_json(storage.DATA/'track-presets.json',[])

    @app.get('/api/creative/catalog')
    def creative_catalog():
        from .creative import catalog
        return catalog()

    @app.post('/api/track-presets')
    def save_track_preset(body: timeline.TrackPreset):
        value=body.model_dump()
        keys=set(value['timeline']['assets'])|{c['asset'] for t in value['timeline']['tracks'] for c in t['clips'] if c['asset']}
        for key in keys:storage.asset(key)
        value['id']=uuid4().hex
        with storage.LOCK:
            rows=storage.read_json(storage.DATA/'track-presets.json',[])
            if len(rows)>=50:raise ValueError('Tối đa 50 preset nhiều track; xóa preset cũ trước.')
            rows.append(value);storage.atomic_json(storage.DATA/'track-presets.json',rows)
        return value

    @app.post('/api/track-presets/{preset_id}/delete')
    def delete_track_preset(preset_id: str):
        storage.identifier(preset_id)
        with storage.LOCK:
            rows=storage.read_json(storage.DATA/'track-presets.json',[])
            storage.atomic_json(storage.DATA/'track-presets.json',[r for r in rows if r['id']!=preset_id])
        return {'ok':True}

    @app.post('/api/downloads/{asset_id}/send')
    def send_download(asset_id: str, body: dict):
        from . import downloads
        return downloads.send(storage.identifier(asset_id),body.get('tab',''))

    @app.post("/api/jobs/{job_id}/cancel")
    def cancel(job_id: str):
        queue.cancel(storage.identifier(job_id))
        return {"ok": True}

    @app.get('/api/jobs/{job_id}/retry-info')
    def retry_info(job_id:str):
        plan=queue.retry_plan(job_id)
        return {key:value for key,value in plan.items() if key!='payload'}

    @app.post('/api/jobs/{job_id}/retry')
    def retry_job(job_id:str,body:RetryJob):
        if getattr(app.state,'update_exit',False):raise HTTPException(409,'Đang cập nhật; không nhận tác vụ mới.')
        if not distribution.license_status()['active']:raise HTTPException(403,'Nhập key bản quyền đang có hiệu lực trước khi chạy tác vụ.')
        return queue.retry(job_id,body.confirmed,body.network_confirmed)

    @app.get("/files/{relative:path}")
    def files(relative: str):
        path = (storage.DATA / relative).resolve()
        root = storage.DATA
        parts = relative.split("/")
        if len(parts) >= 3 and parts[0] == "projects":
            root = storage.project_path(parts[1]).resolve()
            path = (root / "/".join(parts[2:])).resolve()
        if len(parts) >= 3 and parts[0] == "exports":
            registered = storage.read_json(storage.DATA / "output-index.json", {}).get(storage.identifier(parts[1]))
            if not registered:
                raise HTTPException(404)
            root = Path(registered).resolve()
            path = (root / "/".join(parts[2:])).resolve()
        if not path.is_relative_to(root) or not path.is_file():
            raise HTTPException(404)
        allowed_update = path.suffix.lower() == ".exe" and path.name.startswith("ReupVoiceStudio-") and parts[0] in {"outputs", "exports"}
        if relative.split("/")[0] not in {"uploads", "outputs", "projects", "exports"} or (path.suffix.lower() not in UPLOAD_EXTS and not allowed_update):
            raise HTTPException(403)
        inline = path.suffix.lower() in {".mp4", ".webm", ".mp3", ".wav", ".ogg", ".m4a", ".png", ".jpg", ".jpeg", ".webp"}
        return FileResponse(path, filename=path.name, content_disposition_type="inline" if inline else "attachment")

    app.mount("/static", StaticFiles(directory=storage.ROOT / "web"), name="static")
    return app
