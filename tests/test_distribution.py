import base64
import importlib.util
import json
import time

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives import serialization
from fastapi.testclient import TestClient

from reup import distribution, storage
from reup.server import make_app


def envelope(key, value):
    raw = json.dumps(value).encode()
    return {"payload":base64.b64encode(raw).decode(), "signature":base64.b64encode(key.sign(raw)).decode()}


@pytest.fixture
def signing(tmp_path, monkeypatch):
    monkeypatch.setattr(storage, "DATA", tmp_path / "data")
    storage.DATA.mkdir()
    key = Ed25519PrivateKey.generate()
    public = base64.b64encode(key.public_key().public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw)).decode()
    config = {"license_required":True,"public_key":public,"license_url":"https://licenses.example.test"}
    monkeypatch.setattr(distribution, "policy", lambda:config)
    monkeypatch.setattr(distribution, "machine_id", lambda:"a"*64)
    return key, config


def test_lease_bound_expiry_and_signature(signing):
    key, _ = signing
    value = {"product":"reup-voice-studio","machine":"a"*64,"expires":time.time()+120}
    storage.atomic_json(storage.DATA / "license.json", envelope(key,value))
    assert distribution.license_status()["active"]
    for field,bad in [("machine","b"*64),("expires",0),("product","other")]:
        storage.atomic_json(storage.DATA / "license.json", envelope(key,{**value,field:bad}))
        assert not distribution.license_status()["active"]
    storage.atomic_json(storage.DATA / "license.json", envelope(Ed25519PrivateKey.generate(),value))
    assert not distribution.license_status()["active"]


def test_license_gate(signing):
    with TestClient(make_app()) as client:
        client.get('/')
        token = client.get('/api/state').json()['csrf']
        assert client.post('/api/jobs',json={'kind':'tts','payload':{}},headers={'X-Reup-Token':token}).status_code == 403


def test_external_outputs_safe(tmp_path, monkeypatch):
    monkeypatch.setattr(storage,"DATA",tmp_path/'data')
    storage.DATA.mkdir()
    root=tmp_path/'exports';root.mkdir()
    storage.save_settings({'output_root':str(root)})
    folder=storage.output_folder('documents','a'*32)
    (folder/'extracted.txt').write_text('SGK',encoding='utf-8')
    url=storage.file_url(folder/'extracted.txt')
    with TestClient(make_app()) as client:
        client.get('/')
        client.get('/api/state')
        assert client.get(url).text == 'SGK'
        assert client.get('/files/exports/'+'b'*32+'/extracted.txt').status_code == 404
        assert client.get('/files/exports/'+'a'*32+'/%2e%2e/secret.txt').status_code == 404
    assert storage.output_folder('tts','b'*32) != folder
    with pytest.raises(ValueError):
        storage.save_settings({'output_root':'relative'})


def test_update_disabled_and_https(monkeypatch):
    monkeypatch.setattr(distribution,'policy',lambda:{})
    assert not distribution.check_update()['configured']
    for url in ['http://example.com','https://a:b@example.com','file:///x']:
        with pytest.raises(ValueError):distribution.https(url)


def test_signed_update_and_hash(signing, monkeypatch):
    import hashlib
    key, config = signing
    config['update_url']='https://updates.example.test/latest.json'
    content=b'QA simulated installer bytes, not executable'
    manifest={'product':'reup-voice-studio','version':'9.0.0','url':'https://updates.example.test/Setup.exe','sha256':hashlib.sha256(content).hexdigest()}
    class Response:
        status_code=200
        def __enter__(self):return self
        def __exit__(self,*args):pass
        def raise_for_status(self):pass
        def json(self):return envelope(key,manifest)
        @property
        def content(self):return json.dumps(self.json()).encode()
        def iter_content(self,*args):yield content
    class Session:
        def get(self,*args,**kwargs):return Response()
    monkeypatch.setattr(distribution.requests,'Session',Session)
    assert distribution.check_update()['available']
    assert distribution.download_update()['file']['bytes']==len(content)
    manifest['sha256']='0'*64
    with pytest.raises(ValueError,match='Hash'):distribution.download_update()
    assert len(list(storage.DATA.glob('outputs/**/*.exe')))==1
    manifest['version']='0.1.0'
    assert not distribution.check_update()['available']


def test_license_server_seats_revocation(tmp_path):
    spec=importlib.util.spec_from_file_location('issuer',storage.ROOT/'admin'/'LICENSE_SERVER.py')
    issuer=importlib.util.module_from_spec(spec);spec.loader.exec_module(issuer)
    issuer.HOME=tmp_path
    key=Ed25519PrivateKey.generate()
    (tmp_path/'signing.key').write_bytes(key.private_bytes(serialization.Encoding.Raw,serialization.PrivateFormat.Raw,serialization.NoEncryption()))
    with issuer.database() as db:
        db.execute('INSERT INTO licenses(hash,expires,seats) VALUES(?,?,?)',(issuer.digest('RVS-test-key'),time.time()+100,1))
    with TestClient(issuer.app) as client:
        body={'key':'RVS-test-key','machine':'a'*64,'nonce':'b'*48}
        assert client.post('/v1/activate',json=body).status_code == 200
        assert client.post('/v1/activate',json=body).status_code == 200
        assert client.post('/v1/activate',json={**body,'machine':'c'*64}).status_code == 403
        with issuer.database() as db:db.execute('UPDATE licenses SET revoked=1')
        assert client.post('/v1/activate',json=body).status_code == 403
