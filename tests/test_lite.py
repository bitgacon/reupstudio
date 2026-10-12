import sys, threading
from pathlib import Path
import pytest
from reup import storage, libraries, engine, tts_providers

@pytest.fixture
def empty(tmp_path, monkeypatch):
    monkeypatch.setattr(storage, 'ROOT', tmp_path/'app')
    monkeypatch.setattr(storage, 'DATA', tmp_path/'data')
    storage.DATA.mkdir(); return tmp_path

def test_lite_vieneu_is_not_installed(empty):
    row=next(r for r in tts_providers.public()['catalog'] if r['id']=='vieneu')
    assert not row['installed']
    with pytest.raises(RuntimeError, match='Thư viện'):engine.find_home()

def test_vieneu_registration_is_used_without_manual_path(empty):
    home=empty/'optional-vieneu';python=home/'.venv/Scripts/python.exe'
    python.parent.mkdir(parents=True);python.write_bytes(b'test')
    storage.atomic_json(storage.DATA/'library-index.json', {'vieneu':{'path':str(home),'python':str(python)}})
    assert engine.find_home()==home.resolve()
    assert next(r for r in tts_providers.public()['catalog'] if r['id']=='vieneu')['installed']

def test_whisper_optional_runtime_is_preferred(empty):
    python=empty/'whisper/python.exe';python.parent.mkdir();python.write_bytes(b'test')
    storage.atomic_json(storage.DATA/'library-index.json',{'whisper':{'path':str(python.parent),'python':str(python)}})
    assert libraries.whisper_python()==str(python)

def test_lite_installers_register_only_after_checks(empty,monkeypatch):
    monkeypatch.setattr(libraries.shutil,'disk_usage',lambda p:type('Usage',(),{'free':20_000_000_000})())
    def environment(folder,*a):
        python=folder/'Scripts/python.exe';python.parent.mkdir(parents=True);python.write_bytes(b'test');return python
    calls=[]
    def run(args,cwd,log,*a):
        calls.append(args)
        log.write_text('VIENEU_READY' if 'check' in args else 'installed',encoding='utf-8')
    monkeypatch.setattr(libraries,'environment',environment);monkeypatch.setattr(libraries,'run',run)
    result=libraries.install({'library':'vieneu'},'a'*32,lambda *a:None,threading.Event())
    assert result['library']=='vieneu' and engine.find_home().is_dir()
    assert any('check' in a for a in calls)
    calls.clear()
    result=libraries.install({'library':'whisper'},'b'*32,lambda *a:None,threading.Event())
    assert libraries.whisper_python()==libraries.registry()['whisper']['python']
    assert any('faster-whisper==1.1.0' in a for a in calls)
    assert any(str(storage.ROOT/'LIBRARY_WORKER.py') in a for a in calls)
