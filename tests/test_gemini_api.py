import json
from types import SimpleNamespace

import pytest
import requests
from reup import storage,translation_api


@pytest.fixture(autouse=True)
def isolated(tmp_path,monkeypatch):
    monkeypatch.setattr(storage,'DATA',tmp_path)
    monkeypatch.setattr(translation_api,'RETRIES',0)


def test_aistudio_normalizes_endpoint_and_display_model():
    s=storage.save_settings({'translation_url':'https://aistudio.google.com/','translation_model':'Gemini 3.8 Flash','translation_key':'private-key'})
    assert s['translation_url']==translation_api.GEMINI_URL
    assert s['translation_model']=='gemini-3.8-flash'
    assert 'translation_key' not in s and s['has_translation_key']


def test_gemini_request_shape(monkeypatch):
    seen={}
    def post(self,url,**kwargs):
        seen.update(url=url,**kwargs)
        return SimpleNamespace(ok=True,status_code=200,json=lambda:{'choices':[{'message':{'content':'```json\n[{"id":1,"text":"Xin chào"}]\n```'}}]})
    monkeypatch.setattr(requests.Session,'post',post)
    result=translation_api.complete('https://aistudio.google.com/','Gemini 3.8 Flash','private-key',[{'role':'user','content':'hello'}])
    assert result==[{'id':1,'text':'Xin chào'}]
    assert seen['url']==translation_api.GEMINI_URL+'/chat/completions'
    assert seen['json']['model']=='gemini-3.8-flash'
    assert seen['headers']=={'Authorization':'Bearer private-key'}
    assert not seen['allow_redirects']


@pytest.mark.parametrize('status',[400,401,403,404,429,500,302])
def test_http_errors_do_not_expose_keys_or_server_body(monkeypatch,status):
    monkeypatch.setattr(requests.Session,'post',lambda *a,**k:SimpleNamespace(ok=status<400,status_code=status))
    with pytest.raises(RuntimeError) as err:translation_api.complete(translation_api.GEMINI_URL,'gemini-3.8-flash','private-key',[])
    assert str(status) in str(err.value) and 'private-key' not in str(err.value)


@pytest.mark.parametrize('data',[
    {},{'choices':[]},{'choices':[{'message':{'content':None}}]},
    {'choices':[{'message':{'content':'Not JSON'}}]},
    {'choices':[{'message':{'content':'{"id":1,"text":"one"}'}}]},
    {'choices':[{'message':{'content':'[{"id":true,"text":"one"}]'}}]},
])
def test_malformed_response_actionable(monkeypatch,data):
    monkeypatch.setattr(requests.Session,'post',lambda *a,**k:SimpleNamespace(ok=True,status_code=200,json=lambda:data))
    with pytest.raises(ValueError):translation_api.complete(translation_api.GEMINI_URL,'gemini-3.8-flash','private-key',[])


def test_html_response_is_not_raw_jsondecodeerror(monkeypatch):
    def invalid():raise json.JSONDecodeError('HTML','private-key',0)
    monkeypatch.setattr(requests.Session,'post',lambda *a,**k:SimpleNamespace(ok=True,status_code=200,json=invalid))
    with pytest.raises(ValueError,match='HTML/rỗng') as err:translation_api.complete(translation_api.GEMINI_URL,'gemini-3.8-flash','private-key',[])
    assert 'private-key' not in str(err.value)


class Event:
    def __init__(self,cancel=False):self.delays=[];self.cancel=cancel
    def is_set(self):return False
    def wait(self,delay):self.delays.append(delay);return self.cancel


def success():return SimpleNamespace(ok=True,status_code=200,json=lambda:{'choices':[{'message':{'content':'[{"id":1,"text":"Xin chào"}]'}}]})


def test_503_retry_is_bounded_same_model_and_reports_progress(monkeypatch):
    monkeypatch.setattr(translation_api,'RETRIES',2)
    responses=[SimpleNamespace(ok=False,status_code=503,headers={}),SimpleNamespace(ok=False,status_code=503,headers={}),success()]
    calls=[];messages=[];event=Event()
    def post(*a,**k):calls.append(k['json']['model']);return responses.pop(0)
    monkeypatch.setattr(requests.Session,'post',post)
    assert translation_api.complete(translation_api.GEMINI_URL,'gemini-3.8-flash','private-key',[],event,messages.append)[0]['id']==1
    assert calls==['gemini-3.8-flash']*3 and event.delays==[5,10] and len(messages)==2


def test_503_exhaustion_and_long_retry_after(monkeypatch):
    monkeypatch.setattr(translation_api,'RETRIES',2)
    calls=[];event=Event()
    def post(*a,**k):calls.append(1);return SimpleNamespace(ok=False,status_code=503,headers={})
    monkeypatch.setattr(requests.Session,'post',post)
    with pytest.raises(RuntimeError,match='503'):translation_api.complete(translation_api.GEMINI_URL,'gemini-3.8-flash','private-key',[],event)
    assert len(calls)==3 and event.delays==[5,10]
    calls.clear();event.delays.clear()
    monkeypatch.setattr(requests.Session,'post',lambda *a,**k:SimpleNamespace(ok=False,status_code=503,headers={'Retry-After':'120'}))
    with pytest.raises(RuntimeError):translation_api.complete(translation_api.GEMINI_URL,'gemini-3.8-flash','private-key',[],event)
    assert not event.delays


def test_cancel_backoff_stops_before_next_request(monkeypatch):
    monkeypatch.setattr(translation_api,'RETRIES',2)
    calls=[]
    def post(*a,**k):calls.append(1);return SimpleNamespace(ok=False,status_code=503,headers={'Retry-After':'3'})
    monkeypatch.setattr(requests.Session,'post',post)
    event=Event(cancel=True)
    with pytest.raises(InterruptedError):translation_api.complete(translation_api.GEMINI_URL,'gemini-3.8-flash','private-key',[],event)
    assert calls==[1] and event.delays==[3]


def test_api_resume_keeps_completed_batch_manual_edits_and_timing(monkeypatch):
    import threading
    from uuid import uuid4
    from reup.workflows import Workflows
    p=storage.new_project('API resume',edit={'translation_provider':'api'})
    p['cues']=[{'id':i,'start_ms':i*1000,'end_ms':i*1000+900,'source_text':f'source {i}','text':'original','status':'pending'} for i in range(1,12)]
    storage.save_project(p);storage.save_settings({'translation_url':translation_api.GEMINI_URL,'translation_model':'gemini-3.8-flash','translation_key':'private-key'})
    batches=[]
    def complete(*a,**k):
        items=json.loads(a[3][1]['content']);batches.append([x['id'] for x in items])
        if len(batches)==2:raise RuntimeError('API HTTP 503')
        return [{'id':x['id'],'text':f"translated {x['id']}"} for x in items]
    monkeypatch.setattr(translation_api,'complete',complete)
    flow=Workflows();payload={'project_id':p['id'],'allow_external':True}
    with pytest.raises(RuntimeError):flow.job_translate(payload,uuid4().hex,lambda *a:None,threading.Event())
    saved=storage.project(p['id']);saved['cues'][0]['text']='manual correction';storage.save_project(saved)
    result=flow.job_translate(payload,uuid4().hex,lambda *a:None,threading.Event())
    assert result['translated']==1 and result['skipped']==10 and batches[-1]==[11]
    saved=storage.project(p['id']);assert saved['cues'][0]['text']=='manual correction'
    assert [(c['start_ms'],c['end_ms']) for c in saved['cues']]==[(c['start_ms'],c['end_ms']) for c in p['cues']]
    flow.job_translate({**payload,'selected':[1],'force':True},uuid4().hex,lambda *a:None,threading.Event())
    assert batches[-1]==[1]


def test_timeout_does_not_duplicate_ambiguous_request(monkeypatch):
    monkeypatch.setattr(translation_api,'RETRIES',2)
    calls=[]
    def post(*a,**k):calls.append(1);raise requests.ReadTimeout('private-key')
    monkeypatch.setattr(requests.Session,'post',post)
    with pytest.raises(RuntimeError,match='quá thời gian chờ') as err:translation_api.complete(translation_api.GEMINI_URL,'gemini-3.8-flash','private-key',[])
    assert calls==[1] and 'private-key' not in str(err.value)
