import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from reup import VERSION, editor, media, storage
from reup.instance import InstanceLock, identify_server
from reup.server import make_app


def test_legacy_mask_and_multiple_regions_are_independent(tmp_path, monkeypatch):
    monkeypatch.setattr(storage, "DATA", tmp_path)
    legacy = {"original_subtitles": "blur", "mask_x": 10, "mask_y": 80}
    assert editor.config(legacy)["blur_regions"] == []
    regions = [{"mask_x": 10, "mask_y": 10}, {"mask_x": 50, "mask_y": 30}]
    with TestClient(make_app()) as client:
        client.get("/")
        state = client.get("/api/state").json()
        client.headers["X-Reup-Token"] = state["csrf"]
        p = client.post("/api/projects", json={"name": "multi", "edit": {**legacy, "blur_regions": regions}}).json()
        c = p["edit"]
        saved = c["blur_regions"]
        for mode in ("cover", "keep", "blur"):
            c["original_subtitles"] = mode
            r = client.post("/api/projects/"+p["id"], json={"revision": p["revision"], "name": p["name"], "voice": "", "video": "", "cues": [], "edit": c})
            assert r.status_code == 200, r.text
            p = r.json()
            loaded = client.get("/api/projects/"+p["id"]).json()
            assert loaded["edit"]["blur_regions"] == saved
        assert client.get("/api/instance").json()["data"] == str(tmp_path.resolve())


@pytest.mark.parametrize("regions", [[{}]*21, [{"mask_x": float("nan")}], [{"mask_blur": 80}], [{"mask_w": 0}]])
def test_invalid_regions_rejected(regions):
    with pytest.raises(ValidationError):
        editor.config({"blur_regions": regions})


def test_multiple_blurs_and_subtitle_cover_render(tmp_path, monkeypatch):
    video, audio, out = [tmp_path / n for n in ("source.mp4", "audio.wav", "multi.mp4")]
    media.command([media.binary(), "-y", "-v", "error", "-f", "lavfi", "-i", "testsrc2=s=320x180:r=15:d=1", "-c:v", "libx264", str(video)])
    media.command([media.binary(), "-y", "-v", "error", "-f", "lavfi", "-i", "sine=d=1", str(audio)])
    calls = []
    original = media.command
    def capture(args, **kwargs):
        calls.append(args)
        return original(args, **kwargs)
    monkeypatch.setattr(media, "command", capture)
    c = editor.config({"original_subtitles": "cover", "rotation": 15,
                       "blur_regions": [{"mask_x": 10, "mask_y": 20, "mask_w": 30},
                                        {"mask_x": 60, "mask_y": 40, "mask_blur": 25},
                                        {"mask_x": 99, "mask_y": 99}]})
    editor.render_video({"edit": c, "cues": []}, video, audio, out, 1000)
    render_call = next(args for args in calls if "-filter_complex" in args)
    graph = render_call[render_call.index("-filter_complex")+1]
    assert graph.count("boxblur=") == 3 and graph.count("drawbox=") == 1
    info = media.probe(out)
    assert (info["streams"][0]["width"], info["streams"][0]["height"]) == (320, 180)
    assert abs(float(info["format"]["duration"])-1) < .1


def test_process_lock_blocks_second_server_and_releases(tmp_path):
    first = InstanceLock(tmp_path)
    try:
        with pytest.raises(RuntimeError):
            InstanceLock(tmp_path)
    finally:
        first.close()
    second = InstanceLock(tmp_path)
    second.close()


@pytest.mark.parametrize("difference", [None, "root", "data", "version", "web_build", "app", "legacy"])
def test_attach_only_verified_matching_server(tmp_path, monkeypatch, difference):
    root, data = tmp_path / "app", tmp_path / "data"
    info = {"app": "reup-voice-studio", "root": str(root), "data": str(data), "version": VERSION, "web_build": "current"}
    if difference:
        info[difference] = "other"
    class Response:
        status_code = 200
        text = '<meta name="reup-web-build">'
        def json(self):
            return info
    class Session:
        def __enter__(self): return self
        def __exit__(self, *args): pass
        def get(self, url, **kwargs):
            assert kwargs["allow_redirects"] is False and self.trust_env is False
            r = Response()
            if difference == "legacy" and url.endswith("instance"): r.status_code = 404
            return r
    monkeypatch.setattr("reup.instance.requests.Session", Session)
    if difference:
        with pytest.raises(ValueError): identify_server("http://127.0.0.1:18765", root, data, VERSION, "current")
    else:
        assert identify_server("http://127.0.0.1:18765", root, data, VERSION, "current") == info
