import threading,json,sys,wave
from pathlib import Path
from uuid import uuid4
from types import SimpleNamespace
import pytest,numpy as np
from fastapi.testclient import TestClient
from pydantic import ValidationError
from pydub import AudioSegment
from reup import storage,tts_providers as tts,reading,libraries,media
from reup.workflows import Workflows,cue_key,fingerprint
from reup.server import make_app
import TTS_PROVIDER_WORKER as worker

def opt(provider='kokoro',**kwargs):
    return tts.options({'provider':provider,'language':'en-us' if provider=='kokoro' else 'en','voice':'af_sarah' if provider=='kokoro' else 'default',**kwargs})

@pytest.mark.parametrize('value',[{'provider':'kokoro','language':'vi'},{'provider':'kokoro','language':'en-us','emotion':'sad'},{'provider':'chatterbox','language':'en','emotion':'happy'},{'provider':'qwen','language':'vi'},{'provider':'elevenlabs','language':'en','model':'eleven_multilingual_v2','emotion':'sad'},{'provider':'kokoro','language':'en-us','api_key':'secret'},{'provider':'chatterbox','language':'en','reference_asset':'a'*32}])
def test_invalid_capabilities(value):
    with pytest.raises(ValidationError):tts.options(value)

def test_legacy_fingerprint_unchanged_and_emotions_invalidate():
    cue={'text':'Hello','voice':'','start_ms':0,'end_ms':1000,'rate':1};p={'voice':'demo'}
    expected=fingerprint({'text':'Hello','voice':'demo','start_ms':0,'end_ms':1000,'rate':1,'precision':'fp32','fit':1})
    assert cue_key(cue,p,'fp32')==expected
    assert cue_key({**cue,'tts':None},{**p,'tts':None},'fp32')==expected
    p['tts']=opt('qwen',voice='ryan');a=cue_key(cue,p,'fp32')
    p['tts']['emotion']='sad';assert cue_key(cue,p,'fp32')!=a
    assert cue_key({**cue,'tts':tts.options()},p,'fp32')==expected

def test_catalog_and_secret_safe_api(tmp_path,monkeypatch):
    monkeypatch.setattr(storage,'DATA',tmp_path)
    monkeypatch.setattr(tts.requests.Session,'get',lambda *a,**k:pytest.fail('GET catalog must not access internet'))
    with TestClient(make_app()) as client:
        client.get('/');client.headers['X-Reup-Token']=client.get('/api/state').json()['csrf']
        response=client.post('/api/tts-providers/config',json={'elevenlabs_key':'private-secret','device':'cpu'})
        assert response.status_code==200 and 'private-secret' not in response.text
        catalog=client.get('/api/tts-providers').json()
        assert catalog['has_elevenlabs_key'] and len(catalog['catalog'])==5
        assert not any(r['installed'] for r in catalog['catalog'] if r['id'] not in {'vieneu','elevenlabs'})
        assert len(client.get('/api/libraries').json()['catalog'])>=8
        assert client.post('/api/tts-providers/config',json={'device':'automatic'}).status_code==400

def test_project_options_persist_legacy_client_preserves_and_inherits(tmp_path,monkeypatch):
    monkeypatch.setattr(storage,'DATA',tmp_path)
    p=storage.new_project('tts test');p['cues']=[{'id':1,'start_ms':0,'end_ms':1000,'text':'Hello','source_text':'Hello','voice':'','rate':1,'status':'complete'}];storage.save_project(p)
    with TestClient(make_app()) as client:
        client.get('/');client.headers['X-Reup-Token']=client.get('/api/state').json()['csrf']
        body={'revision':p['revision'],'name':p['name'],'voice':p['voice'],'video':'','cues':p['cues'],'tts':opt('qwen',voice='ryan')}
        r=client.post('/api/projects/'+p['id'],json=body);assert r.status_code==200,r.text
        saved=r.json();assert saved['tts']['provider']=='qwen' and saved['cues'][0]['status']=='pending'
        body['revision']=saved['revision'];body.pop('tts');body['cues'][0]['tts']=opt('chatterbox',emotion='expressive')
        saved=client.post('/api/projects/'+p['id'],json=body).json();assert saved['tts']['provider']=='qwen' and saved['cues'][0]['tts']['emotion']=='expressive'
        body['revision']=saved['revision'];body['cues'][0].pop('tts')
        saved=client.post('/api/projects/'+p['id'],json=body).json();assert saved['cues'][0]['tts']['provider']=='chatterbox'
        body['revision']=saved['revision'];body['cues'][0]['tts']=None
        saved=client.post('/api/projects/'+p['id'],json=body).json();assert tts.effective(saved['cues'][0],saved)['provider']=='qwen'

def test_real_ffmpeg_sequence_with_mock_provider_keeps_srt(tmp_path,monkeypatch):
    monkeypatch.setattr(storage,'DATA',tmp_path);flow=Workflows();calls=[]
    monkeypatch.setattr(flow,'prepare',lambda *a:pytest.fail('Must not load VieNeu for Kokoro'))
    def speak(text,voice,out,opt,event,progress,*args):
        calls.append((text,opt['provider']));AudioSegment.silent(300,frame_rate=48000).export(out,format='wav')
    monkeypatch.setattr(flow,'provider_speak',speak)
    storage.reading_settings(reading.config({'pauses':{'enabled':True,'period':.5},'rules':[{'source':'SGK','spoken':'Sách giáo khoa'}]}))
    result=flow('tts',{'text':'SGK. Hello','tts':opt()},uuid4().hex,lambda *a:None,threading.Event())
    assert calls==[('Sách giáo khoa.','kokoro'),('Hello','kokoro')]
    assert result['duration_ms']>=1000 and [r['type'] for r in result['files']]==['wav','mp3','srt']
    subtitle=list(tmp_path.rglob('subtitle.srt'))[0].read_text(encoding='utf-8-sig');assert 'SGK.' in subtitle and 'Sách giáo khoa' not in subtitle

def test_speaker_cleanup_on_failure(monkeypatch):
    flow=Workflows();closed=[];flow.speakers['test']=SimpleNamespace(close=lambda:closed.append(True))
    monkeypatch.setattr(flow,'job_tts',lambda *a:(_ for _ in ()).throw(ValueError('failed')))
    with pytest.raises(ValueError):flow('tts',{},uuid4().hex,lambda *a:None,threading.Event())
    assert closed==[True] and not flow.speakers

def test_cloud_requires_consent_and_no_retry_on_429(tmp_path,monkeypatch):
    monkeypatch.setattr(storage,'DATA',tmp_path);tts.config({'elevenlabs_key':'secret'})
    calls=[]
    class Session:
        def __enter__(self):return self
        def __exit__(self,*a):pass
        def post(self,*args,**kwargs):
            calls.append(kwargs);return Response()
    class Response:
        status_code=429
        def __enter__(self):return self
        def __exit__(self,*a):pass
    monkeypatch.setattr(tts.requests,'Session',Session)
    speaker=tts.Speaker(opt('elevenlabs',voice='demo'),tmp_path,threading.Event(),lambda *a:None)
    with pytest.raises(ValueError,match='Chưa cho phép'):speaker.speak('hello','demo',tmp_path/'test.wav')
    assert calls==[]
    speaker.opt['cloud_consent']=True
    with pytest.raises(ValueError,match='429'):speaker.speak('hello','demo',tmp_path/'test.wav')
    assert len(calls)==1 and calls[0]['headers']['xi-api-key']=='secret'
    assert not (tmp_path/'test.download.mp3').exists()

@pytest.mark.parametrize('provider',['kokoro','chatterbox','qwen'])
def test_worker_contract_audio_not_mock_pitch(provider,tmp_path,monkeypatch):
    def pcm_write(path,audio,sr,**kwargs):
        with wave.open(str(path),'wb') as f:
            f.setnchannels(1);f.setsampwidth(2);f.setframerate(sr);f.writeframes((audio*32767).astype(np.int16).tobytes())
    monkeypatch.setitem(sys.modules,'soundfile',SimpleNamespace(write=pcm_write))
    captured={}
    class Tensor:
        def detach(self):return self
        def cpu(self):return self
        def numpy(self):return np.zeros(2400)
    class Engine:
        sr=24000
        def create(self,text,**kwargs):captured.update(kwargs);return np.zeros(2400),24000
        def generate(self,text,**kwargs):captured.update(kwargs);return Tensor()
        def generate_custom_voice(self,**kwargs):captured.update(kwargs);return [np.zeros(2400)],24000
    choices=opt(provider,voice='ryan' if provider=='qwen' else 'af_sarah' if provider=='kokoro' else 'default',emotion='sad' if provider=='qwen' else 'expressive' if provider=='chatterbox' else 'neutral',intensity=.9)
    path=tmp_path/'test.wav';worker.speak(Engine(),{'provider':provider},{'options':choices,'voice':choices['voice'],'text':'Hello','output':str(path)})
    assert path.stat().st_size>44
    if provider=='kokoro':assert captured['speed']==1 and captured['lang']=='en-us'
    if provider=='chatterbox':assert captured['exaggeration']==.95
    if provider=='qwen':assert 'sadly' in captured['instruct'] and captured['speaker']=='ryan'

def test_missing_runtime_never_installs(tmp_path,monkeypatch):
    monkeypatch.setattr(storage,'DATA',tmp_path)
    monkeypatch.setattr(libraries,'install',lambda *a:pytest.fail('Automatic install forbidden'))
    speaker=tts.Speaker(opt(),tmp_path,threading.Event(),lambda *a:None)
    with pytest.raises(ValueError,match='Chưa cài'):speaker.speak('Hello','af_sarah',tmp_path/'out.wav')

def test_actual_voice_manifest_not_static_qwen(tmp_path,monkeypatch):
    monkeypatch.setattr(storage,'DATA',tmp_path);home=tmp_path/'qwen';home.mkdir();python=home/'python.exe';python.touch()
    storage.atomic_json(home/'voices.json',[{'id':'real_voice','name':'real','language':''}]);storage.atomic_json(tmp_path/'library-index.json',{'tts-qwen':{'path':str(home),'python':str(python)}})
    row=next(r for r in tts.public()['catalog'] if r['id']=='qwen');assert row['voices'][0]['id']=='real_voice'

def test_pinned_chatterbox_v2_local_load_has_no_hub_lookup(tmp_path,monkeypatch):
    model=tmp_path/'model';model.mkdir()
    for name in ['ve.pt','s3gen.pt','t3_mtl23ls_v2.safetensors','grapheme_mtl_merged_expanded_v1.json','conds.pt','Cangjie5_TC.json']:(model/name).touch()
    monkeypatch.setitem(sys.modules,'torch',SimpleNamespace(set_num_threads=lambda n:None))
    tokenizers=SimpleNamespace(hf_hub_download=lambda *a,**k:pytest.fail('Unexpected hub access'))
    monkeypatch.setitem(sys.modules,'chatterbox.models.tokenizers',SimpleNamespace(tokenizer=tokenizers))
    calls=[]
    monkeypatch.setitem(sys.modules,'chatterbox.mtl_tts',SimpleNamespace(ChatterboxMultilingualTTS=SimpleNamespace(from_local=lambda *a,**k:calls.append((a,k)) or 'engine')))
    assert worker.load({'provider':'chatterbox','path':str(tmp_path),'device':'cpu'})=='engine'
    assert calls==[((model,'cpu'),{})]  # exact pinned wheel signature, no unsupported V3 parameter
    assert tokenizers.hf_hub_download('ResembleAI/chatterbox','Cangjie5_TC.json')==str(model/'Cangjie5_TC.json')
    with pytest.raises(ValueError):tokenizers.hf_hub_download('other','missing')

def test_cloud_audio_stream_preserves_original_and_cancellation(tmp_path,monkeypatch):
    monkeypatch.setattr(storage,'DATA',tmp_path);tts.config({'elevenlabs_key':'secret'})
    event=threading.Event();calls=[]
    class Response:
        status_code=200;headers={'Content-Type':'audio/mpeg'}
        def __enter__(self):return self
        def __exit__(self,*a):pass
        def iter_content(self,size):yield b'FAKE_AUDIO'
    class Session:
        def __enter__(self):return self
        def __exit__(self,*a):pass
        def post(self,*a,**k):calls.append(k);return Response()
    monkeypatch.setattr(tts.requests,'Session',Session)
    monkeypatch.setattr(media,'transcode',lambda source,target:target.write_bytes(source.read_bytes()))
    speaker=tts.Speaker(opt('elevenlabs',voice='demo',cloud_consent=True,emotion='sad'),tmp_path,event,lambda *a:None)
    out=tmp_path/'out.wav';speaker.speak('Original words','demo',out)
    assert out.read_bytes()==b'FAKE_AUDIO' and calls[0]['json']['text']=='[sad] Original words'
    assert calls[0]['json']['model_id']=='eleven_v3' and not (tmp_path/'out.download.mp3').exists()
    Response.headers={'Content-Type':'application/json'}
    with pytest.raises(ValueError,match='audio hợp lệ'):speaker.speak('hello','demo',out)
    assert len(calls)==2
    Response.headers={'Content-Type':'audio/mpeg'}
    def cancelled_post(*a,**k):event.set();return Response()
    Session.post=cancelled_post
    with pytest.raises(InterruptedError):speaker.speak('hello','demo',out)
    assert not (tmp_path/'out.download.mp3').exists()

def test_runtime_start_is_offline_and_owned_cancel(tmp_path,monkeypatch):
    monkeypatch.setattr(storage,'DATA',tmp_path);python=tmp_path/'python.exe';python.touch()
    monkeypatch.setattr(libraries,'registry',lambda:{'tts-kokoro':{'path':str(tmp_path),'python':str(python)}})
    event=threading.Event();captured={};stopped=[]
    class Stdin:
        def write(self,line):captured['command']=json.loads(line)
        def flush(self):event.set()
    process=SimpleNamespace(stdin=Stdin(),poll=lambda:None)
    monkeypatch.setattr(tts.subprocess,'Popen',lambda args,**kwargs:captured.update(args=args,kwargs=kwargs) or process)
    monkeypatch.setattr(media,'stop_owned_process',lambda p:stopped.append(p))
    speaker=tts.Speaker(opt(),tmp_path/'worker',event,lambda *a:None)
    try:
        with pytest.raises(InterruptedError):speaker.speak('Hello','af_sarah',tmp_path/'out.wav')
    finally:speaker.close()
    env=captured['kwargs']['env'];assert env['HF_HUB_OFFLINE']==env['TRANSFORMERS_OFFLINE']=='1'
    assert captured['args'][2]=='serve' and stopped==[process]
    assert 'secret' not in json.dumps(captured['command'])

def test_tts_installer_keeps_previous_registry_on_failure(tmp_path,monkeypatch):
    monkeypatch.setattr(storage,'DATA',tmp_path);root=tmp_path/'libraries';root.mkdir();libraries.config({'root':str(root)})
    previous={'tts-kokoro':{'path':str(root/'previous'),'python':'previous-python'}};storage.atomic_json(tmp_path/'library-index.json',previous)
    from reup import tts_install
    def failed(key,folder,*args):
        assert folder!=root/'previous';raise ValueError('offline check failed')
    monkeypatch.setattr(tts_install,'install',failed)
    with pytest.raises(ValueError):libraries.install({'library':'tts-kokoro'},uuid4().hex,lambda *a:None,threading.Event())
    assert libraries.registry()==previous
