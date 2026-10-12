from __future__ import annotations

import threading
import time
import zipfile

import pytest
from fastapi.testclient import TestClient
from pydub import AudioSegment
from pydub.generators import Sine

from reup import media, storage
from reup.jobs import JobQueue
from reup.server import make_app
from reup.workflows import Workflows, cue_key


@pytest.fixture(autouse=True)
def isolated(tmp_path, monkeypatch):
    monkeypatch.setattr(storage, "DATA", tmp_path / "data")
    storage.DATA.mkdir()

def test_fit_cue_exposes_measured_pre_fit_speech(tmp_path):
    raw=tmp_path/'raw.wav';out=tmp_path/'fit.wav'
    (AudioSegment.silent(duration=200)+Sine(440).to_audio_segment(duration=2000)+AudioSegment.silent(duration=200)).export(raw,format='wav')
    metrics=media.fit_cue(raw,out,1000)
    assert metrics['raw_ms']==2400
    assert 2000<=metrics['voiced_ms']<=2080
    assert metrics['fit_duration_ms']==1000
    assert metrics['speed_factor']==round(metrics['voiced_ms']/1000,3)
    assert abs(len(AudioSegment.from_file(out))-1000)<=2


@pytest.mark.parametrize("code,expected", [("00:00:01,230", 1230), ("00:02:01.5", 121500), ("12:00:00,000", 43200000)])
def test_timecode(code, expected):
    assert media.milliseconds(code) == expected
    assert media.milliseconds(media.timecode(expected)) == expected


@pytest.mark.parametrize("code", ["00:60:00,000", "00:00:61,000", "hello", "-1:00:00,000"])
def test_bad_timecode(code):
    with pytest.raises(ValueError):
        media.milliseconds(code)


def test_srt_preserves_invalid_and_overlap():
    rows, issues = media.parse_srt("1\n00:00:00,000 --> 00:00:00,000\nZero\n\n2\n00:00:00,000 --> 00:00:02,000\nTwo\n\n3\n00:00:01,000 --> 00:00:03,000\nThree")
    assert rows[0]["end_ms"] == 0
    assert any(i["level"] == "error" for i in issues)
    assert any(i["level"] == "warning" for i in issues)
    restored, _ = media.parse_srt(media.srt(rows))
    assert restored == rows


def test_malformed_block_is_not_silently_ignored():
    rows, issues = media.parse_srt("bad\ntext\n\n1\n00:00:00,000 --> 00:00:02,000\nValid")
    assert len(rows) == 1
    assert any(i.get("block") == 1 for i in issues)


def test_documents_unicode_and_docx(tmp_path):
    text = "Xin chào tiếng Việt\nMột câu mới."
    source = tmp_path / "sample.txt"
    source.write_bytes(text.encode("utf-16"))
    assert media.document(source)["text"] == text
    source = tmp_path / "sample.docx"
    with zipfile.ZipFile(source, "w") as archive:
        archive.writestr("word/document.xml", '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"><w:body><w:p><w:r><w:t>Xin chào</w:t></w:r></w:p><w:tbl><w:tr><w:tc><w:p><w:r><w:t>Trong bảng</w:t></w:r></w:p></w:tc></w:tr></w:tbl></w:body></w:document>')
    assert media.document(source)["text"] == "Xin chào\n\nTrong bảng"


def test_empty_pdf_reports_ocr(tmp_path):
    from pypdf import PdfWriter
    source = tmp_path / "scan.pdf"
    writer = PdfWriter()
    writer.add_blank_page(200, 200)
    with source.open("wb") as stream:
        writer.write(stream)
    with pytest.raises(ValueError, match="OCR"):
        media.document(source)


def test_dialogue_multiline_and_invalid():
    rows = media.dialogue("[Host]: Xin chào\nDòng tiếp\n[Khách]: Chào bạn")
    assert len(rows) == 2
    assert rows[0]["text"] == "Xin chào\nDòng tiếp"
    with pytest.raises(ValueError):
        media.dialogue("Không có tên")


def test_split_has_no_loss_or_oversize():
    text = "abc " * 500 + "x" * 400
    pieces = media.split_script(text)
    assert all(0 < len(p) <= 350 for p in pieces)
    assert "".join("".join(p.split()) for p in pieces) == "".join(text.split())


@pytest.fixture
def client():
    app = make_app()
    with TestClient(app) as client:
        client.get("/")
        token = client.get("/api/state").json()["csrf"]
        client.headers["X-Reup-Token"] = token
        yield client


def test_api_requires_session_and_csrf():
    with TestClient(make_app()) as client:
        assert client.get("/api/state").status_code == 403
        client.get("/")
        assert client.post("/api/projects", json={}).status_code == 403
        assert client.get("/", headers={"host": "evil.test"}).status_code == 403


def test_settings_never_echo_key(client):
    response = client.post("/api/settings", json={"translation_key": "test-secret-value"})
    assert response.status_code == 200
    assert response.json()["has_translation_key"] is True
    assert "test-secret-value" not in client.get("/api/state").text
    assert client.get("/files/settings.json").status_code == 403
    assert client.post("/api/projects", json={}, headers={"origin": "https://other.test"}).status_code == 403


def test_upload_rejects_scripts_and_path_escape(client):
    assert client.post("/api/upload", files={"file": ("evil.html", b"<script>")}).status_code == 400
    good = client.post("/api/upload", files={"file": ("../../sample.txt", b"xin chao")}).json()
    assert good["name"] == "sample.txt"
    path, _ = storage.asset(good["id"])
    assert path.is_relative_to(storage.DATA)
    assert client.get(good["url"]).content == b"xin chao"
    assert client.get("/files/%2e%2e/settings.json").status_code != 200


def test_project_revision_and_invalidates_audio(client):
    value = client.post("/api/projects", json={"name": "Demo"}).json()
    payload = {"revision": value["revision"], "name": "Demo", "voice": "Mai Anh", "video": "", "cues": [
        {"id": 1, "start_ms": 0, "end_ms": 1000, "source_text": "Hello", "text": "Xin chào", "voice": ""}]}
    result = client.post("/api/projects/" + value["id"], json=payload)
    assert result.status_code == 200
    assert result.json()["cues"][0]["status"] == "pending"
    assert client.post("/api/projects/" + value["id"], json=payload).status_code == 409


def test_job_interrupt_recovery():
    path = storage.DATA / "jobs" / ("a" * 32 + ".json")
    storage.atomic_json(path, {"id": "a" * 32, "status": "running", "created": 1})
    queue = JobQueue(lambda *args: {})
    assert queue.all()[0]["status"] == "interrupted"
    queue.close()


def test_queue_failure_and_cancel():
    entered, release = threading.Event(), threading.Event()
    def handler(kind, payload, job_id, progress, event):
        entered.set()
        release.wait(3)
        return {"ok": True}
    queue = JobQueue(handler)
    job = queue.submit("tts", {})
    assert entered.wait(2)
    queued = queue.submit("tts", {})
    queue.cancel(queued["id"])
    release.set()
    for _ in range(100):
        if not queue.busy():
            break
        time.sleep(.02)
    assert queue.rows[job["id"]]["status"] == "complete"
    assert queue.rows[queued["id"]]["status"] == "cancelled"
    queue.close()


class FakeEngine:
    precision = "fp32"
    calls = 0
    def start(self, *args):
        pass
    def speak(self, text, voice, path, *args):
        self.calls += 1
        Sine(330).to_audio_segment(duration=500).set_frame_rate(48000).export(path, format="wav")


def ready_project():
    value = storage.new_project("Test")
    value["voice"] = "Mai Anh"
    value["cues"], _ = media.parse_srt("1\n00:00:00,500 --> 00:00:01,500\nXin chào\n\n2\n00:00:02,000 --> 00:00:03,000\nTạm biệt")
    storage.save_project(value)
    return value


def test_real_ffmpeg_timeline_resume_and_per_cue_regenerate():
    media.configure_audio()
    flow = Workflows()
    flow.engine = FakeEngine()
    value = ready_project()
    payload = {"project_id": value["id"]}
    event, callback = threading.Event(), lambda *_: None
    result = flow.job_dub(payload, "a" * 32, callback, event)
    assert (result["generated"], result["failed"]) == (2, 0)
    result = flow.job_dub(payload, "b" * 32, callback, event)
    assert result["skipped"] == 2 and flow.engine.calls == 2
    result = flow.job_dub(payload | {"selected": [1], "force": True}, "c" * 32, callback, event)
    assert result["generated"] == 1 and flow.engine.calls == 3
    exported = flow.job_export(payload | {"mode": "audio", "normalize": False}, "d" * 32, callback, event)
    wav = storage.DATA / exported["files"][0]["url"].removeprefix("/files/")
    assert len(AudioSegment.from_wav(wav)) == 3000
    assert AudioSegment.from_wav(wav)[:450].dBFS == float("-inf")
    assert media.srt(storage.project(value["id"])["cues"]) == media.srt(value["cues"])
    current = storage.project(value["id"])
    current["cues"][0]["text"] = "Đổi câu"
    storage.save_project(current)
    with pytest.raises(ValueError, match="phiên bản"):
        flow.job_export(payload | {"mode": "audio"}, "e" * 32, callback, event)


def test_zero_duration_blocks_synthesis():
    flow = Workflows()
    flow.engine = FakeEngine()
    value = ready_project()
    value["cues"][0]["end_ms"] = value["cues"][0]["start_ms"]
    storage.save_project(value)
    with pytest.raises(ValueError, match="SRT còn lỗi"):
        flow.job_dub({"project_id": value["id"]}, "a" * 32, lambda *_: None, threading.Event())
    assert flow.engine.calls == 0


def test_synthesis_fingerprint_includes_voice_rate_and_precision():
    value = ready_project()
    cue = value["cues"][0]
    key = cue_key(cue, value, "fp32")
    assert key != cue_key(cue | {"voice": "Minh Đức"}, value, "fp32")
    assert key != cue_key(cue | {"rate": 1.5}, value, "fp32")
    assert key != cue_key(cue, value, "int8")


def test_translation_requires_consent():
    with pytest.raises(ValueError, match="cho phép"):
        Workflows().job_translate({}, "a" * 32, lambda *_: None, threading.Event())


def test_tts_pause_actual_duration_and_srt():
    media.configure_audio()
    flow = Workflows()
    flow.engine = FakeEngine()
    result = flow.job_tts({"text": "Xin chào [nghỉ 1s] Tạm biệt", "voice": "Mai Anh"}, "f" * 32, lambda *_: None, threading.Event())
    assert result["duration_ms"] == 2000
    sub = storage.DATA / result["files"][2]["url"].removeprefix("/files/")
    cues, issues = media.parse_srt(sub.read_text(encoding="utf-8-sig"))
    assert not issues
    assert [c["start_ms"] for c in cues] == [0, 1500]


def test_pdf_with_text_extracts(tmp_path):
    from pypdf import PdfWriter
    from pypdf.generic import DecodedStreamObject, DictionaryObject, NameObject
    writer = PdfWriter()
    page = writer.add_blank_page(400, 300)
    font = DictionaryObject({NameObject("/Type"): NameObject("/Font"), NameObject("/Subtype"): NameObject("/Type1"),
                             NameObject("/BaseFont"): NameObject("/Helvetica")})
    page[NameObject("/Resources")] = DictionaryObject({NameObject("/Font"): DictionaryObject({NameObject("/F1"): writer._add_object(font)})})
    content = DecodedStreamObject()
    content.set_data(b"BT /F1 14 Tf 20 200 Td (A readable PDF document.) Tj ET")
    page[NameObject("/Contents")] = writer._add_object(content)
    source = tmp_path / "text.pdf"
    with source.open("wb") as stream:
        writer.write(stream)
    assert "readable PDF" in media.document(source)["text"]


def test_translation_validates_ids_and_keeps_timeline(monkeypatch):
    value = ready_project()
    value.setdefault("edit", {})["translation_provider"] = "api"
    storage.save_project(value)
    storage.save_settings({"translation_url": "https://example.invalid/v1", "translation_model": "test"})
    class Response:
        ok = True
        status_code = 200
        def json(self):
            return {"choices": [{"message": {"content": '[{"id":1,"text":"Câu một"},{"id":2,"text":"Câu hai"}]'}}]}
    monkeypatch.setattr("requests.Session.post", lambda *_args, **_kwargs: Response())
    Workflows().job_translate({"project_id": value["id"], "allow_external": True}, "a" * 32, lambda *_: None, threading.Event())
    after = storage.project(value["id"])
    assert [c["start_ms"] for c in after["cues"]] == [c["start_ms"] for c in value["cues"]]
    assert [c["text"] for c in after["cues"]] == ["Câu một", "Câu hai"]
    monkeypatch.setattr(Response, "json", lambda _: {"choices": [{"message": {"content": '[{"id":999,"text":"Sai"}]'}}]})
    with pytest.raises(ValueError, match="id"):
        Workflows().job_translate({"project_id": value["id"], "allow_external": True,"force":True}, "b" * 32, lambda *_: None, threading.Event())
    assert storage.project(value["id"])["cues"] == after["cues"]


def test_asr_mock_adapter_keeps_real_segment_timestamps(monkeypatch):
    import sys
    from types import SimpleNamespace
    asset_id = "c" * 32
    folder = storage.DATA / "uploads" / asset_id
    folder.mkdir(parents=True)
    (folder / "source.mp4").write_bytes(b"test")
    storage.atomic_json(folder / "asset.json", {"file": "source.mp4"})
    value = storage.new_project("ASR")
    value["video"] = asset_id
    storage.save_project(value)
    observed = {}
    class Whisper:
        def __init__(self, *args, **kwargs):
            observed.update(kwargs)
        def transcribe(self, *args, **kwargs):
            return iter([SimpleNamespace(start=.35, end=1.75, text=" Xin chào ")]), SimpleNamespace(duration=2)
    monkeypatch.setitem(sys.modules, "faster_whisper", SimpleNamespace(WhisperModel=Whisper))
    monkeypatch.setattr(media, "command", lambda *_args, **_kwargs: "")
    Workflows().job_asr({"project_id": value["id"], "allow_download": False}, "d" * 32, lambda *_: None, threading.Event())
    cue = storage.project(value["id"])["cues"][0]
    assert (cue["start_ms"], cue["end_ms"], cue["text"]) == (350, 1750, "Xin chào")
    assert observed["local_files_only"] is True


def test_clone_collision_never_overwrites(monkeypatch, tmp_path):
    from reup.engine import Engine
    engine = Engine()
    engine.voices = [{"id": "Mai Anh"}]
    with pytest.raises(ValueError, match="đã có"):
        engine.clone("Mai Anh", tmp_path / "irrelevant.mp3")
    assert not (storage.DATA / "voices").exists()
