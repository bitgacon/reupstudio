import threading,time
from uuid import uuid4
import pytest
from fastapi.testclient import TestClient
from reup import storage
from reup.jobs import JobQueue
from reup.server import make_app

@pytest.fixture(autouse=True)
def isolate(tmp_path,monkeypatch):
    monkeypatch.setattr(storage,'DATA',tmp_path/'data');storage.DATA.mkdir()

def finished(queue,key):
    for _ in range(200):
        if 'finished' in queue.rows[key]:return queue.rows[key]
        time.sleep(.01)
    pytest.fail('Job timeout')

def failed(queue,kind='tts',payload=None):
    row=queue.submit(kind,payload or {});finished(queue,row['id']);return row['id']

def test_retry_new_id_private_input_and_single_child():
    calls=[]
    def handler(kind,payload,key,*a):
        calls.append(payload)
        if len(calls)==1:raise ValueError('test failure')
        return {'files':[]}
    queue=JobQueue(handler)
    try:
        key=failed(queue,payload={'text':'Private text','force':True})
        assert 'Private text' not in str(queue.all())
        assert storage.read_json(storage.DATA/'jobs'/'requests'/(key+'.json'))['payload']['text']=='Private text'
        with pytest.raises(ValueError,match='xác nhận'):queue.retry(key)
        child=queue.retry(key,True);assert child['id']!=key
        assert finished(queue,child['id'])['status']=='complete'
        assert 'force' not in calls[-1] and queue.rows[key]['status']=='error'
        with pytest.raises(ValueError,match='Đã tạo'):queue.retry(key,True)
    finally:queue.close()

def test_restart_never_autoruns_and_poison_record_kept():
    key=uuid4().hex;path=storage.DATA/'jobs'/(key+'.json')
    storage.atomic_json(path,{'id':key,'kind':'tts','status':'running','created':1,'request_saved':True})
    storage.atomic_json(storage.DATA/'jobs'/'requests'/(key+'.json'),{'kind':'tts','payload':{'text':'A'}})
    bad=storage.DATA/'jobs'/'broken.json';bad.write_bytes(b'')
    calls=[];queue=JobQueue(lambda *a:calls.append(a) or {})
    try:
        assert queue.rows[key]['status']=='interrupted' and not calls
        assert queue.all()[0]['retryable'] and queue.load_issues and bad.read_bytes()==b''
        child=queue.retry(key,True);finished(queue,child['id']);assert len(calls)==1
    finally:queue.close()

def test_network_confirmation_and_credentials_not_saved():
    queue=JobQueue(lambda *a:(_ for _ in ()).throw(ValueError('failure')))
    try:
        key=failed(queue,'translate')
        with pytest.raises(ValueError,match='Internet'):queue.retry(key,True)
        child=queue.retry(key,True,True);finished(queue,child['id'])
        private=failed(queue,payload={'tts':{'api_key':'SECRET'}})
        assert not (storage.DATA/'jobs'/'requests'/(private+'.json')).exists()
        assert not next(r for r in queue.all() if r['id']==private)['retryable']
    finally:queue.close()

def test_missing_asset_deleted_project_and_old_job_blocked():
    queue=JobQueue(lambda *a:(_ for _ in ()).throw(ValueError('failure')))
    try:
        key=failed(queue,'subtitle_remove',{'asset':uuid4().hex})
        with pytest.raises(ValueError):queue.retry(key,True)
        p=storage.new_project('Original');key=failed(queue,'dub',{'project_id':p['id']})
        storage.delete_project(p['id'])
        with pytest.raises(ValueError):queue.retry(key,True)
        old=uuid4().hex;queue.rows[old]={'id':old,'status':'error','created':1,'kind':'tts'}
        with pytest.raises(ValueError,match='chưa lưu'):queue.retry(old,True)
    finally:queue.close()

def test_download_retry_only_remaining_urls():
    queue=JobQueue(lambda *a:(_ for _ in ()).throw(ValueError('failure')))
    try:
        key=failed(queue,'download',{'urls':['https://example.com/a','https://example.com/b']})
        asset=uuid4().hex;folder=storage.DATA/'uploads'/asset;folder.mkdir(parents=True)
        (folder/'source.mp4').write_bytes(b'media');storage.atomic_json(folder/'asset.json',{'file':'source.mp4'})
        storage.atomic_json(storage.DATA/'download-index.json',[{'job_id':key,'asset':asset,'source_url':'https://example.com/a'}])
        plan=queue.retry_plan(key);assert plan['payload']['urls']==['https://example.com/b'] and plan['skipped_downloads']==1
    finally:queue.close()

def test_retry_api_csrf_license_and_no_payload_exposure(monkeypatch):
    app=make_app();queue=app.state.queue;queue.handler=lambda *a:(_ for _ in ()).throw(ValueError('failure'))
    with TestClient(app) as client:
        key=failed(queue,payload={'text':'Private'});client.get('/');state=client.get('/api/state').json();headers={'X-Reup-Token':state['csrf']}
        assert 'Private' not in client.get('/api/jobs/'+key).text
        assert 'payload' not in client.get('/api/jobs/'+key+'/retry-info').json()
        url='/api/jobs/'+key+'/retry'
        assert client.post(url,json={'confirmed':True}).status_code==403
        assert client.post(url,json={'confirmed':'true'},headers=headers).status_code==422
        monkeypatch.setattr('reup.distribution.license_status',lambda:{'active':False})
        assert client.post(url,json={'confirmed':True},headers=headers).status_code==403
        monkeypatch.setattr('reup.distribution.license_status',lambda:{'active':True})
        response=client.post(url,json={'confirmed':True},headers=headers);assert response.status_code==200
        finished(queue,response.json()['id'])

def test_failed_metadata_write_does_not_leave_busy_job(monkeypatch):
    queue=JobQueue(lambda *a:pytest.fail('Should not run'))
    original=storage.atomic_json
    def write(path,value):
        if path.parent.name=='jobs':raise OSError('disk full')
        return original(path,value)
    try:
        monkeypatch.setattr(storage,'atomic_json',write)
        with pytest.raises(OSError):queue.submit('tts',{'text':'A'})
        assert not queue.busy() and not queue.rows and not queue.events
    finally:queue.close()
