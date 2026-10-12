import threading
from uuid import uuid4

import pytest
from PIL import Image
from reup import media, storage, timeline


def test_flip_only_requested_intervals_real_render(tmp_path, monkeypatch):
    monkeypatch.setattr(storage,'DATA',tmp_path/'data');storage.DATA.mkdir()
    key=uuid4().hex;folder=storage.DATA/'uploads'/key;folder.mkdir(parents=True);source=folder/'source.mp4'
    pattern='color=black:s=160x90:r=25:d=3,drawbox=x=0:y=0:w=80:h=45:color=red:t=fill,drawbox=x=80:y=0:w=80:h=45:color=blue:t=fill,drawbox=x=0:y=45:w=80:h=45:color=lime:t=fill,drawbox=x=80:y=45:w=80:h=45:color=yellow:t=fill'
    media.command([media.binary(),'-y','-v','error','-f','lavfi','-i',pattern,'-c:v','libx264',str(source)])
    storage.atomic_json(folder/'asset.json',{'id':key,'file':source.name,'name':'Quadrants'})
    project=storage.new_project('Mirror')
    clips=[timeline.Clip(id=uuid4().hex,asset=key,start_ms=i*1000,in_ms=i*1000,duration_ms=1000,flip_h=i==1,flip_v=i==2) for i in range(3)]
    doc=timeline.Timeline(width=320,height=180,assets=[key],tracks=[timeline.Track(id=uuid4().hex,name='Video',kind='video',clips=clips)]).model_dump()
    saved=timeline.save(project['id'],doc)
    output=storage.DATA/'flip.mp4';timeline.render(project,saved,output,threading.Event(),lambda *a:None)
    for i,channel in enumerate([0,2,1]):
        frame=tmp_path/f'flip-{i}.png';media.command([media.binary(),'-y','-v','error','-ss',str(i+.5),'-i',str(output),'-frames:v','1',str(frame)])
        pixel=Image.open(frame).convert('RGB').getpixel((40,30));assert pixel[channel]>220
        assert all(v<30 for j,v in enumerate(pixel) if j!=channel)
    assert timeline.load(project['id'])['tracks'][0]['clips'][1]['flip_h']


def test_flip_validation_and_preset():
    preset=timeline.LayoutPreset(name='Mirror',kind='video',layout={'flip_h':True})
    assert preset.layout['flip_h'] is True
    with pytest.raises(ValueError):
        timeline.Timeline(tracks=[timeline.Track(id=uuid4().hex,name='Text',kind='text',clips=[timeline.Clip(id=uuid4().hex,start_ms=0,duration_ms=1000,text='X',flip_h=True)])])
