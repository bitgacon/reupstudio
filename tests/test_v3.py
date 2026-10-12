import sys
import threading
from types import SimpleNamespace
from uuid import uuid4

import pytest
import requests

from reup import editor, media, storage
from reup.translation import GoogleWebTranslator, GoogleV1Translator, ResultParser, TranslationError
from reup.workflows import Workflows


@pytest.fixture(autouse=True)
def isolated(tmp_path, monkeypatch):
    monkeypatch.setattr(storage, "DATA", tmp_path / "data")
    storage.DATA.mkdir()
    media.configure_audio()
    monkeypatch.setattr(GoogleWebTranslator,'retries',0)
    monkeypatch.setattr(GoogleWebTranslator,'interval',0)
    monkeypatch.setattr(GoogleWebTranslator,'backoff',0)


@pytest.mark.parametrize("ratio,expected", [("source", (1280,720)), ("9:16",(720,1280)),
    ("16:9",(1280,720)),("1:1",(720,720)),("4:5",(720,900)),("4:3",(960,720)),("custom",(1080,1920))])
def test_output_geometry(ratio, expected):
    assert editor.geometry(1280,720,editor.config({"output_ratio":ratio}))[:2] == expected


def test_fit_and_metadata():
    assert editor.geometry(1280,720,editor.config({"output_ratio":"9:16"})) == (720,1280,720,406)
    assert editor.geometry(1280,720,editor.config({"output_ratio":"9:16","video_fit":"cover"})) == (720,1280,2276,1280)
    assert editor.geometry(720,1280,editor.config({"output_ratio":"16:9","video_fit":"cover"})) == (1280,720,1280,2276)
    assert editor.display_size({"width":720,"height":576,"sample_aspect_ratio":"16:15"}) == (768,576)
    assert editor.display_size({"width":1280,"height":720,"side_data_list":[{"rotation":-90}]}) == (720,1280)
    for c in [{"output_width":127}, {"output_ratio":"2;evil"}, {"video_fit":"stretch"}, {"canvas_color":"red;evil"}]:
        with pytest.raises(ValueError):
            editor.config(c)


@pytest.mark.parametrize("mask", [{"mask_x":99,"mask_y":99,"mask_w":100,"mask_h":100},
    {"mask_x":10.25,"mask_y":20.75,"mask_w":30.5,"mask_h":18.25}])
def test_export_real_blur_handles_edges_and_fractional_direct_selection(tmp_path, mask):
    video,audio,out=[tmp_path/name for name in ("source.mp4","audio.wav","blur.mp4")]
    media.command([media.binary(),"-y","-v","error","-f","lavfi","-i","testsrc2=s=320x180:r=15:d=1","-c:v","libx264",str(video)])
    media.command([media.binary(),"-y","-v","error","-f","lavfi","-i","sine=d=1",str(audio)])
    p=storage.new_project("blur",edit={"original_subtitles":"blur","mask_blur":40,"rotation":30,"zoom":1.25,**mask})
    editor.render_video(p,video,audio,out,1000)
    info=media.probe(out)
    assert (info["streams"][0]["width"],info["streams"][0]["height"]) == (320,180)


@pytest.mark.parametrize("fit", ["contain", "cover"])
def test_actual_landscape_to_portrait(tmp_path, fit):
    video, audio, out = [tmp_path/name for name in ("source.mp4","audio.wav","portrait.mp4")]
    media.command([media.binary(),"-y","-v","error","-f","lavfi","-i","testsrc2=s=320x180:r=15:d=1","-c:v","libx264",str(video)])
    media.command([media.binary(),"-y","-v","error","-f","lavfi","-i","sine=d=1",str(audio)])
    p=storage.new_project("portrait",edit={"output_ratio":"9:16","video_fit":fit,"title":"Test","canvas_color":"#223344"})
    p["cues"]=[{"start_ms":120,"end_ms":880,"text":"Xin chào"}]
    original=video.read_bytes()
    editor.render_video(p,video,audio,out,1000)
    info=media.probe(out)
    assert (info["streams"][0]["width"], info["streams"][0]["height"]) == (720,1280)
    assert abs(float(info["format"]["duration"])-1) < .1
    assert video.read_bytes()==original
    ass=(tmp_path/"styled.ass").read_text(encoding="utf-8-sig")
    assert "PlayResX: 720" in ass and "PlayResY: 1280" in ass and "0:00:00.12,0:00:00.88" in ass


def project(edit=None):
    p=storage.new_project("translate test",edit={"translation_provider":"google",**(edit or {})})
    p["cues"]=[{"id":i,"start_ms":i*1000+127,"end_ms":i*1000+880,"source_text":f"Hello {i}","text":f"Hello {i}","status":"complete"} for i in (1,2)]
    storage.save_project(p)
    return p


def run(p, **kwargs):
    return Workflows().job_translate({"project_id":p["id"],"allow_external":True,**kwargs},uuid4().hex,lambda *a:None,threading.Event())


def response(text="Xin chào", status=200):
    return SimpleNamespace(ok=status==200,status_code=status,text=f'<div class="result-container">{text}</div>')


def test_parser_nested_unicode_and_entities():
    parser=ResultParser()
    parser.feed('<div>ignored</div><div class="result-container">Chào &amp; <b>bạn</b><br/>Tốt</div><div>ignored</div>')
    assert parser.finished and "".join(parser.parts)=="Chào & bạn\nTốt"


def test_google_resume_preserves_ids_timings_manual_edits_and_retries_only_failed(monkeypatch):
    p=project()
    calls=[]
    def get(*a,**kw):
        calls.append(kw)
        return response(status=429) if len(calls)==2 else response("Xin chào")
    monkeypatch.setattr(requests.Session,"get",get)
    with pytest.raises(RuntimeError,match="câu 2"):
        run(p)
    saved=storage.project(p["id"])
    assert saved["cues"][0]["text"]=="Xin chào" and saved["cues"][1]["text"]=="Hello 2"
    assert saved["cues"][1]["translation_state"]["text"]["status"]=="error"
    saved["cues"][0]["text"]="Sửa thủ công"
    storage.save_project(saved)
    result=run(p)
    saved=storage.project(p["id"])
    assert result["skipped"]==1 and result["translated"]==1 and len(calls)==3
    assert saved["cues"][0]["text"]=="Sửa thủ công"
    assert [(c["id"],c["start_ms"],c["end_ms"],c["source_text"]) for c in saved["cues"]] == [(c["id"],c["start_ms"],c["end_ms"],c["source_text"]) for c in p["cues"]]
    assert calls[0]["timeout"]==(10,35) and calls[0]["params"]["tl"]=="vi"
    assert run(p)["skipped"]==2
    assert run(p,selected=[1],force=True)["translated"]==1
    saved=storage.project(p["id"])
    saved["cues"][0]["source_text"]="New source"
    storage.save_project(saved)
    assert run(p)["translated"]==1


def test_google_foreign_caption_separate_and_same_language_local(monkeypatch):
    p=project({"target_language":"en","source_language":"en"})
    monkeypatch.setattr(requests.Session,"get",lambda *a,**kw:pytest.fail("same language must not call network"))
    run(p)
    cue=storage.project(p["id"])["cues"][0]
    assert cue["text"]=="Hello 1" and cue["translation"]=="Hello 1" and cue["status"]=="complete"
    assert cue["translation_language"]=="en"
    monkeypatch.setattr(requests.Session,"get",lambda *a,**kw:response("Lời Việt"))
    run(p,for_speech=True)
    cue=storage.project(p["id"])["cues"][0]
    assert cue["text"]=="Lời Việt" and cue["translation"]=="Hello 1"


@pytest.mark.parametrize("mode", ["blocked", "html", "timeout"])
def test_google_clear_errors_and_no_silent_fallback(monkeypatch, mode):
    def get(*a,**kw):
        if mode=="timeout":
            raise requests.Timeout()
        return response(status=403) if mode=="blocked" else SimpleNamespace(ok=True,status_code=200,text="<html>Verification</html>")
    monkeypatch.setattr(requests.Session,"get",get)
    translator=GoogleWebTranslator("auto","vi",threading.Event())
    try:
        with pytest.raises(TranslationError):
            translator.translate("Hello")
    finally:
        translator.close()


def test_google_consent_cancel_and_shorten(monkeypatch):
    monkeypatch.setattr(requests.Session,"get",lambda *a,**kw:pytest.fail("must not send"))
    p=project()
    with pytest.raises(ValueError,match="cho phép"):
        run(p,allow_external=False)
    with pytest.raises(ValueError,match="không rút gọn"):
        run(p,shorten=True)
    event=threading.Event();event.set()
    with pytest.raises(InterruptedError):
        Workflows().job_translate({"project_id":p["id"],"allow_external":True},uuid4().hex,lambda *a:None,event)


def test_google_v1_default_and_response(monkeypatch):
    assert editor.config()["translation_provider"]=="google_v1"
    calls=[]
    def get(session,url,**kw):
        calls.append((url,kw))
        return SimpleNamespace(ok=True,status_code=200,json=lambda:[[['Xin chào. ', 'Hello.'],['Hôm nay.','Today.']]])
    monkeypatch.setattr(requests.Session,"get",get)
    p=project({"translation_provider":"google_v1"})
    run(p)
    assert storage.project(p["id"])["cues"][0]["text"]=="Xin chào. Hôm nay."
    assert calls[0][0]=="https://translate.googleapis.com/translate_a/single"
    assert calls[0][1]["params"]["client"]=="gtx"


def test_stale_foreign_caption_is_not_exported():
    p=project({"target_language":"de"})
    p["cues"][0].update(translation="Hello",translation_language="en")
    storage.save_project(p)
    with pytest.raises(ValueError,match="Ngôn ngữ đích đã đổi"):
        Workflows().job_export({"project_id":p["id"],"mode":"srt"},uuid4().hex,lambda *a:None,threading.Event())


@pytest.mark.parametrize("data", [None, {}, [], [None], [[None]], [[[None]]]])
def test_google_v1_rejects_malformed_response(data):
    translator=GoogleV1Translator("auto","vi",threading.Event())
    try:
        with pytest.raises(TranslationError):
            translator.parse(SimpleNamespace(json=lambda:data))
    finally:
        translator.close()


@pytest.mark.parametrize("failed", [True,False])
def test_asr_then_translate_checkpoints_recognition_before_network(monkeypatch, failed):
    p=project()
    class Whisper:
        def __init__(self,*a,**kw):pass
        def transcribe(self,*a,**kw):
            return iter([SimpleNamespace(start=.127,end=1.333,text=" Hello ")]),SimpleNamespace(duration=2)
    monkeypatch.setitem(sys.modules,"faster_whisper",SimpleNamespace(WhisperModel=Whisper))
    monkeypatch.setattr(media,"command",lambda *a,**kw:None)
    monkeypatch.setattr(storage,"project_asset",lambda *a:(storage.DATA/"fake.mp4",{}))
    p["video"]="a"*32;storage.save_project(p)
    def get(*a,**kw):
        assert storage.project(p["id"])["cues"][0]["source_text"]=="Hello"
        return response(status=429) if failed else response("Xin chào")
    monkeypatch.setattr(requests.Session,"get",get)
    args={"project_id":p["id"],"translate_after":True,"allow_external":True}
    progress=[]
    if failed:
        with pytest.raises(RuntimeError,match="câu 1"):
            Workflows().job_asr(args,uuid4().hex,lambda n,m:progress.append(n),threading.Event())
    else:
        Workflows().job_asr(args,uuid4().hex,lambda n,m:progress.append(n),threading.Event())
    cue=storage.project(p["id"])["cues"][0]
    assert (cue["start_ms"],cue["end_ms"])==(127,1333)
    assert cue["text"]==("Hello" if failed else "Xin chào")
    assert progress==sorted(progress)
