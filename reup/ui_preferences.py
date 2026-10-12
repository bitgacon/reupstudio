"""UI-only preferences: safe to change without restarting inference or jobs."""
from . import storage

LANGUAGES = {'vi': 'Tiếng Việt', 'en': 'English', 'zh': '简体中文'}
DEFAULTS = {'language': 'vi', 'theme': 'light', 'density': 'compact'}

def preferences(value=None):
    with storage.LOCK:
        saved = storage.read_json(storage.DATA/'ui-preferences.json', {})
        if not isinstance(saved,dict):saved={}
        current = {**DEFAULTS, **{k:v for k,v in saved.items() if k in DEFAULTS}}
        allowed = {'language': LANGUAGES, 'theme': {'light','dark','system'}, 'density': {'compact','comfortable'}}
        for k in DEFAULTS:
            if not isinstance(current[k],str) or current[k] not in allowed[k]: current[k] = DEFAULTS[k]
        if value is not None:
            if not isinstance(value, dict) or set(value)-set(DEFAULTS): raise ValueError('Tùy chọn giao diện không hợp lệ.')
            if any(not isinstance(v,str) or v not in allowed[k] for k,v in value.items()):
                raise ValueError('Ngôn ngữ/giao diện không được hỗ trợ.')
            current.update(value)
            storage.atomic_json(storage.DATA/'ui-preferences.json', current)
        return {**current, 'languages': LANGUAGES, 'configured': (storage.DATA/'ui-preferences.json').is_file()}
