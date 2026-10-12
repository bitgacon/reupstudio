from __future__ import annotations

from copy import deepcopy
import json
import os
from pathlib import Path
import re
import shutil
import threading
import time
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[1]
_default_data = Path(os.environ.get("LOCALAPPDATA", str(ROOT))) / "ReupVoiceStudio" if (ROOT / "installed.flag").exists() else ROOT / "data"
DATA = Path(os.environ.get("REUP_DATA", str(_default_data))).resolve()
LOCK = threading.RLock()


def identifier(value: str) -> str:
    if not re.fullmatch(r"[a-f0-9]{32}", value):
        raise ValueError("Mã dữ liệu không hợp lệ.")
    return value


def atomic_json(path: Path, value) -> None:
    """Flush before replace and retain the previous valid JSON, never a damaged copy."""
    path = Path(path)
    content = json.dumps(value, ensure_ascii=False, indent=2).encode('utf-8')
    with LOCK:
        path.parent.mkdir(parents=True, exist_ok=True)
        if path.exists():
            previous = path.read_bytes()
            try:
                json.loads(previous.decode('utf-8-sig'))
            except (ValueError, UnicodeError):
                # Preserve evidence before overwriting an already damaged file.
                _preserve_corrupt(path)
            else:
                _durable_replace(path.with_name(path.name+'.bak'), previous)
        _durable_replace(path, content)


def _durable_replace(path: Path, content: bytes) -> None:
    temporary = path.with_name(path.name + "." + uuid4().hex + ".tmp")
    try:
        with temporary.open('wb') as stream:
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def _preserve_corrupt(path: Path):
    copy = path.with_name(path.name+'.corrupt-'+time.strftime('%Y%m%d-%H%M%S')+'-'+uuid4().hex[:8])
    _durable_replace(copy, path.read_bytes())
    return copy


def read_json(path: Path, default=None):
    path = Path(path)
    with LOCK:
        if not path.exists():
            backup=path.with_name(path.name+'.bak')
            if not backup.exists():return deepcopy(default)
        try:
            return json.loads(path.read_text(encoding='utf-8-sig'))
        except (ValueError, UnicodeError, FileNotFoundError) as exc:
            backup=path.with_name(path.name+'.bak')
            try:
                content=backup.read_bytes()
                value=json.loads(content.decode('utf-8-sig'))
            except (ValueError, UnicodeError, FileNotFoundError):
                raise ValueError(f'File dữ liệu {path.name} bị hỏng, chưa có bản sao hợp lệ. Dữ liệu chưa bị xóa; cần khôi phục trước khi dùng.') from exc
            if path.exists():_preserve_corrupt(path)
            _durable_replace(path,content)
            return value


def default_settings() -> dict:
    value = {"precision": "fp32", "translation_url": "", "translation_model": "",
             "translation_key": "", "translation_batch":"10", "translation_pause":"2", "whisper_model": "small", "vieneu_home": "", "project_root": "",
             **{key: "" for key in ("output_root", "tts_output", "clone_output", "dub_output", "edit_output", "podcast_output", "documents_output", "downloads_output", "removal_output")}}
    return value


def settings(public=False) -> dict:
    value=default_settings()
    value.update(read_json(DATA / "settings.json", {}))
    from .translation_api import normalize
    value['translation_url'],value['translation_model']=normalize(value['translation_url'],value['translation_model'])
    if public:
        value["has_translation_key"] = bool(value.pop("translation_key", ""))
    return value


def save_settings(value: dict) -> dict:
    with LOCK:
        current = settings()
        for key in current:
            if key in value:
                current[key] = value[key]
        if current["precision"] not in {"fp32", "int8"}:
            raise ValueError("Chọn FP32 hoặc INT8.")
        from .translation_api import normalize
        current['translation_url'],current['translation_model']=normalize(current['translation_url'],current['translation_model'])
        try:batch=int(current['translation_batch']);pause=float(current['translation_pause'])
        except (ValueError,TypeError):raise ValueError('Batch/khoảng nghỉ API không hợp lệ.')
        if not 1<=batch<=20 or not 0<=pause<=60:raise ValueError('Batch 1–20 cue; khoảng nghỉ 0–60 giây.')
        for key in ("output_root", "tts_output", "clone_output", "dub_output", "edit_output", "podcast_output", "documents_output", "downloads_output", "removal_output"):
            if current[key] and (not Path(current[key]).is_absolute() or not Path(current[key]).is_dir()):
                raise ValueError("Thư mục đầu ra phải là đường dẫn đầy đủ tới thư mục đã có.")
        atomic_json(DATA / "settings.json", current)
        return settings(public=True)


def reading_settings(value=None):
    from .reading import config
    with LOCK:
        if value is not None:
            atomic_json(DATA / "reading.json", config(value))
        return config(read_json(DATA / "reading.json", {}))


def asset(asset_id: str) -> tuple[Path, dict]:
    folder = DATA / "uploads" / identifier(asset_id)
    meta = read_json(folder / "asset.json")
    if not meta:
        raise ValueError("File chưa được tải vào ứng dụng.")
    path = folder / meta["file"]
    if not path.is_file():
        raise ValueError("Không tìm thấy file đã nhập.")
    return path, meta


def project_path(project_id: str) -> Path:
    key = identifier(project_id)
    registered = read_json(DATA / "project-index.json", {}).get(key)
    return Path(registered) if registered else DATA / "projects" / key


def project_asset(value, asset_id):
    local = value.get("local_assets", {}).get(identifier(asset_id))
    if local:
        path = project_path(value["id"]) / "assets" / local["file"]
        if path.is_file():
            return path, local
    return asset(asset_id)


def retain_assets(value):
    """Keep project sources next to the selected project, without moving originals."""
    edit = value.get("edit", {})
    for key in filter(None, [value.get("video"), edit.get("logo"), edit.get("background"),
                            *[edit.get(k, {}).get("asset") for k in ("visual_background", "overlay_layer", "blend_layer")]]):
        source, meta = project_asset(value, key)
        destination = project_path(value["id"]) / "assets" / (key + source.suffix)
        destination.parent.mkdir(parents=True, exist_ok=True)
        if not destination.exists():
            shutil.copy2(source, destination)
        value.setdefault("local_assets", {})[key] = {**meta, "file": destination.name}


def file_url(path):
    path = Path(path).resolve()
    # Registered projects keep UUID URLs even when their disk folders are readable.
    for key,folder in read_json(DATA/'project-index.json',{}).items():
        root=Path(folder).resolve()
        if path.is_relative_to(root):return f'/files/projects/{key}/'+path.relative_to(root).as_posix()
    if path.is_relative_to(DATA):
        return "/files/" + path.relative_to(DATA).as_posix()
    for key, folder in read_json(DATA / "output-index.json", {}).items():
        root = Path(folder).resolve()
        if path.is_relative_to(root):
            return f"/files/exports/{key}/" + path.relative_to(root).as_posix()
    for key, folder in read_json(DATA / "project-index.json", {}).items():
        root = Path(folder).resolve()
        if path.is_relative_to(root):
            return f"/files/projects/{key}/" + path.relative_to(root).as_posix()
    raise ValueError("File chưa nằm trong thư mục ứng dụng/dự án đã đăng ký.")


OUTPUT_NAMES={"tts":"TextSpeech","clone":"VoiceClone","dub":"VideoDubbing","edit":"VideoEditor","podcast":"Podcast","documents":"Documents","downloads":"Downloads","removal":"RemoveSRT"}

def safe_name(name: str) -> str:
    name=re.sub(r'[<>:"/\\|?*\x00-\x1f]', '_', name).strip(' .')[:90] or 'Job'
    if re.fullmatch(r'(?i)(con|prn|aux|nul|com[1-9]|lpt[1-9])',name.split('.')[0]):name='Job-'+name
    return name

def output_root(tab: str) -> Path:
    if tab not in OUTPUT_NAMES:raise ValueError("Tab đầu ra không hợp lệ.")
    config=settings();configured=config[tab+"_output"] or config["output_root"]
    if configured:
        root=Path(configured)
        if not root.is_absolute() or not root.is_dir():raise ValueError("Thư mục đầu ra không còn tồn tại. Kiểm tra cài đặt lưu file.")
    else:root=DATA/'outputs'
    root=root.resolve()/OUTPUT_NAMES[tab];root.mkdir(parents=True,exist_ok=True)
    return root

def numbered_folder(parent: Path, prefix: str) -> Path:
    with LOCK:
        parent.mkdir(parents=True,exist_ok=True)
        counters=read_json(DATA/'folder-counters.json',{});key=str(parent.resolve()).casefold()+'|'+prefix.casefold()
        number=int(counters.get(key,0))+1
        while True:
            folder=parent/(prefix+str(number))
            try:
                folder.mkdir();counters[key]=number;atomic_json(DATA/'folder-counters.json',counters);return folder
            except FileExistsError:number+=1

def output_folder(tab: str, job_id: str, fallback=None) -> Path:
    identifier(job_id)
    if tab not in {"tts", "clone", "dub", "edit", "podcast", "documents", "downloads", "removal"}:
        raise ValueError("Tab đầu ra không hợp lệ.")
    with LOCK:
        index=read_json(DATA/'output-index.json',{})
        if job_id in index:
            folder=Path(index[job_id]);folder.mkdir(parents=True,exist_ok=True);return folder
        old=Path(fallback) if fallback and Path(fallback).is_dir() else DATA/'outputs'/job_id
        if old.is_dir():folder=old
        else:
            root=output_root(tab)
            folder=numbered_folder(root/'.jobs' if tab=='removal' else root,'Job' if tab=='removal' else OUTPUT_NAMES[tab])
        index[job_id]=str(folder.resolve());atomic_json(DATA/'output-index.json',index)
    return folder

def removal_destination(job_id: str, name: str, extension: str) -> Path:
    """Reserve one shared basename for a job's PNG/MP4/SRT; never overwrite."""
    identifier(job_id)
    if extension not in {'.png','.mp4','.srt'}:raise ValueError('Định dạng kết quả không hợp lệ.')
    with LOCK:
        index=read_json(DATA/'removal-output-index.json',{})
        if job_id not in index:
            root=output_root('removal');base=safe_name(Path(name.replace('\\','/')).stem)+'_clean';candidate=base;n=2
            reserved={row['base'].casefold() for row in index.values() if row['root']==str(root)}
            while candidate.casefold() in reserved or any((root/(candidate+ext)).exists() for ext in ('.png','.mp4','.srt')):
                candidate=base+'_'+str(n);n+=1
            index[job_id]={'root':str(root),'base':candidate};atomic_json(DATA/'removal-output-index.json',index)
        row=index[job_id];root=Path(row['root'])
        # Register shared exports as well as private diagnostic job folders.
        exports=read_json(DATA/'output-index.json',{});shared_key=job_id
        if exports.get(shared_key)!=str(root):
            # Distinct key retains workspace URLs and can serve external shared files.
            shared_key=read_json(DATA/'removal-export-keys.json',{}).get(job_id)
            if not shared_key:
                shared_key=uuid4().hex;keys=read_json(DATA/'removal-export-keys.json',{});keys[job_id]=shared_key;atomic_json(DATA/'removal-export-keys.json',keys)
            exports[shared_key]=str(root);atomic_json(DATA/'output-index.json',exports)
        return root/(row['base']+extension)

def publish_removal(path: Path, job_id: str, name: str) -> Path:
    target=removal_destination(job_id,name,path.suffix)
    # Exclusive creation protects even files added outside the app after reservation.
    created=False
    try:
        with Path(path).open('rb') as source,target.open('xb') as destination:
            created=True;shutil.copyfileobj(source,destination)
            destination.flush();os.fsync(destination.fileno())
    except BaseException:
        if created:target.unlink(missing_ok=True)  # Only our incomplete newly-created copy.
        raise
    return target


def reveal_folder(tab: str, artifact: str = "", project_id: str = "") -> Path:
    """Resolve folders only; never accept a command or an arbitrary local file."""
    from urllib.parse import unquote, urlsplit
    if tab not in {"tts", "clone", "dub", "edit", "podcast", "documents", "downloads", "removal", "history"}:
        raise ValueError("Tab không hợp lệ.")
    if artifact:
        url = urlsplit(artifact)
        if url.scheme or url.netloc or url.query or url.fragment or not url.path.startswith("/files/"):
            raise ValueError("Chỉ mở thư mục của kết quả cục bộ.")
        relative = unquote(url.path[7:])
        parts = relative.split("/")
        if len(parts) < 3 or parts[0] not in {"uploads", "outputs", "projects", "exports"} or any(p in {"", ".", ".."} or "\\" in p or ":" in p for p in parts):
            raise ValueError("Đường dẫn kết quả không hợp lệ.")
        if parts[0]!='outputs':identifier(parts[1])
        root = DATA.resolve()
        path = root / relative
        if parts[0] == "projects":
            project(parts[1])
            root = project_path(parts[1]).resolve()
            path = root.joinpath(*parts[2:])
        elif parts[0] == "exports":
            registered = read_json(DATA / "output-index.json", {}).get(parts[1])
            if not registered:
                raise ValueError("Kết quả chưa được đăng ký.")
            root = Path(registered).resolve()
            path = root.joinpath(*parts[2:])
        path = path.resolve()
        if not path.is_relative_to(root) or not path.is_file():
            raise ValueError("Không tìm thấy kết quả đã lưu.")
        return path.parent
    if project_id and tab in {"dub", "edit"}:
        project(project_id)
        return project_path(project_id).resolve()
    config = settings()
    configured = config.get(tab + "_output") or config["output_root"]
    path = (Path(configured) if configured else DATA / "outputs") if tab=='history' else output_root(tab)
    if configured and (not path.is_absolute() or not path.is_dir()):
        raise ValueError("Thư mục đã chọn không còn tồn tại. Kiểm tra cài đặt.")
    path.mkdir(parents=True, exist_ok=True)
    return path.resolve()


def project(project_id: str) -> dict:
    value = read_json(project_path(project_id) / "project.json")
    if not value or value.get('deleted'):
        raise ValueError("Không tìm thấy dự án.")
    return value


def delete_project(project_id,restore=False):
    with LOCK:
        path=project_path(project_id)/'project.json';value=read_json(path)
        if not value or value.get('id')!=identifier(project_id):raise ValueError('Không tìm thấy dự án.')
        value['deleted']=not restore;value['updated']=time.time()
        if restore and value.pop('transfer_pending',False):
            value.setdefault('import_issues',[]).append({'level':'warning','message':'Bản chuyển dự án chưa hoàn tất; kiểm tra media/timeline trước khi tiếp tục.'})
        atomic_json(path,value)
    return {'message':'Đã khôi phục dự án.' if restore else 'Đã xóa khỏi danh sách; thư mục và file vẫn giữ để khôi phục.'}


def save_project(value: dict) -> dict:
    with LOCK:
        path=project_path(value["id"]) / "project.json"
        if read_json(path,{}).get('deleted'):
            raise ValueError('Dự án đã xóa khỏi danh sách; khôi phục trước khi lưu.')
        value["updated"] = time.time()
        value["revision"] = int(value.get("revision", 0)) + 1
        atomic_json(path, value)
    return value


def project_kind(value, folder=None):
    """Classify old projects without silently migrating or discarding either view."""
    if value.get('kind') in {'dub', 'edit'}:return value['kind']
    source=(folder or project_path(value['id']))/'editor-timeline.json'
    doc=read_json(source, {})
    if doc.get('tracks') or doc.get('assets'):
        return 'hybrid' if value.get('cues') else 'edit'
    return 'edit' if source.is_file() and not value.get('cues') else 'dub'


def new_project(name: str, parent: str = "", edit=None, kind='dub', transfer_pending=False) -> dict:
    from .editor import config
    if kind not in {'dub','edit'}:raise ValueError('Loại dự án không hợp lệ.')
    value = {"id": uuid4().hex, "name": name.strip()[:100] or "Lồng tiếng mới",
             "kind":kind, "video": "", "cues": [], "voice": "", "revision": 0, "exports": [], "import_issues": [], "edit": config(edit)}
    if transfer_pending:value['transfer_pending']=True
    parent = parent.strip() or settings().get("project_root", "")
    root=Path(parent) if parent else DATA/'projects'
    if parent and (not root.is_absolute() or not root.is_dir()):raise ValueError("Thư mục lưu phải là đường dẫn đầy đủ tới thư mục đã có.")
    with LOCK:
        target=numbered_folder(root.resolve(),safe_name(value['name'])+'-')
        index=read_json(DATA/'project-index.json',{});index[value['id']]=str(target);atomic_json(DATA/'project-index.json',index)
    return save_project(value)


def list_projects(deleted=False) -> list[dict]:
    result = []
    paths = list((DATA / "projects").glob("*/project.json"))
    paths.extend(Path(folder) / "project.json" for folder in read_json(DATA / "project-index.json", {}).values())
    for path in dict.fromkeys(paths):
        if not path.is_file():
            continue
        value = read_json(path)
        if bool(value.get('deleted'))!=deleted:continue
        if value.get('transfer_pending') and not deleted:continue
        result.append({k: value.get(k) for k in ("id", "name", "updated", "video")}
                      | {"kind": project_kind(value,path.parent), "cues": len(value["cues"]), "complete": sum(
                          row.get("status") in {"complete", "review"} for row in value["cues"])})
    return sorted(result, key=lambda row: row["updated"], reverse=True)


def recover_pending_transfers():
    """At startup only: retain incomplete copies in the recoverable deleted list."""
    recovered=[]
    paths=list((DATA/'projects').glob('*/project.json'))
    paths.extend(Path(folder)/'project.json' for folder in read_json(DATA/'project-index.json',{}).values())
    with LOCK:
        for path in dict.fromkeys(paths):
            if not path.is_file():continue
            value=read_json(path,{})
            if value.get('transfer_pending') is not True or value.get('deleted'):continue
            key=value.get('id','')
            if not re.fullmatch(r'[a-f0-9]{32}',key) or path.parent.resolve()!=project_path(key).resolve():continue
            value.update(deleted=True,recovery_reason='interrupted_transfer',updated=time.time())
            atomic_json(path,value);recovered.append(key)
    return recovered


def voice_library() -> list[dict]:
    return [read_json(path) for path in (DATA / "voices").glob("*/voice.json")]
