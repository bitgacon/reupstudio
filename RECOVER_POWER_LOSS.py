"""Inspect metadata and explicitly repair settings after preserving all metadata.

Run without --apply first. Never deletes media, resets projects or reruns render.
"""
import argparse
import json
import shutil
import time
from pathlib import Path
from reup import storage

def valid(path):
    try:return json.loads(path.read_text(encoding='utf-8-sig'))
    except (ValueError,UnicodeError):return None

def run(apply=False):
    root=storage.DATA
    files=list(root.glob('*.json'))
    for name in ('jobs','projects','uploads','voices'):
        files.extend((root/name).rglob('*.json'))
    invalid=[p for p in files if valid(p) is None]
    projects=list((root/'projects').glob('*/project.json'))
    jobs=list((root/'jobs').glob('*.json'))
    report={'data':str(root),'metadata_files':len(files),'invalid':[str(p.relative_to(root)) for p in invalid],
            'projects_valid':sum(isinstance(valid(p),dict) for p in projects),
            'jobs_valid':sum(isinstance(valid(p),dict) for p in jobs),'applied':False}
    if apply:
        # Only the confirmed settings failure is reset; unrelated damage is never erased.
        settings=root/'settings.json'
        if settings not in invalid:raise ValueError('Settings chưa bị hỏng; không reset dữ liệu hợp lệ.')
        backup=root/'recovery'/('power-loss-'+time.strftime('%Y%m%d-%H%M%S'))
        backup.mkdir(parents=True,exist_ok=False)
        for p in files:
            dest=backup/p.relative_to(root);dest.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(p,dest)
            if dest.read_bytes()!=p.read_bytes():raise ValueError('Bản sao không khớp; không sửa dữ liệu.')
        candidates=[settings.with_name('settings.json.bak'),*sorted(root.glob('settings.json.*.tmp'),key=lambda p:p.stat().st_mtime,reverse=True)]
        recovered=next((valid(p) for p in candidates if p.is_file() and isinstance(valid(p),dict)),None)
        value=storage.default_settings() if recovered is None else recovered
        storage.atomic_json(settings,value)
        if not settings.with_name('settings.json.bak').exists():
            storage._durable_replace(settings.with_name('settings.json.bak'),settings.read_bytes())
        report.update(applied=True,backup=str(backup),settings_recovered=recovered is not None,
                      settings_reset_to_defaults=recovered is None)
        storage.atomic_json(backup/'recovery-report.json',report)
    return report

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--apply',action='store_true');args=parser.parse_args()
    print(json.dumps(run(args.apply),ensure_ascii=False,indent=2))
