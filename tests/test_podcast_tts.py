import threading
from uuid import uuid4
from pathlib import Path
from pydub import AudioSegment
import pytest
from fastapi.testclient import TestClient
from reup import storage,tts_providers as tts,libraries
from reup.workflows import Workflows
from reup.server import make_app

def options(provider='kokoro',**kwargs):
    return tts.options({'provider':provider,'language':'en-us' if provider=='kokoro' else 'en','voice':'af_sarah' if provider=='kokoro' else 'ryan',**kwargs})

def register(tmp_path,monkeypatch):
    monkeypatch.setattr(storage,'DATA',tmp_path);python=tmp_path/'python.exe';python.touch()
    monkeypatch.setattr(libraries,'registry',lambda:{'tts-'+p:{'path':str(tmp_path),'python':str(python)} for p in ['kokoro','qwen','chatterbox']})

def test_multilingual_turns_real_ffmpeg_uses_distinct_voices_and_preserves_text(tmp_path,monkeypatch):
    register(tmp_path,monkeypatch);flow=Workflows();calls=[]
    monkeypatch.setattr(flow,'prepare',lambda *a:pytest.fail('Should not load VieNeu for external-only podcast'))
    def speak(text,voice,out,opt,event,progress,*args):
        calls.append((text,voice,opt['provider'],opt['language'],opt['emotion']))
        AudioSegment.silent(300,frame_rate=48000).export(out,format='wav')
    monkeypatch.setattr(flow,'provider_speak',speak)
    script='[Alice]: Hello.\n[Ryan]: Bonjour.\n[Alice]: Welcome back.'
    result=flow('podcast',{'text':script,'speakers':{},'speaker_tts':{'Alice':options(),'Ryan':options('qwen',language='fr',emotion='happy')},'pause':.4},uuid4().hex,lambda *a:None,threading.Event())
    assert calls==[('Hello.','af_sarah','kokoro','en-us','neutral'),('Bonjour.','ryan','qwen','fr','happy'),('Welcome back.','af_sarah','kokoro','en-us','neutral')]
    srt=next(tmp_path.rglob('subtitle.srt')).read_text(encoding='utf-8-sig')
    assert 'Hello.' in srt and 'Bonjour.' in srt and 'Welcome back.' in srt and '[happy]' not in srt
    assert result['duration_ms']>=1500 and [f['type'] for f in result['files']]==['wav','mp3','srt']
    assert not flow.speakers

def test_legacy_podcast_mapping_and_mixed_vieneu_default(tmp_path,monkeypatch):
    register(tmp_path,monkeypatch);flow=Workflows();prepared=[];calls=[]
    monkeypatch.setattr(flow,'prepare',lambda *a:prepared.append(True))
    def speak(text,voice,out,opt,event,progress,*args):
        calls.append((voice,opt['provider']));AudioSegment.silent(200,frame_rate=48000).export(out,format='wav')
    monkeypatch.setattr(flow,'provider_speak',speak)
    flow('podcast',{'text':'[Việt]: Xin chào\n[English]: Hello','speakers':{'Việt':'voice-old'},'speaker_tts':{'English':options()}},uuid4().hex,lambda *a:None,threading.Event())
    assert prepared==[True] and calls==[('voice-old','vieneu'),('af_sarah','kokoro')]

@pytest.mark.parametrize('kind',['consent','runtime','voice'])
def test_preflight_all_speakers_before_any_generation(tmp_path,monkeypatch,kind):
    register(tmp_path,monkeypatch);flow=Workflows()
    monkeypatch.setattr(flow,'prepare',lambda *a:pytest.fail('Must fail before engine load'))
    monkeypatch.setattr(flow,'provider_speak',lambda *a:pytest.fail('Must fail before creating audio'))
    second=options('elevenlabs',voice='remote') if kind=='consent' else options('qwen',voice='' if kind=='voice' else 'ryan')
    if kind=='runtime':monkeypatch.setattr(libraries,'registry',lambda:{})
    with pytest.raises(ValueError):flow('podcast',{'text':'[A]: Xin chào\n[B]: Hello','speakers':{'A':'old','B':'old'},'speaker_tts':{'B':second}},uuid4().hex,lambda *a:None,threading.Event())
    assert not list(tmp_path.rglob('audio.wav'))

def test_api_rejects_invalid_provider_and_keys_before_queue(tmp_path,monkeypatch):
    monkeypatch.setattr(storage,'DATA',tmp_path)
    with TestClient(make_app()) as client:
        client.get('/');client.headers['X-Reup-Token']=client.get('/api/state').json()['csrf']
        for row in [{'provider':'kokoro','language':'vi'},{'provider':'qwen','language':'en','api_key':'secret'}]:
            response=client.post('/api/jobs',json={'kind':'podcast','payload':{'text':'[A]: hello','speaker_tts':{'A':row}}})
            assert response.status_code in {400,422},response.text
        assert not client.get('/api/state').json()['jobs']

def test_pool_reuses_provider_worker_between_voices_and_closes_at_end(tmp_path,monkeypatch):
    register(tmp_path,monkeypatch);created=[];closed=[]
    class Speaker:
        def __init__(self,opt,folder,event,progress):created.append(opt['provider']);self.opt=opt
        def speak(self,text,voice,out):AudioSegment.silent(200,frame_rate=48000).export(out,format='wav')
        def close(self):closed.append(self.opt['provider'])
    monkeypatch.setattr(tts,'Speaker',Speaker);flow=Workflows()
    flow('podcast',{'text':'[A]: Hello\n[B]: Hi\n[A]: Bye','speaker_tts':{'A':options(),'B':options(voice='am_adam')},'speakers':{}},uuid4().hex,lambda *a:None,threading.Event())
    assert created==['kokoro'] and closed==['kokoro']
