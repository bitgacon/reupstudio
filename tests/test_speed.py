import threading
from uuid import uuid4

import numpy as np
import pytest
from PIL import Image
from pydub import AudioSegment
from reup import media, storage, timeline


@pytest.fixture(autouse=True)
def isolated(tmp_path, monkeypatch):
    monkeypatch.setattr(storage, 'DATA', tmp_path / 'data')
    storage.DATA.mkdir()


@pytest.mark.parametrize('speed', [0, .1, 5, float('nan')])
def test_invalid_speed(speed):
    with pytest.raises(ValueError):
        timeline.Clip(id=uuid4().hex, start_ms=0, duration_ms=1000, speed=speed)


@pytest.mark.parametrize('speed', [.25, .5, 2, 4])
def test_speed_render_source_timing_and_audio_pitch(tmp_path, speed):
    key=uuid4().hex; folder=storage.DATA/'uploads'/key; folder.mkdir(parents=True)
    source=folder/'source.mp4'
    media.command([media.binary(),'-y','-v','error','-f','lavfi','-i','color=red:s=160x90:r=25:d=2',
        '-f','lavfi','-i','color=blue:s=160x90:r=25:d=2','-f','lavfi','-i','sine=frequency=440:duration=4',
        '-filter_complex','[0:v][1:v]concat=n=2:v=1:a=0[v]','-map','[v]','-map','2:a',
        '-c:v','libx264','-c:a','aac','-shortest',str(source)])
    storage.atomic_json(folder/'asset.json',{'id':key,'file':source.name,'name':'Speed'})
    project=storage.new_project('Speed'); duration=round(2000/speed)
    clip=timeline.Clip(id=uuid4().hex,asset=key,start_ms=400,in_ms=1000,duration_ms=duration,speed=speed)
    doc=timeline.Timeline(width=320,height=180,assets=[key],tracks=[timeline.Track(id=uuid4().hex,name='Video',kind='video',clips=[clip])]).model_dump()
    saved=timeline.save(project['id'],doc)
    assert timeline.load(project['id'])['tracks'][0]['clips'][0]['speed']==speed
    output=storage.DATA/'speed.mp4';timeline.render(project,saved,output,threading.Event(),lambda *a:None)
    assert abs(float(media.probe(output)['format']['duration'])-(duration+400)/1000)<.1
    for source_offset, channel in [(.4,0),(1.6,2)]:
        frame=tmp_path/f'frame-{channel}.png'
        media.command([media.binary(),'-y','-v','error','-ss',str(.4+source_offset/speed),'-i',str(output),'-frames:v','1',str(frame)])
        pixel=Image.open(frame).convert('RGB').getpixel((160,90))
        assert pixel[channel]>200 and pixel[2-channel]<30
    wave=tmp_path/'speed.wav'
    media.command([media.binary(),'-y','-v','error','-i',str(output),'-vn',str(wave)])
    audio=AudioSegment.from_wav(wave).set_channels(1)[500:500+min(300,duration-150)]
    samples=np.array(audio.get_array_of_samples(),dtype=float)
    spectrum=np.abs(np.fft.rfft(samples*np.hanning(len(samples))))
    peak=np.fft.rfftfreq(len(samples),1/audio.frame_rate)[spectrum.argmax()]
    assert abs(peak-440)<12
    invalid=timeline.Timeline.model_validate(saved); invalid.tracks[0].clips[0].in_ms=3500
    with pytest.raises(ValueError,match='nguồn'):
        timeline.save(project['id'],invalid.model_dump())
