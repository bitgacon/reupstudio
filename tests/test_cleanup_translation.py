import threading
from types import SimpleNamespace

import pytest

from reup import storage
from reup.jobs import JobQueue
from reup.translation import GoogleWebTranslator, TranslationError


@pytest.fixture(autouse=True)
def isolated(tmp_path, monkeypatch):
    monkeypatch.setattr(storage, 'DATA', tmp_path)


def test_delete_restore_project_preserves_assets_and_rejects_stale_save():
    p=storage.new_project('Test')
    folder=storage.project_path(p['id'])
    source=folder/'source.mp4';source.write_bytes(b'unchanged')
    storage.delete_project(p['id'])
    assert not storage.list_projects()
    assert storage.list_projects(deleted=True)[0]['id']==p['id']
    with pytest.raises(ValueError):storage.project(p['id'])
    with pytest.raises(ValueError):storage.save_project(p)
    assert source.read_bytes()==b'unchanged'
    storage.delete_project(p['id'],restore=True)
    assert storage.project(p['id'])['name']=='Test'


def test_forget_history_preserves_outputs_and_active_jobs():
    storage.atomic_json(storage.DATA/'jobs'/'finished.json',{'id':'finished','status':'complete','created':1,'finished':2})
    output=storage.DATA/'result.wav';output.write_bytes(b'keep')
    q=JobQueue(lambda *args:None)
    try:
        q.rows['active']={'id':'active','status':'running','created':3}
        q.rows['finishing']={'id':'finishing','status':'complete','created':4}
        assert q.forget()['removed']==1
        assert set(q.rows)=={'active','finishing'}
        assert output.read_bytes()==b'keep'
        assert (storage.DATA/'jobs'/'forgotten'/'finished.json').exists()
        fresh=JobQueue(lambda *args:None)
        try:assert not fresh.all()
        finally:fresh.close()
    finally:q.close()


def translator(monkeypatch, responses):
    t=GoogleWebTranslator('zh','vi',threading.Event())
    calls=[];waits=[]
    def request(part):
        calls.append(part)
        return responses.pop(0)
    monkeypatch.setattr(t,'request',request)
    monkeypatch.setattr(t,'wait',lambda seconds=0:waits.append(seconds))
    return t,calls,waits


def response(status, retry=''):
    return SimpleNamespace(status_code=status,ok=status==200,headers={'Retry-After':retry},text='<div class="result-container">Xin chào</div>')


def test_google_bounded_retry_and_cache(monkeypatch):
    t,calls,waits=translator(monkeypatch,[response(429,'2'),response(200)])
    try:
        assert t.translate('你好')=='Xin chào'
        assert len(calls)==2 and 2 in waits
        assert t.translate('你好')=='Xin chào'
        assert len(calls)==2
    finally:t.close()


def test_google_long_cooldown_does_not_repeat_requests(monkeypatch):
    t,calls,_=translator(monkeypatch,[response(429,'120')])
    try:
        with pytest.raises(TranslationError):t.translate('你好')
        with pytest.raises(TranslationError,match='Chưa gửi'):t.translate('再见')
        assert len(calls)==1
    finally:t.close()


def test_google_cancellation_during_backoff(monkeypatch):
    t,calls,_=translator(monkeypatch,[response(429,'2')])
    def wait(seconds=0):
        if seconds:raise InterruptedError('stopped')
    monkeypatch.setattr(t,'wait',wait)
    try:
        with pytest.raises(InterruptedError):t.translate('你好')
        assert len(calls)==1
    finally:t.close()


def test_cleanup_api_requires_csrf_and_blocks_active_project():
    from fastapi.testclient import TestClient
    from reup.server import make_app
    app=make_app()
    with TestClient(app) as client:
        client.get('/')
        headers={'X-Reup-Token':client.get('/api/state').json()['csrf']}
        p=storage.new_project('API delete test');pid=p['id']
        assert client.post('/api/projects/'+pid+'/delete',json={}).status_code==403
        from uuid import uuid4
        jid=uuid4().hex
        app.state.queue.rows[jid]={'id':jid,'created':1,'status':'running','project_id':pid}
        assert client.post('/api/projects/'+pid+'/delete',json={},headers=headers).status_code==400
        assert client.post('/api/history/clear',json={},headers=headers).json()['removed']==0
        app.state.queue.rows[jid].update(status='complete',finished=2)
        storage.atomic_json(storage.DATA/'jobs'/(jid+'.json'),app.state.queue.rows[jid])
        assert client.post('/api/history/clear',json={'ids':[jid,jid]},headers=headers).json()['removed']==1
        assert client.post('/api/history/clear',json={'ids':[None]},headers=headers).status_code==400
        assert client.post('/api/projects/'+pid+'/delete',json={},headers=headers).status_code==200
        assert client.get('/api/deleted-projects').json()[0]['id']==pid
        assert client.post('/api/projects/'+pid+'/restore',json={},headers=headers).status_code==200
