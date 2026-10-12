from uuid import uuid4
import pytest
from fastapi.testclient import TestClient
from reup import storage,timeline
from reup.server import make_app


def test_track_preset_store_delete_and_csrf(tmp_path,monkeypatch):
    monkeypatch.setattr(storage,'DATA',tmp_path/'data');storage.DATA.mkdir()
    doc=timeline.Timeline(tracks=[timeline.Track(id=uuid4().hex,name='Text',kind='text',clips=[timeline.Clip(id=uuid4().hex,start_ms=100,duration_ms=1000,text='Example')])]).model_dump()
    with TestClient(make_app()) as client:
        client.get('/');headers={'x-reup-token':client.get('/api/state').json()['csrf']}
        assert client.post('/api/track-presets',json={'name':'Test','timeline':doc}).status_code==403
        saved=client.post('/api/track-presets',json={'name':'Test','timeline':doc},headers=headers)
        assert saved.status_code==200 and saved.json()['timeline']['tracks'][0]['clips'][0]['text']=='Example'
        assert len(client.get('/api/track-presets').json())==1
        assert client.post('/api/track-presets/'+saved.json()['id']+'/delete',json={},headers=headers).status_code==200
        assert client.get('/api/track-presets').json()==[]


def test_empty_preset_rejected():
    with pytest.raises(ValueError):timeline.TrackPreset(name='Empty',timeline=timeline.Timeline())
