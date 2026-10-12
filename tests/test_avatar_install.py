import threading,zipfile
from pathlib import Path
from uuid import uuid4
import pytest
from reup import avatar_install,avatar_manifest,libraries,storage,advanced_ai
from AVATAR_INSTALL_WORKER import verify


@pytest.fixture(autouse=True)
def isolated(tmp_path,monkeypatch):
    monkeypatch.setattr(storage,'DATA',tmp_path/'data');storage.DATA.mkdir()


def test_install_requires_consent_and_nvidia_before_download(tmp_path,monkeypatch):
    monkeypatch.setattr(libraries,'download',lambda *a:pytest.fail('Unexpected download'))
    with pytest.raises(ValueError,match='xác nhận'):avatar_install.install({},tmp_path,tmp_path,tmp_path/'log',threading.Event(),lambda *a:None)
    monkeypatch.setattr(avatar_install,'gpu_preflight',lambda:(_ for _ in ()).throw(ValueError('No NVIDIA')))
    with pytest.raises(ValueError):avatar_install.install({'accept_avatar_models':True},tmp_path,tmp_path,tmp_path/'log',threading.Event(),lambda *a:None)


def test_extract_source_rejects_traversal(tmp_path):
    archive=tmp_path/'bad.zip'
    with zipfile.ZipFile(archive,'w') as z:z.writestr('MuseTalk-'+avatar_manifest.COMMIT+'/../evil.py','evil')
    home=tmp_path/'source'
    with pytest.raises(ValueError):avatar_install.extract_source(archive,home,threading.Event())
    assert not home.exists() and not (tmp_path/'evil.py').exists()


def test_extract_valid_source_and_cancel(tmp_path):
    archive=tmp_path/'source.zip'
    with zipfile.ZipFile(archive,'w') as z:z.writestr('MuseTalk-'+avatar_manifest.COMMIT+'/scripts/inference.py','source')
    home=tmp_path/'source';avatar_install.extract_source(archive,home,threading.Event())
    assert (home/'scripts/inference.py').read_text()=='source'
    cancel=threading.Event();cancel.set()
    with pytest.raises(InterruptedError):avatar_install.extract_source(archive,tmp_path/'cancelled',cancel)
    assert not (tmp_path/'cancelled').exists()


def test_model_hash_verification_does_not_deserialize(tmp_path):
    import hashlib
    path=tmp_path/'weights.pth';path.write_bytes(b'not a pickle')
    verify(path,path.stat().st_size,'sha256',hashlib.sha256(path.read_bytes()).hexdigest())
    verify(path,path.stat().st_size,'git-sha1',hashlib.sha1(b'blob 12\0not a pickle').hexdigest())
    with pytest.raises(ValueError):verify(path,12,'sha256','0'*64)


def test_avatar_unlink_keeps_external_files(tmp_path):
    home=tmp_path/'MuseTalk';(home/'scripts').mkdir(parents=True);(home/'scripts/inference.py').touch()
    python=tmp_path/'python.exe';python.touch()
    advanced_ai.config({'avatar_home':str(home),'avatar_python':str(python)})
    assert libraries.status()['catalog'][next(i for i,r in enumerate(libraries.CATALOG) if r['id']=='avatar')]['installed']
    result=libraries.remove({'library':'avatar','delete_files':False})
    assert not result['deleted_files'] and python.exists() and (home/'scripts/inference.py').exists()
    assert not advanced_ai.config()['avatar_python']


def test_catalog_and_pins_complete_without_model_downloads():
    assert 'avatar' in {r['id'] for r in libraries.CATALOG}
    assert len(avatar_manifest.COMMIT)==40 and len(avatar_manifest.SOURCE['sha256'])==64
    for repo,revision,name,target,size,algorithm,digest in avatar_manifest.MODELS:
        assert len(revision)==40 and size>0
        assert len(digest)==(64 if algorithm=='sha256' else 40)
        assert not Path(target).is_absolute() and '..' not in Path(target).parts
