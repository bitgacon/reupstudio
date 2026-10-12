"""Build public MIT Lite setup from a clean checkout and a verified core runtime."""
from pathlib import Path
import argparse,datetime,hashlib,importlib.util,json,shutil,subprocess
ROOT=Path(__file__).resolve().parent
def sha(path):
    with path.open('rb') as stream:return hashlib.file_digest(stream,'sha256').hexdigest()
def main():
    p=argparse.ArgumentParser();p.add_argument('--source',type=Path,required=True)
    p.add_argument('--baseline',type=Path);p.add_argument('--compile-stage',type=Path)
    args=p.parse_args();source=args.source.resolve();release=source.parent/'release'
    spec=importlib.util.spec_from_file_location('community_packager',source/'BUILD_INSTALLER.py')
    packager=importlib.util.module_from_spec(spec);spec.loader.exec_module(packager)
    version=packager.VERSION;name=f'ReupStudio-{version}-Community-Lite-Setup'
    output=release/(name+'.exe')
    if output.exists():raise FileExistsError('Do not overwrite an existing setup: '+str(output))
    if args.compile_stage:
        app=args.compile_stage.resolve()
        if app.parent.parent!=release.resolve() or not app.parent.name.startswith('Reup-community-build-'):
            raise ValueError('Not an owned community stage')
        packager.audit(app)
        with (app.parent/'compile.log').open('w',encoding='utf-8') as log:
            subprocess.run([r'C:\Program Files (x86)\Inno Setup 6\ISCC.exe',str(app.parent/'installer.iss')],stdout=log,stderr=subprocess.STDOUT,check=True)
        digest=sha(output);output.with_suffix('.exe.sha256').write_text(digest+'  '+output.name+'\n',encoding='ascii')
        print(json.dumps({'installer':str(output),'bytes':output.stat().st_size,'sha256':digest},indent=2));return
    if not args.baseline:raise ValueError('Supply --baseline with audited Lite core runtime/tools.')
    base=args.baseline.resolve();manifest=json.loads((base/'MANIFEST.sha256.json').read_text())
    if json.loads((base/'BUILD.json').read_text()).get('ai_bundled') is not False:raise ValueError('Not a Lite baseline')
    # Verify every shipped cached file, never copy mutable app data or AI environments.
    for directory in ('runtime','tools'):
        for path in (base/directory).rglob('*'):
            if path.is_file() and '__pycache__' not in path.parts and path.suffix not in {'.pyc','.log'}:
                key=path.relative_to(base).as_posix()
                if sha(path)!=manifest.get(key):raise ValueError('Baseline file not verified: '+key)
    commit=subprocess.check_output(['git','rev-parse','HEAD'],cwd=source,text=True).strip()
    tracked=subprocess.check_output(['git','status','--porcelain','--untracked-files=no'],cwd=source,text=True)
    if tracked.strip():raise ValueError('Commit source changes before building a public release.')
    stage=release/('Reup-community-build-'+datetime.datetime.now().strftime('%Y%m%d-%H%M%S'))
    app=stage/'ReupVoiceStudio';app.mkdir(parents=True,exist_ok=False)
    for name_ in packager.CORE_FILES:shutil.copy2(source/name_,app/name_)
    for directory in ('reup','web','examples'):shutil.copytree(source/directory,app/directory,ignore=packager.ignore)
    for directory in ('runtime','tools'):shutil.copytree(base/directory,app/directory,ignore=packager.ignore)
    policy={'license_required':False,'license_url':'','public_key':'','update_url':''}
    (app/'release-policy.json').write_text(json.dumps(policy,indent=2),encoding='utf-8')
    (app/'installed.flag').write_text(version,encoding='ascii')
    (app/'BUILD.json').write_text(json.dumps({'version':version,'flavor':'Community-Lite','source_commit':commit,
      'source_repository':'https://github.com/bitgacon/reupstudio','ai_bundled':False,'signed':False,
      'encrypted':False,'license_required':False,'private_data_included':False},indent=2),encoding='utf-8')
    template=(source/'installer.iss').read_text(encoding='utf-8').replace('__STAGE__',str(app)).replace('__OUTPUT__',str(release)).replace('__VERSION__',version)
    template=template.replace('OutputBaseFilename=ReupVoiceStudio-'+version+'-Lite-Setup','OutputBaseFilename='+name)
    (stage/'installer.iss').write_text(template,encoding='utf-8-sig');packager.audit(app)
    print(json.dumps({'stage':str(app),'source_commit':commit},indent=2))
if __name__=='__main__':main()
