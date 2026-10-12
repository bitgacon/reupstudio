import threading
from types import SimpleNamespace as NS
from uuid import uuid4
import pytest
from reup import word_timing,timeline,captions,storage,studio_tools,vision

def clip(**kw):return timeline.Clip(id=uuid4().hex,start_ms=0,duration_ms=2000,text='Xin chào',word_cues=[{'word':'Xin','start':300,'end':600},{'word':'chào','start':1000,'end':1400}],**kw)

def test_track_boundary_accepts_21_and_64_rejects_65():
    tracks=[timeline.Track(id=uuid4().hex,name='QA layer',kind='text',clips=[]) for _ in range(65)]
    assert len(timeline.Timeline(tracks=tracks[:21]).tracks)==21
    assert len(timeline.Timeline(tracks=tracks[:64]).tracks)==64
    with pytest.raises(ValueError):timeline.Timeline(tracks=tracks)

def test_word_schema_persists_and_requires_text_track():
    c=clip();assert timeline.Clip.model_validate(c.model_dump())==c
    with pytest.raises(ValueError):timeline.Timeline(tracks=[timeline.Track(id=uuid4().hex,name='Blur',kind='blur',clips=[c])])

@pytest.mark.parametrize('changes',[
    {'text':'Chào bạn'},
    {'word_cues':[{'word':'Xin chào','start':0,'end':100}]},
    {'word_cues':[{'word':'Xin','start':300,'end':700},{'word':'chào','start':500,'end':1000}]},
    {'word_cues':[{'word':'Xin','start':300,'end':700},{'word':'chào','start':1000,'end':2001}]},
    {'word_cues':[{'word':'Xin','start':300,'end':300},{'word':'chào','start':1000,'end':1500}]},
])
def test_word_schema_bad(changes):
    data=clip().model_dump();data.update(changes)
    with pytest.raises(ValueError):timeline.Clip.model_validate(data)

def test_normalize_cjk_spaces_overlap_and_silence():
    segments=[NS(words=[NS(word=' Xin chào',start=.3,end=.6),NS(word=' bạn',start=.59,end=.8),NS(word='你好',start=1,end=1.4)])]
    rows=word_timing.normalize_words(segments,2000)
    assert rows==[{'word':'Xin','start':300,'end':450},{'word':'chào','start':450,'end':600},{'word':'bạn','start':600,'end':800},{'word':'你好','start':1000,'end':1400}]
    with pytest.raises(ValueError):word_timing.normalize_words([NS(words=[])],2000)

@pytest.mark.parametrize('mode',['karaoke','typewriter'])
def test_ass_uses_onsets_keeps_silence_and_holds_last_word(mode):
    c=clip(text_animation=mode).model_dump()
    body='Dialogue: 0,0:00:00.00,0:00:02.00,Default,,0,0,0,,{\\pos(10,20)}Xin chào\n'
    out=captions.animate_ass(body,c)
    assert '0:00:00.30' in out and '0:00:01.00' in out and '0:00:02.00' in out
    if mode=='typewriter':assert out.splitlines()[0].split(',')[1]=='0:00:00.30'
    else:assert '{\\c&H00FFFF&}Xin' in out.splitlines()[0] and '{\\c&Hffffff&}Xin' in out.splitlines()[1]

def test_proposal_rejects_curve_and_cancel_before_extraction(tmp_path,monkeypatch):
    c={'speed_curve':[1],'duration_ms':1000};monkeypatch.setattr(studio_tools,'selected',lambda p:({}, {}, {}, c, tmp_path/'source',{'has_audio':True}))
    with pytest.raises(ValueError,match='5 phút'):word_timing.proposal({},tmp_path,threading.Event(),lambda *a:None)
    c['speed_curve']=[];event=threading.Event();event.set()
    with pytest.raises(InterruptedError):word_timing.proposal({},tmp_path,event,lambda *a:None)

@pytest.mark.parametrize('rate',[.5,1.25,2])
def test_extract_bounds_source_and_output_duration_real(tmp_path,monkeypatch,rate):
    from reup import media
    source=tmp_path/'long.wav';media.command([media.binary(),'-y','-v','error','-f','lavfi','-i','sine=f=440:d=5',str(source)])
    c={'speed_curve':[],'duration_ms':1200,'speed':rate,'in_ms':300}
    monkeypatch.setattr(studio_tools,'selected',lambda p:({}, {}, {}, c,source,{'has_audio':True}))
    # Real extraction, terminate before expensive worker startup.
    run=timeline.run_cancel
    def extract(args,*a,**kw):run(args,*a,**kw);raise InterruptedError('extraction tested')
    monkeypatch.setattr(timeline,'run_cancel',extract)
    with pytest.raises(InterruptedError):word_timing.proposal({},tmp_path/'result',threading.Event(),lambda *a:None)
    duration=float(media.probe(tmp_path/'result'/'words.wav')['format']['duration'])
    assert abs(duration-1.2)<.08

def test_word_event_fade_does_not_restart():
    c=clip(text_animation='karaoke',fade_in_ms=500,fade_out_ms=500,opacity=.8).model_dump()
    out=captions.animate_ass('Dialogue: 0,0:00:00.00,0:00:02.00,Default,,0,0,0,,{\\fad(500,500)\\alpha&H33&\\pos(10,20)}Xin chào\n',c)
    assert '\\fad(' not in out and '0:00:00.50' in out and '0:00:01.50' in out
    assert '\\alpha&HFF&' in out and '\\alpha&H33&' in out

def test_tracking_sample_includes_trimmed_source_in(tmp_path,monkeypatch):
    c=timeline.Clip(id=uuid4().hex,asset=uuid4().hex,start_ms=2000,in_ms=500,duration_ms=1000).model_dump();calls=[]
    monkeypatch.setattr(vision,'clip_request',lambda p:({'id':'x'},{'revision':1,'width':160,'height':90},c,tmp_path/'source',{'kind':'video','width':160,'height':90}))
    def run(request,*args):
        calls.append(request);return {'rows':[{'ms':s['ms'],'center':[.5,.5]} for s in request['samples']]}
    monkeypatch.setattr(vision,'run',run)
    vision.object_tracking({'at_ms':2200,'region':{'x':50,'y':50,'region_w':10,'region_h':10}},tmp_path,threading.Event(),lambda *a:None)
    assert calls[0]['samples'][0]['source_ms']==700

def test_comic_seek_includes_source_in(tmp_path,monkeypatch):
    from PIL import Image
    c=timeline.Clip(id=uuid4().hex,start_ms=2000,in_ms=700,duration_ms=1000).model_dump();calls=[]
    monkeypatch.setattr(studio_tools,'selected',lambda p:({}, {}, {'kind':'video'}, c,tmp_path/'source',{'kind':'video'}))
    def run(args,*a,**kw):calls.append(args);Image.new('RGB',(64,64),'blue').save(tmp_path/'frame.png')
    monkeypatch.setattr(timeline,'run_cancel',run);monkeypatch.setattr(studio_tools,'register',lambda *a:{'id':'qa'})
    studio_tools.comic({'at_ms':2300},tmp_path,threading.Event(),lambda *a:None)
    assert calls[0][calls[0].index('-ss')+1]=='1.0'

@pytest.mark.parametrize('mode',['karaoke','typewriter'])
def test_timed_text_real_render(tmp_path,monkeypatch,mode):
    monkeypatch.setattr(storage,'DATA',tmp_path/'data');storage.DATA.mkdir();p=storage.new_project('Words QA');c=clip(text_animation=mode,font_size=20)
    doc=timeline.Timeline(width=320,height=180,tracks=[timeline.Track(id=uuid4().hex,name='Words',kind='text',clips=[c])]).model_dump();doc=timeline.save(p['id'],doc)
    out=tmp_path/'timed.mp4';timeline.render(p,doc,out,threading.Event(),lambda *a:None)
    assert out.stat().st_size>1000 and timeline.load(p['id'])['tracks'][0]['clips'][0]['word_cues']==c.model_dump()['word_cues']
