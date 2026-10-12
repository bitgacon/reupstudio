import threading
from uuid import uuid4

import pytest
from PIL import Image
from pydub import AudioSegment
from reup import media, storage, timeline


@pytest.fixture(autouse=True)
def isolated(tmp_path, monkeypatch):
    monkeypatch.setattr(storage, 'DATA', tmp_path / 'data')
    storage.DATA.mkdir()


def make_clip(**kwargs):
    return timeline.Clip(**{'id':uuid4().hex,'start_ms':0,'duration_ms':2000,**kwargs})


@pytest.mark.parametrize('keys', [[{'ms':1000,'x':20,'y':50},{'ms':500,'x':50,'y':50}],
    [{'ms':500,'x':20,'y':50},{'ms':500,'x':50,'y':50}], [{'ms':2500,'x':20,'y':50}], [{'ms':0,'x':float('nan'),'y':50}]])
def test_invalid_motion(keys):
    with pytest.raises(ValueError):
        make_clip(keyframes=keys)


def test_invalid_fades_and_track_support():
    with pytest.raises(ValueError):
        make_clip(fade_in_ms=1200,fade_out_ms=1200)
    with pytest.raises(ValueError):
        timeline.Timeline(tracks=[timeline.Track(id=uuid4().hex,name='Text',kind='text',clips=[make_clip(text='X',keyframes=[{'ms':0,'x':20,'y':50}])])])


@pytest.mark.parametrize('start_ms',[0,700])
@pytest.mark.parametrize('easing',['linear','smooth','hold'])
def test_real_position_and_video_audio_fades(tmp_path,start_ms,easing):
    key=uuid4().hex;folder=storage.DATA/'uploads'/key;folder.mkdir(parents=True)
    source=folder/'source.mp4'
    media.command([media.binary(),'-y','-v','error','-f','lavfi','-i','color=red:s=160x90:r=25:d=2',
                   '-f','lavfi','-i','sine=frequency=440:duration=2','-c:v','libx264','-c:a','aac','-shortest',str(source)])
    storage.atomic_json(folder/'asset.json',{'id':key,'file':source.name,'name':'Motion'})
    project=storage.new_project('Motion')
    clip=make_clip(start_ms=start_ms,motion_easing=easing,asset=key,scale=.25,fade_in_ms=500,fade_out_ms=500,keyframes=[{'ms':0,'x':20,'y':50},{'ms':2000,'x':80,'y':50}])
    doc=timeline.Timeline(width=320,height=180,assets=[key],tracks=[timeline.Track(id=uuid4().hex,name='Video',kind='video',clips=[clip])]).model_dump()
    before=storage.project(project['id'])
    saved=timeline.save(project['id'],doc)
    assert timeline.load(project['id'])['tracks'][0]['clips'][0]['keyframes']==doc['tracks'][0]['clips'][0]['keyframes']
    after=storage.project(project['id']);after.pop('local_assets',None)
    assert after==before
    output=storage.DATA/'motion.mp4'
    timeline.render(project,saved,output,threading.Event(),lambda *a:None)
    for second in (.08,.8,1.8):
        frame=tmp_path/f'motion-{second}.png'
        media.command([media.binary(),'-y','-v','error','-ss',str(second+start_ms/1000),'-i',str(output),'-frames:v','1',str(frame)])
        image=Image.open(frame).convert('RGB')
        pixels=[(x,p[0]) for y in range(60,120) for x in range(320) if (p:=image.getpixel((x,y)))[0]>15]
        center=sum(x for x,v in pixels)/len(pixels)
        f=second/2
        f=f*f*(3-2*f) if easing=='smooth' else 0 if easing=='hold' else f
        expected=320*(20+f*60)/100
        assert abs(center-expected)<8
        peak=max(v for x,v in pixels)
        assert peak>220 if second==.8 else peak<150
    audio=tmp_path/'motion.wav'
    media.command([media.binary(),'-y','-v','error','-i',str(output),'-vn',str(audio)])
    wave=AudioSegment.from_wav(audio)[start_ms:]
    assert wave[20:100].rms < wave[700:900].rms*.4
    assert wave[1880:1960].rms < wave[700:900].rms*.4
    assert (output.parent/'motion-filters.txt').is_file()


def test_fade_text_real_render(tmp_path):
    project=storage.new_project('Fade text')
    doc=timeline.Timeline(width=320,height=180,tracks=[timeline.Track(id=uuid4().hex,name='Text',kind='text',clips=[make_clip(text='TEST',font_size=50,fade_in_ms=600,fade_out_ms=600)])]).model_dump()
    output=storage.DATA/'text-fade.mp4'
    timeline.render(project,doc,output,threading.Event(),lambda *a:None)
    peaks=[]
    for second in (.04,1,1.96):
        frame=tmp_path/f'text-{second}.png';media.command([media.binary(),'-y','-v','error','-ss',str(second),'-i',str(output),'-frames:v','1',str(frame)])
        peaks.append(Image.open(frame).convert('RGB').getextrema()[0][1])
    assert peaks[1]>200 and peaks[0]<100 and peaks[2]<100


def test_full_transform_keys_real_render(tmp_path):
    import math
    key=uuid4().hex;folder=storage.DATA/'uploads'/key;folder.mkdir(parents=True);source=folder/'source.mp4'
    media.command([media.binary(),'-y','-v','error','-f','lavfi','-i','color=red:s=160x90:r=25:d=2','-c:v','libx264',str(source)])
    storage.atomic_json(folder/'asset.json',{'id':key,'file':source.name,'name':'Transform'})
    project=storage.new_project('Transform');clip=make_clip(start_ms=700,asset=key,keyframes=[{'ms':0,'x':50,'y':50,'scale':.2,'rotation':0,'opacity':.4},{'ms':2000,'x':50,'y':50,'scale':.6,'rotation':90,'opacity':1}])
    doc=timeline.Timeline(width=320,height=180,assets=[key],tracks=[timeline.Track(id=uuid4().hex,name='Video',kind='video',clips=[clip])]).model_dump()
    output=storage.DATA/'transform.mp4';timeline.render(project,doc,output,threading.Event(),lambda *a:None)
    for second in [.4,1.4]:
        frame=tmp_path/f'transform-{second}.png';media.command([media.binary(),'-y','-v','error','-ss',str(.7+second),'-i',str(output),'-frames:v','1',str(frame)])
        im=Image.open(frame).convert('RGB');points=[(x,y,p[0]) for y in range(180) for x in range(320) if (p:=im.getpixel((x,y)))[0]>40 and p[0]>p[1]*2]
        actual_w=max(p[0] for p in points)-min(p[0] for p in points);actual_h=max(p[1] for p in points)-min(p[1] for p in points)
        scale=.2+.4*second/2;angle=math.pi/2*second/2
        assert abs(actual_w-scale*(320*math.cos(angle)+180*math.sin(angle)))<12
        assert abs(actual_h-scale*(320*math.sin(angle)+180*math.cos(angle)))<12
        # Center avoids H.264 ringing peaks along the rotated high-contrast edge.
        assert abs(im.getpixel((160,90))[0]-255*(.4+.6*second/2))<10


@pytest.mark.parametrize('kind',['crossfade','wipeleft','wiperight'])
def test_true_transition_pixels_and_audio(tmp_path,kind):
    assets=[]
    for color in ['red','blue']:
        key=uuid4().hex;folder=storage.DATA/'uploads'/key;folder.mkdir(parents=True);source=folder/'source.mp4'
        media.command([media.binary(),'-y','-v','error','-f','lavfi','-i',f'color={color}:s=160x90:r=25:d=2','-f','lavfi','-i','sine=frequency=440:duration=2','-c:v','libx264','-c:a','aac','-shortest',str(source)])
        storage.atomic_json(folder/'asset.json',{'id':key,'file':source.name,'name':color});assets.append(key)
    project=storage.new_project('Transition')
    outgoing=make_clip(asset=assets[0],audio_fade_out_ms=500)
    incoming=make_clip(asset=assets[1],start_ms=1500,transition_in=kind,transition_ms=500,fit='cover')
    doc=timeline.Timeline(width=320,height=180,assets=assets,tracks=[timeline.Track(id=uuid4().hex,name='A',kind='video',clips=[outgoing]),timeline.Track(id=uuid4().hex,name='B',kind='video',clips=[incoming])]).model_dump()
    output=tmp_path/(kind+'.mp4');timeline.render(project,doc,output,threading.Event(),lambda *a:None)
    image=tmp_path/'mid.png';media.command([media.binary(),'-y','-v','error','-ss','1.76','-i',str(output),'-frames:v','1',str(image)])
    im=Image.open(image).convert('RGB')
    if kind=='crossfade':
        r,g,b=im.getpixel((160,90));assert 100<r<150 and 110<b<160 and g<10
    else:
        left,right=im.getpixel((40,90)),im.getpixel((280,90))
        assert (left[2]>230 and right[0]>230) if kind=='wipeleft' else (left[0]>230 and right[2]>230)
    wav=tmp_path/'mix.wav';media.command([media.binary(),'-y','-v','error','-i',str(output),'-vn',str(wav)])
    audio=AudioSegment.from_wav(wav)
    assert audio[1720:1800].rms < audio[900:1100].rms*1.2
