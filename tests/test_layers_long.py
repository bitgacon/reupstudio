import threading
from uuid import uuid4

import pytest
from PIL import Image
from reup import media, storage, timeline


@pytest.fixture(autouse=True)
def isolated(tmp_path, monkeypatch):
    monkeypatch.setattr(storage, 'DATA', tmp_path / 'data')
    storage.DATA.mkdir()


def image_asset(tmp_path, color, size=(160, 90)):
    key = uuid4().hex
    folder = storage.DATA / 'uploads' / key
    folder.mkdir(parents=True)
    source = folder / 'image.png'
    Image.new('RGB', size, color).save(source)
    storage.atomic_json(folder / 'asset.json', {'id': key, 'file': source.name, 'name': color})
    return key


@pytest.mark.parametrize('blend,base,top,expected', [('screen','red','blue',(255,0,255)), ('multiply','red','white',(255,0,0)), ('addition','red','blue',(255,0,255))])
def test_real_blend_is_local_and_timed(tmp_path, blend, base, top, expected):
    project = storage.new_project('Blend')
    a,b = image_asset(tmp_path,base),image_asset(tmp_path,top)
    value = timeline.Timeline(width=320,height=180,assets=[a,b],tracks=[
        timeline.Track(id=uuid4().hex,name='Background',kind='video',muted=True,clips=[timeline.Clip(id=uuid4().hex,asset=a,start_ms=0,duration_ms=1000)]),
        timeline.Track(id=uuid4().hex,name='Blend',kind='video',muted=True,clips=[timeline.Clip(id=uuid4().hex,asset=b,start_ms=300,duration_ms=400,scale=.5,blend=blend)])]).model_dump()
    output=storage.DATA/'blend.mp4'
    timeline.render(project,value,output,threading.Event(),lambda *a:None)
    for time in (.1,.5,.85):
        frame=tmp_path/f'frame-{time}.png'
        media.command([media.binary(),'-y','-v','error','-ss',str(time),'-i',str(output),'-frames:v','1',str(frame)])
        image=Image.open(frame).convert('RGB')
        target=expected if time==.5 else (255,0,0)
        assert all(abs(a-b)<20 for a,b in zip(image.getpixel((160,90)),target))
        assert all(abs(a-b)<20 for a,b in zip(image.getpixel((10,10)),(255,0,0)))


def test_cover_fills_portrait_with_landscape_source(tmp_path):
    project=storage.new_project('Cover')
    asset=image_asset(tmp_path,'red')
    value=timeline.Timeline(width=180,height=320,assets=[asset],tracks=[timeline.Track(id=uuid4().hex,name='Background',kind='video',clips=[timeline.Clip(id=uuid4().hex,asset=asset,start_ms=0,duration_ms=500,fit='cover')])]).model_dump()
    output=storage.DATA/'portrait.mp4'
    timeline.render(project,value,output,threading.Event(),lambda *a:None)
    frame=tmp_path/'portrait.png'
    media.command([media.binary(),'-y','-v','error','-i',str(output),'-frames:v','1',str(frame)])
    assert Image.open(frame).convert('RGB').getpixel((10,10))[0]>200


def test_long_proxy_policy_and_version_cache(tmp_path,monkeypatch):
    project=storage.new_project('Long')
    source=tmp_path/'source.mp4';source.write_bytes(b'fake')
    key=uuid4().hex
    item={'id':key,'kind':'video','duration_ms':600_000}
    monkeypatch.setattr(storage,'project_asset',lambda *a:(source,{}))
    monkeypatch.setattr(timeline,'describe',lambda *a:item)
    calls=[]
    def run(args,*a):
        calls.append(args)
        from pathlib import Path
        Path(args[-1]).write_bytes(b'proxy')
    monkeypatch.setattr(timeline,'run_cancel',run)
    timeline.prepare_proxy(project,key,threading.Event(),lambda *a:None)
    args=calls[0]
    assert 'min(640,iw)' in args[args.index('-vf')+1] and 'fps=24' in args[args.index('-vf')+1]
    assert args[args.index('-threads')+1]=='2'
    assert timeline.proxy_path(project,key,source).name.startswith('proxy-v2-')


def test_new_layout_enums_reject_unknown_modes():
    for data in ({'fit':'stretch'},{'blend':'command;evil'}):
        with pytest.raises(ValueError):
            timeline.Clip(id=uuid4().hex,start_ms=0,duration_ms=1000,**data)


def test_filmstrip_source_in_and_cache(tmp_path):
    source=tmp_path/'scenes.mp4'
    media.command([media.binary(),'-y','-v','error','-f','lavfi','-i','color=red:s=160x90:r=25:d=1',
                   '-f','lavfi','-i','color=blue:s=160x90:r=25:d=1','-filter_complex','[0:v][1:v]concat=n=2:v=1:a=0[v]',
                   '-map','[v]','-c:v','libx264',str(source)])
    key=uuid4().hex;folder=storage.DATA/'uploads'/key;folder.mkdir(parents=True)
    import shutil
    shutil.copy2(source,folder/'source.mp4')
    storage.atomic_json(folder/'asset.json',{'id':key,'file':'source.mp4','name':'Scenes'})
    project=storage.new_project('Filmstrip')
    item=timeline.prepare(project,key,threading.Event())
    assert len(item['thumbnails'])==16
    first=item['thumbnails'][0];last=item['thumbnails'][-1]
    for sample,color in [(first,0),(last,2)]:
        frame=storage.project_path(project['id'])/sample['url'][7:].split('/',2)[2]
        assert Image.open(frame).convert('RGB').getpixel((50,30))[color]>200
    path=storage.project_path(project['id'])/first['url'][7:].split('/',2)[2];stamp=path.stat().st_mtime_ns
    timeline.prepare(project,key,threading.Event())
    assert path.stat().st_mtime_ns==stamp


def test_cancelled_filmstrip_never_publishes_partial_frame(tmp_path,monkeypatch):
    project=storage.new_project('Cancel strip');key=uuid4().hex
    source=tmp_path/'source.mp4';source.write_bytes(b'fixture')
    monkeypatch.setattr(storage,'project_asset',lambda *a:(source,{}))
    monkeypatch.setattr(timeline,'describe',lambda *a:{'id':key,'kind':'video','duration_ms':2000,'has_audio':False})
    def run(args,*a):
        from pathlib import Path
        output=Path(args[-1]);output.write_bytes(b'incomplete')
        if '.partial.' in output.name:
            raise InterruptedError('cancel')
    monkeypatch.setattr(timeline,'run_cancel',run)
    with pytest.raises(InterruptedError):
        timeline.prepare(project,key,threading.Event())
    folder=storage.project_path(project['id'])/'editor-media'/key
    assert not (folder/'filmstrip.json').exists()
    assert not list(folder.glob('frame-*.png'))
