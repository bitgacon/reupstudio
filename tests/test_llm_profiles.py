from copy import deepcopy
import pytest
from fastapi.testclient import TestClient
from reup import storage,llm_profiles,subtitle_qc
from reup.server import make_app

@pytest.fixture(autouse=True)
def isolated(tmp_path,monkeypatch):monkeypatch.setattr(storage,'DATA',tmp_path)

def profile(**extra):return {'name':'Gemini A','provider':'gemini','url':'https://aistudio.google.com','model':'Gemini 3.8 Flash','key':'secret-one',**extra}

def test_profiles_private_save_activate_delete():
    first=llm_profiles.save(profile());pid=first['profiles'][0]['id']
    assert 'secret-one' not in str(first) and first['profiles'][0]['has_key']
    llm_profiles.save(profile(name='Gemini B',key='secret-two',batch_size=5,pause_seconds=4))
    assert len(llm_profiles.public()['profiles'])==2
    llm_profiles.activate(pid);assert storage.settings()['translation_key']=='secret-one'
    row=llm_profiles.public()['profiles'][0];row.pop('has_key');llm_profiles.save(row)
    assert llm_profiles.read()['profiles'][-1]['key']=='secret-one'
    llm_profiles.delete(pid);assert storage.settings()['translation_key']=='secret-one'
    assert not llm_profiles.public()['active']

def test_no_cross_provider_key_reuse():
    storage.save_settings({'translation_url':'https://aistudio.google.com','translation_model':'gemini-3.8-flash','translation_key':'gemini-secret'})
    with pytest.raises(ValueError):llm_profiles.save({'name':'Other','provider':'openai','url':'https://api.openai.com/v1','model':'test','use_current_key':True})
    public=llm_profiles.save({'name':'Saved current','provider':'gemini','url':storage.settings()['translation_url'],'model':'gemini-3.8-flash','use_current_key':True})
    row=public['profiles'][0];row.pop('has_key');row.update(url='https://api.openai.com/v1',provider='openai')
    with pytest.raises(ValueError):llm_profiles.save(row)

@pytest.mark.parametrize('extra',[{'batch_size':0},{'batch_size':21},{'pause_seconds':float('nan')},{'pause_seconds':61},{'model':''},{'url':'https://user:pass@example.com'},{'url':'https://example.com?key=secret'}])
def test_profile_validation(extra):
    with pytest.raises(ValueError):llm_profiles.save(profile(**extra))

def test_api_csrf_busy_and_secret_redaction():
    app=make_app()
    with TestClient(app) as c:
        c.get('/');h={'X-Reup-Token':c.get('/api/state').json()['csrf']}
        assert c.post('/api/llm-profiles/save',json=profile()).status_code==403
        response=c.post('/api/llm-profiles/save',json=profile(),headers=h)
        assert response.status_code==200 and 'secret-one' not in response.text
        pid=response.json()['profiles'][0]['id']
        app.state.queue.rows['busy']={'id':'busy','status':'running','created':1}
        assert c.post('/api/llm-profiles/activate',json={'id':pid},headers=h).status_code==409
        app.state.queue.rows.clear()
        assert c.post('/api/llm-profiles/activate',json={'id':pid},headers=h).status_code==200
        assert 'secret-one' not in c.get('/api/state').text

def test_subtitle_review_read_only_sparse_ids():
    p=storage.new_project('Review',edit={'target_language':'en'})
    p['cues']=[{'id':9,'start_ms':0,'end_ms':500,'source_text':'original','text':'你好 '+('nội dung '*25),'rate':1},{'id':20,'start_ms':400,'end_ms':1000,'text':'','source_text':''}]
    before=deepcopy(p);result=subtitle_qc.review(p)
    assert p==before and result['cues']==2
    assert {r['cue'] for r in result['issues']}=={9,20}
    assert any('ký tự Trung' in r['message'] for r in result['issues'])
    assert any('ước tính' in r['message'] for r in result['issues'])

def test_actual_speed_includes_user_rate_and_ignores_stale_audio():
    p=storage.new_project('Speed')
    cue={'id':1,'start_ms':0,'end_ms':5000,'text':'Xin chào','rate':1,'generated_rate':1.2,'speed_factor':1.2,'audio':'fit.wav','status':'complete'}
    p['cues']=[cue]
    assert any('1.44×' in r['message'] for r in subtitle_qc.review(p)['issues'])
    cue['status']='pending'
    assert not any('Audio thực tế' in r['message'] for r in subtitle_qc.review(p)['issues'])

def test_pre_audio_estimate_warns_and_respects_reading_rules():
    c={'id':1,'text':'SGK','rate':1,'start_ms':0,'end_ms':500}
    rules={'rules':[{'source':'SGK','spoken':'Sách giáo khoa','whole_word':True,'case_sensitive':False,'enabled':True}]}
    e=subtitle_qc.estimate_cue(c)
    assert not e['warning']
    expanded=subtitle_qc.estimate_cue(c,__import__('reup.reading',fromlist=['config']).config(rules))
    assert expanded['words']==3 and expanded['speed']>1.3 and expanded['warning']
    c['text']='Xin [2] chào';c['rate']=2
    e=subtitle_qc.estimate_cue(c)
    assert e['seconds']>1 and e['speed']>4
    c['end_ms']=0
    assert subtitle_qc.estimate_cue(c)['speed'] is None
