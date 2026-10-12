"""Allowlisted Lite installer: core GUI/media only, never AI models or user data."""
from pathlib import Path
import argparse, datetime, hashlib, json, shutil, subprocess
from reup import VERSION
ROOT = Path(__file__).resolve().parent
WORK = ROOT.parent
CORE_FILES = (
    'ReupVoiceStudio.exe', 'launcher.py', 'run.py', 'MO_REUP_VOICE_STUDIO.bat',
    'MO_BANG_TRINH_DUYET.bat', 'INSTALL_DOWNLOADS.bat', 'requirements-core.txt',
    'requirements-vision.txt', 'HUONG_DAN.md', 'HUONG_DAN_TTS_DA_NGON_NGU.md', 'HUONG_DAN_AI_NANG_CAO.md', 'TRANG_THAI_HOAN_THIEN_2026_10_10.md',
    'LICENSE', 'README.md', 'THIRD_PARTY_NOTICES.md', 'LICENSE-MPT.txt', 'OFL-BeVietnamPro.txt', 'CAI_DAT_LITE.md', 'HUONG_DAN_XOA_NHE.md', 'HUONG_DAN_KHOI_PHUC_JOB.md', 'HUONG_DAN_SAO_LUU.md',
    'ALIGNMENT_WORKER.py', 'AVATAR_INSTALL_WORKER.py', 'CTC_ALIGNMENT.py', 'LIBRARY_WORKER.py', 'INPAINT_WORKER.py', 'REIDENTIFY_POLICY.py',
    'REIDENTIFY_WORKER.py', 'TRACKING_POLICY.py', 'TTS_PROVIDER_WORKER.py',
    'VIENEU_INSTALL_WORKER.py', 'VISION_WORKER.py', 'VSR_LEGACY_WORKER.py', 'WORD_TIMING_WORKER.py')

def ignore(directory, names):
    return [n for n in names if n in {'__pycache__', '.git', '.pytest_cache', 'EXTERNALLY-MANAGED'} or n.endswith(('.pyc', '.log'))]

def run(args):
    print('RUN:', ' '.join(map(str, args)), flush=True)
    subprocess.run(list(map(str, args)), check=True, cwd=ROOT)

def audit(app):
    forbidden = {'data', 'VieNeuLocal', 'whisper-models', 'separation-runtime',
                 'separation-models', 'vision-env', 'separation-env', 'admin', 'tests', 'qa'}
    if forbidden.intersection(p.name for p in app.iterdir()):
        raise ValueError('Forbidden data/model directory in Lite payload')
    query = "import importlib.metadata,json; print(json.dumps(sorted((d.metadata['Name'],d.version) for d in importlib.metadata.distributions())))"
    packages = json.loads(subprocess.check_output([str(app/'runtime/python.exe'), '-I', '-c', query], text=True))
    prohibited = {'torch', 'torchaudio', 'torchvision', 'faster-whisper', 'onnxruntime',
                  'vieneu', 'demucs', 'rembg', 'qwen-tts', 'kokoro-onnx', 'transformers'}
    if prohibited.intersection(n.lower() for n, v in packages): raise ValueError('AI dependency bundled')
    (app/'DEPENDENCIES.json').write_text(json.dumps({'runtime': packages}, indent=2), encoding='utf-8')
    manifest = {}
    for path in sorted(app.rglob('*')):
        if path.is_file() and path.name != 'MANIFEST.sha256.json' and path.suffix not in {'.pyc','.log'}:
            with path.open('rb') as stream: manifest[path.relative_to(app).as_posix()] = hashlib.file_digest(stream, 'sha256').hexdigest()
    (app/'MANIFEST.sha256.json').write_text(json.dumps(manifest, indent=2), encoding='utf-8')

def compile_stage(app):
    output = WORK/'release'/f'ReupVoiceStudio-{VERSION}-Lite-Setup.exe'
    if output.exists(): raise FileExistsError('Refusing overwrite: '+str(output))
    # Keep the exact tool's GPL text alongside its binary; record upstream build/source.
    import urllib.request
    license_path=app/'tools/COPYING.GPLv3'
    if not license_path.exists():
        with urllib.request.urlopen('https://raw.githubusercontent.com/FFmpeg/FFmpeg/n8.0.1/COPYING.GPLv3',timeout=60) as response:
            content=response.read()
        if b'GNU GENERAL PUBLIC LICENSE' not in content or len(content)<30000:
            raise ValueError('Invalid FFmpeg license response')
        license_path.write_bytes(content)
    notice='FFmpeg/ffprobe 8.0.1 essentials_build, gyan.dev; GPLv3 or later.\nBinary provider: https://www.gyan.dev/ffmpeg/builds/\nFFmpeg source: https://github.com/FFmpeg/FFmpeg/tree/n8.0.1\nThis is a separate executable invoked by the app, not an encrypted proprietary component.\nBuild configuration and license notice:\n'
    result=subprocess.run([str(app/'tools/ffmpeg.exe'),'-L'],capture_output=True,text=True,check=True)
    (app/'tools/BUILD-AND-LICENSE.txt').write_text(notice+result.stdout+result.stderr,encoding='utf-8')
    audit(app)
    with (app.parent/'compile.log').open('w',encoding='utf-8') as log:
        subprocess.run([r'C:\Program Files (x86)\Inno Setup 6\ISCC.exe',str(app.parent/'installer.iss')],
                       stdout=log,stderr=subprocess.STDOUT,check=True)
    with output.open('rb') as stream: checksum=hashlib.file_digest(stream, 'sha256').hexdigest()
    output.with_suffix('.exe.sha256').write_text(checksum+'  '+output.name+'\n', encoding='ascii')
    print('INSTALLER='+str(output), 'SHA256='+checksum, flush=True)

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--stage-only', action='store_true')
    parser.add_argument('--compile-stage', type=Path)
    args=parser.parse_args()
    if args.compile_stage:
        app=args.compile_stage.resolve()
        if app.parent.parent != (WORK/'release').resolve() or not (app/'BUILD.json').is_file():
            raise ValueError('Not a generated release stage')
        compile_stage(app); return
    stage=WORK/'release'/('Reup-lite-build-'+datetime.datetime.now().strftime('%Y%m%d-%H%M%S'))
    app=stage/'ReupVoiceStudio'; app.mkdir(parents=True, exist_ok=False)
    for name in CORE_FILES: shutil.copy2(ROOT/name, app/name)
    for name in ('reup','web','examples'):
        shutil.copytree(ROOT/name, app/name, ignore=ignore)
    policy={'license_required':False,'license_url':'','update_url':'','public_key':''}
    (app/'release-policy.json').write_text(json.dumps(policy,indent=2),encoding='utf-8')
    (app/'installed.flag').write_text(VERSION,encoding='ascii')
    source=WORK/'release/MPT/MoneyPrinterTurbo/runtime'
    runtime=app/'runtime'; runtime.mkdir()
    for path in source.iterdir():
        if path.is_file(): shutil.copy2(path, runtime/path.name)
        elif path.name in {'DLLs','libs','include'}:
            shutil.copytree(path,runtime/path.name,ignore=ignore)
        elif path.name=='Lib':
            shutil.copytree(path,runtime/'Lib',ignore=lambda directory,names:ignore(directory,names)+(['site-packages'] if Path(directory)==path else []))
    run([runtime/'python.exe','-I','-m','ensurepip','--upgrade'])
    run([runtime/'python.exe','-I','-m','pip','install','--no-cache-dir','--only-binary=:all:', '-r',ROOT/'requirements-core.txt'])
    tools=app/'tools'; tools.mkdir()
    for name in ('ffmpeg.exe','ffprobe.exe'):
        shutil.copy2(WORK/'release/MPT/tools'/name,tools/name)
    (app/'BUILD.json').write_text(json.dumps({'version':VERSION,'flavor':'Lite','ai_bundled':False,
        'signed':False,'encrypted':False,'license_required':False,'private_data_included':False},indent=2),encoding='utf-8')
    template=(ROOT/'installer.iss').read_text(encoding='utf-8')
    (stage/'installer.iss').write_text(template.replace('__STAGE__',str(app)).replace('__OUTPUT__',str(WORK/'release')).replace('__VERSION__',VERSION),encoding='utf-8-sig')
    audit(app)
    print('STAGE='+str(app),flush=True)
    if not args.stage_only: compile_stage(app)

if __name__=='__main__': main()
