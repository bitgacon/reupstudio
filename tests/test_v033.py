import pytest
from pydantic import ValidationError
from reup import editor, media, storage


def test_interval_validation_and_legacy_defaults():
    assert editor.config({"blur_regions": [{}]})["blur_regions"][0]["end_ms"] is None
    for row in ({"start_ms": 100, "end_ms": 100}, {"start_ms": -1}, {"end_ms": 0}):
        with pytest.raises(ValidationError):
            editor.config({"blur_regions": [row]})
        with pytest.raises(ValidationError):
            editor.config({"overlay_layer": row})
    assert editor.time_enable({"start_ms": 100, "end_ms": 500}) == "gte(t,0.1)*lt(t,0.5)"


def test_layer_assets_retained_and_times_roundtrip(tmp_path, monkeypatch):
    from fastapi.testclient import TestClient
    from reup.server import make_app
    monkeypatch.setattr(storage, "DATA", tmp_path)
    with TestClient(make_app()) as client:
        client.get("/")
        client.headers["X-Reup-Token"] = client.get("/api/state").json()["csrf"]
        asset = client.post("/api/upload", files={"file": ("layer.png", b"synthetic-source")}).json()
        p = client.post("/api/projects", json={"name": "timed layers"}).json()
        c = p["edit"]
        for key in ("visual_background", "overlay_layer", "blend_layer"):
            c[key].update(asset=asset["id"], start_ms=1234, end_ms=4567)
        response = client.post("/api/projects/"+p["id"], json={"revision":p["revision"],"name":p["name"],"voice":"","video":"","cues":[],"edit":c})
        assert response.status_code == 200, response.text
        loaded = client.get("/api/projects/"+p["id"]).json()
        for key in ("visual_background", "overlay_layer", "blend_layer"):
            assert loaded["edit"][key]["end_ms"] == 4567
            assert "/assets/" in loaded["edit_assets"][key]["url"]
        assert storage.project_asset(loaded, asset["id"])[0].read_bytes() == b"synthetic-source"


@pytest.mark.parametrize("mode", ["normal", "screen", "multiply"])
def test_visual_layers_and_timed_blur_real_render(tmp_path, monkeypatch, mode):
    video, audio, layer, out = [tmp_path/n for n in ("source.mp4", "audio.wav", "layer.mp4", "out.mp4")]
    for path, color in ((video, "blue"), (layer, "red")):
        media.command([media.binary(), "-y", "-v", "error", "-f", "lavfi", "-i", f"color=c={color}:s=160x90:r=10:d=2", "-c:v", "libx264", str(path)])
    media.command([media.binary(), "-y", "-v", "error", "-f", "lavfi", "-i", "sine=d=2", str(audio)])
    monkeypatch.setattr(storage, "project_asset", lambda *args: (layer, {}))
    value = {"asset": "a"*32, "start_ms": 500, "end_ms": 1500, "mode": mode}
    c = editor.config({"visual_background": {"asset": "b"*32}, "overlay_layer": value if mode=="normal" else {},
                       "blend_layer": value if mode!="normal" else {},
                       "blur_regions": [{"start_ms": 500, "end_ms": 1500}]})
    editor.render_video({"edit": c, "cues": []}, video, audio, out, 2000)
    info = media.probe(out)
    assert abs(float(info["format"]["duration"])-2)<.15
    # Decode one center pixel at three times to verify the active interval.
    import subprocess
    pixels=[]
    for t in (.2, .9, 1.8):
        result=subprocess.run([media.binary(), "-v", "error", "-ss", str(t), "-i", str(out), "-frames:v", "1", "-vf", "crop=2:2:80:44,scale=1:1", "-pix_fmt", "rgb24", "-f", "rawvideo", "-"], capture_output=True, check=True)
        pixels.append(tuple(result.stdout[:3]))
    assert pixels[0][2]>150 and pixels[2][2]>150
    if mode in {"normal", "screen"}: assert pixels[1][0]>150
    else: assert pixels[1][2]<60


def test_image_background_and_timed_subtitle_cover(tmp_path, monkeypatch):
    import subprocess
    video, audio, image, out = [tmp_path/n for n in ("source.mp4", "voice.wav", "bg.png", "out.mp4")]
    media.command([media.binary(), "-y", "-v", "error", "-f", "lavfi", "-i", "color=c=blue:s=160x90:r=10:d=2", str(video)])
    media.command([media.binary(), "-y", "-v", "error", "-f", "lavfi", "-i", "color=c=red:s=160x90", "-frames:v", "1", str(image)])
    media.command([media.binary(), "-y", "-v", "error", "-f", "lavfi", "-i", "sine=d=2", str(audio)])
    monkeypatch.setattr(storage, "project_asset", lambda *args:(image, {}))
    c=editor.config({"zoom":.5,"visual_background":{"asset":"a"*32},"original_subtitles":"cover","mask_x":0,"mask_y":0,"mask_w":100,"mask_h":100,"mask_start_ms":500,"mask_end_ms":1500})
    editor.render_video({"edit":c,"cues":[]},video,audio,out,2000)
    def pixel(t,x,y):
        return tuple(subprocess.run([media.binary(),"-v","error","-ss",str(t),"-i",str(out),"-frames:v","1","-vf",f"crop=2:2:{x}:{y},scale=1:1","-pix_fmt","rgb24","-f","rawvideo","-"],capture_output=True,check=True).stdout[:3])
    assert pixel(.2,2,2)[0]>150  # Image remains below the scaled main video.
    assert pixel(.2,80,44)[2]>150
    assert max(pixel(.9,80,44))<30
    assert pixel(1.8,80,44)[2]>150
