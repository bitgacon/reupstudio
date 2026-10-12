import threading
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from reup import editor, media, storage
from reup.server import make_app
from reup.workflows import Workflows, artifact


@pytest.fixture(autouse=True)
def isolated(tmp_path, monkeypatch):
    monkeypatch.setattr(storage, "DATA", tmp_path / "data")
    storage.DATA.mkdir()
    media.configure_audio()


def upload(path):
    key = uuid4().hex
    folder = storage.DATA / "uploads" / key
    folder.mkdir(parents=True)
    target = folder / ("source" + path.suffix)
    target.write_bytes(path.read_bytes())
    storage.atomic_json(folder / "asset.json", {"id": key, "file": target.name, "name": path.name})
    return key


@pytest.fixture
def movie(tmp_path):
    target = tmp_path / "input.mp4"
    media.command([media.binary(), "-y", "-v", "error", "-f", "lavfi", "-i", "testsrc2=size=320x180:rate=15:duration=2",
                   "-f", "lavfi", "-i", "sine=frequency=440:duration=2", "-c:v", "libx264", "-c:a", "aac", "-shortest", str(target)])
    return target


def test_settings_reject_untrusted_values():
    for value in [{"zoom": 0}, {"rotation": float('nan')}, {"subtitle_color": "red;movie=x"},
                  {"logo": "../x"}, {"subtitle_font": "Arial,evil"}, {"target_language": "xx"}, {"original_audio": "unknown"}]:
        with pytest.raises(ValueError):
            editor.config(value)


def test_stop_owned_windows_launcher_tree(monkeypatch):
    from types import SimpleNamespace
    commands=[]
    monkeypatch.setattr(media.subprocess,"run",lambda args,**kwargs: commands.append(args))
    process=SimpleNamespace(pid=12345,poll=lambda:None,wait=lambda **kwargs:None)
    media.stop_owned_process(process)
    assert commands == [["taskkill","/PID","12345","/T","/F"]]


def test_external_project_and_files(tmp_path, movie):
    app = make_app()
    try:
        with TestClient(app) as client:
            client.get("/")
            headers = {"x-reup-token": client.get("/api/state").json()["csrf"]}
            p = client.post("/api/projects", json={"name": "Phim thử", "parent": str(tmp_path)}, headers=headers).json()
            key = upload(movie)
            payload = {"revision": p["revision"], "name": "Đổi tên", "video": key, "voice": "", "cues": [], "edit": {"rotation": 30}}
            response = client.post("/api/projects/" + p["id"], json=payload, headers=headers)
            assert response.status_code == 200, response.text
            p = response.json()
            assert storage.project_path(p["id"]).is_relative_to(tmp_path)
            assert not storage.project_path(p["id"]).is_relative_to(storage.DATA)
            assert p["edit"]["rotation"] == 30
            path, _ = storage.project_asset(p, key)
            assert path.is_file() and path.parent.name == "assets"
            url = artifact(path)["url"]
            r = client.get(url, headers={"Range": "bytes=0-31"})
            assert r.status_code == 206 and len(r.content) == 32
            assert client.get(f"/files/projects/{p['id']}/project.json").status_code == 403
            assert client.get(f"/files/projects/{p['id']}/%2E%2E/settings.json").status_code in {403,404}
            preset = client.post("/api/presets", json={"name": "Preset", "edit": p["edit"]}, headers=headers)
            assert preset.status_code == 200
            assert client.get("/api/state").json()["presets"][0]["edit"]["rotation"] == 30
    finally:
        app.state.queue.close()


@pytest.mark.parametrize("mask", ["keep", "cover", "blur"])
def test_render_transforms_subtitles_logo_and_audio(tmp_path, movie, mask):
    logo = tmp_path / "logo.png"
    media.command([media.binary(), "-y", "-v", "error", "-f", "lavfi", "-i", "color=red:s=50x30", "-frames:v", "1", str(logo)])
    speech = tmp_path / "voice.wav"
    media.command([media.binary(), "-y", "-v", "error", "-f", "lavfi", "-i", "sine=frequency=700:duration=2", str(speech)])
    p = storage.new_project("render")
    p.update(video=upload(movie), cues=[{"id": 1,"start_ms":0,"end_ms":1600,"text":"Xin chào tiếng Việt", "translation":"Hello"}])
    p["edit"] = editor.config({"zoom":1.2, "rotation":15,"subtitle_style":"karaoke", "subtitle_font":"Be Vietnam Pro", "target_language":"en",
                              "title":"Tiêu đề {không lệnh} \\path", "logo":upload(logo), "original_subtitles":mask,
                              "original_audio":"original", "background":upload(speech), "ducking":True, "denoise":True})
    storage.retain_assets(p)
    mixed = tmp_path / "mixed.wav"
    editor.mix_audio(p,speech,mixed,2000)
    assert abs(float(media.probe(mixed)["format"]["duration"])-2)<.05
    output = tmp_path / "render.mp4"
    editor.render_video(p,movie,mixed,output,2000,True)
    info = media.probe(output)
    assert abs(float(info["format"]["duration"])-2)<.1
    assert info["streams"][0]["width"] == 320
    assert "Hello" in (tmp_path / "styled.ass").read_text(encoding="utf-8-sig")


def test_preview_real_webm(tmp_path, movie):
    p = storage.new_project("preview")
    p["video"] = upload(movie)
    storage.save_project(p)
    flow = Workflows()
    result = flow.job_preview({"project_id": p["id"]},uuid4().hex,lambda *x: None,threading.Event())
    assert result["project_id"] == p["id"]
    info = media.probe(storage.project_path(p["id"]) / "preview.webm")
    assert info["streams"][0]["codec_name"] == "vp8"
    assert abs(float(info["format"]["duration"])-2) < .1


def test_ass_injection_and_timing(tmp_path):
    path=tmp_path/"styled.ass"
    editor.write_ass(path,[{"start_ms":1270,"end_ms":2370,"text":"{\\pos(0,0)}Hi\nNext"}],editor.config(),1280,720,3000)
    text=path.read_text(encoding="utf-8-sig")
    assert "0:00:01.27,0:00:02.37" in text
    assert "{\\pos(0,0)}" not in text


def test_stem_required(tmp_path, movie):
    p=storage.new_project("stems")
    p.update(video=upload(movie),edit=editor.config({"original_audio":"instrumental"}))
    with pytest.raises(ValueError,match="Tách giọng AI"):
        editor.mix_audio(p,movie,tmp_path/"audio.wav",2000)


def test_translation_separate_from_vietnamese_speech(monkeypatch):
    p=storage.new_project("translate", edit={"target_language":"en", "translation_provider":"api"})
    p["cues"]=[{"id":1,"start_ms":200,"end_ms":1400,"source_text":"Xin chào", "text":"Lời Việt", "status":"complete"}]
    storage.save_project(p)
    storage.save_settings({"translation_url":"https://example.invalid/v1", "translation_model":"test"})
    instructions=[]
    class Response:
        ok=True
        status_code=200
        def json(self):
            return {"choices":[{"message":{"content":'[{"id":1,"text":"Hello"}]'}}]}
    def post(*args,**kwargs):
        instructions.append(kwargs["json"]["messages"][0]["content"])
        return Response()
    monkeypatch.setattr("requests.Session.post",post)
    flow=Workflows()
    args={"project_id":p["id"],"allow_external":True}
    flow.job_translate(args,uuid4().hex,lambda *x:None,threading.Event())
    cue=storage.project(p["id"])["cues"][0]
    assert cue["text"]=="Lời Việt" and cue["translation"]=="Hello" and cue["status"]=="complete"
    assert "tiếng Anh" in instructions[-1]
    assert editor.caption(cue,editor.config({"target_language":"en"}))=="Hello"
    assert editor.caption(cue,editor.config())=="Lời Việt"
    flow.job_translate({**args,"for_speech":True},uuid4().hex,lambda *x:None,threading.Event())
    cue=storage.project(p["id"])["cues"][0]
    assert cue["translation"]=="Hello" and cue["text"]=="Hello"
    assert "tiếng Việt" in instructions[-1]
    assert (cue["start_ms"],cue["end_ms"])==(200,1400)
