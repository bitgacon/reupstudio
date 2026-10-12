import threading
from uuid import uuid4
import numpy as np
import pytest
from CTC_ALIGNMENT import align,word_rows
from REIDENTIFY_POLICY import ReidentifyPolicy
from reup import advanced_ai,composition,timeline,storage

def emission(labels,vocab=3):
    result=np.full((len(labels),vocab),-12,dtype=np.float32)
    result[np.arange(len(labels)),labels]=-.001
    return result

def test_ctc_real_path_repeated_letters_and_silence():
    rows=align(emission([0,1,1,0,1,0,2,0]),[1,1,2],0)
    assert [(r['start'],r['end']) for r in rows]==[(1,3),(4,5),(6,7)]
    words=word_rows(['aa','b'],[(0,2),(2,3)],rows,800,8)
    assert [(r['start'],r['end']) for r in words]==[(100,500),(600,700)]
    assert all(r['confidence']>.99 for r in words)

def test_ctc_never_omits_required_tokens():
    with pytest.raises(ValueError):align(emission([1,1]),[1,1],0)
    with pytest.raises(ValueError):align(np.array([[np.nan,1]]),[1],0)
    with pytest.raises(ValueError):align(emission([0,1]),[0],0)

def test_reidentify_requires_two_hits_and_margin_after_scene():
    p=ReidentifyPolicy();p.update(0,[.2,.2],1,1)
    p.update(200,[.8,.8],.95,.2,True)
    p.update(400,[.8,.8],.95,.2);p.update(600,[.81,.8],.95,.2)
    p.update(800,[.81,.8],.95,.01);p.update(1000,[.81,.8],.95,.2)
    p.update(1200,[.81,.8],.95,.2)
    r=p.result(1400)
    assert [(s['start'],s['end']) for s in r['segments']]==[(0,200),(600,800),(1200,1400)]
    assert r['reacquired_samples']==2
    assert not any(row['visible'] for row in r['rows'] if row['ms'] in (200,400,800,1000))

def doc():
    return timeline.Timeline(assets=['a'*32,'b'*32,'c'*32],tracks=[timeline.Track(id=uuid4().hex,name='Gốc',kind='video',locked=True,clips=[timeline.Clip(id=uuid4().hex,asset='a'*32,start_ms=0,duration_ms=3000)])]).model_dump()

def items():return {'a'*32:{'kind':'video','duration_ms':3000,'has_audio':True},'b'*32:{'kind':'image','duration_ms':0,'has_audio':False},'c'*32:{'kind':'audio','duration_ms':1000,'has_audio':True}}

def test_compose_preserves_locked_original_and_bounds_sources():
    original=doc();r=composition.build(original,items(),{'background':'b'*32,'overlay':'a'*32,'music':'c'*32,'duration_ms':5000,'title':'Xin chào'})
    assert r['timeline']['tracks'][1]==original['tracks'][0]
    assert r['timeline']['tracks'][0]['name']=='Phối · background'
    assert [t['clips'][0]['duration_ms'] for t in r['timeline']['tracks']]==[5000,3000,3000,1000,5000]
    assert len(original['tracks'])==1

@pytest.mark.parametrize('options',[{}, {'overlay':'d'*32},{'music':'b'*32},{'duration_ms':float('nan'),'title':'x'},{'duration_ms':60001,'title':'x'}])
def test_compose_rejects_bad(options):
    with pytest.raises(ValueError):composition.build(doc(),items(),options)

def test_ai_config_no_downloads_or_runtime_imports(tmp_path,monkeypatch):
    monkeypatch.setattr(storage,'DATA',tmp_path)
    assert advanced_ai.config()['alignment_model']==''
    assert list(tmp_path.iterdir())==[]
    saved=advanced_ai.config({'alignment_language':'vie','alignment_romanize':False})
    assert not saved['alignment_romanize']
    assert advanced_ai.config()==saved
    with pytest.raises(ValueError):advanced_ai.config({'alignment_model':'remote/model'})
    with pytest.raises(ValueError):advanced_ai.config({'alignment_romanize':'true'})

def test_install_model_requires_license_before_any_setup(tmp_path):
    with pytest.raises(ValueError,match='phi thương mại'):
        advanced_ai.install_alignment({},tmp_path,tmp_path/'log',threading.Event(),lambda *x:None)
    assert list(tmp_path.iterdir())==[]

def test_avatar_requires_consent_before_source_access(tmp_path):
    with pytest.raises(ValueError,match='quyền'):
        advanced_ai.avatar({},tmp_path,threading.Event(),lambda *x:None)

def test_cancel_worker_before_launch(tmp_path):
    event=threading.Event();event.set()
    with pytest.raises(InterruptedError):advanced_ai.execute(['does-not-exist'],tmp_path,tmp_path,event,lambda *x:None,'QA')
    assert list(tmp_path.iterdir())==[]

def test_compose_real_ffmpeg_layer_order(tmp_path,monkeypatch):
    from PIL import Image
    from reup import media
    monkeypatch.setattr(storage,'DATA',tmp_path/'data');storage.DATA.mkdir()
    project=storage.new_project('QA composition');assets=[]
    for name,color in [('original','red'),('background','blue'),('overlay','lime')]:
        key=uuid4().hex;folder=storage.DATA/'uploads'/key;folder.mkdir(parents=True)
        Image.new('RGB',(160,90),color).save(folder/'source.png')
        storage.atomic_json(folder/'asset.json',{'id':key,'name':name,'file':'source.png'});assets.append(key)
    original=timeline.Timeline(width=160,height=90,assets=assets,tracks=[timeline.Track(id=uuid4().hex,name='Original',kind='video',locked=True,clips=[timeline.Clip(id=uuid4().hex,asset=assets[0],start_ms=0,duration_ms=1000,scale=.2,volume=0)])]).model_dump()
    r=composition.build(original,{key:timeline.describe(project,key) for key in assets},{'background':assets[1],'overlay':assets[2],'duration_ms':1000})
    output=tmp_path/'composed.mp4';timeline.render(project,r['timeline'],output,threading.Event(),lambda *a:None)
    frame=tmp_path/'frame.png';media.command([media.binary(),'-y','-v','error','-ss','0.5','-i',str(output),'-frames:v','1',str(frame)])
    with Image.open(frame) as image:
        background=image.getpixel((10,80));foreground=image.getpixel((80,45));overlay=image.getpixel((128,22))
    assert background[2]>200 and background[0]<30
    assert foreground[0]>200 and foreground[2]<30
    assert overlay[1]>180 and overlay[2]<80
