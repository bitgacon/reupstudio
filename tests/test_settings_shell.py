import json
from pathlib import Path
from uuid import uuid4
import pytest
from fastapi.testclient import TestClient
from reup import storage,libraries,advanced_ai
from reup.ui_preferences import preferences
from reup.server import make_app

@pytest.fixture
def isolated(tmp_path,monkeypatch):
    monkeypatch.setattr(storage,'DATA',tmp_path/'data');storage.DATA.mkdir()
    return tmp_path

def owned(tmp,key='tts-kokoro'):
    root=tmp/'libraries';folder=root/(key+'-'+uuid4().hex);folder.mkdir(parents=True)
    python=folder/'Scripts/python.exe';python.parent.mkdir();python.write_bytes(b'fake')
    entry={'path':str(folder),'python':str(python),'managed':True,'managed_root':str(root),'install_root':str(folder)}
    storage.atomic_json(storage.DATA/'library-index.json',{key:entry});return folder

def test_preferences_persist_without_engine_settings(isolated):
    old=storage.settings()
    assert preferences()['language']=='vi'
    preferences({'language':'zh','theme':'system','density':'comfortable'})
    assert preferences()['language']=='zh' and preferences()['theme']=='system'
    assert storage.settings()==old
    for bad in ({'language':'de'},{'theme':False},{'translation_key':'secret'},{'density':'invalid'}):
        with pytest.raises(ValueError):preferences(bad)
    assert preferences()['language']=='zh'

def test_bad_legacy_ui_preferences_fall_back_safely(isolated):
    storage.atomic_json(storage.DATA/'ui-preferences.json',{'language':[], 'theme':None})
    assert preferences()['language']=='vi' and preferences()['theme']=='light'
    storage.atomic_json(storage.DATA/'ui-preferences.json',[])
    assert preferences()['language']=='vi'

def test_preferences_api_and_csrf(isolated):
    with TestClient(make_app()) as client:
        client.get('/')
        token=client.get('/api/state').json()['csrf']
        assert client.get('/api/ui-preferences').json()['language']=='vi'
        assert client.post('/api/ui-preferences',json={'language':'en'}).status_code==403
        assert client.post('/api/ui-preferences',headers={'X-Reup-Token':token},json={'language':'en'}).json()['language']=='en'
        assert client.get('/api/advanced-ai/status').json()['features'][0]['files_ready'] is False

def test_disconnect_preserves_library_and_user_data(isolated):
    folder=owned(isolated);(folder/'model.bin').write_bytes(b'model')
    project=storage.new_project('Keep project');project_file=storage.project_path(project['id'])/'project.json'
    r=libraries.remove({'library':'tts-kokoro'})
    assert folder.is_dir() and project_file.is_file() and not r['deleted_files']
    assert 'tts-kokoro' not in libraries.registry()

def test_remove_only_selected_managed_installation(isolated):
    folder=owned(isolated);(folder/'model.bin').write_bytes(b'model')
    untouched=folder.parent/('tts-kokoro-'+uuid4().hex);untouched.mkdir();(untouched/'keep').touch()
    result=libraries.remove({'library':'tts-kokoro','delete_files':True})
    assert result['deleted_files'] and not folder.exists() and (untouched/'keep').is_file()

def test_external_runtime_cannot_be_deleted(isolated):
    external=isolated/'external';external.mkdir();(external/'model.bin').write_bytes(b'user')
    storage.atomic_json(storage.DATA/'library-index.json',{'tts-kokoro':{'path':str(external)}})
    with pytest.raises(ValueError,match='kết nối ngoài'):libraries.remove({'library':'tts-kokoro','delete_files':True})
    assert external.is_dir() and 'tts-kokoro' in libraries.registry()
    libraries.remove({'library':'tts-kokoro','delete_files':False});assert external.is_dir()

def test_remove_refuses_root_or_project_folder(isolated):
    folder=owned(isolated);entry=libraries.registry()['tts-kokoro']
    storage.atomic_json(storage.DATA/'project-index.json',{'a'*32:str(folder/'project')})
    with pytest.raises(ValueError,match='dữ liệu'):libraries.remove({'library':'tts-kokoro','delete_files':True})
    assert folder.exists()
    storage.atomic_json(storage.DATA/'project-index.json',{})
    entry['install_root']=str(folder.parent)
    storage.atomic_json(storage.DATA/'library-index.json',{'tts-kokoro':entry})
    with pytest.raises(ValueError,match='đường dẫn'):libraries.remove({'library':'tts-kokoro','delete_files':True})
    assert folder.exists()

def test_busy_queue_blocks_removal_but_not_ui(isolated,monkeypatch):
    folder=owned(isolated)
    app=make_app();monkeypatch.setattr(app.state.queue,'busy',lambda:True)
    with TestClient(app) as client:
        client.get('/')
        token=client.get('/api/state').json()['csrf'];headers={'X-Reup-Token':token}
        assert client.post('/api/libraries/remove',headers=headers,json={'library':'tts-kokoro','delete_files':True}).status_code==409
        assert client.post('/api/ui-preferences',headers=headers,json={'language':'en'}).status_code==200
    assert folder.exists()

def test_ai_status_checks_files_not_inference(isolated):
    folder=isolated/'ctc';folder.mkdir();(folder/'config.json').write_text('{}')
    python=folder/'python.exe';python.touch()
    advanced_ai.config({'alignment_python':str(python),'alignment_model':str(folder)})
    rows=advanced_ai.readiness()['features']
    assert rows[0]['files_ready'] and not rows[1]['files_ready'] and rows[3]['files_ready']

def test_vsr_autodetection_keeps_ownership_metadata(isolated):
    from test_libraries import backend
    from reup import subtitle_removal as vsr
    folder=owned(isolated,'vsr-directml');backend(folder)
    vsr.config({'home':str(folder),'python':str(folder/'Scripts/python.exe')})
    rows=libraries.available();assert rows['vsr-directml']['managed']
    libraries.remember_vsr(folder,folder/'Scripts/python.exe')
    assert libraries.registry()['vsr-directml']['managed']
    libraries.remove({'library':'vsr-directml','delete_files':True})
    assert not folder.exists() and not vsr.config()['home']
