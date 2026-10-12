import threading
from uuid import uuid4
import pytest
from reup import storage,timeline,reframe,vision,media

@pytest.fixture
def fixture(tmp_path,monkeypatch):
    monkeypatch.setattr(storage,'DATA',tmp_path/'data')
    project=storage.new_project('Reframe QA');key=uuid4().hex;folder=storage.DATA/'uploads'/key;folder.mkdir(parents=True)
    media.command([media.binary(),'-y','-v','error','-f','lavfi','-i','color=blue:s=160x90:r=25:d=1','-c:v','libx264',str(folder/'source.mp4')])
    storage.atomic_json(folder/'asset.json',{'id':key,'file':'source.mp4','name':'Synthetic'})
    clip=timeline.Clip(id=uuid4().hex,asset=key,start_ms=500,duration_ms=1000,in_ms=0).model_dump()
    doc=timeline.Timeline(assets=[key],tracks=[timeline.Track(id=uuid4().hex,kind='video',name='Source',clips=[clip])]).model_dump()
    doc=timeline.save(project['id'],doc)
    monkeypatch.setattr(vision,'run',lambda req,*a:{'rows':[{'ms':s['ms'],'face':[.65,.5]} for s in req['samples']]})
    payload={'project_id':project['id'],'revision':doc['revision'],'ratio':'9:16','clip_ids':[clip['id']]}
    return project,doc,clip,payload,tmp_path/'job'

def test_reframe_returns_review_only(fixture):
    project,doc,clip,payload,folder=fixture;before=storage.project(project['id'])
    result=reframe.proposal(payload,folder,threading.Event(),lambda *a:None)
    assert result['width']==720 and result['height']==1280 and len(result['proposals'])==1
    layout=result['proposals'][0]['layout'];assert layout['x']<50 and layout['scale']>3
    assert layout['keyframes'][0]['ms']==0 and layout['keyframes'][-1]['ms']==1000
    assert timeline.load(project['id'])==doc and storage.project(project['id'])==before
    applied={**doc,'width':result['width'],'height':result['height']};applied['tracks'][0]['clips'][0].update({k:v for k,v in layout.items() if k not in {'detected_samples','total_samples'}})
    saved=timeline.save(project['id'],applied)
    assert saved['tracks'][0]['clips'][0]['start_ms']==500

def test_reframe_no_face_is_not_applied(fixture,monkeypatch):
    project,doc,clip,payload,folder=fixture
    monkeypatch.setattr(vision,'run',lambda req,*a:{'rows':[{'ms':s['ms'],'face':None} for s in req['samples']]})
    result=reframe.proposal(payload,folder,threading.Event(),lambda *a:None)
    assert not result['proposals'] and len(result['skipped'])==1
    assert timeline.load(project['id'])==doc

@pytest.mark.parametrize('change',[{'ratio':'bad'},{'revision':-1},{'clip_ids':[]},{'clip_ids':['f'*32]},{'clip_ids':['invalid']}])
def test_reframe_bad_requests(fixture,change):
    *_,payload,folder=fixture
    with pytest.raises(ValueError):reframe.proposal({**payload,**change},folder,threading.Event(),lambda *a:None)

def test_reframe_cancel(fixture):
    *_,payload,folder=fixture;event=threading.Event();event.set()
    with pytest.raises(InterruptedError):reframe.proposal(payload,folder,event,lambda *a:None)
    assert not folder.exists()

def test_reframe_locked_and_mirrored_skip(fixture):
    project,doc,clip,payload,folder=fixture;doc['tracks'][0]['locked']=True;doc=timeline.save(project['id'],doc)
    result=reframe.proposal({**payload,'revision':doc['revision']},folder,threading.Event(),lambda *a:None)
    assert not result['proposals'] and 'khóa' in result['skipped'][0]['reason']

def test_reframe_worker_failure_does_not_modify(fixture,monkeypatch):
    project,doc,clip,payload,folder=fixture
    monkeypatch.setattr(vision,'run',lambda *a:(_ for _ in ()).throw(RuntimeError('model missing')))
    with pytest.raises(RuntimeError,match='model missing'):reframe.proposal(payload,folder,threading.Event(),lambda *a:None)
    assert timeline.load(project['id'])==doc
