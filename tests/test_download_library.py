from uuid import uuid4
import shutil
import pytest
from fastapi.testclient import TestClient
from reup import downloads,media,storage,timeline
from reup.server import make_app

@pytest.fixture(autouse=True)
def isolate(tmp_path,monkeypatch):
    monkeypatch.setattr(storage,'DATA',tmp_path/'data');storage.DATA.mkdir()

def item(audio=False):
    job=uuid4().hex;folder=storage.output_folder('downloads',job)/'001';folder.mkdir()
    source=folder/('audio.mp3' if audio else 'video.mp4')
    args=['-f','lavfi','-i','sine=frequency=440:duration=0.4','-c:a','libmp3lame'] if audio else ['-f','lavfi','-i','color=red:s=160x90:r=25:d=0.4','-c:v','libx264']
    media.command([media.binary(),'-y','-v','error',*args,str(source)])
    row=downloads.publish(source,'Test','https://example.com/x',job)
    return row,source

def test_bulk_editor_and_dubbing_preflight():
    a,_=item();b,_=item();audio,_=item(True)
    edit=downloads.send_many([a['id'],audio['id'],b['id']],'edit');doc=timeline.load(edit['project_id'])
    clips=sorted([c for t in doc['tracks'] for c in t['clips']],key=lambda c:c['start_ms'])
    assert [c['asset'] for c in clips]==[a['id'],audio['id'],b['id']]
    assert len(doc['tracks'])==2 and clips[1]['start_ms']==clips[0]['duration_ms']
    dub=downloads.send_many([a['id'],b['id']],'dub');assert len(dub['project_ids'])==2
    assert [storage.project(p)['video'] for p in dub['project_ids']]==[a['id'],b['id']]
    before=len(storage.list_projects())
    with pytest.raises(ValueError):downloads.send_many([a['id'],audio['id']],'dub')
    with pytest.raises(ValueError):downloads.send_many([a['id'],uuid4().hex],'edit')
    assert len(storage.list_projects())==before

def test_list_only_remove_preserves_all_files():
    row,source=item();asset,_=storage.asset(row['id'])
    assert downloads.remove_many([row['id']])['files_moved']==0
    assert source.exists() and asset.exists() and not storage.read_json(storage.DATA/'download-index.json',[])

def test_delete_moves_exact_owned_files_and_preserves_project():
    row,source=item();raw=source.parent/'source.mp4';shutil.copy2(source,raw)
    unrelated=source.parent/'my-file.txt';unrelated.write_text('User data')
    project=downloads.send(row['id'],'edit')['project_id']
    result=downloads.remove_many([row['id']],True)
    assert result['retained_assets']==1 and not source.exists() and not raw.exists() and unrelated.exists()
    assert storage.asset(row['id'])[0].exists()
    saved=storage.project(project);assert storage.project_asset(saved,row['id'])[0].exists()
    from pathlib import Path
    manifest=storage.read_json(Path(result['trash'])/'restore.json');assert len(manifest['moves'])==2
    assert all(Path(m['saved']).exists() for m in manifest['moves'])

def test_unreferenced_asset_soft_deleted_and_csrf():
    row,source=item();asset,_=storage.asset(row['id'])
    with TestClient(make_app()) as client:
        client.get('/');token=client.get('/api/state').json()['csrf']
        body={'ids':[row['id']],'delete_files':True}
        assert client.post('/api/downloads/remove',json=body).status_code==403
        response=client.post('/api/downloads/remove',json=body,headers={'X-Reup-Token':token})
        assert response.status_code==200,response.text
        assert response.json()['retained_assets']==0
        assert client.get('/api/downloads').json()==[]
    assert not source.exists() and not asset.exists()

def test_delete_rejects_tampered_path_before_moving_any_file():
    a,source=item();b,second=item()
    rows=storage.read_json(storage.DATA/'download-index.json',[]);rows[0]['file']['url']='/files/outputs/'+b['job_id']+'/../video.mp4';storage.atomic_json(storage.DATA/'download-index.json',rows)
    with pytest.raises(ValueError):downloads.remove_many([a['id'],b['id']],True)
    assert source.exists() and second.exists() and len(storage.read_json(storage.DATA/'download-index.json',[]))==2

def test_batch_send_api():
    a,_=item();b,_=item()
    with TestClient(make_app()) as client:
        client.get('/');token=client.get('/api/state').json()['csrf'];body={'ids':[a['id'],b['id']],'tab':'edit'}
        assert client.post('/api/downloads/send',json=body).status_code==403
        response=client.post('/api/downloads/send',json=body,headers={'X-Reup-Token':token})
        assert response.status_code==200,response.text
        assert response.json()['count']==2
