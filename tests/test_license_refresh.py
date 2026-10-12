import base64,hashlib,importlib.util,json,time
from types import SimpleNamespace
from pathlib import Path
import pytest,requests
from fastapi.testclient import TestClient
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives import serialization
from reup import distribution,license_session,storage


@pytest.fixture
def server(tmp_path,monkeypatch):
    spec=importlib.util.spec_from_file_location('test_refresh_issuer',Path(__file__).parents[1]/'admin/LICENSE_SERVER.py')
    issuer=importlib.util.module_from_spec(spec);spec.loader.exec_module(issuer);issuer.HOME=tmp_path/'issuer';issuer.HOME.mkdir()
    key=Ed25519PrivateKey.generate()
    (issuer.HOME/'signing.key').write_bytes(key.private_bytes(serialization.Encoding.Raw,serialization.PrivateFormat.Raw,serialization.NoEncryption()))
    with issuer.database() as db:db.execute('INSERT INTO licenses(hash,expires,seats) VALUES(?,?,?)',(issuer.digest('test-license-key'),time.time()+86400*40,1))
    config={'license_required':True,'public_key':base64.b64encode(key.public_key().public_bytes(serialization.Encoding.Raw,serialization.PublicFormat.Raw)).decode(),'license_url':'https://issuer.example.test'}
    monkeypatch.setattr(distribution,'policy',lambda:config);monkeypatch.setattr(distribution,'machine_id',lambda:'a'*64)
    monkeypatch.setattr(storage,'DATA',tmp_path/'client');storage.DATA.mkdir()
    return issuer,config


def test_server_refresh_idempotent_and_revocation_bound(server):
    issuer,_=server
    with TestClient(issuer.app) as client:
        body={'key':'test-license-key','machine':'a'*64,'nonce':'b'*48}
        old=client.post('/v1/activate',json=body).json();assert 'refresh_token' not in old
        active=client.post('/v1/activate',json=body|{'refresh':True}).json();token=active['refresh_token']
        request={'token':token,'machine':'a'*64,'nonce':'c'*48}
        for _ in range(2):assert client.post('/v1/refresh',json=request).status_code==200
        assert client.post('/v1/refresh',json=request|{'machine':'d'*64}).status_code==403
        with issuer.database() as db:
            assert token not in db.execute('SELECT token_hash FROM sessions').fetchone()[0]
            db.execute('UPDATE licenses SET revoked=1')
        assert client.post('/v1/refresh',json=request).status_code==403


def test_server_reset_invalidates_session(server):
    issuer,_=server
    with TestClient(issuer.app) as client:
        active=client.post('/v1/activate',json={'key':'test-license-key','machine':'a'*64,'nonce':'b'*48,'refresh':True}).json()
        with issuer.database() as db:db.execute('DELETE FROM machines')
        assert client.post('/v1/refresh',json={'token':active['refresh_token'],'machine':'a'*64,'nonce':'c'*48}).status_code==403


def test_client_end_to_end_no_raw_secrets_and_network_failure_keeps_lease(server,monkeypatch):
    issuer,config=server
    with TestClient(issuer.app) as client:
        monkeypatch.setattr(requests.Session,'post',lambda self,url,**kwargs:client.post('/v1/'+url.rsplit('/',1)[1],json=kwargs['json']))
        status=distribution.activate('test-license-key');assert status['active']
        on_disk=(storage.DATA/'license-session.json').read_text();raw=storage.read_json(storage.DATA/'license.json')
        token=license_session.read(config,'a'*64)['token']
        assert token not in on_disk and 'test-license-key' not in on_disk and 'refresh_token' not in raw
        assert distribution.refresh_license()['active']
        before=(storage.DATA/'license.json').read_bytes()
        def fail(*a,**k):raise requests.ConnectionError('SECRET '+token)
        monkeypatch.setattr(requests.Session,'post',fail)
        with pytest.raises(ValueError) as err:distribution.refresh_license()
        assert token not in str(err.value) and (storage.DATA/'license.json').read_bytes()==before
        assert license_session.read(config,'different-machine') is None
        assert license_session.read(config|{'license_url':'https://other.test'},'a'*64) is None


def test_dpapi_round_trip():
    import os
    if os.name!='nt':pytest.skip('Windows DPAPI')
    raw=b'test-session-secret';sealed=license_session.protect(raw)
    assert raw not in sealed and license_session.protect(sealed,True)==raw


def test_private_build_background_does_not_call_network(tmp_path,monkeypatch):
    monkeypatch.setattr(storage,'DATA',tmp_path);monkeypatch.setattr(distribution,'policy',lambda:{})
    monkeypatch.setattr(distribution,'refresh_license',lambda:pytest.fail('Private build called refresh'))
    stop,thread=license_session.start();stop.set();thread.join(2);assert not thread.is_alive()
