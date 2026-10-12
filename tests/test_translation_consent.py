import pytest
from fastapi.testclient import TestClient
from reup import storage
from reup.server import make_app

def test_consent_persists_per_project_and_can_be_revoked(tmp_path,monkeypatch):
    monkeypatch.setattr(storage,'DATA',tmp_path)
    p=storage.new_project('Consent');other=storage.new_project('Other')
    with TestClient(make_app()) as client:
        client.get('/');headers={'X-Reup-Token':client.get('/api/state').json()['csrf']}
        def save(consent=None):
            p=client.get('/api/projects/'+pid).json()
            body={k:p[k] for k in ('revision','name','voice','video','cues','edit')}
            if consent is not None:body['translation_consent']=consent
            return client.post('/api/projects/'+pid,json=body,headers=headers)
        pid=p['id']
        assert not client.get('/api/projects/'+pid).json().get('translation_consent',False)
        assert save(True).json()['translation_consent'] is True
        assert storage.project(pid)['translation_consent'] is True
        assert save().json()['translation_consent'] is True # Older client does not revoke.
        assert not client.get('/api/projects/'+other['id']).json().get('translation_consent',False)
        assert save(False).json()['translation_consent'] is False
        assert save('true').status_code==422
