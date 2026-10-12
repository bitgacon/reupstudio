"""Portable, additive project backups. Archives are data, never executable code."""
from contextlib import contextmanager
from copy import deepcopy
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import time
from uuid import uuid4
import zipfile

from . import storage

FORMAT = 'reup-backup-1'
LIMIT = 2 * 1024**3
MAX_FILES = 10000
MEDIA = {'.wav', '.mp3', '.m4a', '.ogg', '.flac', '.webm', '.mp4', '.mov', '.mkv', '.avi', '.png', '.jpg', '.jpeg', '.webp', '.srt', '.txt'}
CONFIGS = ('settings.json', 'ui-preferences.json', 'reading.json', 'tts-provider-settings.json', 'llm-profiles.json')
PORTABLE = {'precision', 'translation_url', 'translation_model', 'translation_key', 'translation_batch', 'translation_pause', 'whisper_model'}
ID = re.compile(r'^[a-f0-9]{32}$')


@contextmanager
def idle(queue):
    # Serialises project saves and submissions, including retry submissions.
    with queue.lock:
        if queue.busy() or not queue.accepting or getattr(queue, 'maintenance', False):
            raise ValueError('Chờ tác vụ hoàn tất trước khi sao lưu/khôi phục.')
        queue.maintenance = True
    try:
        with storage.LOCK: yield
    finally:
        with queue.lock: queue.maintenance = False


def _json(value):
    return json.dumps(value, ensure_ascii=False, allow_nan=False).encode('utf-8')


def _load(content):
    try:
        return json.loads(content.decode('utf-8'), parse_constant=lambda _: (_ for _ in ()).throw(ValueError('JSON không hợp lệ.')))
    except (UnicodeError, RecursionError, ValueError) as exc:
        raise ValueError('JSON trong bản sao lưu không hợp lệ.') from exc


def _secrets(value):
    if isinstance(value, dict):
        return {k: _secrets(v) for k, v in value.items() if k not in {'key', 'translation_key', 'elevenlabs_key'}}
    if isinstance(value, list):
        return [_secrets(v) for v in value]
    return value


def _portable_settings(include_keys):
    result = {}
    for name in CONFIGS:
        if (storage.DATA / name).exists():
            value = storage.read_json(storage.DATA / name)
            if name == 'settings.json':
                value = {k: v for k, v in value.items() if k in PORTABLE}
            result[name] = value if include_keys else _secrets(value)
    return result


def _safe_path(name):
    parts = name.split('/')
    if not name or '\\' in name or any(c in name for c in ':<>"|?*') or any(p in {'', '.', '..'} or p.endswith((' ', '.')) or re.fullmatch(r'(?i)(con|prn|aux|nul|com[1-9]|lpt[1-9])(?:\..*)?', p) for p in parts) or any(ord(c) < 32 for c in name):
        raise ValueError('Đường dẫn trong gói không an toàn.')
    if PurePosixPath(name).is_absolute() or len(name) > 300:
        raise ValueError('Đường dẫn trong gói không an toàn.')
    return parts


def _contained(path, root):
    path = Path(path)
    if path.is_symlink() or not path.resolve().is_relative_to(root.resolve()):
        raise ValueError('Không sao lưu liên kết/đường dẫn bên ngoài dự án.')
    return path


def _refs(value):
    if isinstance(value, dict):
        for k, v in value.items():
            if k in {'video', 'asset', 'logo', 'background', 'reference_asset'} and isinstance(v, str) and ID.fullmatch(v):
                yield v
            yield from _refs(v)
    elif isinstance(value, list):
        for v in value:
            yield from _refs(v)


def _reference_ids(value):
    if isinstance(value, dict):
        if value.get('reference_asset'): yield value['reference_asset']
        for v in value.values(): yield from _reference_ids(v)
    elif isinstance(value, list):
        for v in value: yield from _reference_ids(v)


def create(project_ids, include_settings=True, include_keys=False):
    if not isinstance(project_ids, list) or len(project_ids) > 100 or any(not isinstance(k, str) for k in project_ids) or len(set(project_ids)) != len(project_ids):
        raise ValueError('Chọn tối đa 100 dự án khác nhau.')
    if not project_ids and not include_settings:
        raise ValueError('Chọn dự án hoặc cài đặt để sao lưu.')
    with storage.LOCK:
        manifest = {'format': FORMAT, 'created': time.time(), 'include_keys': include_keys,
                    'settings': _portable_settings(include_keys) if include_settings else {}, 'projects': [], 'files': {}}
        sources = {}
        for pid in project_ids:
            value = deepcopy(storage.project(pid))
            root = storage.project_path(pid)
            timeline_path = root / 'editor-timeline.json'
            tl = storage.read_json(timeline_path) if timeline_path.exists() else None
            refs = set(_refs(value)) | set(value.get('local_assets', {})) | set(tl.get('assets', []) if tl else [])
            assets = {}
            for key in sorted(refs):
                source, meta = storage.project_asset(value, key)
                if source.suffix.lower() not in MEDIA or source.is_symlink():
                    raise ValueError('Định dạng nguồn dự án không được sao lưu.')
                if key in value.get('local_assets', {}):
                    _contained(source, root / 'assets')
                else:
                    _contained(source, storage.DATA / 'uploads' / key)
                name = f'projects/{pid}/assets/{key}{source.suffix.lower()}'
                sources[name] = source
                assets[key] = {'path': name, 'name': str(meta.get('name', source.name))[:500]}
            audio = []
            cues = root / 'cues'
            if cues.exists():
                for source in cues.iterdir():
                    if source.is_file() and source.suffix.lower() in {'.wav', '.mp3', '.srt'}:
                        _contained(source, cues)
                        name = f'projects/{pid}/cues/{source.name}'
                        _safe_path(name)
                        sources[name] = source
                        audio.append(name)
            for filename in ('no_vocals.wav', 'vocals.wav'):
                source = root / 'stems' / filename
                if source.is_file():
                    _contained(source, root / 'stems')
                    name = f'projects/{pid}/stems/{filename}'
                    sources[name] = source; audio.append(name)
            # Keep only portable state; derived renders/proxies are regenerated.
            for key in ('exports', 'preview', 'stems', 'local_assets'):
                value.pop(key, None)
            manifest['projects'].append({'project': value, 'timeline': tl, 'assets': assets, 'audio': audio})
        if len(sources) > MAX_FILES or sum(p.stat().st_size for p in sources.values()) > LIMIT - 4 * 1024**2:
            raise ValueError('Bản sao lưu tối đa 2 GB / 10000 file. Chọn ít dự án hơn.')
        folder = storage.DATA / 'outputs' / 'Backups'
        folder.mkdir(parents=True, exist_ok=True)
        target = folder / ('ReupBackup-' + time.strftime('%Y%m%d-%H%M%S') + '-' + uuid4().hex[:8] + '.rvbackup')
        temporary = target.with_suffix('.partial')
        try:
            with zipfile.ZipFile(temporary, 'x', compression=zipfile.ZIP_STORED) as archive:
                for name, source in sources.items():
                    digest = hashlib.sha256(); size = 0
                    with source.open('rb') as src, archive.open(name, 'w', force_zip64=True) as dest:
                        while block := src.read(1024**2):
                            size += len(block); digest.update(block); dest.write(block)
                            if size > LIMIT:
                                raise ValueError('Nguồn quá lớn.')
                    manifest['files'][name] = {'size': size, 'sha256': digest.hexdigest()}
                content = _json(manifest)
                if len(content) > 4 * 1024**2:
                    raise ValueError('Metadata quá lớn.')
                archive.writestr('manifest.json', content)
            if temporary.stat().st_size > LIMIT:
                raise ValueError('Bản sao lưu vượt 2 GB.')
            with temporary.open('r+b') as stream:
                os.fsync(stream.fileno())
            validate(temporary)
            os.replace(temporary, target)
        finally:
            temporary.unlink(missing_ok=True)
        return {'url': storage.file_url(target), 'name': target.name, 'projects': len(project_ids), 'include_keys': include_keys}


def validate(source, stage=None):
    """Hash every entry before touching live projects. Never extractall."""
    try:
        with zipfile.ZipFile(source) as archive:
            infos = archive.infolist()
            if len(infos) > MAX_FILES + 1 or sum(i.file_size for i in infos) > LIMIT:
                raise ValueError('Gói vượt giới hạn 2 GB / 10000 file.')
            names = [i.filename for i in infos]
            if len(set(n.casefold() for n in names)) != len(names):
                raise ValueError('Gói có file trùng tên.')
            for info in infos:
                _safe_path(info.filename)
                if info.is_dir() or info.flag_bits & 1 or ((info.external_attr >> 16) & 0o170000) == 0o120000:
                    raise ValueError('Gói chứa liên kết/file mã hóa không hỗ trợ.')
            info = archive.getinfo('manifest.json')
            if info.file_size > 4 * 1024**2:
                raise ValueError('Manifest quá lớn.')
            manifest = _load(archive.read(info))
            if not isinstance(manifest, dict) or manifest.get('format') != FORMAT or type(manifest.get('include_keys')) is not bool:
                raise ValueError('Không phải bản sao lưu Reup Voice Studio.')
            files = manifest.get('files'); projects = manifest.get('projects'); configs = manifest.get('settings')
            if not isinstance(files, dict) or not isinstance(projects, list) or len(projects) > 100 or not isinstance(configs, dict) or set(configs) - set(CONFIGS):
                raise ValueError('Metadata không hợp lệ.')
            if not manifest['include_keys'] and _secrets(configs) != configs:
                raise ValueError('Gói có key nhưng khai báo không có key.')
            if set(names) != {'manifest.json', *files}:
                raise ValueError('Danh sách file không khớp manifest.')
            expected = set(); pids = set()
            from .timeline import Timeline
            from .editor import config as edit_config
            for row in projects:
                p = row['project']; pid = storage.identifier(p['id'])
                if pid in pids or not isinstance(p.get('name'), str) or len(p['name']) > 100 or not isinstance(p.get('cues'), list) or len(p['cues']) > 5000:
                    raise ValueError('Dự án không hợp lệ.')
                pids.add(pid)
                if p.get('video'): storage.identifier(p['video'])
                if not isinstance(p.get('voice', ''), str) or len(p.get('voice', '')) > 64: raise ValueError('Giọng dự án không hợp lệ.')
                edit_config(p.get('edit', {}))
                # Cue model validates timings, text, rates, TTS options without executing anything.
                from .server import Cue
                from .tts_providers import options
                if p.get('tts'): options(p['tts'])
                for cue in p['cues']:
                    Cue.model_validate(cue)
                    if cue['end_ms'] <= cue['start_ms']: raise ValueError('Khung cue không hợp lệ.')
                    if cue.get('audio') and (Path(cue['audio']).name != cue['audio'] or '\\' in cue['audio']):
                        raise ValueError('Tên audio cue không hợp lệ.')
                if len({c['id'] for c in p['cues']}) != len(p['cues']): raise ValueError('Cue trùng mã.')
                assets = row['assets']
                if not isinstance(assets, dict) or not isinstance(row['audio'], list):
                    raise ValueError('Nguồn dự án không hợp lệ.')
                for key, meta in assets.items():
                    storage.identifier(key); name = meta['path']; parts = _safe_path(name)
                    if len(parts) != 4 or parts[:3] != ['projects', pid, 'assets'] or Path(name).stem != key or Path(name).suffix.lower() not in MEDIA or not isinstance(meta.get('name'), str):
                        raise ValueError('Nguồn dự án không hợp lệ.')
                    expected.add(name)
                if set(_refs(p)) - set(assets):
                    raise ValueError('Thiếu nguồn dự án.')
                if row.get('timeline') is not None:
                    tl = Timeline.model_validate(row['timeline']).model_dump()
                    if set(tl['assets']) - set(assets):
                        raise ValueError('Thiếu nguồn timeline.')
                for name in row['audio']:
                    parts = _safe_path(name)
                    if len(parts) != 4 or parts[:2] != ['projects', pid] or parts[2] not in {'cues', 'stems'} or Path(name).suffix.lower() not in {'.wav', '.mp3', '.srt'} or parts[2] == 'stems' and parts[3] not in {'no_vocals.wav', 'vocals.wav'}:
                        raise ValueError('Audio cue không hợp lệ.')
                    expected.add(name)
            if expected != set(files):
                raise ValueError('Gói chứa file ngoài phạm vi dự án.')
            _validate_settings(configs)
            for number, (name, spec) in enumerate(files.items()):
                if not isinstance(spec, dict) or type(spec.get('size')) is not int or spec['size'] != archive.getinfo(name).file_size or not re.fullmatch('[a-f0-9]{64}', str(spec.get('sha256', ''))):
                    raise ValueError('Checksum/size không hợp lệ.')
                dest = None
                if stage:
                    # Flat temporary names avoid Windows MAX_PATH for imported archives.
                    dest = _staged(stage, number, name); dest.parent.mkdir(parents=True, exist_ok=True)
                digest = hashlib.sha256(); size = 0
                with archive.open(name) as src:
                    output = dest.open('xb') if dest else None
                    try:
                        while block := src.read(1024**2):
                            size += len(block)
                            if size > spec['size']:
                                raise ValueError('File vượt kích thước khai báo.')
                            digest.update(block)
                            if output: output.write(block)
                    finally:
                        if output: output.flush(); os.fsync(output.fileno()); output.close()
                if size != spec['size'] or digest.hexdigest() != spec['sha256']:
                    raise ValueError('Bản sao lưu bị hỏng: checksum không khớp.')
            return manifest
    except (zipfile.BadZipFile, KeyError, TypeError, RecursionError, OverflowError) as exc:
        raise ValueError('Bản sao lưu bị hỏng hoặc metadata không hợp lệ.') from exc


def _validate_settings(configs):
    for name, value in configs.items():
        if not isinstance(value, dict): raise ValueError('Cài đặt không hợp lệ.')
        if name == 'settings.json':
            if set(value) - PORTABLE or any(not isinstance(v, str) or len(v) > 4096 for v in value.values()): raise ValueError('Cài đặt không hợp lệ.')
            if value.get('precision', 'fp32') not in {'fp32', 'int8'} or not 1 <= int(value.get('translation_batch', 10)) <= 20 or not 0 <= float(value.get('translation_pause', 2)) <= 60: raise ValueError('Cài đặt không hợp lệ.')
        elif name == 'reading.json':
            from .reading import config
            config(value)
        elif name == 'ui-preferences.json':
            from .ui_preferences import DEFAULTS, LANGUAGES
            allowed = {'language': LANGUAGES, 'theme': {'light', 'dark', 'system'}, 'density': {'compact', 'comfortable'}}
            if set(value) - set(DEFAULTS) or any(not isinstance(v, str) or v not in allowed[k] for k, v in value.items()): raise ValueError('Giao diện không hợp lệ.')
        elif name == 'tts-provider-settings.json':
            if set(value) - {'device', 'elevenlabs_key'} or value.get('device', 'cpu') not in {'cpu', 'cuda'} or not isinstance(value.get('elevenlabs_key', ''), str) or len(value.get('elevenlabs_key', '')) > 512 or re.search(r'\s', value.get('elevenlabs_key', '')): raise ValueError('Cài đặt TTS không hợp lệ.')
        elif name == 'llm-profiles.json':
            rows = value.get('profiles')
            if set(value) - {'profiles', 'active'} or not isinstance(rows, list) or len(rows) > 50: raise ValueError('Cấu hình LLM không hợp lệ.')
            from .translation_api import normalize
            from .llm_profiles import PRESETS
            from urllib.parse import urlsplit
            for row in rows:
                storage.identifier(row['id'])
                if set(row) - {'id', 'name', 'provider', 'url', 'model', 'key', 'batch_size', 'pause_seconds'} or not row.get('name'): raise ValueError('Cấu hình LLM không hợp lệ.')
                if row.get('provider', 'custom') not in {p['id'] for p in PRESETS}: raise ValueError('Nhà cung cấp LLM không hợp lệ.')
                if any(not isinstance(row.get(k, ''), str) or len(row.get(k, '')) > 4096 for k in ('name', 'url', 'model', 'key')): raise ValueError('Cấu hình LLM không hợp lệ.')
                url, model = normalize(row.get('url', ''), row.get('model', '')); parsed = urlsplit(url)
                if parsed.username or parsed.password or parsed.query or parsed.fragment or not model or not (parsed.scheme == 'https' or parsed.scheme == 'http' and parsed.hostname in {'localhost', '127.0.0.1'}): raise ValueError('URL LLM không hợp lệ.')
                if not 1 <= int(row.get('batch_size', 10)) <= 20 or not 0 <= float(row.get('pause_seconds', 2)) <= 60: raise ValueError('Cấu hình LLM không hợp lệ.')


def inspect(source):
    value = validate(source)
    return {'projects': [{'name': r['project']['name'], 'cues': len(r['project']['cues'])} for r in value['projects']],
            'settings': bool(value['settings']), 'include_keys': value['include_keys'], 'bytes': sum(r['size'] for r in value['files'].values())}


def _staged(stage, number, name):
    return stage / 'f' / (str(number) + Path(name).suffix)


def _remap(value, mapping):
    if isinstance(value, str):
        if value in mapping: return mapping[value]
        # Cached artifact URLs are not retained; audio cue basenames stay unchanged.
        for old, new in mapping.items():
            value = value.replace('/projects/' + old + '/', '/projects/' + new + '/').replace('/uploads/' + old + '/', '/uploads/' + new + '/')
        return value
    if isinstance(value, list): return [_remap(v, mapping) for v in value]
    if isinstance(value, dict): return {mapping.get(k, k): False if k == 'cloud_consent' else _remap(v, mapping) for k, v in value.items()}
    return value


def restore(source, projects=True, settings=False, keys=False):
    if not projects and not settings: raise ValueError('Chọn dự án hoặc cài đặt để khôi phục.')
    with storage.LOCK:
        stage = storage.DATA / '.restore' / uuid4().hex[:12]
        stage.mkdir(parents=True, exist_ok=False)
        created = []; created_uploads = []; old_index = storage.read_json(storage.DATA / 'project-index.json', {})
        previous = {name: (storage.DATA / name).read_bytes() if (storage.DATA / name).exists() else None for name in CONFIGS}
        touched_settings = False; index_attempted = False
        try:
            manifest = validate(source, stage)
            staged_files = {name: _staged(stage, number, name) for number, name in enumerate(manifest['files'])}
            imported = []
            if projects:
                for row in manifest['projects']:
                    old = row['project']; mapping = {old['id']: uuid4().hex, **{k: uuid4().hex for k in row['assets']}}
                    # Restored sources live only in this new project's assets directory.
                    parent = storage.DATA / 'projects'
                    target = storage.numbered_folder(parent, storage.safe_name(old['name']) + '-restored-')
                    created.append(target); local = {}
                    ready = stage / 'ready' / mapping[old['id']][:8]
                    ready.mkdir(parents=True)
                    references = set(_reference_ids(old))
                    for key, meta in row['assets'].items():
                        src = staged_files[meta['path']]; dest = ready / 'assets' / (mapping[key] + src.suffix)
                        dest.parent.mkdir(exist_ok=True); shutil.copy2(src, dest)
                        local[mapping[key]] = {'id': mapping[key], 'file': dest.name, 'name': meta['name'], 'bytes': dest.stat().st_size}
                        # Reference-speech workers resolve upload IDs, unlike editor sources.
                        if key in references:
                            upload = storage.DATA / 'uploads' / mapping[key]
                            upload.mkdir(parents=True, exist_ok=False); created_uploads.append(upload)
                            name = 'source' + src.suffix; shutil.copy2(src, upload / name)
                            storage.atomic_json(upload / 'asset.json', {**local[mapping[key]], 'file': name})
                    for name in row['audio']:
                        dest = ready / name.split('/')[2] / Path(name).name
                        dest.parent.mkdir(exist_ok=True); shutil.copy2(staged_files[name], dest)
                    value = _remap(old, mapping)
                    for key in ('exports', 'preview', 'stems', 'deleted', 'deleted_at'): value.pop(key, None)
                    value.update(id=mapping[old['id']], local_assets=local, exports=[], revision=0, updated=time.time())
                    value['translation_consent'] = False
                    for cue in value['cues']:
                        if cue.get('audio') and not (ready / 'cues' / cue['audio']).is_file():
                            cue.pop('audio', None); cue['status'] = 'pending'
                    storage.atomic_json(ready / 'project.json', value)
                    if row.get('timeline') is not None:
                        tl = _remap(row['timeline'], mapping); tl['revision'] = 0
                        storage.atomic_json(ready / 'editor-timeline.json', tl)
                    # Publish only a fully written project directory. A power interruption
                    # cannot expose half-copied source media as a usable project.
                    target.rmdir()  # Our own reserved empty directory only.
                    os.replace(ready, target)
                    imported.append({'id': value['id'], 'name': value['name'], 'path': str(target)})
            if settings and manifest['settings']:
                # Durable rollback copy before applying imported settings; never served by /files.
                safety = storage.DATA / 'backups' / ('settings-before-' + time.strftime('%Y%m%d-%H%M%S') + '-' + uuid4().hex[:8])
                safety.mkdir(parents=True)
                for name, content in previous.items():
                    if content is not None: storage._durable_replace(safety / name, content)
                touched_settings = True
                for name, incoming in manifest['settings'].items():
                    incoming = deepcopy(incoming) if keys and manifest['include_keys'] else _secrets(incoming)
                    current = storage.read_json(storage.DATA / name, {})
                    if name == 'llm-profiles.json':
                        # Append configurations, keeping existing profiles and secrets unchanged.
                        rows = current.get('profiles', [])
                        if len(rows) + len(incoming['profiles']) > 50: raise ValueError('Khôi phục vượt 50 cấu hình LLM.')
                        for row in incoming['profiles']: row['id'] = uuid4().hex; row.setdefault('key', '')
                        incoming = {**current, 'profiles': rows + incoming['profiles'], 'active': current.get('active', '')}
                    elif name == 'settings.json':
                        incoming = {**current, **incoming}
                        # Never attach a surviving key to a different provider URL.
                        if 'translation_key' not in manifest['settings'][name] or not keys:
                            incoming['translation_url'] = current.get('translation_url', '')
                            incoming['translation_model'] = current.get('translation_model', '')
                    else: incoming = {**current, **incoming}
                    storage.atomic_json(storage.DATA / name, incoming)
            index = deepcopy(old_index)
            index.update({r['id']: r['path'] for r in imported})
            index_attempted = True
            storage.atomic_json(storage.DATA / 'project-index.json', index)
            return {'projects': [{'id': r['id'], 'name': r['name']} for r in imported], 'settings': bool(settings and manifest['settings'])}
        except BaseException:
            # Only directories reserved by this invocation are removed.
            try:
                if index_attempted: storage.atomic_json(storage.DATA / 'project-index.json', old_index)
                if touched_settings:
                    for name, content in previous.items():
                        path = storage.DATA / name
                        if content is None: path.unlink(missing_ok=True); path.with_name(path.name + '.bak').unlink(missing_ok=True)
                        else: storage._durable_replace(path, content)
            finally:
                for folder in created:
                    if folder.exists() and folder.resolve().is_relative_to((storage.DATA / 'projects').resolve()): shutil.rmtree(folder)
                for folder in created_uploads:
                    if folder.exists() and folder.resolve().is_relative_to((storage.DATA / 'uploads').resolve()): shutil.rmtree(folder)
            raise
        finally:
            if stage.resolve().is_relative_to((storage.DATA / '.restore').resolve()): shutil.rmtree(stage)
