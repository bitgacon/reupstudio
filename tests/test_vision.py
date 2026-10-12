import threading
from uuid import uuid4
import pytest
from reup import storage,timeline,vision

def test_face_geometry_and_no_face():
    clip=timeline.Clip(id=uuid4().hex,start_ms=0,duration_ms=1000).model_dump()
    result=vision.face_keys(clip,{'width':90,'height':160},{'width':160,'height':90},[{'ms':0,'face':[.7,.5]},{'ms':1000,'face':None}])
    assert result['fit']=='contain' and result['scale']==pytest.approx(256/81)
    assert result['keyframes'][0]['x']<50 and result['keyframes'][0]['x']==result['keyframes'][1]['x']
    with pytest.raises(ValueError,match='Không tìm'):vision.face_keys(clip,{'width':90,'height':160},{'width':160,'height':90},[{'ms':0,'face':None}])

def test_worker_missing_is_actionable(tmp_path,monkeypatch):
    monkeypatch.setattr(storage,'ROOT',tmp_path)
    monkeypatch.setattr(storage,'DATA',tmp_path/'data')
    with pytest.raises(ValueError,match='Thư viện'):vision.run({},tmp_path/'job',threading.Event(),lambda *a:None)

def test_phase_validation():
    with pytest.raises(ValueError):timeline.PositionKeyframe(ms=0,x=50,y=50,ease_start=.5,ease_end=.5)
    with pytest.raises(ValueError):timeline.PositionKeyframe(ms=0,x=50,y=50,ease_start=float('nan'))

def test_cancel_before_launch_leaves_no_files(tmp_path):
    event=threading.Event();event.set();folder=tmp_path/'cancel'
    with pytest.raises(InterruptedError):vision.run({},folder,event,lambda *a:None)
    assert not folder.exists()
