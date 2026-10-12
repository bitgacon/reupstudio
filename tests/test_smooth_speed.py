import threading
from uuid import uuid4
import pytest
from PIL import Image
import numpy as np
from pydub import AudioSegment
from reup import storage,media,timeline,speed

def test_integral_inverse_and_validation():
    c=timeline.Clip(id=uuid4().hex,start_ms=0,duration_ms=4000,speed_curve=[{'ms':0,'speed':.5},{'ms':4000,'speed':1.5}]).model_dump()
    assert speed.source_ms(c,2000)==1500 and speed.source_ms(c,4000)==4000
    assert speed.rate(c,2000)==1
    with pytest.raises(ValueError):timeline.Clip(id=uuid4().hex,start_ms=0,duration_ms=4000,speed_curve=[{'ms':0,'speed':.5},{'ms':3000,'speed':1.5}])

@pytest.mark.parametrize('begin,end',[(.5,1.5),(.25,1.75),(1.5,.5)])
def test_real_video_and_pitch_preserving_audio_ramp(tmp_path,monkeypatch,begin,end):
    monkeypatch.setattr(storage,'DATA',tmp_path/'data');storage.DATA.mkdir()
    key=uuid4().hex;folder=storage.DATA/'uploads'/key;folder.mkdir(parents=True);source=folder/'source.mp4'
    graph="[0:v][1:v]concat=n=2:v=1:a=0[v];[2:a][3:a]concat=n=2:v=0:a=1[a]"
    media.command([media.binary(),'-y','-v','error','-f','lavfi','-i','color=red:s=160x90:r=50:d=2','-f','lavfi','-i','color=blue:s=160x90:r=50:d=2','-f','lavfi','-i','sine=frequency=440:duration=2','-f','lavfi','-i','sine=frequency=880:duration=2','-filter_complex',graph,'-map','[v]','-map','[a]','-c:v','libx264','-c:a','aac',str(source)])
    storage.atomic_json(folder/'asset.json',{'id':key,'file':source.name,'name':'Ramp'})
    project=storage.new_project('Ramp');clip=timeline.Clip(id=uuid4().hex,asset=key,start_ms=500,duration_ms=4000,speed_curve=[{'ms':0,'speed':begin},{'ms':4000,'speed':end}])
    doc=timeline.Timeline(width=160,height=90,assets=[key],tracks=[timeline.Track(id=uuid4().hex,kind='video',name='Ramp',clips=[clip])]).model_dump()
    saved=timeline.save(project['id'],doc);output=tmp_path/'ramp.mp4';timeline.render(project,saved,output,threading.Event(),lambda *a:None)
    target=4/(begin+np.sqrt(begin*begin+(end-begin)))
    for t,color in [(target-.25,'red'),(target+.25,'blue')]:
        frame=tmp_path/f'{t}.png';media.command([media.binary(),'-y','-v','error','-ss',str(t+.5),'-i',str(output),'-frames:v','1',str(frame)])
        r,g,b=Image.open(frame).convert('RGB').getpixel((80,45));assert r>230 if color=='red' else b>230
    wav=tmp_path/'audio.wav';media.command([media.binary(),'-y','-v','error','-i',str(output),'-vn',str(wav)])
    audio=AudioSegment.from_wav(wav).set_channels(1)
    for ms,expected in [(int((target-.4)*1000)+500,440),(int((target+.4)*1000)+500,880)]:
        part=audio[ms:ms+200];samples=np.array(part.get_array_of_samples());peak=np.argmax(np.abs(np.fft.rfft(samples*np.hanning(len(samples)))))*part.frame_rate/len(samples)
        assert abs(peak-expected)<12
    assert 4480<=len(audio)<=4530
    crossing=[]
    for ms in range(int(target*1000)+200,int(target*1000)+801,20):
        part=audio[ms:ms+80];samples=np.array(part.get_array_of_samples());spectrum=np.abs(np.fft.rfft(samples*np.hanning(len(samples))));freq=np.fft.rfftfreq(len(samples),1/part.frame_rate)
        if spectrum[(freq>850)&(freq<910)].max()>spectrum[(freq>410)&(freq<470)].max():crossing.append(ms+40)
    assert crossing and abs(crossing[0]-(500+target*1000))<120,crossing[:3]
