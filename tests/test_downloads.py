import functools
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
import shutil
import threading
from uuid import uuid4

from fastapi.testclient import TestClient
import pytest
from reup import downloads, editor, media, storage, timeline
from reup.server import make_app


@pytest.fixture(autouse=True)
def isolated(tmp_path,monkeypatch):
    monkeypatch.setattr(storage,'DATA',tmp_path/'data');storage.DATA.mkdir()


@pytest.mark.parametrize('url',['file:///C:/x','http://127.0.0.1/a','http://192.168.1.2/a','http://localhost/x','https://user:pass@example.com/a'])
def test_url_rejects_local_and_credentials(url):
    with pytest.raises(ValueError):downloads.normalize(url)


def test_normalize_and_quality():
    assert downloads.normalize('https://www.douyin.com/jingxuan?modal_id=123')=='https://www.douyin.com/video/123'
    assert editor.geometry(320,180,editor.config({'output_ratio':'16:9','output_short_side':2160}))[:2]==(3840,2160)
    assert editor.geometry(180,320,editor.config({'output_ratio':'9:16','output_short_side':2160}))[:2]==(2160,3840)
    assert timeline.Timeline(width=3840,height=2160).width==3840


def test_download_mock_render_4k_and_transfer(tmp_path,monkeypatch):
    source=tmp_path/'sample.mp4';media.command([media.binary(),'-y','-v','error','-f','lavfi','-i','color=red:s=160x90:r=25:d=0.24','-c:v','libx264',str(source)])
    def fake(args,event,progress=None):
        assert '--no-simulate' in args and '--ignore-config' in args
        destination=args[args.index('-o')+1].replace('%(ext)s','mp4');shutil.copy2(source,destination)
        return 'REUP_TITLE:Sample\n'
    monkeypatch.setattr(downloads,'process',fake)
    result=downloads.download({'urls':['https://example.com/a'],'quality':'2160'},uuid4().hex,lambda *a:None,threading.Event())
    row=result['entries'][0];assert (row['width'],row['height'])==(3840,2160)
    assert row['original']=={'width':160,'height':90}
    client=TestClient(make_app());client.get('/');state=client.get('/api/state').json();headers={'X-Reup-Token':state['csrf']}
    assert client.get('/api/downloads').json()[0]['id']==row['id']
    assert client.post('/api/downloads/'+row['id']+'/send',json={'tab':'edit'}).status_code==403
    response=client.post('/api/downloads/'+row['id']+'/send',json={'tab':'edit'},headers=headers)
    assert response.status_code==200
    doc=timeline.load(response.json()['project_id']);assert doc['tracks'][0]['clips'][0]['asset']==row['asset']
    dub=downloads.send(row['id'],'dub');assert storage.project(dub['project_id'])['video']==row['asset']
    assert storage.reveal_folder('downloads',row['file']['url']).is_dir()


def test_real_ytdlp_download_local_synthetic_source(tmp_path,monkeypatch):
    source=tmp_path/'sample.mp4';media.command([media.binary(),'-y','-v','error','-f','lavfi','-i','color=blue:s=160x90:r=25:d=0.4','-c:v','libx264',str(source)])
    handler=functools.partial(SimpleHTTPRequestHandler,directory=str(tmp_path))
    server=ThreadingHTTPServer(('127.0.0.1',0),handler);thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
    # Only the test bypasses public-URL guard for our own synthetic HTTP fixture.
    monkeypatch.setattr(downloads,'normalize',lambda value:value)
    try:
        url=f'http://127.0.0.1:{server.server_port}/sample.mp4'
        result=downloads.download({'urls':[url],'quality':'native'},uuid4().hex,lambda *a:None,threading.Event())
        assert result['entries'][0]['width']==160
        output=storage.reveal_folder('downloads',result['entries'][0]['file']['url'])
        assert [p.name for p in output.iterdir()]==['video.mp4']
    finally:server.shutdown();server.server_close();thread.join(timeout=2)


def test_scan_and_cancel(monkeypatch):
    runner=downloads.process
    monkeypatch.setattr(downloads,'process',lambda *a:'{"entries":[{"ie_key":"Youtube","id":"abc","title":"X","url":"abc"},{"url":"https://example.com/a"},{"url":"file:///C:/x"}]}')
    assert len(downloads.scan({'url':'https://example.com/playlist'},threading.Event())['entries'])==2
    event=threading.Event();event.set()
    with pytest.raises(InterruptedError):runner(['ignored'],event)
