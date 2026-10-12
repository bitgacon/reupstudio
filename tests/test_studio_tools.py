import json,threading,zipfile
from uuid import uuid4
from PIL import Image
import pytest
from reup import storage,timeline,media,studio_tools,captions

@pytest.mark.parametrize('quality,size',[(720,(1280,720)),(1080,(1920,1080)),(1440,(2560,1440)),(2160,(3840,2160))])
def test_multi_quality_preserves_project(tmp_path,monkeypatch,quality,size):
    project,doc,p=fixture(tmp_path,monkeypatch);before=timeline.load(project['id']);calls=[]
    def render(project,version,out,*a):calls.append((version['width'],version['height']));out.write_bytes(b'test')
    monkeypatch.setattr(timeline,'render',render)
    studio_tools.multi_export({**p,'ratios':['16:9','9:16'],'quality':quality},tmp_path,threading.Event(),lambda *a:None)
    assert calls==[size,size[::-1]] and timeline.load(project['id'])==before

@pytest.mark.parametrize('quality',[True,'2160',0,4320])
def test_multi_rejects_bad_quality(tmp_path,monkeypatch,quality):
    *_,p=fixture(tmp_path,monkeypatch)
    with pytest.raises(ValueError,match='chất lượng'):studio_tools.multi_export({**p,'quality':quality},tmp_path,threading.Event(),lambda *a:None)

def fixture(tmp_path,monkeypatch):
    monkeypatch.setattr(storage,'DATA',tmp_path/'data');storage.DATA.mkdir();project=storage.new_project('Tools QA');key=uuid4().hex;folder=storage.DATA/'uploads'/key;folder.mkdir(parents=True);source=folder/'source.mp4'
    media.command([media.binary(),'-y','-v','error','-f','lavfi','-i','testsrc2=s=160x90:r=24:d=2','-f','lavfi','-i','sine=f=440:d=2','-c:v','libx264','-pix_fmt','yuv420p','-c:a','aac','-shortest',str(source)])
    storage.atomic_json(folder/'asset.json',{'id':key,'name':'QA video','file':source.name,'attribution':'QA attribution'})
    doc=timeline.Timeline(width=160,height=90,assets=[key],tracks=[timeline.Track(id=uuid4().hex,name='Source',kind='video',clips=[timeline.Clip(id=uuid4().hex,asset=key,start_ms=0,duration_ms=2000)])]).model_dump();doc=timeline.save(project['id'],doc)
    return storage.project(project['id']),doc,{'project_id':project['id'],'revision':doc['revision'],'clip_id':doc['tracks'][0]['clips'][0]['id'],'at_ms':500}

def test_comic_stage_analysis_and_benchmark_real(tmp_path,monkeypatch):
    project,doc,p=fixture(tmp_path,monkeypatch);event=threading.Event();progress=lambda *a:None
    comic=studio_tools.comic(p,tmp_path/'comic',event,progress);source,_=storage.project_asset(project,comic['media']['id']);Image.open(source).verify()
    stage=studio_tools.stage(p,tmp_path/'stage',event,progress);assert stage['media']['kind']=='video' and not stage['media']['has_audio'] and abs(stage['media']['duration_ms']-2000)<100
    proposal=studio_tools.analyze(p,tmp_path/'analyze',event,progress);assert proposal['revision']==doc['revision'] and all(100<=x<=1900 for x in proposal['points'])
    report=studio_tools.benchmark(p,tmp_path/'bench',event,progress);assert report['seconds']>0 and report['duration_ms']==2000
    assert timeline.load(project['id'])==doc

def test_bundle_roundtrip_no_keys_or_original_mutation(tmp_path,monkeypatch):
    project,doc,p=fixture(tmp_path,monkeypatch);storage.atomic_json(storage.DATA/'settings.json',{'api_key':'DO NOT EXPORT'});event=threading.Event()
    bundle=studio_tools.export_bundle(p,tmp_path/'bundle',event,lambda *a:None)
    with zipfile.ZipFile(bundle) as z:
        assert len(z.namelist())==2 and 'DO NOT EXPORT' not in z.read('manifest.json').decode()
    imported=studio_tools.import_bundle(bundle,event);next_doc=timeline.load(imported['id']);assert imported['id']!=project['id'] and next_doc['assets']!=doc['assets'] and next_doc['tracks'][0]['clips'][0]['duration_ms']==2000
    assert storage.project_asset(imported,next_doc['assets'][0])[1]['attribution']=='QA attribution'
    assert timeline.load(project['id'])==doc

@pytest.mark.parametrize('rate',[.5,1,1.25])
def test_podcast_stage_covers_video_with_short_audio_and_can_save(tmp_path,monkeypatch,rate):
    project,doc,p=fixture(tmp_path,monkeypatch);source,_=storage.project_asset(project,doc['assets'][0])
    media.command([media.binary(),'-y','-v','error','-f','lavfi','-i','testsrc2=s=160x90:r=24:d=2','-f','lavfi','-i','sine=f=440:d=0.6','-c:v','libx264','-pix_fmt','yuv420p','-c:a','aac',str(source)])
    c=doc['tracks'][0]['clips'][0];c.update(in_ms=250,speed=rate,duration_ms=round(1500/rate));doc=timeline.save(project['id'],doc);p['revision']=doc['revision']
    result=studio_tools.stage(p,tmp_path/'short-audio-stage',threading.Event(),lambda *a:None);item=result['media']
    assert item['duration_ms']>=c['duration_ms']-40 and not item['has_audio']
    doc['assets'].append(item['id']);doc['tracks'].append(timeline.Track(id=uuid4().hex,name='Stage',kind='video',clips=[timeline.Clip(id=uuid4().hex,asset=item['id'],start_ms=0,duration_ms=c['duration_ms'])]).model_dump())
    timeline.save(project['id'],doc)

def test_bundle_traversal_rejected_before_project(tmp_path,monkeypatch):
    monkeypatch.setattr(storage,'DATA',tmp_path/'data');storage.DATA.mkdir();path=tmp_path/'bad.rvp'
    with zipfile.ZipFile(path,'w') as z:z.writestr('../bad','evil');z.writestr('manifest.json','{}')
    with pytest.raises((ValueError,KeyError)):studio_tools.import_bundle(path,threading.Event())
    assert storage.list_projects()==[] and not (tmp_path/'bad').exists()

@pytest.mark.parametrize('style',['karaoke','typewriter','pop'])
def test_text_animation_real_render(tmp_path,monkeypatch,style):
    monkeypatch.setattr(storage,'DATA',tmp_path/'data');storage.DATA.mkdir();project=storage.new_project('Caption');c=timeline.Clip(id=uuid4().hex,start_ms=0,duration_ms=1200,text='Xin chào bạn',text_animation=style,font_size=20)
    doc=timeline.Timeline(width=320,height=180,tracks=[timeline.Track(id=uuid4().hex,name='Text',kind='text',clips=[c])]).model_dump();doc=timeline.save(project['id'],doc)
    out=tmp_path/'caption.mp4';timeline.render(project,doc,out,threading.Event(),lambda *a:None);assert out.stat().st_size>1000
    assert captions.words(c.text,1200)[-1][2]==1200

def test_moving_blur_render_and_validation(tmp_path,monkeypatch):
    project,doc,p=fixture(tmp_path,monkeypatch);doc['tracks'].append(timeline.Track(id=uuid4().hex,name='Moving blur',kind='blur',clips=[timeline.Clip(id=uuid4().hex,start_ms=0,duration_ms=2000,keyframes=[timeline.PositionKeyframe(ms=0,x=25,y=50),timeline.PositionKeyframe(ms=2000,x=75,y=50)])]).model_dump())
    doc=timeline.save(project['id'],doc);out=tmp_path/'blur.mp4';timeline.render(project,doc,out,threading.Event(),lambda *a:None);assert out.stat().st_size>1000
    with pytest.raises(ValueError):timeline.Timeline(tracks=[timeline.Track(id=uuid4().hex,name='bad',kind='blur',clips=[timeline.Clip(id=uuid4().hex,start_ms=0,duration_ms=2000,keyframes=[timeline.PositionKeyframe(ms=0,x=50,y=50,scale=1)])])])

def test_multi_export_real_preserves_doc(tmp_path,monkeypatch):
    project,doc,p=fixture(tmp_path,monkeypatch);folder=tmp_path/'multi';folder.mkdir();files=studio_tools.multi_export(p,folder,threading.Event(),lambda *a:None)
    assert len(files)==4 and files[-1].name=='ATTRIBUTION.txt'
    sizes=[(1280,720),(720,1280),(1080,1080)]
    for file,(w,h) in zip(files,sizes):
        stream=next(s for s in media.probe(file)['streams'] if s['codec_type']=='video');assert (stream['width'],stream['height'])==(w,h)
    assert timeline.load(project['id'])==doc

def test_tracking_real_worker(tmp_path,monkeypatch):
    from reup import vision
    import numpy as np
    if not (storage.ROOT/'vision-env'/'Scripts'/'python.exe').is_file():pytest.skip('Optional vision runtime not installed')
    project,doc,p=fixture(tmp_path,monkeypatch);key=doc['assets'][0];source,_=storage.project_asset(project,key)
    patch=tmp_path/'tile.png';Image.fromarray(np.random.default_rng(123).integers(0,255,(20,20,3),dtype=np.uint8)).save(patch)
    media.command([media.binary(),'-y','-v','error','-f','lavfi','-i','color=black:s=160x90:r=24:d=2','-loop','1','-i',str(patch),'-filter_complex',"[0:v][1:v]overlay=x='30+t*30':y=35:shortest=1[v]",'-map','[v]','-t','2','-c:v','libx264','-pix_fmt','yuv420p',str(source)])
    result=vision.object_tracking({**p,'at_ms':0,'region':{'x':25,'y':50,'region_w':12.5,'region_h':20/90*100}},tmp_path/'tracking',threading.Event(),lambda *a:None)
    assert result['keyframes'][-1]['x']>result['keyframes'][0]['x']+25
    assert 10<=len(result['keyframes'])<=64 and timeline.load(project['id'])==doc

@pytest.mark.parametrize('encoder',['h264_nvenc','h264_qsv','h264_amf'])
def test_hardware_encoder_command_contract(tmp_path,monkeypatch,encoder):
    project,doc,p=fixture(tmp_path,monkeypatch);doc['encoder']=encoder;calls=[]
    monkeypatch.setattr(timeline,'run_cancel',lambda args,*a,**kw:calls.append(args))
    timeline.render(project,doc,tmp_path/'gpu.mp4',threading.Event(),lambda *a:None)
    args=calls[-1];assert args[args.index('-c:v')+1]==encoder and '-b:v' in args and '-crf' not in args
    assert timeline.load(project['id'])['encoder']=='libx264'

def test_encoder_allowlist():
    with pytest.raises(ValueError):timeline.Timeline(encoder='h264_nvenc;exec')

def test_comic_image_cursor_not_zero(tmp_path,monkeypatch):
    monkeypatch.setattr(storage,'DATA',tmp_path/'data');storage.DATA.mkdir();project=storage.new_project('Still comic');key=uuid4().hex;folder=storage.DATA/'uploads'/key;folder.mkdir(parents=True);Image.new('RGB',(160,90),'blue').save(folder/'source.png');storage.atomic_json(folder/'asset.json',{'id':key,'name':'Image','file':'source.png'})
    doc=timeline.Timeline(width=160,height=90,assets=[key],tracks=[timeline.Track(id=uuid4().hex,name='Image',kind='video',clips=[timeline.Clip(id=uuid4().hex,asset=key,start_ms=0,duration_ms=2000)])]).model_dump();doc=timeline.save(project['id'],doc)
    result=studio_tools.comic({'project_id':project['id'],'revision':doc['revision'],'clip_id':doc['tracks'][0]['clips'][0]['id'],'at_ms':800},tmp_path/'comic',threading.Event(),lambda *a:None)
    assert result['media']['kind']=='image'
