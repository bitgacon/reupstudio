"""Export only allowlisted source/assets to a clean public checkout; no private data."""
from pathlib import Path
import argparse,hashlib,json,re,shutil
ROOT=Path(__file__).resolve().parent
FILES=('README.md','CONTRIBUTING.md','.gitignore','.gitattributes','requirements-core.txt',
 'requirements-dev.txt','requirements.txt','requirements-vision.txt','INSTALL_CORE.bat',
 'INSTALL_DOWNLOADS.bat','MO_REUP_VOICE_STUDIO.bat','MO_BANG_TRINH_DUYET.bat',
 'run.py','launcher.py','release-policy.json','LICENSE','LICENSE-MPT.txt','OFL-BeVietnamPro.txt',
 'THIRD_PARTY_NOTICES.md','BUILD_LAUNCHER.py','BUILD_INSTALLER.py','BUILD_COMMUNITY_SETUP.py','installer.iss',
 'PREPARE_CREATIVE.py','RECOVER_POWER_LOSS.py','CTC_ALIGNMENT.py','TRACKING_POLICY.py',
 'REIDENTIFY_POLICY.py','BUILD_PUBLIC_SOURCE.py','HUONG_DAN.md','CAI_DAT_LITE.md',
 'HUONG_DAN_TTS_DA_NGON_NGU.md','HUONG_DAN_AI_NANG_CAO.md',
 'HUONG_DAN_KHOI_PHUC_JOB.md','HUONG_DAN_SAO_LUU.md','HUONG_DAN_XOA_NHE.md',
 'TRANG_THAI_HOAN_THIEN_2026_10_10.md','admin/LICENSE_SERVER.py',
 'admin/README.md','admin/requirements.txt','admin/nginx.example.conf')
EXTS={'.py','.js','.cjs','.html','.css','.json','.png','.ico','.ttf','.woff2','.txt','.srt','.cs'}
SECRET=re.compile(r'AIza[0-9A-Za-z_-]{30,}|sk-(?:proj-)?[0-9A-Za-z_-]{30,}|gh[pousr]_[0-9A-Za-z]{30,}|-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----')
def main():
    parser=argparse.ArgumentParser();parser.add_argument('--target',type=Path,required=True)
    target=parser.parse_args().target.resolve()
    if target==ROOT or target.is_relative_to(ROOT) or not (target/'.git').is_dir():
        raise ValueError('Use a separate clean Git checkout, not the live app directory.')
    names=set(FILES)|{p.name for p in ROOT.glob('*_WORKER.py')}
    for folder in ('reup','web','tests','examples','native'):
        for path in (ROOT/folder).rglob('*'):
            if path.is_symlink():raise ValueError('Symlink not allowed: '+str(path.relative_to(ROOT)))
            if path.is_file() and path.suffix.lower() in EXTS and '__pycache__' not in path.parts:
                names.add(path.relative_to(ROOT).as_posix())
    records={}
    for name in sorted(names):
        path=ROOT/name;content=path.read_bytes()
        if len(content)>5_000_000:raise ValueError('Oversized public source file: '+name)
        if path.suffix.lower() not in {'.png','.ico','.ttf','.woff2'}:
            text=content.decode('utf-8-sig')
            if SECRET.search(text):raise ValueError('Potential secret detected; inspect locally: '+name)
        records[name]=hashlib.sha256(content).hexdigest()
    policy=json.loads((ROOT/'release-policy.json').read_text())
    if policy!={'license_required':False,'license_url':'','public_key':'','update_url':''}:
        raise ValueError('Public source requires an unconfigured community release policy.')
    for name in sorted(names):
        destination=target/name;destination.parent.mkdir(parents=True,exist_ok=True)
        shutil.copy2(ROOT/name,destination)
    report=ROOT.parent/'release'/'ReupStudio-Public-Source-20261012.manifest.json'
    report.write_text(json.dumps({'files':records,'contains_runtime_models_or_user_data':False},indent=2),encoding='utf-8')
    print(json.dumps({'files':len(names),'bytes':sum((ROOT/n).stat().st_size for n in names),'manifest':str(report)},indent=2))
if __name__=='__main__':main()
