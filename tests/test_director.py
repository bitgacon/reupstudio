import json,threading
from copy import deepcopy
from uuid import uuid4
import pytest
from reup import director,timeline,storage,translation_api


def doc():
    return timeline.Timeline(assets=['a'*32,'b'*32],tracks=[timeline.Track(id=uuid4().hex,name='Original',kind='text',locked=True,
        clips=[timeline.Clip(id=uuid4().hex,start_ms=0,duration_ms=2000,text='Private script')])]).model_dump()


def plan():
    return {'summary':'Test proposal','layers':[{'role':'background','asset':'a'*32,'offset_ms':0,'duration_ms':1000},
        {'role':'text','text':'Hello','offset_ms':200,'duration_ms':800,'box_color':'#00ff00','box_opacity':.7}]}


def items():return {'a'*32:{'name':'Public asset','kind':'image','duration_ms':0,'has_audio':False},'b'*32:{'name':'Private media','kind':'video','duration_ms':1000,'has_audio':True}}


def test_build_preserves_locked_clips_and_places_background_below():
    original=doc();snapshot=deepcopy(original);result=director.build(original,items(),plan(),1000,2000)
    assert result['timeline']['tracks'][1]==original['tracks'][0] and original==snapshot
    text=result['timeline']['tracks'][2]['clips'][0]
    assert text['start_ms']==1200 and text['box_color']=='#00ff00' and text['box_opacity']==.7


@pytest.mark.parametrize('layer',[
    {'role':'video','asset':'c'*32,'offset_ms':0,'duration_ms':500},
    {'role':'video','asset':'b'*32,'offset_ms':0,'duration_ms':1100},
    {'role':'music','asset':'a'*32,'offset_ms':0,'duration_ms':500},
    {'role':'text','text':'x','offset_ms':1900,'duration_ms':500},
    {'role':'text','text':'x','offset_ms':0,'duration_ms':500,'command':'evil'},
    {'role':'text','text':'x','offset_ms':True,'duration_ms':500},
    {'role':'text','text':'x','offset_ms':0,'duration_ms':500,'x':float('nan')},
    {'role':'text','asset':'a'*32,'text':'x','offset_ms':0,'duration_ms':500},
])
def test_reject_invalid_plan_atomically(layer):
    original=doc();snapshot=deepcopy(original)
    with pytest.raises(ValueError):director.build(original,items(),{'summary':'bad','layers':[layer]},0,2000)
    assert original==snapshot


def test_director_requires_opt_in_before_any_read_or_api():
    with pytest.raises(ValueError,match='cho phép'):director.proposal({},threading.Event(),lambda *a:None)


def test_prompt_only_selected_metadata_no_private_content(tmp_path,monkeypatch):
    monkeypatch.setattr(storage,'DATA',tmp_path);p=storage.new_project('Private project name',kind='edit')
    original=doc();storage.atomic_json(timeline.path(p['id']),original)
    monkeypatch.setattr(timeline,'describe',lambda p,key:items()[key]|{'file':'C:/private/source.mp4','url':'private-url'})
    seen=[]
    def model(*args):seen.extend(args[3]);return plan()
    monkeypatch.setattr(translation_api,'request_json',model)
    payload={'project_id':p['id'],'revision':original['revision'],'prompt':'Add a title','assets':['a'*32],
        'start_ms':0,'duration_ms':2000,'allow_external':True}
    result=director.proposal(payload,threading.Event(),lambda *a:None)
    sent=json.dumps(seen)
    for private in ('Private script','Private media','Private project name','private-url','C:/private', 'b'*32):assert private not in sent
    assert result['timeline']!=original and timeline.load(p['id'])==original
    payload['revision']=2
    with pytest.raises(ValueError,match='đổi'):director.proposal(payload,threading.Event(),lambda *a:None)


def test_generic_json_keeps_translation_schema_strict(monkeypatch):
    monkeypatch.setattr(translation_api,'request_json',lambda *a,**k:plan())
    with pytest.raises(ValueError,match='mảng'):translation_api.complete('https://example.test','model','key',[])
