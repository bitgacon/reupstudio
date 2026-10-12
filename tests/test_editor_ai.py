import threading
from uuid import uuid4
from reup import media, storage, separation, timeline
from reup.workflows import Workflows


def test_editor_separation_returns_library_assets_without_replacing_source(tmp_path,monkeypatch):
    monkeypatch.setattr(storage,'DATA',tmp_path/'data');storage.DATA.mkdir()
    key=uuid4().hex;folder=storage.DATA/'uploads'/key;folder.mkdir(parents=True);source=folder/'source.wav'
    media.command([media.binary(),'-y','-v','error','-f','lavfi','-i','sine=frequency=440:duration=0.3',str(source)])
    storage.atomic_json(folder/'asset.json',{'id':key,'file':source.name,'name':'Source'})
    project=storage.new_project('AI mock');before=storage.project(project['id'])
    def fake_separate(source,folder,progress,event):
        folder.mkdir(parents=True,exist_ok=True);paths=[]
        for name in ['vocals.wav','no_vocals.wav']:
            import shutil
            target=folder/name;shutil.copy2(source,target);paths.append(target)
        return paths
    monkeypatch.setattr(separation,'separate',fake_separate)
    result=Workflows().job_editor_separate({'project_id':project['id'],'asset':key},uuid4().hex,lambda *a:None,threading.Event())
    assert [i['name'] for i in result['media_items']]==['vocals.wav','no_vocals.wav']
    assert len({i['id'] for i in result['media_items']})==2
    assert all(i['kind']=='audio' for i in result['media_items'])
    assert storage.project(project['id'])==before
    assert not timeline.load(project['id'])['tracks']
    assert source.exists() and len(result['files'])==2
