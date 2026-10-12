import hashlib
import sys
import threading
from pathlib import Path
from uuid import uuid4
import pytest
from reup import storage, libraries, subtitle_removal as vsr, media
from reup.desktop_links import external_url

@pytest.fixture(autouse=True)
def isolated(tmp_path,monkeypatch):
    monkeypatch.setattr(storage,'DATA',tmp_path/'data');storage.DATA.mkdir()

def backend(root,legacy=False):
    (root/'backend/tools').mkdir(parents=True)
    if legacy:
        (root/'backend/config.py').write_text('VERSION = "1.1.1"\nclass InpaintMode:STTN="sttn"\n')
        (root/'backend/main.py').write_text('''import shutil
import config
from backend import config as backend_config
assert config is backend_config
class SubtitleRemover:
 def __init__(self,vd_path,sub_area=None,gui_mode=False):self.source=vd_path
 def run(self):
  assert config.MODE==config.InpaintMode.STTN and config.STTN_SKIP_DETECTION
  shutil.copy2(self.source,self.video_out_name)
''')
    else:
        (root/'backend/tools/args_handler.py').write_text('# --subtitle-area-coords')
        (root/'backend/main.py').write_text('print("--subtitle-area-coords --inpaint-mode")')
    return root

def test_file_and_backend_folder_normalization(tmp_path):
    home=backend(tmp_path/'VSR');assert vsr.home_path(home/'backend/main.py')==home
    vsr.config({'home':str(home/'backend/main.py'),'python':sys.executable})
    assert vsr.status()['home']==str(home)
    assert vsr.home_path(home/'backend')==home

def test_source_zip_explains_missing_runtime(tmp_path):
    home=backend(tmp_path/'source')
    with pytest.raises(ValueError,match='Source code'):libraries.detect_vsr(str(home/'backend/main.py'))
    vsr.config({'home':str(home),'python':str(tmp_path/'Start Menu/Python.exe')})
    assert 'Start Menu' in vsr.status()['message']

def test_bundled_detection_without_system_python(tmp_path):
    home=backend(tmp_path/'full');(home/'Python').mkdir();(home/'Python/python.exe').write_bytes(b'test')
    result=libraries.detect_vsr(str(home));assert result['connected']
    assert result['python']==str(home/'Python/python.exe')

@pytest.mark.parametrize('name',['../evil','/tmp/file','C:/evil','a/../../evil','a:file','\\\\server\\share\\x'])
def test_archive_paths(name):assert not libraries.valid_member(name)

def test_optional_location_and_output_are_independent(tmp_path):
    root=tmp_path/'libs';libraries.config({'root':str(root)})
    (tmp_path/'results').mkdir()
    storage.save_settings({'removal_output':str(tmp_path/'results')})
    assert storage.output_folder('removal',uuid4().hex).is_relative_to(tmp_path/'results')
    assert libraries.config()['root']==str(root)
    assert libraries.valid_member('VSR/backend/main.py')

def test_external_links():
    assert external_url('https://github.com/YaoFANGUK/video-subtitle-remover/releases')
    for url in ['http://127.0.0.1:18765/','file:///C:/Windows/system32','javascript:alert(1)','https://user:pass@example.com/','http://localhost/']:
        assert not external_url(url)

def test_legacy_multiple_regions_preserve_source(tmp_path):
    home=backend(tmp_path/'legacy',True);source=tmp_path/'source.mp4';source.write_bytes(b'original')
    out=tmp_path/'result.mp4'
    args=vsr.removal_command(home,Path(sys.executable),home/'backend/main.py',source,out,'sttn-auto',[[0,10,0,10],[20,30,20,30]],device='auto')
    vsr.run_worker(args,home,tmp_path/'legacy.log',threading.Event(),lambda *a:None,timeout=20)
    assert out.read_bytes()==source.read_bytes()==b'original';assert not (tmp_path/'vsr-region-0.mp4').exists()
    with pytest.raises(ValueError,match='STTN auto'):vsr.removal_command(home,Path(sys.executable),home/'backend/main.py',source,out,'lama',[[0,10,0,10]])

def test_preview_real_media_and_source_hash(tmp_path):
    source=tmp_path/'input.mp4'
    media.command([media.binary(),'-y','-v','error','-f','lavfi','-i','color=blue:s=160x90:r=24:d=1','-c:v','libx264',str(source)])
    before=hashlib.sha256(source.read_bytes()).hexdigest();key=vsr.store_asset(source,'test.mp4')
    result=vsr.prepare_preview({'asset':key},uuid4().hex,lambda *a:None,threading.Event())
    assert result['preview']['width']/result['preview']['height']==160/90 and result['preview']['poster_url'].endswith('.jpg')
    assert result['preview']['proxy_url'].endswith('.webm')
    assert hashlib.sha256(source.read_bytes()).hexdigest()==before

def test_download_hash_failure_does_not_publish(tmp_path,monkeypatch):
    class Response:
        def __enter__(self):return self
        def __exit__(self,*a):pass
        def raise_for_status(self):pass
        def iter_content(self,*a):yield b'bad'
    class Session(Response):
        def get(self,*a,**k):return Response()
    monkeypatch.setattr(libraries.requests,'Session',Session)
    target=tmp_path/'download.7z'
    with pytest.raises(ValueError,match='SHA256'):libraries.download({'url':'https://example.org/','bytes':3,'sha256':'0'*64},target,threading.Event(),lambda *a:None)
    assert not target.exists() and not target.with_suffix('.7z.partial').exists()


def test_fresh_windows_uses_pinned_native_extractor_not_py7zr(tmp_path,monkeypatch):
    if libraries.os.name != 'nt':pytest.skip('Windows fallback')
    monkeypatch.setattr(storage,'ROOT',tmp_path/'program')
    monkeypatch.setenv('ProgramFiles',str(tmp_path/'pf'));monkeypatch.setenv('ProgramFiles(x86)',str(tmp_path/'pfx86'))
    downloads=[]
    def download(asset,target,*a):downloads.append(asset);target.write_bytes(b'test-console')
    monkeypatch.setattr(libraries,'download',download)
    archive=tmp_path/'vsr.7z';archive.touch();output=tmp_path/'out';output.mkdir();log=tmp_path/'extract.log'
    calls=[]
    def run(args,cwd,log,*a):
        calls.append(args)
        if args[1]=='l':log.write_text('header\n----------\nPath = resources/backend/main.py\n')
    monkeypatch.setattr(libraries,'run',run)
    libraries.extract(archive,output,log,threading.Event(),lambda *a:None,tmp_path)
    assert downloads==[libraries.SEVEN_ASSET]
    assert libraries.SEVEN_ASSET['bytes']==602624 and '/26.04/7zr.exe' in libraries.SEVEN_ASSET['url']
    assert [args[1] for args in calls]==['l','x'] and all(args[0].endswith('7zr.exe') for args in calls)
    assert not (tmp_path/'extractor-env').exists()


@pytest.mark.parametrize('listing',['Path = ../evil.py','Symbolic Link = ../../outside','Hard Link = C:\\outside'])
def test_native_extractor_checks_listing_before_unpack(tmp_path,monkeypatch,listing):
    console=tmp_path/'7zr.exe';console.touch();monkeypatch.setattr(libraries,'seven_zip',lambda *a:console)
    calls=[]
    def run(args,cwd,log,*a):calls.append(args);log.write_text('header\n----------\n'+listing+'\n')
    monkeypatch.setattr(libraries,'run',run)
    with pytest.raises(ValueError):libraries.extract(tmp_path/'input.7z',tmp_path/'out',tmp_path/'log',threading.Event(),lambda *a:None,tmp_path)
    assert len(calls)==1 and calls[0][1]=='l'

def test_failed_install_keeps_previous_connection(tmp_path,monkeypatch):
    old=backend(tmp_path/'old');vsr.config({'home':str(old),'python':sys.executable})
    monkeypatch.setattr(libraries,'download',lambda *a:None)
    monkeypatch.setattr(libraries,'run',lambda *a:(_ for _ in ()).throw(ValueError('runtime failed')))
    monkeypatch.setattr(libraries.shutil,'disk_usage',lambda p:type('Usage',(),{'free':20_000_000_000})())
    with pytest.raises(ValueError,match='runtime failed'):libraries.install({'library':'vsr-directml'},uuid4().hex,lambda *a:None,threading.Event())
    assert vsr.config()['home']==str(old) and libraries.registry()=={}

def test_known_vsr_is_detected_and_reused_without_download(tmp_path,monkeypatch):
    home=backend(tmp_path/'ready');vsr.config({'home':str(home),'python':sys.executable})
    def forbid(*a):raise AssertionError('must reuse local runtime')
    monkeypatch.setattr(libraries,'download',forbid);monkeypatch.setattr(libraries,'extract',forbid)
    monkeypatch.setattr(libraries,'run',lambda args,cwd,log,*a:log.write_text('--subtitle-area-coords --inpaint-mode'))
    result=libraries.install({'library':'vsr-directml'},uuid4().hex,lambda *a:None,threading.Event())
    assert result['library']=='vsr-directml'
    assert next(r for r in libraries.status()['catalog'] if r['id']=='vsr-directml')['installed']
    assert libraries.registry()['vsr-directml']['home']==str(home)

def test_registry_connects_runtime_without_manual_settings(tmp_path):
    home=backend(tmp_path/'registered')
    storage.atomic_json(storage.DATA/'library-index.json',{'vsr-directml':{'path':str(home),'home':str(home),'python':sys.executable}})
    assert vsr.runtime()[0]==home.resolve()
    assert vsr.config()['home']==str(home)

def test_known_vision_and_separation_paths_are_visible(tmp_path,monkeypatch):
    monkeypatch.setattr(storage,'ROOT',tmp_path)
    for name in ['vision-env','separation-env']:
        python=tmp_path/name/'Scripts/python.exe';python.parent.mkdir(parents=True);python.write_bytes(b'test')
    rows=libraries.status()['catalog']
    assert all(next(r for r in rows if r['id']==key)['installed'] for key in ['vision','separation'])

def test_whisper_cache_is_linked_to_selected_model(tmp_path):
    cache=storage.DATA/'models/whisper';model=cache/'models--Systran--faster-whisper-small/snapshots/test/model.bin'
    model.parent.mkdir(parents=True);model.write_bytes(b'fixture')
    assert libraries.installed_path('whisper',tmp_path/'missing')==cache
    storage.save_settings({'whisper_model':'medium'})
    assert libraries.installed_path('whisper',tmp_path/'missing')==tmp_path/'missing'

@pytest.mark.parametrize('kind',['vision','separation'])
def test_existing_ai_runtime_is_checked_without_new_install(tmp_path,monkeypatch,kind):
    monkeypatch.setattr(storage,'ROOT',tmp_path);runtime=tmp_path/(kind+'-env');python=runtime/'Scripts/python.exe'
    python.parent.mkdir(parents=True);python.write_bytes(b'fixture')
    def forbid(*a):raise AssertionError('no new environment for existing runtime')
    monkeypatch.setattr(libraries,'environment',forbid)
    calls=[]
    def run(args,cwd,log,*a):calls.append(args);log.write_text('ok')
    monkeypatch.setattr(libraries,'run',run)
    libraries.install({'library':kind},uuid4().hex,lambda *a:None,threading.Event())
    assert len(calls)==1 and calls[0][0]==str(python) and calls[0][1]=='-c'
    assert libraries.installed_path(kind,tmp_path/'missing')==runtime
