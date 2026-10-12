from pathlib import Path
import pytest
from fastapi.testclient import TestClient
from reup import distribution, storage
from reup.server import make_app


def test_dropbox_https_redirects():
    class Response:
        def __init__(self, code, location=''):
            self.status_code=code; self.headers={'Location':location}; self.closed=False
        def close(self): self.closed=True
        def raise_for_status(self): pass
    first=Response(302,'https://dl.dropboxusercontent.com/file')
    last=Response(200)
    class Session:
        def __init__(self): self.urls=[]
        def get(self,url,**kwargs):
            self.urls.append(url); assert kwargs['allow_redirects'] is False
            return first if len(self.urls)==1 else last
    session=Session()
    assert distribution.get_https(session,'https://www.dropbox.com/file?dl=1') is last
    assert first.closed and len(session.urls)==2
    first.headers['Location']='http://unsafe.test/file'
    with pytest.raises(ValueError):distribution.get_https(Session(),'https://www.dropbox.com/file')


def test_update_install_never_accepts_client_path(tmp_path,monkeypatch):
    monkeypatch.setattr(storage,'DATA',tmp_path)
    app=make_app()
    with TestClient(app) as client:
        client.get('/')
        token=client.get('/api/state').json()['csrf']
        response=client.post('/api/update/install',json={'path':'C:/fake.exe'},headers={'X-Reup-Token':token})
        assert response.status_code==409
        app.state.desktop_update=True
        monkeypatch.setattr(distribution,'launch_update',lambda:{'ok':True})
        assert client.post('/api/update/install',json={},headers={'X-Reup-Token':token}).status_code==200
        assert app.state.update_exit
        assert client.post('/api/jobs',json={'kind':'tts'},headers={'X-Reup-Token':token}).status_code==409


def test_native_icon_shortcut_and_mandatory_check():
    root=storage.ROOT
    script=(root/'installer.iss').read_text(encoding='utf-8')
    assert 'Filename: "{app}\\runtime\\pythonw.exe"' not in script
    assert 'SetupIconFile=' in script and 'Filename: "{app}\\ReupVoiceStudio.exe"' in script
    assert (root/'web'/'app.ico').stat().st_size>1000
    ui=(root/'web'/'storage-ui.js').read_text(encoding='utf-8')
    assert 'auto-update-check' not in ui and 'rv-auto-update' not in ui
    assert 'setTimeout(update,4000)' in ui
    assert "querySelector('.card-heading').after(folders)" in ui
    assert "add(folders,'output_root'" in ui
    assert "document.getElementById('page-'+tab)" not in ui
