import hashlib, sys, threading
from pathlib import Path
from uuid import uuid4
import pytest
from reup import storage, media, subtitle_removal as vsr, fast_removal as fast

@pytest.fixture(autouse=True)
def isolate(tmp_path,monkeypatch):
    monkeypatch.setattr(storage,'DATA',tmp_path/'data');storage.DATA.mkdir()

def source(tmp_path):
    path=tmp_path/'logo.mp4'
    media.command([media.binary(),'-y','-v','error','-f','lavfi','-i','color=red:s=160x90:r=25:d=1,drawbox=x=40:y=30:w=30:h=20:color=white:t=fill','-f','lavfi','-i','sine=f=440:d=1','-c:v','libx264','-c:a','aac','-t','1',str(path)])
    return path

def payload(key,mode):return {'asset':key,'mode':mode,'regions':[{'x':25,'y':33.34,'w':18.75,'h':22.22}],'subtitle_mode':'none','margin':3,'radius':6}

@pytest.mark.parametrize('mode',['fast-delogo','blur','mosaic','solid'])
def test_real_ffmpeg_no_vsr_audio_skip_and_preview(tmp_path,monkeypatch,mode):
    monkeypatch.setattr(vsr,'runtime',lambda:pytest.fail('Fast mode must not load VSR'))
    original=source(tmp_path);digest=hashlib.sha256(original.read_bytes()).hexdigest();key=vsr.store_asset(original,'Logo test');p=payload(key,mode);event=threading.Event()
    preview=fast.preview({**p,'seconds':.2,'signature':'test'},uuid4().hex,lambda *a:None,event)
    assert preview['signature']=='test' and preview['picture']['bytes']>0
    row=vsr.remove(p,uuid4().hex,lambda *a:None,event)['entry'];out,_=storage.asset(row['asset']);info=media.probe(out)
    assert any(s['codec_type']=='audio' for s in info['streams']);assert info['streams'][0]['width']==160
    assert hashlib.sha256(original.read_bytes()).hexdigest()==digest
    assert vsr.remove({**p,'skip_existing':True},uuid4().hex,lambda *a:None,event)['entry']['id']==row['id']
    muted=vsr.remove({**p,'keep_audio':False},uuid4().hex,lambda *a:None,event)['entry'];out,_=storage.asset(muted['asset'])
    assert not any(s['codec_type']=='audio' for s in media.probe(out)['streams'])

@pytest.mark.parametrize('mode',['telea','navier-stokes','smooth','opencv'])
def test_real_opencv_optional_worker(tmp_path,monkeypatch,mode):
    python=storage.ROOT/'vision-env/Scripts/python.exe'
    if not python.is_file():pytest.skip('Optional local OpenCV runtime not installed')
    monkeypatch.setattr(fast,'cv_python',lambda:python)
    key=vsr.store_asset(source(tmp_path),'CV test');p=payload(key,mode);event=threading.Event()
    assert fast.preview({**p,'seconds':.2},uuid4().hex,lambda *a:None,event)['picture']['bytes']>0
    result=vsr.remove(p,uuid4().hex,lambda *a:None,event);out,_=storage.asset(result['entry']['asset']);assert out.is_file()

def test_options_edges_cancellation(tmp_path):
    for p in [{'radius':0},{'margin':float('nan')},{'margin':2.5},{'radius':True},{'keep_audio':'no'},{'mode':'oops'}]:
        with pytest.raises(ValueError):fast.options(p)
    with pytest.raises(ValueError,match='viền'):fast.filters([[0,20,1,30]],'fast-delogo',6,160,90)
    assert fast.padded([[1,10,2,15]],20,15,3)==[[0,13,0,18]]
    event=threading.Event();event.set();key=vsr.store_asset(source(tmp_path),'Keep')
    with pytest.raises(InterruptedError):vsr.remove(payload(key,'fast-delogo'),uuid4().hex,lambda *a:None,event)

@pytest.mark.parametrize('mode',['crop','logo'])
def test_crop_and_logo_preserve_audio_and_preview(tmp_path,mode):
    key=vsr.store_asset(source(tmp_path),'Crop/logo');p=payload(key,mode);event=threading.Event()
    if mode=='logo':
        picture=tmp_path/'logo.png';media.command([media.binary(),'-y','-v','error','-f','lavfi','-i','color=blue:s=20x10','-frames:v','1',str(picture)])
        p['logo_asset']=vsr.store_asset(picture,'New logo')
        p['regions'].append({'x':60,'y':60,'w':20,'h':20})
    assert fast.preview({**p,'seconds':.2},uuid4().hex,lambda *a:None,event)['picture']['bytes']>0
    row=vsr.remove(p,uuid4().hex,lambda *a:None,event)['entry'];output,_=storage.asset(row['asset']);info=media.probe(output)
    assert any(s['codec_type']=='audio' for s in info['streams'])
    assert info['streams'][0]['width']==(30 if mode=='crop' else 160)

@pytest.mark.parametrize('mode',['fast-delogo','blur','mosaic','solid','crop','telea','navier-stokes','smooth','opencv','logo'])
def test_images_real_output_without_vsr(tmp_path,monkeypatch,mode):
    monkeypatch.setattr(vsr,'runtime',lambda:pytest.fail('Images must not load VSR'))
    if mode in {'telea','navier-stokes','smooth','opencv'}:
        python=storage.ROOT/'vision-env/Scripts/python.exe'
        if not python.is_file():pytest.skip('Optional OpenCV not installed')
        monkeypatch.setattr(fast,'cv_python',lambda:python)
    picture=tmp_path/'picture.png'
    media.command([media.binary(),'-y','-v','error','-f','lavfi','-i','color=red:s=160x90,drawbox=x=40:y=30:w=30:h=20:color=white:t=fill','-frames:v','1',str(picture)])
    digest=hashlib.sha256(picture.read_bytes()).hexdigest();key=vsr.store_asset(picture,'picture.png');p=payload(key,mode)
    if mode=='logo':p['logo_asset']=key
    row=vsr.remove(p,uuid4().hex,lambda *a:None,threading.Event())['entry']
    out,_=storage.asset(row['asset']);assert row['kind']=='image' and out.suffix=='.png'
    assert media.probe(out)['streams'][0]['width']==(30 if mode=='crop' else 160)
    assert hashlib.sha256(picture.read_bytes()).hexdigest()==digest
    assert vsr.remove({**p,'skip_existing':True},uuid4().hex,lambda *a:None,threading.Event())['entry']['id']==row['id']
