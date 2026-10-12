from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from reup import storage, timeline
from reup.server import make_app


@pytest.fixture(autouse=True)
def isolated(tmp_path, monkeypatch):
    monkeypatch.setattr(storage, "DATA", tmp_path / "data")
    storage.DATA.mkdir()


def test_reveal_latest_output_and_configured_fallback(tmp_path):
    root = tmp_path / "saved"
    root.mkdir()
    storage.save_settings({"tts_output": str(root)})
    assert storage.reveal_folder("tts") == (root/'TextSpeech').resolve()
    folder = storage.output_folder("tts", uuid4().hex)
    audio = folder / "voice.wav"
    audio.write_bytes(b"audio")
    assert storage.reveal_folder("tts", storage.file_url(audio)) == folder.resolve()
    assert storage.reveal_folder("documents") == (storage.DATA / "outputs" / 'Documents').resolve()


@pytest.mark.parametrize("url", ["https://evil/files/a", "file:///C:/Windows", "/files/outputs/" + "a"*32 + "/../settings.json", "/files/outputs/" + "a"*32 + "/%2e%2e/settings.json", "/files/outputs/" + "a"*32 + "/C:foo", "/files/exports/" + "a"*32 + "/x.wav", "/files/settings.json", "/files/outputs/" + "a"*32 + "/x.wav?cmd=1"])
def test_reveal_rejects_arbitrary_targets(url):
    with pytest.raises(ValueError):
        storage.reveal_folder("tts", url)


def test_reveal_registered_project(tmp_path):
    project = storage.new_project("External", str(tmp_path))
    root = storage.project_path(project["id"])
    assert storage.reveal_folder("edit", project_id=project["id"]) == root.resolve()
    result = root / "audio.wav"
    result.write_bytes(b"ok")
    assert storage.reveal_folder("dub", storage.file_url(result)) == root.resolve()


def test_api_opens_directory_only_and_requires_csrf():
    app = make_app()
    opened = []
    app.state.open_folder = opened.append
    with TestClient(app) as client:
        assert client.post("/api/open-output-folder", json={"tab": "tts"}).status_code == 403
        client.get("/")
        headers = {"x-reup-token": client.get("/api/state").json()["csrf"]}
        response = client.post("/api/open-output-folder", json={"tab": "tts"}, headers=headers)
        assert response.status_code == 200
        assert opened == [(storage.DATA / "outputs" / 'TextSpeech').resolve()]
        assert opened[0].is_dir()
        assert client.post("/api/open-output-folder", json={"tab": "tts", "path": "C:/Windows"}, headers=headers).status_code == 422


def test_layout_presets_do_not_store_content_files_or_timing():
    value = timeline.LayoutPreset(name=" Vertical ", kind="text", layout={"x": 30, "font_size": 42})
    assert value.name == "Vertical"
    assert value.layout["font_size"] == 42
    for layout in ({"asset": "a"*32}, {"text": "private"}, {"start_ms": 1000}, {"scale": float("nan")}, {"rotation": 181}):
        with pytest.raises(ValueError):
            timeline.LayoutPreset(name="Bad", kind="video", layout=layout)
    with pytest.raises(ValueError):
        timeline.LayoutPreset(name="Blur", kind="blur", layout={"x": -1})


def test_layout_preset_api_persists_without_changing_project():
    project = storage.new_project("Original")
    before = (storage.project_path(project["id"]) / "project.json").read_bytes()
    with TestClient(make_app()) as client:
        client.get("/")
        headers = {"x-reup-token": client.get("/api/state").json()["csrf"]}
        result = client.post("/api/layout-presets", json={"name": "Half", "kind": "video", "layout": {"scale": .5}}, headers=headers)
        assert result.status_code == 200
        assert client.get("/api/layout-presets").json() == [result.json()]
    assert (storage.project_path(project["id"]) / "project.json").read_bytes() == before

def test_numbered_jobs_and_legacy_reuse():
    key=uuid4().hex;first=storage.output_folder('tts',key)
    assert first.name=='TextSpeech1' and first.parent.name=='TextSpeech'
    assert storage.output_folder('tts',key)==first
    assert storage.output_folder('tts',uuid4().hex).name=='TextSpeech2'
    first.rmdir()  # Deleted outputs must never make the next job reuse an old path.
    assert storage.output_folder('tts',uuid4().hex).name=='TextSpeech3'
    old_key=uuid4().hex;old=storage.DATA/'outputs'/old_key;old.mkdir()
    assert storage.output_folder('clone',old_key)==old
    result=old/'voice.wav';result.write_bytes(b'old')
    assert storage.reveal_folder('clone',storage.file_url(result))==old.resolve()

def test_shared_clean_names_collision_external_and_routes(tmp_path):
    root=tmp_path/'results';root.mkdir();storage.save_settings({'removal_output':str(root)})
    source=tmp_path/'x.png';source.write_bytes(b'image');sub=tmp_path/'x.srt';sub.write_bytes(b'subtitles')
    first=uuid4().hex;storage.output_folder('removal',first)
    image=storage.publish_removal(source,first,'Episode.mp4');subtitle=storage.publish_removal(sub,first,'Episode.mp4')
    assert image.parent==subtitle.parent==root/'RemoveSRT'
    assert image.name=='Episode_clean.png' and subtitle.name=='Episode_clean.srt'
    second=storage.publish_removal(source,uuid4().hex,'Episode.mp4');assert second.name=='Episode_clean_2.png'
    assert storage.removal_destination(uuid4().hex,'EPISODE.mp4','.mp4').name=='EPISODE_clean_3.mp4'
    with pytest.raises(FileExistsError):storage.publish_removal(source,first,'Episode.mp4')
    assert image.read_bytes()==b'image'
    assert storage.reveal_folder('removal',storage.file_url(image))==image.parent.resolve()
    with TestClient(make_app()) as client:
        client.get('/');client.get('/api/state');assert client.get(storage.file_url(image)).content==b'image'

def test_readable_projects_and_reserved_names():
    one=storage.new_project('Episode');two=storage.new_project('Episode')
    assert storage.project_path(one['id']).name=='Episode-1'
    assert storage.project_path(two['id']).name=='Episode-2'
    assert len(storage.list_projects())==2
    assert storage.safe_name('CON')=='Job-CON'
    assert '/' not in storage.safe_name('../bad:file')
    result=storage.project_path(one['id'])/'voice.wav';result.write_bytes(b'voice')
    assert storage.file_url(result)==f"/files/projects/{one['id']}/voice.wav"
    with TestClient(make_app()) as client:
        client.get('/');client.get('/api/state');assert client.get(storage.file_url(result)).content==b'voice'
