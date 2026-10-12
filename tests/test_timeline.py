import threading
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from reup import media, storage, timeline
from reup.server import make_app


@pytest.fixture(autouse=True)
def isolated(tmp_path, monkeypatch):
    monkeypatch.setattr(storage, "DATA", tmp_path / "data")
    storage.DATA.mkdir()


def upload(source):
    key = uuid4().hex
    folder = storage.DATA / "uploads" / key
    folder.mkdir(parents=True)
    target = folder / ("source" + source.suffix)
    target.write_bytes(source.read_bytes())
    storage.atomic_json(folder / "asset.json", {"id": key, "file": target.name, "name": source.name})
    return key


@pytest.fixture
def movie(tmp_path):
    target = tmp_path / "red.mp4"
    media.command([media.binary(), "-y", "-v", "error", "-f", "lavfi", "-i", "color=red:s=160x90:r=25:d=2",
                   "-f", "lavfi", "-i", "sine=frequency=440:duration=2", "-c:v", "libx264", "-c:a", "aac", "-shortest", str(target)])
    return target


def document(asset):
    return timeline.Timeline(width=320,height=180,assets=[asset],tracks=[timeline.Track(id=uuid4().hex,name="Video",kind="video",clips=[
        timeline.Clip(id=uuid4().hex,asset=asset,start_ms=500,in_ms=500,duration_ms=1000)])]).model_dump()


def test_legacy_open_does_not_migrate_or_mutate():
    project=storage.new_project("Legacy")
    source=storage.project_path(project["id"]) / "project.json"
    before=source.read_bytes()
    assert timeline.load(project["id"])["tracks"] == []
    assert source.read_bytes() == before
    assert not timeline.path(project["id"]).exists()


@pytest.mark.parametrize("change",[{"width":319},{"fps":0},{"version":2},{"assets":["../foo"]}])
def test_invalid_models(change):
    with pytest.raises(ValueError):timeline.Timeline.model_validate(change)


def test_identity_and_overlap():
    data=document("a"*32)
    clip=data["tracks"][0]["clips"][0]
    data["tracks"][0]["clips"].append({**clip,"id":uuid4().hex,"start_ms":700})
    with pytest.raises(ValueError,match="chồng"):timeline.Timeline.model_validate(data)
    data["tracks"][0]["clips"][1]["start_ms"]=1500
    timeline.Timeline.model_validate(data)
    data["tracks"][0]["clips"][1]["id"]=clip["id"]
    with pytest.raises(ValueError,match="trùng"):timeline.Timeline.model_validate(data)


def test_save_preserves_legacy_and_sources_and_backup(movie):
    p=storage.new_project("Dự án")
    before=storage.project(p["id"])
    asset=upload(movie)
    data=document(asset)
    saved=timeline.save(p["id"],data)
    assert saved["revision"]==1
    after=storage.project(p["id"])
    assert {k:v for k,v in after.items() if k!="local_assets"}==before
    source,_=storage.project_asset(after,asset)
    assert source.read_bytes()==movie.read_bytes()
    with pytest.raises(ValueError,match="phiên khác"):timeline.save(p["id"],data)
    timeline.save(p["id"],saved)
    assert (timeline.path(p["id"]).parent/"editor-backups"/"revision-1.json").is_file()


def test_source_bounds_and_wrong_track(movie):
    p=storage.new_project("Bounds")
    data=document(upload(movie))
    data["tracks"][0]["clips"][0]["in_ms"]=1800
    with pytest.raises(ValueError,match="vượt"):timeline.save(p["id"],data)


def test_api_revision_and_session_guard(movie):
    p=storage.new_project("API")
    data=document(upload(movie))
    app=make_app()
    with TestClient(app) as client:
        url="/api/projects/"+p["id"]+"/timeline"
        assert client.get(url).status_code==403
        client.get("/")
        csrf=client.get("/api/state").json()["csrf"]
        headers={"x-reup-token":csrf}
        assert client.post(url,json=data).status_code==403
        assert client.get(url).json()["timeline"]["revision"]==0
        response=client.post(url,json=data,headers=headers)
        assert response.status_code==200,response.text
        assert client.post(url,json=data,headers=headers).status_code==409
        loaded=client.get(url).json()
        assert loaded["media"][0]["has_audio"]


@pytest.mark.parametrize("extension",[".mp4",".webm"])
def test_real_render_timeline_gap_trim_audio(tmp_path,movie,extension):
    p=storage.new_project("Render")
    value=document(upload(movie))
    output=storage.DATA/("out"+extension)
    timeline.render(p,value,output,threading.Event(),lambda *args:None)
    info=media.probe(output)
    assert abs(float(info["format"]["duration"])-1.5)<.12
    assert {s["codec_type"] for s in info["streams"]}=={"audio","video"}
    # Frame before the clip must be black, frame inside it red.
    for seconds,red in [("0.2",False),("0.8",True)]:
        from PIL import Image
        image=tmp_path/(seconds+extension+".png")
        media.command([media.binary(),"-y","-v","error","-ss",seconds,"-i",str(output),"-frames:v","1",str(image)])
        r,g,b=Image.open(image).convert("RGB").getpixel((160,90))
        assert (r>150 and g<30 and b<30) if red else max(r,g,b)<15
    audio=tmp_path/("audio"+extension+".wav")
    media.command([media.binary(),"-y","-v","error","-i",str(output),"-vn",str(audio)])
    from pydub import AudioSegment
    samples=AudioSegment.from_wav(audio)
    assert samples[:300].rms<10
    assert samples[700:1000].rms>100


def test_thumbnail_waveform_and_cancellation(movie):
    p=storage.new_project("Preview")
    item=timeline.prepare(p,upload(movie),threading.Event())
    assert item["thumbnail"].endswith(".png") and item["waveform"].endswith(".png")
    event=threading.Event();event.set()
    with pytest.raises(InterruptedError):timeline.render(p,document(item["id"]),storage.DATA/"cancelled.mp4",event,lambda *args:None)
    assert not (storage.DATA/"cancelled.mp4").exists()


def test_proxy_is_cached_and_never_mutates_project(movie):
    p=storage.new_project("Proxy")
    asset=upload(movie)
    before=storage.project_path(p["id"]).joinpath("project.json").read_bytes()
    item=timeline.prepare_proxy(p,asset,threading.Event(),lambda *a:None)
    assert item["preview_url"].endswith(".webm")
    source,_=storage.project_asset(p,asset)
    proxy=timeline.proxy_path(p,asset,source)
    stamp=proxy.stat().st_mtime_ns
    assert {s["codec_name"] for s in media.probe(proxy)["streams"]}=={"vp9","opus"}
    assert abs(float(media.probe(proxy)["format"]["duration"])-2)<.1
    timeline.prepare_proxy(p,asset,threading.Event(),lambda *a:None)
    assert proxy.stat().st_mtime_ns==stamp
    assert storage.project_path(p["id"]).joinpath("project.json").read_bytes()==before
    assert not timeline.path(p["id"]).exists()


@pytest.mark.parametrize("field,value",[("scale",0),("opacity",2),("rotation",181),("x",float("nan"))])
def test_invalid_transform(field,value):
    data=document("a"*32)
    data["tracks"][0]["clips"][0][field]=value
    with pytest.raises(ValueError):timeline.Timeline.model_validate(data)


def test_transform_render_matches_position_and_opacity(tmp_path,movie):
    from PIL import Image
    p=storage.new_project("Transform")
    value=document(upload(movie));clip=value["tracks"][0]["clips"][0]
    clip.update(x=25,y=50,scale=.5,rotation=90,opacity=.5)
    output=storage.DATA/"transform.mp4"
    timeline.render(p,value,output,threading.Event(),lambda *a:None)
    frame=tmp_path/"transform.png"
    media.command([media.binary(),"-y","-v","error","-ss","0.8","-i",str(output),"-frames:v","1",str(frame)])
    image=Image.open(frame).convert("RGB")
    r,g,b=image.getpixel((80,90))
    assert 100<r<145 and g<15 and b<15
    assert max(image.getpixel((250,90)))<15


def test_multiple_layers_hidden_and_muted(tmp_path,movie):
    from PIL import Image
    p=storage.new_project("Layers")
    image=tmp_path/"blue.png"
    Image.new("RGB",(160,90),"blue").save(image)
    image_id=upload(image)
    value=document(upload(movie))
    base=value["tracks"][0]
    base["muted"]=True
    base["clips"][0].update(start_ms=0,in_ms=0,duration_ms=2000)
    top=timeline.Track(id=uuid4().hex,name="Overlay",kind="video",clips=[
        timeline.Clip(id=uuid4().hex,asset=image_id,start_ms=500,duration_ms=1000)]).model_dump()
    value["tracks"].append(top)
    for hidden in (False,True):
        top["hidden"]=hidden
        output=storage.DATA/f"layers-{hidden}.mp4"
        timeline.render(p,value,output,threading.Event(),lambda *args:None)
        frame=tmp_path/f"frame-{hidden}.png"
        media.command([media.binary(),"-y","-v","error","-ss","0.8","-i",str(output),"-frames:v","1",str(frame)])
        r,g,b=Image.open(frame).convert("RGB").getpixel((160,90))
        assert r>150 and b<30 if hidden else b>150 and r<30
        wav=tmp_path/f"muted-{hidden}.wav"
        media.command([media.binary(),"-y","-v","error","-i",str(output),"-vn",str(wav)])
        from pydub import AudioSegment
        assert AudioSegment.from_wav(wav).rms<10


def test_real_source_in_selects_second_scene(tmp_path):
    from PIL import Image
    source=tmp_path/"scenes.mp4"
    media.command([media.binary(),"-y","-v","error","-f","lavfi","-i","color=red:s=160x90:r=25:d=1",
                   "-f","lavfi","-i","color=blue:s=160x90:r=25:d=1","-filter_complex","[0:v][1:v]concat=n=2:v=1:a=0[v]",
                   "-map","[v]","-c:v","libx264",str(source)])
    p=storage.new_project("Trim")
    value=document(upload(source))
    value["tracks"][0]["clips"][0].update(start_ms=0,in_ms=1000,duration_ms=500)
    output=storage.DATA/"trimmed.mp4"
    timeline.render(p,value,output,threading.Event(),lambda *args:None)
    frame=tmp_path/"trimmed.png"
    media.command([media.binary(),"-y","-v","error","-ss","0.2","-i",str(output),"-frames:v","1",str(frame)])
    r,g,b=Image.open(frame).convert("RGB").getpixel((160,90))
    assert b>150 and r<30


def test_text_and_blur_without_media_preserve_legacy_and_render(tmp_path):
    from PIL import Image
    p=storage.new_project("Visual tracks")
    before=storage.project_path(p["id"]).joinpath("project.json").read_bytes()
    value=timeline.Timeline(width=320,height=180,tracks=[
        timeline.Track(id=uuid4().hex,name="Text",kind="text",clips=[
            timeline.Clip(id=uuid4().hex,start_ms=200,duration_ms=1000,text="Xin chào {\\pos(1,1)}",font_size=30)]),
        timeline.Track(id=uuid4().hex,name="Blur",kind="blur",clips=[
            timeline.Clip(id=uuid4().hex,start_ms=500,duration_ms=200,region_w=40,region_h=40)])]).model_dump()
    saved=timeline.save(p["id"],value)
    assert storage.project_path(p["id"]).joinpath("project.json").read_bytes()==before
    assert timeline.load(p["id"])["tracks"][0]["clips"][0]["text"]==value["tracks"][0]["clips"][0]["text"]
    output=storage.DATA/"text.mp4"
    timeline.render(p,saved,output,threading.Event(),lambda *a:None)
    assert abs(float(media.probe(output)["format"]["duration"])-1.2)<.1
    for second,lit in [(0.08,False),(.35,True)]:
        frame=tmp_path/f"text-{second}.png"
        media.command([media.binary(),"-y","-v","error","-ss",str(second),"-i",str(output),"-frames:v","1",str(frame)])
        maximum=max(Image.open(frame).convert("RGB").getextrema()[0])
        assert maximum>150 if lit else maximum<15
    assert "{\\pos(1,1)}" not in (output.parent/"text-0.ass").read_text(encoding="utf-8-sig")


def test_visual_sources_and_media_sources_are_validated():
    key=uuid4().hex
    for kind,clip in [("video",{"text":"X"}),("text",{"asset":key,"text":"X"}),("blur",{"in_ms":100}),("text",{})]:
        with pytest.raises(ValueError):
            timeline.Timeline(tracks=[timeline.Track(id=uuid4().hex,name=kind,kind=kind,clips=[timeline.Clip(id=uuid4().hex,start_ms=0,duration_ms=1000,**clip)])])


def test_157_caption_clips_are_supported():
    value=timeline.Timeline(tracks=[timeline.Track(id=uuid4().hex,name="Subtitles",kind="text",clips=[
        timeline.Clip(id=uuid4().hex,start_ms=i*1000,duration_ms=500,text=f"Cue {i}") for i in range(157)])])
    assert len(value.tracks[0].clips)==157


def test_blur_is_applied_only_inside_its_time_interval(tmp_path):
    from PIL import Image,ImageDraw,ImageStat
    image=Image.new("RGB",(320,180),"black");draw=ImageDraw.Draw(image)
    for x in range(0,320,8):
        for y in range(0,180,8):
            if (x//8+y//8)%2:draw.rectangle((x,y,x+7,y+7),fill="white")
    source=tmp_path/"pattern.png";image.save(source)
    p=storage.new_project("Timed mask");asset=upload(source)
    value=document(asset);value["tracks"][0]["clips"][0].update(start_ms=0,in_ms=0,duration_ms=2000)
    value["tracks"].append(timeline.Track(id=uuid4().hex,name="Blur",kind="blur",clips=[
        timeline.Clip(id=uuid4().hex,start_ms=500,duration_ms=500,region_w=50,region_h=60,blur=12)]).model_dump())
    output=storage.DATA/"masked.mp4";timeline.render(p,value,output,threading.Event(),lambda *a:None)
    for second,blurred in [(.2,False),(.7,True),(1.3,False)]:
        frame=tmp_path/f"mask-{second}.png"
        media.command([media.binary(),"-y","-v","error","-ss",str(second),"-i",str(output),"-frames:v","1",str(frame)])
        deviation=ImageStat.Stat(Image.open(frame).convert("RGB").crop((120,65,200,115))).stddev[0]
        assert deviation<25 if blurred else deviation>100


def test_cancelled_proxy_has_no_published_or_partial_file(movie):
    p=storage.new_project("Cancel proxy");asset=upload(movie);event=threading.Event();event.set()
    with pytest.raises(InterruptedError):timeline.prepare_proxy(p,asset,event,lambda *a:None)
    source,_=storage.project_asset(p,asset)
    path=timeline.proxy_path(p,asset,source)
    assert not path.exists()
    assert not path.with_name(path.stem+".partial.webm").exists()
